#!/usr/bin/env python3

import sys
import re
from enum import Enum
import xml.dom.minidom
from xml.etree.ElementTree import Element, SubElement, tostring

# Error types
class ErrorType(Enum):
    NO_ERROR = 0
    MISSING_PARAM = 10
    LEX_ERR_INPUT = 21  # lexikalna chyba vo zdrojovom kode v SOL25
    SYN_ERR_INPUT = 22  # syntakticka chyba vo zdrojovom kode v SOL25
    SEM_IN_MAIN   = 31  # semanticka chyba - chybejuca trieda Main alebo metoda run v Main
    SEM_UNDEFINED = 32
    SEM_MISSMATCH = 33
    SEM_COLLISION = 34
    SEM_OTHER     = 35

def show_help():
    """
    Vypise napovedu a ukonci program.
    """
    print("Skript parse25.py parsuje zdrojovy kod jazyka SOL25 zo standartneho vstupu")
    print("a generuje XML reprezentaciu programu na standartny vystup.")
    print("Pouzitie: python3 parse25.py < input_file > output_file")
    print("Parametre:")
    print("  --help        Vypise tuto napovedu a skonci.")
    sys.exit(ErrorType.NO_ERROR.value)

# Spracovanie argumentov
if len(sys.argv) != 1:
    if len(sys.argv) == 2 and sys.argv[1] == "--help":
        show_help()
    else:
        print("Neznamy parameter alebo zakazana kombinacia parametrov.", file=sys.stderr)
        sys.exit(ErrorType.MISSING_PARAM.value)

# Nacitanie vsetkych riadkov zo stdin
lines = sys.stdin.read().splitlines()
while lines and not lines[0].strip():
    lines.pop(0)
if not lines:
    sys.exit(ErrorType.LEX_ERR_INPUT.value)  # prazdny vstup

def remove_comments_from_line(line):
    """
    Odstrani vsetky komentare zo vstupneho retazca.
    Komentare su texty medzi dvojitymi uvodzovkami.
    Ak sa najde otvorena uvodzovka, ktora nie je uzavreta,
    program ukonci s chybovym kodom LEX_ERR_INPUT (21).
    """
    result = ""
    i = 0
    while i < len(line):
        if line[i] == '"':
            j = i + 1
            while j < len(line) and line[j] != '"':
                j += 1
            if j >= len(line):
                sys.exit(ErrorType.LEX_ERR_INPUT.value)
            # Preskocime komentarovy blok vrátane ukoncujucej uvodzovky.
            i = j + 1
        else:
            result += line[i]
            i += 1
    return result

# Regex pre definiciu triedy:
# Format: class MenoTriedy [: Nadtrieda] { <zvisok>
class_header_re = re.compile(r"^class\s+([A-Z][A-Za-z0-9]*)\s*(?::\s*([A-Z][A-Za-z0-9]*))?\s*\{(.*)$")
# Regex pre definiciu metody s volitelnym popisom:
# Format: selector [medzera] "popis"
method_header_re = re.compile(r"^([a-z_][A-Za-z0-9_:]*)(?:\s+\"([^\"]+)\")?\s*$")

classes = []             # zoznam definicii tried
current_class = None     # prave spracovavana trieda
current_method = None    # prave spracovavana metoda

# Premenne pre spracovanie bloku metody
in_block = False         # ci citame telo bloku
block_params = []        # zoznam parametrov (bez dvojtych bodiek)
block_body_lines = []    # riadky tela bloku

# Programovy popis (popis metody run v triede Main)
program_description = None

# Hlavna slucka spracovania vstupu
while lines:
    line = lines.pop(0)
    stripped = line.strip()
    if not stripped:
        continue

    if current_class is None:
        # Ocakavame definiciu triedy
        m = class_header_re.match(stripped)
        if m:
            cls_name = m.group(1)
            parent = m.group(2) if m.group(2) else ""
            current_class = {
                "name": cls_name,
                "parent": parent,
                "methods": []
            }
            # Ak po "{" je zvisok riadku, vlozime ho naspat na zaciatok zoznamu riadkov.
            remainder = m.group(3).strip()
            if remainder:
                lines.insert(0, remainder)
            continue
        else:
            sys.exit(ErrorType.SYN_ERR_INPUT.value)
    else:
        # Sme vo vnutri triedy.
        if stripped.startswith("}"):
            # Koniec triedy.
            classes.append(current_class)
            current_class = None
            continue

        # Spracovanie definicie metody.
        if current_method is None and not in_block:
            # Ak v riadku je blokovy literal, oddelime cast s metodou a blokom.
            if "[" in stripped:
                idx = stripped.find("[")
                header_part = stripped[:idx].strip()
                block_part = stripped[idx:].strip()
                m = method_header_re.match(header_part)
                if m:
                    current_method = {
                        "selector": m.group(1),
                        "description": m.group(2) if m.group(2) else ""
                    }
                    if current_class["name"] == "Main" and current_method["selector"] == "run" and m.group(2):
                        program_description = m.group(2)
                else:
                    sys.exit(ErrorType.SYN_ERR_INPUT.value)
                stripped = block_part
            else:
                # Ak metoda je zadana samostatne, ocakavame blok v dalsom riadku.
                m = method_header_re.match(stripped)
                if m:
                    current_method = {
                        "selector": m.group(1),
                        "description": m.group(2) if m.group(2) else ""
                    }
                    if current_class["name"] == "Main" and current_method["selector"] == "run" and m.group(2):
                        program_description = m.group(2)
                    continue
                else:
                    sys.exit(ErrorType.SYN_ERR_INPUT.value)
        # Spracovanie bloku metody.
        if not in_block:
            # Ak riadok obsahuje kompletny blokovy literal (tj. obsahuje aj "]")
            if stripped.startswith("[") and "]" in stripped:
                idx_open = stripped.find("[")
                idx_close = stripped.find("]")
                block_literal = stripped[idx_open:idx_close+1]
                trailing = stripped[idx_close+1:].strip()
                in_block = True
                block_params = []
                block_body_lines = []
                if "|" in block_literal:
                    left = block_literal[1:block_literal.index("|")].strip()
                    if left:
                        tokens = left.split()
                        for token in tokens:
                            if token.startswith(":"):
                                block_params.append(token[1:])
                    right = block_literal[block_literal.index("|")+1:-1].strip()
                    # Odstranime komentare z casti tela.
                    right = remove_comments_from_line(right)
                    if right:
                        block_body_lines.append(right)
                current_method["block"] = {
                    "arity": len(block_params),
                    "parameters": block_params,
                    "body": "\n".join(block_body_lines).strip()
                }
                current_class["methods"].append(current_method)
                current_method = None
                in_block = False
                if trailing.startswith("}"):
                    trailing = trailing[1:].strip()
                    classes.append(current_class)
                    current_class = None
                if trailing:
                    lines.insert(0, trailing)
                continue
            else:
                # Zaciatok multiline bloku.
                if stripped.startswith("["):
                    in_block = True
                    block_params = []
                    block_body_lines = []
                    if "|" in stripped:
                        left = stripped[1:stripped.index("|")].strip()
                        if left:
                            tokens = left.split()
                            for token in tokens:
                                if token.startswith(":"):
                                    block_params.append(token[1:])
                        right = stripped[stripped.index("|")+1:].strip()
                        # Odstranime komentare z riadku.
                        right = remove_comments_from_line(right)
                        if right and right != "]":
                            block_body_lines.append(right)
                    continue
                else:
                    sys.exit(ErrorType.SYN_ERR_INPUT.value)
        else:
            # Sme vo vnutri multiline bloku.
            if stripped == "]":
                current_method["block"] = {
                    "arity": len(block_params),
                    "parameters": block_params,
                    "body": "\n".join(block_body_lines).strip()
                }
                current_class["methods"].append(current_method)
                current_method = None
                in_block = False
                block_params = []
                block_body_lines = []
            else:
                # Odstranime komentare z riadku a pridame vysledok.
                clean_line = remove_comments_from_line(stripped)
                if "|" in clean_line and not block_params:
                    left = clean_line[:clean_line.index("|")].strip()
                    if left:
                        tokens = left.split()
                        for token in tokens:
                            if token.startswith(":"):
                                block_params.append(token[1:])
                    right = clean_line[clean_line.index("|")+1:].strip()
                    if right:
                        block_body_lines.append(right)
                else:
                    block_body_lines.append(clean_line)

# Kontrola, ci ostali neuzavrete definicie
if current_class is not None or in_block or current_method is not None:
    sys.exit(ErrorType.SYN_ERR_INPUT.value)

def check_main(classes):
    """Skontroluje, ci je deklarovana trieda Main s metodou run.
       Ak nie, ukonci program s chybovym kodom SEM_IN_MAIN (31).
       Vrati popis metody run, ak existuje.
    """
    main_found = False
    run_found = False
    run_description = ""
    for cls in classes:
        if cls["name"] == "Main":
            main_found = True
            for meth in cls["methods"]:
                if meth["selector"] == "run":
                    run_found = True
                    run_description = meth.get("description", "")
                    break
            break
    if not main_found or not run_found:
        sys.exit(ErrorType.SEM_IN_MAIN.value)
    return run_description

run_desc = check_main(classes)
if run_desc:
    program_description = run_desc

# Vytvorenie XML vystupu
root = Element('program')
root.attrib['language'] = "SOL25"
if program_description:
    root.attrib['description'] = program_description

for cls in classes:
    class_elem = SubElement(root, 'class')
    class_elem.attrib['name'] = cls["name"]
    if cls["parent"]:
        class_elem.attrib['parent'] = cls["parent"]
    for meth in cls["methods"]:
        method_elem = SubElement(class_elem, 'method')
        method_elem.attrib['selector'] = meth["selector"]
        block = meth.get("block", {"arity":0, "parameters":[], "body":""})
        block_elem = SubElement(method_elem, 'block')
        block_elem.attrib['arity'] = str(block["arity"])
        for idx, par in enumerate(block["parameters"], start=1):
            param_elem = SubElement(block_elem, 'parameter')
            param_elem.attrib['order'] = str(idx)
            param_elem.attrib['name'] = par
        if block["body"]:
            body_elem = SubElement(block_elem, 'body')
            body_elem.text = block["body"]

dom = xml.dom.minidom.parseString(tostring(root, encoding="utf-8"))
pretty_xml = dom.toprettyxml(indent="    ", encoding="UTF-8")
sys.stdout.buffer.write(pretty_xml)
