#!/usr/bin/env python3

import sys
import re
import xml.dom.minidom
from xml.etree.ElementTree import Element, SubElement, tostring

def show_help():
    """
    Vypíše nápovedu k skriptu a ukončí program.
    """
    print("Skript parse.py parsuje zdrojový kód jazyka SOL25 zo štandardného vstupu")
    print("a generuje XML reprezentáciu programu na štandardný výstup.")
    print("Použitie: python3 parse.py < input_file > output_file")
    print("Parametre:")
    print("  --help        Vypíše túto nápovedu a skončí.")
    sys.exit(0)


# Spracovanie parametrov
if len(sys.argv) > 1:
    if sys.argv[1] == "--help":
        show_help()
    else:
        # Ďalšie parametre môžete spracovať podľa potreby
        print("Neznámy parameter alebo zakázaná kombinácia parametrov.", file=sys.stderr)
        sys.exit(10)

# Nacitanie vsetkych riadkov zo stdin
lines = sys.stdin.read().splitlines()

# Odstranenie pripadnych prazdnych riadkov na zaciatku
while lines and not lines[0].strip():
    lines.pop(0)

# Kontrola, ci amem aspon jeden riadok
if not lines:
    sys.exit(21)  # prazdny vstup => chybajuca hlavicka

# Pravidla pre identifikaciu definicie triedy:
# class MenoTriedy [: Nadtrieda] {
class_header_re = re.compile(r"^class\s+([A-Z][A-Za-z0-9]*)\s*(?::\s*([A-Z][A-Za-z0-9]*))?\s*\{$")

# Pravidla pre nazov metody (napr. run, compute:and:, plusOne:, atď.)
# Jednoduche zodpoveda: [a-z][A-Za-z0-9_]* s moznymi dvojbodkami
method_header_re = re.compile(r"^([a-z_][A-Za-z0-9_:]*)\s*$")

classes = []             # zoznam definícií tried
current_class = None     # práve spracovávaná trieda
current_method = None    # práve spracovávaná metóda
in_block = False         # či práve čítame telo bloku (metódy)
block_lines = []         # akumulácia riadkov pre blok

for line in lines:
    stripped = line.strip()

    # Preskočíme prázdne riadky
    if not stripped:
        continue

    # (Jednoriadkový) blokový komentár v dvojitých úvodzovkách?
    # Ak to potrebujete, môžete implementovať odstraňovanie takýchto komentárov.
    # if stripped.startswith('"') and stripped.endswith('"'):
    #     continue

    # Ak nie je otvorená žiadna trieda, očakávame definíciu triedy
    if current_class is None:
        match_class = class_header_re.match(stripped)
        if match_class:
            cls_name = match_class.group(1)
            super_cls = match_class.group(2) if match_class.group(2) else ""
            current_class = {
                "name": cls_name,
                "superclass": super_cls,
                "methods": []
            }
        else:
            sys.exit(23)  # syntaktická chyba mimo definície triedy
    else:
        # Sme vo vnútri definície triedy
        if stripped == "}":
            # Koniec triedy
            classes.append(current_class)
            current_class = None
            continue

        # Ak nečítame telo metódy, očakávame názov metódy
        if current_method is None and not in_block:
            m = method_header_re.match(stripped)
            if m:
                current_method = {"name": m.group(1), "body": ""}
                block_lines = []
            else:
                sys.exit(23)
        else:
            # Už sme načítali názov metódy, teraz očakávame blok [ ... ]
            if not in_block:
                # Začiatok blokového literálu
                if stripped == "[":
                    in_block = True
                    block_lines = []
                else:
                    sys.exit(23)
            else:
                # Sme vo vnútri bloku
                if stripped == "]":
                    # Koniec bloku
                    current_method["body"] = "\n".join(block_lines)
                    current_class["methods"].append(current_method)
                    current_method = None
                    in_block = False
                    block_lines = []
                else:
                    # Ukladáme riadky bloku metódy
                    block_lines.append(line)

# Ak ostali neuzavreté triedy alebo metódy
if current_class is not None or in_block or current_method is not None:
    sys.exit(23)

# Vytvorenie XML výstupu
root = Element('program')
root.attrib['language'] = "SOL25"

for cls in classes:
    class_elem = SubElement(root, 'class')
    class_elem.attrib['name'] = cls["name"]
    if cls["superclass"]:
        class_elem.attrib['superclass'] = cls["superclass"]
    for meth in cls["methods"]:
        method_elem = SubElement(class_elem, 'method')
        method_elem.attrib['name'] = meth["name"]
        body_elem = SubElement(method_elem, 'body')
        # Telo metódy vkladáme ako text do elementu <body>
        body_elem.text = meth["body"]

# Naformátovanie XML pomocou minidom
dom = xml.dom.minidom.parseString(tostring(root, encoding="utf-8"))
pretty_xml = dom.toprettyxml(indent="  ", encoding="utf-8")

# Výstup na stdout
sys.stdout.buffer.write(pretty_xml)
