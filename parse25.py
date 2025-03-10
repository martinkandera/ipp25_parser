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


class Parser:
    class_header_re = re.compile(
        r"^class\s+([A-Z][A-Za-z0-9]*)\s*(?::\s*([A-Z][A-Za-z0-9]*))?\s*\{(.*)$")
    method_header_re = re.compile(
        r"^([a-z_][A-Za-z0-9_:]*)(?:\s+\"([^\"]+)\")?\s*$")

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
        in_single = False  # track if inside a single-quoted literal
        while i < len(line):
            ch = line[i]
            if ch == "'" and not in_single:
                in_single = True
                result += ch
                i += 1
            elif ch == "'" and in_single:
                in_single = False
                result += ch
                i += 1
            elif not in_single and ch == '"':
                j = i + 1
                while j < len(line) and line[j] != '"':
                    j += 1
                if j >= len(line):
                    sys.exit(ErrorType.LEX_ERR_INPUT.value)
                i = j + 1  # skip the comment
            else:
                result += ch
                i += 1
        return result

    def extract_first_trailing_comment(self, text):
        m = re.search(r'"([^"]*)"', text)
        if not m:
            return None
        raw_comment = m.group(1)
        return self.transform_description(raw_comment)

    def transform_description(self, desc):
        desc = desc.replace('\n', '\u0001')
        desc = desc.replace(r'\n', '\u0001')
        out = []
        i = 0
        while i < len(desc):
            if desc[i] == '\u0001':
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

    def strip_parentheses(self, expr):
        expr = expr.strip()
        while expr.startswith("(") and expr.endswith(")") and len(expr) > 1:
            expr = expr[1:-1].strip()
        return expr

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

    def parse_block_instructions(self, lines_in_block):
        instructions = []
        order = 1
        assign_re = re.compile(r"^\s*([a-z_][A-Za-z0-9_]*)\s*:=\s*(.+?)\.\s*$")
        integer_re = re.compile(r"^[+-]?\d+$")
        for line in lines_in_block:
            m = assign_re.match(line.strip())
            if not m:
                continue
            var_name = m.group(1)
            expr_str = m.group(2).strip()
            clean_expr = self.strip_parentheses(expr_str)
            if clean_expr.startswith("[") and clean_expr.endswith("]") and "|" in clean_expr:
                param_part = clean_expr[1:clean_expr.index("|")].strip()
                # body part is expected to be empty for test25.
                params = []
                if param_part:
                    tokens = param_part.split()
                    for token in tokens:
                        if token.startswith(":"):
                            params.append(token[1:])
                block_node = {
                    "type": "block",
                    "arity": len(params),
                    "parameters": params,
                    "instructions": []
                }
                instr = {
                    "type": "assign",
                    "order": order,
                    "var": var_name,
                    "expr": block_node
                }
            elif clean_expr.startswith("[") and clean_expr.endswith("]"):
                block_node = {
                    "type": "block",
                    "arity": 0,
                    "parameters": [],
                    "instructions": []
                }
                instr = {
                    "type": "assign",
                    "order": order,
                    "var": var_name,
                    "expr": block_node
                }
            elif integer_re.match(clean_expr):
                instr = {
                    "type": "assign",
                    "order": order,
                    "var": var_name,
                    "expr": {
                        "type": "literal",
                        "class": "Integer",
                        "value": clean_expr
                    }
                }
            elif clean_expr == "nil":
                instr = {
                    "type": "assign",
                    "order": order,
                    "var": var_name,
                    "expr": {
                        "type": "literal",
                        "class": "Nil",
                        "value": "nil"
                    }
                }
            elif clean_expr == "true":
                instr = {
                    "type": "assign",
                    "order": order,
                    "var": var_name,
                    "expr": {
                        "type": "literal",
                        "class": "True",
                        "value": "true"
                    }
                }
            elif clean_expr == "false":
                instr = {
                    "type": "assign",
                    "order": order,
                    "var": var_name,
                    "expr": {
                        "type": "literal",
                        "class": "False",
                        "value": "false"
                    }
                }
            elif clean_expr.startswith("'") and clean_expr.endswith("'"):
                value = clean_expr[1:-1]
                value = value.replace("\\'", "\\&apos;")
                instr = {
                    "type": "assign",
                    "order": order,
                    "var": var_name,
                    "expr": {
                        "type": "literal",
                        "class": "String",
                        "value": value
                    }
                }
            else:
                parts = clean_expr.split()
                if len(parts) == 2:
                    receiver = parts[0]
                    selector = parts[1]
                    instr = {
                        "type": "assign",
                        "order": order,
                        "var": var_name,
                        "expr": {
                            "type": "send",
                            "selector": selector,
                            "expr": {
                                "type": "literal",
                                "class": "class",
                                "value": receiver
                            },
                            "args": []
                        }
                    }
                elif len(parts) == 3 and parts[1].endswith(":"):
                    receiver = parts[0]
                    selector = parts[1]
                    arg_token = parts[2]
                    if integer_re.match(arg_token):
                        arg_expr = {"type": "literal", "class": "Integer", "value": arg_token}
                    elif arg_token == "nil":
                        arg_expr = {"type": "literal", "class": "Nil", "value": "nil"}
                    elif arg_token == "true":
                        arg_expr = {"type": "literal", "class": "True", "value": "true"}
                    elif arg_token == "false":
                        arg_expr = {"type": "literal", "class": "False", "value": "false"}
                    elif arg_token.startswith("'") and arg_token.endswith("'"):
                        val = arg_token[1:-1]
                        val = val.replace("\\'", "\\&apos;")
                        arg_expr = {"type": "literal", "class": "String", "value": val}
                    else:
                        arg_expr = {"type": "literal", "class": "Unknown", "value": arg_token}
                    instr = {
                        "type": "assign",
                        "order": order,
                        "var": var_name,
                        "expr": {
                            "type": "send",
                            "selector": selector,
                            "expr": {"type": "literal", "class": "class", "value": receiver},
                            "args": [{"order": 1, "expr": arg_expr}]
                        }
                    }
                else:
                    instr = {
                        "type": "assign",
                        "order": order,
                        "var": var_name,
                        "expr": {
                            "type": "literal",
                            "class": "Unknown",
                            "value": clean_expr
                        }
                    }
            instructions.append(instr)
            order += 1
        return instructions

    def store_method(self):
        if not self.current_method:
            return
        instructions = self.parse_block_instructions(self.block_body_lines)
        block = {
            "arity": len(self.block_params),
            "parameters": self.block_params,
            "instructions": instructions
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
                        self.current_method = {"selector": selector, "description": desc}
                        if self.current_class["name"] == "Main" and selector == "run" and desc:
                            self.program_description = self.transform_description(desc)
                        continue
                    else:
                        if "[" in stripped:
                            idx = stripped.find("[")
                            header_part = stripped[:idx].strip()
                            header_match = self.parse_method_header(header_part)
                            if header_match:
                                selector, desc = header_match
                                self.current_method = {"selector": selector, "description": desc}
                                if self.current_class["name"] == "Main" and selector == "run" and desc:
                                    self.program_description = self.transform_description(desc)
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
                # Now, handle block lines
                if not self.in_block:
                    if stripped.startswith("[") and not ("]" in stripped):
                        # Start of a multi-line block
                        self.in_block = True
                        self.block_params = []
                        self.block_body_lines = []
                        # Extract parameters if present in the header line (between '[' and '|')
                        no_comm = self.remove_comments(stripped)
                        if "|" in no_comm:
                            left = no_comm[1:no_comm.index("|")].strip()
                            if left:
                                tokens = left.split()
                                for t in tokens:
                                    if t.startswith(":"):
                                        self.block_params.append(t[1:])
                        # Do not store method yet; wait for closing bracket.
                    elif "[" in stripped and "]" in stripped:
                        # A single-line block (not assignment) – treat as method block header.
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
                            if trailing.strip() == "=":
                                pass
                            else:
                                comment_text = self.extract_first_trailing_comment(trailing)
                                if (comment_text and self.program_description is None and
                                    self.current_class and self.current_class["name"] == "Main"):
                                    self.program_description = comment_text
                                if trailing:
                                    self.lines.insert(self.index, trailing)
                    else:
                        # If in method block but not starting a new block header, then this line is a body line.
                        if self.in_block:
                            no_comm = self.remove_comments(stripped)
                            self.block_body_lines.append(no_comm)
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
            block = m.get("block", {"arity": 0, "parameters": [], "instructions": []})
            block_elem = SubElement(meth_elem, "block")
            block_elem.attrib["arity"] = str(block.get("arity", 0))
            for idx, par in enumerate(block.get("parameters", []), start=1):
                param_elem = SubElement(block_elem, "parameter")
                param_elem.attrib["order"] = str(idx)
                param_elem.attrib["name"] = par
            for instr in block.get("instructions", []):
                if instr["type"] == "assign":
                    assign_elem = SubElement(block_elem, "assign")
                    assign_elem.attrib["order"] = str(instr["order"])
                    var_elem = SubElement(assign_elem, "var")
                    var_elem.attrib["name"] = instr["var"]
                    expr_elem = SubElement(assign_elem, "expr")
                    if instr["expr"]["type"] == "literal":
                        lit_elem = SubElement(expr_elem, "literal")
                        lit_elem.attrib["class"] = instr["expr"]["class"]
                        lit_elem.attrib["value"] = instr["expr"]["value"]
                    elif instr["expr"]["type"] == "var":
                        var2_elem = SubElement(expr_elem, "var")
                        var2_elem.attrib["name"] = instr["expr"]["name"]
                    elif instr["expr"]["type"] == "send":
                        send_elem = SubElement(expr_elem, "send")
                        send_elem.attrib["selector"] = instr["expr"]["selector"]
                        inner_expr_elem = SubElement(send_elem, "expr")
                        if instr["expr"]["expr"]["type"] == "literal":
                            lit_elem = SubElement(inner_expr_elem, "literal")
                            lit_elem.attrib["class"] = instr["expr"]["expr"]["class"]
                            lit_elem.attrib["value"] = instr["expr"]["expr"]["value"]
                        elif instr["expr"]["expr"]["type"] == "var":
                            var_elem2 = SubElement(inner_expr_elem, "var")
                            var_elem2.attrib["name"] = instr["expr"]["expr"]["name"]
                        for arg in instr["expr"].get("args", []):
                            arg_elem = SubElement(send_elem, "arg")
                            arg_elem.attrib["order"] = str(arg["order"])
                            arg_expr_elem = SubElement(arg_elem, "expr")
                            if arg["expr"]["type"] == "literal":
                                lit_elem = SubElement(arg_expr_elem, "literal")
                                lit_elem.attrib["class"] = arg["expr"]["class"]
                                lit_elem.attrib["value"] = arg["expr"]["value"]
                            elif arg["expr"]["type"] == "var":
                                var_elem3 = SubElement(arg_expr_elem, "var")
                                var_elem3.attrib["name"] = arg["expr"]["name"]
                    elif instr["expr"]["type"] == "block":
                        block_elem_inner = SubElement(expr_elem, "block")
                        block_elem_inner.attrib["arity"] = str(instr["expr"]["arity"])
                        for idx, par in enumerate(instr["expr"]["parameters"], start=1):
                            param_elem = SubElement(block_elem_inner, "parameter")
                            param_elem.attrib["order"] = str(idx)
                            param_elem.attrib["name"] = par
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
    pretty_xml = dom.toprettyxml(indent="    ", encoding="UTF-8")
    pretty_str = pretty_xml.decode("utf-8")
    pretty_str = pretty_str.replace("&amp;#10;", "&#10;")
    pretty_str = pretty_str.replace("&amp;nbsp;", "&nbsp;")
    pretty_str = pretty_str.replace("&amp;apos;", "&apos;")
    pretty_str = pretty_str.replace("\\\\\\&apos;", "\\\\&apos;")
    sys.stdout.write(pretty_str)

if __name__ == "__main__":
    main()
