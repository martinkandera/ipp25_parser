#!/usr/bin/env python3

import sys
import re
from enum import Enum
import xml.dom.minidom
from xml.etree.ElementTree import Element, SubElement, tostring

class ErrorType(Enum):
    NO_ERROR = 0
    MISSING_PARAM = 10
    LEX_ERR_INPUT = 21
    SYN_ERR_INPUT = 22
    SEM_IN_MAIN = 31
    SEM_UNDEFINED = 32
    SEM_MISSMATCH = 33
    SEM_COLLISION = 34
    SEM_OTHER = 35

def show_help():
    print("Skript parse25.py parsuje zdrojovy kod jazyka SOL25 zo vstupu")
    print("a generuje XML reprezentaciu programu na vystup.")
    print("Pouzitie: python3 parse25.py < input_file > output_file")
    print("Parametre:")
    print("  --help        Vypise tuto napovedu a skonci.")
    sys.exit(ErrorType.NO_ERROR.value)

# Trieda Parser z predchadzajuceho kodu; nezmenena alebo len minimalne zmeny
class Parser:
    class_header_re = re.compile(r"^class\s+([A-Z][A-Za-z0-9]*)\s*(?::\s*([A-Z][A-Za-z0-9]*))?\s*\{(.*)$")
    method_header_re = re.compile(r"^([a-z_][A-Za-z0-9_:]*)(?:\s+\"([^\"]+)\")?\s*$")

    def __init__(self, lines):
        self.lines = lines
        self.index = 0
        self.classes = []
        self.current_class = None
        self.current_method = None
        self.in_block = False
        self.block_params = []
        self.block_body_lines = []
        self.program_description = None

    def eof(self):
        return self.index >= len(self.lines)

    def get_line(self):
        if self.eof():
            return None
        return self.lines[self.index]

    def advance(self):
        self.index += 1

    def remove_comments(self, line):
        result = ""
        i = 0
        while i < len(line):
            if line[i] == '"':
                j = i + 1
                while j < len(line) and line[j] != '"':
                    j += 1
                if j >= len(line):
                    sys.exit(ErrorType.LEX_ERR_INPUT.value)
                i = j + 1
            else:
                result += line[i]
                i += 1
        return result

    def extract_first_trailing_comment(self, text):
        m = re.search(r'"([^"]*)"', text)
        if not m:
            return None
        raw_comment = m.group(1)
        return self.transform_description(raw_comment)

    def transform_description(self, desc):
        # 1. Zjednotenie reálnych newline a literalnych \n do jedneho symbolu
        desc = desc.replace('\n', '\u0001')
        desc = desc.replace(r'\n', '\u0001')
        # 2. Transformacia skupin
        out = []
        i = 0
        while i < len(desc):
            if desc[i] == '\u0001':
                # zistime dlzku skupiny
                start = i
                while i < len(desc) and desc[i] == '\u0001':
                    i += 1
                count = i - start
                if count == 1:
                    out.append("&nbsp;")
                else:
                    out.append("&#10;" * count)
            else:
                out.append(desc[i])
                i += 1
        return "".join(out)

    def parse_class_header(self, stripped):
        m = self.class_header_re.match(stripped)
        if not m:
            sys.exit(ErrorType.SYN_ERR_INPUT.value)
        cls_name = m.group(1)
        parent = m.group(2) if m.group(2) else ""
        remainder = m.group(3).strip()
        self.current_class = {
            "name": cls_name,
            "parent": parent,
            "methods": []
        }
        if remainder:
            self.lines.insert(self.index, remainder)

    def parse_method_header(self, stripped):
        mm = self.method_header_re.match(stripped)
        if not mm:
            return None
        selector = mm.group(1)
        desc = mm.group(2) if mm.group(2) else ""
        return (selector, desc)

    def store_method(self):
        if not self.current_method:
            return
        block = {
            "arity": len(self.block_params),
            "parameters": self.block_params,
            "body": "\n".join(self.block_body_lines).strip()
        }
        self.current_method["block"] = block
        self.current_class["methods"].append(self.current_method)
        self.current_method = None
        self.in_block = False
        self.block_params = []
        self.block_body_lines = []

    def parse_main(self):
        while not self.eof():
            line = self.get_line()
            self.advance()
            if not line.strip():
                continue

            if self.current_class is None:
                self.parse_class_header(line.strip())
            else:
                stripped = line.strip()
                if stripped.startswith("}"):
                    self.classes.append(self.current_class)
                    self.current_class = None
                    continue

                if self.current_method is None and not self.in_block:
                    m_head = self.parse_method_header(stripped)
                    if m_head:
                        selector, desc = m_head
                        self.current_method = {
                            "selector": selector,
                            "description": desc
                        }
                        if self.current_class["name"] == "Main" and selector == "run" and desc:
                            self.program_description = desc
                        continue
                    else:
                        if "[" in stripped:
                            idx = stripped.find("[")
                            header_part = stripped[:idx].strip()
                            header_match = self.parse_method_header(header_part)
                            if header_match:
                                selector, desc = header_match
                                self.current_method = {
                                    "selector": selector,
                                    "description": desc
                                }
                                if (self.current_class["name"] == "Main"
                                    and selector == "run" and desc):
                                    self.program_description = desc
                                stripped = stripped[idx:].strip()
                            else:
                                no_comm = self.remove_comments(stripped)
                                if not no_comm.strip():
                                    continue
                                sys.exit(ErrorType.SYN_ERR_INPUT.value)
                        else:
                            no_comm = self.remove_comments(stripped)
                            if not no_comm.strip():
                                continue
                            sys.exit(ErrorType.SYN_ERR_INPUT.value)

                if not self.in_block:
                    if "[" in stripped and "]" in stripped:
                        idx_open = stripped.find("[")
                        idx_close = stripped.find("]")
                        block_literal = stripped[idx_open:idx_close+1]
                        trailing = stripped[idx_close+1:].strip()
                        self.in_block = True
                        self.block_params = []
                        self.block_body_lines = []
                        no_comm_block = self.remove_comments(block_literal)
                        if "|" in no_comm_block:
                            left = no_comm_block[1:no_comm_block.index("|")].strip()
                            if left:
                                tokens = left.split()
                                for t in tokens:
                                    if t.startswith(":"):
                                        self.block_params.append(t[1:])
                            right = no_comm_block[no_comm_block.index("|")+1:-1].strip()
                            if right:
                                self.block_body_lines.append(right)
                        self.store_method()
                        if trailing:
                            comment_text = self.extract_first_trailing_comment(trailing)
                            if (comment_text and self.program_description is None
                                and self.current_class and self.current_class["name"] == "Main"):
                                self.program_description = comment_text
                            if trailing:
                                self.lines.insert(self.index, trailing)
                    elif stripped.startswith("["):
                        self.in_block = True
                        self.block_params = []
                        self.block_body_lines = []
                        no_comm = self.remove_comments(stripped)
                        if "|" in no_comm:
                            left = no_comm[1:no_comm.index("|")].strip()
                            if left:
                                tokens = left.split()
                                for t in tokens:
                                    if t.startswith(":"):
                                        self.block_params.append(t[1:])
                            right = no_comm[no_comm.index("|")+1:].strip()
                            if right and right != "]":
                                self.block_body_lines.append(right)
                    else:
                        no_comm = self.remove_comments(stripped)
                        if not no_comm.strip():
                            continue
                        sys.exit(ErrorType.SYN_ERR_INPUT.value)
                else:
                    if stripped == "]":
                        self.store_method()
                    else:
                        no_comm = self.remove_comments(stripped)
                        if "|" in no_comm and not self.block_params:
                            left = no_comm[:no_comm.index("|")].strip()
                            if left:
                                tokens = left.split()
                                for t in tokens:
                                    if t.startswith(":"):
                                        self.block_params.append(t[1:])
                            right = no_comm[no_comm.index("|")+1:].strip()
                            if right:
                                self.block_body_lines.append(right)
                        else:
                            if no_comm.strip():
                                self.block_body_lines.append(no_comm)

    def check_main(self):
        main_found = False
        run_found = False
        for cls in self.classes:
            if cls["name"] == "Main":
                main_found = True
                for m in cls["methods"]:
                    if m["selector"] == "run":
                        run_found = True
                        break
                break
        if not main_found or not run_found:
            sys.exit(ErrorType.SEM_IN_MAIN.value)


def build_xml(classes, description):
    root = Element("program")
    root.attrib["language"] = "SOL25"
    if description:
        root.attrib["description"] = description
    for c in classes:
        class_elem = SubElement(root, "class")
        class_elem.attrib["name"] = c["name"]
        if c["parent"]:
            class_elem.attrib["parent"] = c["parent"]
        for m in c["methods"]:
            meth_elem = SubElement(class_elem, "method")
            meth_elem.attrib["selector"] = m["selector"]
            block = m.get("block", {"arity": 0, "parameters": [], "body": ""})
            block_elem = SubElement(meth_elem, "block")
            block_elem.attrib["arity"] = str(block["arity"])
            for idx, par in enumerate(block["parameters"], start=1):
                param_elem = SubElement(block_elem, "parameter")
                param_elem.attrib["order"] = str(idx)
                param_elem.attrib["name"] = par
            if block["body"]:
                body_elem = SubElement(block_elem, "body")
                body_elem.text = block["body"]
    return root

def main():
    if len(sys.argv) != 1:
        if len(sys.argv) == 2 and sys.argv[1] == "--help":
            show_help()
        else:
            print("Neznamy parameter alebo zakazana kombinacia parametrov.", file=sys.stderr)
            sys.exit(ErrorType.MISSING_PARAM.value)

    lines = sys.stdin.read().splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if not lines:
        sys.exit(ErrorType.LEX_ERR_INPUT.value)

    parser = Parser(lines)
    parser.parse_main()
    if parser.current_class is not None or parser.in_block or parser.current_method is not None:
        sys.exit(ErrorType.SYN_ERR_INPUT.value)

    parser.check_main()
    root = build_xml(parser.classes, parser.program_description)
    dom = xml.dom.minidom.parseString(tostring(root, encoding="utf-8"))
    # Vrati bytes
    pretty_xml = dom.toprettyxml(indent="    ", encoding="UTF-8")
    # Prevedieme na str
    pretty_str = pretty_xml.decode("utf-8")

    # Nahradime &amp;#10; => &#10;
    pretty_str = pretty_str.replace("&amp;#10;", "&#10;")
    # Nahradime &amp;nbsp; => &nbsp;
    pretty_str = pretty_str.replace("&amp;nbsp;", "&nbsp;")

    sys.stdout.write(pretty_str)

if __name__ == "__main__":
    main()
