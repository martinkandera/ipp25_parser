#!/usr/bin/env python3

import sys
import re
import xml.dom.minidom
from xml.etree.ElementTree import Element, SubElement, tostring

def show_help():
    """
    Vypise napovedu a ukonci program.
    """
    print("Skript parse25.py parsuje zdrojovy kod jazyka SOL25 zo standartneho vstupu")
    print("a generuje XML reprezentaciu programu na standartny vystup.")
    print("Pouzitie: python3 parse25.py < input_file > output_file")
    print("Parametre:")
    print("  --help        Vypise tuto napovedu a skonci.")
    sys.exit(0)

if len(sys.argv) != 1:
    if len(sys.argv) == 2 and sys.argv[1] == "--help":
        show_help()
    else:
        print("Neznamy parameter alebo zakazana kombinacia parametrov.", file=sys.stderr)
        sys.exit(10)

# Nacitanie vsetkych riadkov zo stdin
lines = sys.stdin.read().splitlines()

# Odstranenie prazdnych riadkov na zaciatku
while lines and not lines[0].strip():
    lines.pop(0)

if not lines:
    sys.exit(21)  # prazdny vstup

# Regex pre definiciu triedy:
#   class MenoTriedy [: Nadtrieda] {
class_header_re = re.compile(r"^class\s+([A-Z][A-Za-z0-9]*)\s*(?::\s*([A-Z][A-Za-z0-9]*))?\s*\{$")

# Regex pre definiciu metody. Teraz ocakavame moznost volitelneho popisu v uvozovkach.
# Format: selector [medzera] "popis"
method_header_re = re.compile(r"^([a-z_][A-Za-z0-9_:]*)(?:\s+\"([^\"]+)\")?\s*$")

classes = []             # zoznam definicii tried
current_class = None     # prave spracovavana trieda
current_method = None    # prave spracovavana metoda
in_block = False         # ci citame telo bloku
block_params_parsed = False  # ci sme uz spracovali parametre bloku
block_params = []        # zoznam parametrov (bez dvojtych bodiek)
block_body_lines = []    # riadky tela bloku

# Ak je prvy metod s popisom, ten sa ulozi do atributu description korenovho elementu
program_description = None

line_iter = iter(lines)
for line in line_iter:
    stripped = line.strip()
    if not stripped:
        continue

    # Ak neni otvorena ziadna trieda, ocakavame definiciu triedy
    if current_class is None:
        m = class_header_re.match(stripped)
        if m:
            cls_name = m.group(1)
            parent = m.group(2) if m.group(2) else ""
            current_class = {
                "name": cls_name,
                "parent": parent,
                "methods": []
            }
        else:
            sys.exit(23)  # syntakticka chyba mimo definicie triedy
    else:
        # Ak narazime riadok obsahujuci "}", znamena koniec triedy
        if stripped == "}":
            classes.append(current_class)
            current_class = None
            continue

        # Ak nie sme v metode, ocakavame definiciu metody
        if current_method is None and not in_block:
            m = method_header_re.match(stripped)
            if m:
                # m.group(1) je selector, m.group(2) je mozny popis
                current_method = {
                    "selector": m.group(1),
                    "description": m.group(2) if m.group(2) else ""
                }
                # Ak este program description nie je nastaveny a popis existuje, ulozime ho
                if program_description is None and current_method["description"]:
                    program_description = current_method["description"]
                # Ocakavame nasledujuci riadok, ktory musi obsahovat zaciatok bloku
                continue
            else:
                sys.exit(23)
        else:
            # Sme v metode – ocakavame blokovy literal
            if not in_block:
                if stripped.startswith("["):
                    in_block = True
                    block_params_parsed = False
                    block_params = []
                    block_body_lines = []
                    # Odstranime otvaraci zatvorku a mozno parametre
                    # Ocakavame format: [ <params> | (mozno text) ]
                    # Najdeme ciarku "|" v riadku
                    if "|" in stripped:
                        # Obsah medzi [ a | je zoznam parametrov
                        left = stripped[1:stripped.index("|")].strip()
                        if left:
                            # Parametre su oddelene medzerou, ocakavame format :x :y ...
                            tokens = left.split()
                            for token in tokens:
                                token = token.strip()
                                if token.startswith(":"):
                                    # Odstranime dvojtycky
                                    block_params.append(token[1:])
                        block_params_parsed = True
                        # Zvyšok riadku za "|" moze obsahovat cast tela, ak nie je len "]"
                        right = stripped[stripped.index("|")+1:].strip()
                        if right and right != "]":
                            block_body_lines.append(right)
                    else:
                        # Ak nie je "|" v riadku, ocakavame dalsie riadky s parametrami
                        block_params_parsed = False
                    continue
                else:
                    sys.exit(23)
            else:
                # Sme vo vnutri bloku
                if stripped == "]":
                    # Koniec bloku; ulozime data do metody
                    # Vytvorime strukturu bloku: arity, parametre, telo (spojeny text)
                    current_method["block"] = {
                        "arity": len(block_params),
                        "parameters": block_params,
                        "body": "\n".join(block_body_lines).strip()
                    }
                    # Pridame metodu do triedy
                    current_class["methods"].append(current_method)
                    # Resetujeme pre dalsiu metodu
                    current_method = None
                    in_block = False
                    block_params_parsed = False
                    block_params = []
                    block_body_lines = []
                else:
                    # Ak este neboli precitane parametre, pokusime sa ich precitat z prveho riadku bloku
                    if not block_params_parsed:
                        # Ocakavame riadok obsahujuci parametre oddelene medzerou, ukoncene znakom "|"
                        if "|" in stripped:
                            left = stripped[:stripped.index("|")].strip()
                            if left:
                                tokens = left.split()
                                for token in tokens:
                                    token = token.strip()
                                    if token.startswith(":"):
                                        block_params.append(token[1:])
                            block_params_parsed = True
                            right = stripped[stripped.index("|")+1:].strip()
                            if right:
                                block_body_lines.append(right)
                        else:
                            # Ak znak "|" nie je prítomny, predpokladame, ze sa parametricke riadky este citaju
                            tokens = stripped.split()
                            for token in tokens:
                                token = token.strip()
                                if token.startswith(":"):
                                    block_params.append(token[1:])
                    else:
                        # Uz mame precitane parametre, riadky patria telu bloku
                        block_body_lines.append(line)

# Ak ostali neuzavrete definicie
if current_class is not None or in_block or current_method is not None:
    sys.exit(23)

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
        # Vytvorime element block s atributom arity
        block_elem = SubElement(method_elem, 'block')
        block_elem.attrib['arity'] = str(meth["block"]["arity"])
        # Pre kazdy parameter vytvorime element parameter
        for idx, par in enumerate(meth["block"]["parameters"], start=1):
            param_elem = SubElement(block_elem, 'parameter')
            param_elem.attrib['order'] = str(idx)
            param_elem.attrib['name'] = par
        # Pridame telo bloku ako element body
        body_elem = SubElement(block_elem, 'body')
        body_elem.text = meth["block"]["body"]

# Formatovanie XML pomocou minidom
dom = xml.dom.minidom.parseString(tostring(root, encoding="utf-8"))
pretty_xml = dom.toprettyxml(indent="  ", encoding="utf-8")

# Vystup na stdout
sys.stdout.buffer.write(pretty_xml)
