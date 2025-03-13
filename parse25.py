#!/usr/bin/env python3
import sys
import re
from enum import Enum
import xml.dom.minidom
from xml.etree.ElementTree import Element, SubElement, tostring


# Pomocna funkcia: Overuje, ci retazcovy literal obsahuje iba povolene escape sekvencie.
# Povolene escape sekvencie su: \' a \\.
# Ak spatne lomitko nie je nasledovane iba znakmi ' alebo \, alebo literal obsahuje skutocny znak noveho riadku,
# alebo obsahuje retazec "\n", program skonci s chybovym kodom 21.
def validate_string_literal(literal):
    # Prejdeme literal znak po znaku
    i = 0
    while i < len(literal):
        # Overime, ci literal neobsahuje skutocny znak noveho riadku
        if literal[i] == "\n":
            sys.exit(ErrorType.LEX_ERR_INPUT.value)
        # Ak narazime na spatne lomitko
        if literal[i] == "\\":
            # Ak spatne lomitko je posledny znak, chyba
            if i + 1 >= len(literal):
                sys.exit(ErrorType.LEX_ERR_INPUT.value)
            next_char = literal[i + 1]
            # Povolene su iba escapovane apostrofy alebo escapovane spatne lomitka
            if next_char not in ["'", "\\"]:
                sys.exit(ErrorType.LEX_ERR_INPUT.value)
            # Preskocime nasledujuci znak, pretoze je castou escape sekvencie
            i += 2
        else:
            i += 1


# Definicia chybovych kodov.
class ErrorType(Enum):
    NO_ERROR = 0
    MISSING_PARAM = 10
    LEX_ERR_INPUT = 21  # Lexikalna chyba vo vstupnom kode
    SYN_ERR_INPUT = 22  # Syntakticka chyba vo vstupnom kode
    SEM_IN_MAIN = 31  # Chyba: chybaju Main trieda alebo metoda run
    SEM_UNDEFINED = 32  # Chyba: pouzita trieda, metoda alebo premenna nie je definovana
    SEM_MISSMATCH = 33
    SEM_COLLISION = 34
    SEM_OTHER = 35


# Funkcia show_help() vypise napovedu a skonci program.
def show_help():
    print("Skript parse25.py parsuje zdrojovy kod jazyka SOL25 zo vstupu")
    print("a generuje XML reprezentaciu programu na vystup.")
    print("Pouzitie: python3 parse25.py < input_file > output_file")
    print("Parametre:")
    print("  --help        Vypise tuto napovedu a skonci.")
    sys.exit(ErrorType.NO_ERROR.value)


# Trieda Parser obsahuje metody na lexikalnu a syntakticku analyzu vstupneho kodu.
class Parser:
    # Regularne vyrazy pre hlavicku triedy a hlavicku metody.
    class_header_re = re.compile(r"^class\s+([A-Z][A-Za-z0-9]*)\s*(?::\s*([A-Z][A-Za-z0-9]*))?\s*\{(.*)$")
    method_header_re = re.compile(r"^([a-z_][A-Za-z0-9_:]*)(?:\s+\"([^\"]+)\")?\s*$")

    def __init__(self, lines):
        self.lines = lines  # zoznam vstupnych riadkov
        self.index = 0  # aktualny index v zozname
        self.classes = []  # zoznam parsovanych tried
        self.current_class = None  # aktualne spracovavana trieda
        self.current_method = None  # aktualne spracovavana metoda
        self.in_block = False  # ci sa spracovava telo bloku
        self.block_params = []  # parametre bloku (zoznam retezcov bez dvojtych bodiek)
        self.block_body_lines = []  # riadky tela bloku
        self.program_description = None  # popis ulozeny z hlavicky metody run v triede Main

    # Funkcia eof() vracia True, ak sme dosiahli koniec vstupnych riadkov.
    def eof(self):
        return self.index >= len(self.lines)

    # Funkcia get_line() vrati aktualny riadok.
    def get_line(self):
        if self.eof():
            return None
        return self.lines[self.index]

    # Funkcia advance() posunie index o 1.
    def advance(self):
        self.index += 1

    # Funkcia remove_comments() odstrani komentarove casti (text medzi dvojitymi uvodzovkami)
    # a zachova retazcove literaly v jednoduchych uvodzovkach.
    def remove_comments(self, line):
        result = ""
        i = 0
        in_single = False  # Sledovanie, ci sme vo vnutri retazcoveho literalu v jednoduchych uvodzovkach
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
                i = j + 1  # Preskocime komentarovu cast
            else:
                result += ch
                i += 1
        return result

    # Funkcia extract_first_trailing_comment() extrahuje prvy trailing komentar zo vstupneho textu.
    def extract_first_trailing_comment(self, text):
        m = re.search(r'"([^"]*)"', text)
        if not m:
            return None
        raw_comment = m.group(1)
        return self.transform_description(raw_comment)

    # Funkcia transform_description() transformuje text popisu: nahradi skutocne znaky noveho riadku
    # a literalne "\n" specialnymi symbolmi.
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

    # Funkcia strip_parentheses() odstrani vonkajsie zatvorky, ak su vyvazene.
    def strip_parentheses(self, expr):
        expr = expr.strip()
        while expr.startswith("(") and expr.endswith(")") and self.check_balanced(expr[1:-1]):
            expr = expr[1:-1].strip()
        return expr

    # Funkcia check_balanced() kontroluje, ci su zatvorky vyvazene.
    def check_balanced(self, s):
        depth = 0
        for ch in s:
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth < 0:
                    return False
        return depth == 0

    # Funkcia tokenize() rozdeluje retazec na tokeny, pri zachovani vnorenia zatvoriek.
    # Doplneny kod: Ak token obsahuje dvojbodku nasledovanu dalsim textom, rozdelime ho.
    def tokenize(self, s):
        # Insert a space after a closing parenthesis if immediately followed by a letter or digit.
        s = re.sub(r'\)([A-Za-z0-9])', r') \1', s)
        # Insert a space before an opening parenthesis if immediately preceded by a letter or digit.
        s = re.sub(r'([A-Za-z0-9])(\()', r'\1 \2', s)
        tokens = []
        current = ""
        pdepth = 0  # depth for parentheses
        bdepth = 0  # depth for square brackets
        for ch in s:
            if ch == '(':
                pdepth += 1
                current += ch
            elif ch == ')':
                pdepth -= 1
                current += ch
            elif ch == '[':
                bdepth += 1
                current += ch
            elif ch == ']':
                bdepth -= 1
                current += ch
            elif ch.isspace() and pdepth == 0 and bdepth == 0:
                if current:
                    tokens.append(current)
                    current = ""
            else:
                current += ch
        if current:
            tokens.append(current)
        # Post-process tokens: if a token contains a colon followed by text, split it.
        final_tokens = []
        for token in tokens:
            m = re.fullmatch(r"([A-Za-z0-9]+:)(.+)", token)
            if m:
                final_tokens.append(m.group(1))
                final_tokens.append(m.group(2))
            else:
                final_tokens.append(token)
        return final_tokens

    def parse_inline_block(self, block_str):
        # Remove the surrounding brackets.
        inner = block_str[1:-1].strip()
        params = []
        instr_str = ""
        if "|" in inner:
            param_part, instr_str = inner.split("|", 1)
            param_part = param_part.strip()
            if param_part:
                # Parameters should start with ':'; remove the colon.
                for token in param_part.split():
                    if token.startswith(":"):
                        params.append(token[1:])
                    else:
                        sys.exit(ErrorType.LEX_ERR_INPUT.value)
            instr_str = instr_str.strip()
        else:
            instr_str = inner
        # Ensure the instructions end with a period.
        if instr_str and not instr_str.endswith("."):
            instr_str += "."
        # Split the instructions by period and reattach the period.
        raw_instr = [s.strip() + "." for s in instr_str.split(".") if s.strip()]
        # Use the existing parse_block_instructions to parse the list of instruction lines.
        instructions = self.parse_block_instructions(raw_instr)
        return {"type": "block", "arity": len(params), "parameters": params, "instructions": instructions}

    def parse_expr(self, expr_str):
        expr_str = expr_str.strip()
        # If the expression is an inline block literal, handle it separately.
        if expr_str.startswith("[") and expr_str.endswith("]"):
            return self.parse_inline_block(expr_str)
        expr_str = self.strip_parentheses(expr_str)
        # String literal must end on the same line.
        if expr_str.startswith("'") and not expr_str.endswith("'"):
            sys.exit(ErrorType.LEX_ERR_INPUT.value)
        if expr_str and expr_str[0] in "+-" and not re.fullmatch(r"[+-]\d+", expr_str):
            sys.exit(ErrorType.LEX_ERR_INPUT.value)
        if re.fullmatch(r"[+-]?\d+", expr_str):
            return {"type": "literal", "class": "Integer", "value": expr_str}
        if expr_str == "nil":
            return {"type": "literal", "class": "Nil", "value": expr_str}
        if expr_str == "true":
            return {"type": "literal", "class": "True", "value": expr_str}
        if expr_str == "false":
            return {"type": "literal", "class": "False", "value": expr_str}
        if expr_str.startswith("'") and expr_str.endswith("'"):
            value = expr_str[1:-1]
            if "\n" in value:
                sys.exit(ErrorType.LEX_ERR_INPUT.value)
            validate_string_literal(value)
            value = value.replace("\\'", "\\&apos;")
            value = value.replace("<", "&lt;").replace(">", "&gt;").replace("&", "&amp;").replace('"', "&quot;")
            return {"type": "literal", "class": "String", "value": value}
        tokens = self.tokenize(expr_str)
        if len(tokens) == 0:
            return None
        # Single-token branch.
        if len(tokens) == 1:
            token = tokens[0].strip()
            if token.endswith(":"):
                token = token.rstrip(":").strip()
            if token == "":
                sys.exit(ErrorType.LEX_ERR_INPUT.value)
            if token[0].isupper():
                if not re.fullmatch(r"[A-Z][A-Za-z0-9]*", token):
                    sys.exit(ErrorType.LEX_ERR_INPUT.value)
                return {"type": "literal", "class": "class", "value": token}
            else:
                if not re.fullmatch(r"[a-z_][A-Za-z0-9]*", token):
                    print("Problem token (variable):", token, file=sys.stderr)
                    sys.exit(ErrorType.LEX_ERR_INPUT.value)
                return {"type": "var", "name": token}
        # Two-token branch: treat as simple send with no arguments.
        if len(tokens) == 2:
            receiver_token = tokens[0].strip()
            # Always re-parse the receiver.
            receiver_node = self.parse_expr(receiver_token)
            selector = tokens[1].strip()
            return {"type": "send", "selector": selector, "expr": receiver_node, "args": []}
        # Multi-token send expression branch.
        if len(tokens) > 2 and tokens[1].strip().endswith(":"):
            if len(tokens) % 2 == 0:
                sys.exit(ErrorType.LEX_ERR_INPUT.value)
            # Clean up the last token: if it ends with extraneous ")" characters, strip them off.
            tokens[-1] = tokens[-1].strip()
            while tokens[-1].endswith(")") and not self.check_balanced(tokens[-1]):
                tokens[-1] = tokens[-1][:-1].strip()
            receiver_token = tokens[0].strip()
            # Always re-parse the receiver.
            receiver_node = self.parse_expr(receiver_token)
            selector_parts = []
            args = []
            for i in range(1, len(tokens), 2):
                token_sel = tokens[i].strip()
                if not token_sel.endswith(":"):
                    sys.exit(ErrorType.LEX_ERR_INPUT.value)
                if not re.fullmatch(r"[A-Za-z0-9]+:$", token_sel):
                    sys.exit(ErrorType.LEX_ERR_INPUT.value)
                selector_parts.append(token_sel)
                if i + 1 < len(tokens):
                    arg_node = self.parse_expr(tokens[i + 1])
                    args.append({"order": len(args) + 1, "expr": arg_node})
            selector = "".join(selector_parts)
            return {"type": "send", "selector": selector, "expr": receiver_node, "args": args}
        sys.exit(ErrorType.LEX_ERR_INPUT.value)

    # Funkcia parse_class_header() parsuje hlavicku triedy a inicializuje current_class.
    def parse_class_header(self, stripped):
        m = self.class_header_re.match(stripped)
        if not m:
            sys.exit(ErrorType.SYN_ERR_INPUT.value)
        cls_name = m.group(1)
        parent = m.group(2) if m.group(2) else ""
        # Overime, ci nazov triedy zacina velkym pismenom.
        if not re.fullmatch(r"[A-Z][A-Za-z0-9]*", cls_name):
            sys.exit(ErrorType.LEX_ERR_INPUT.value)
        remainder = m.group(3).strip()
        self.current_class = {"name": cls_name, "parent": parent, "methods": []}
        if remainder:
            self.lines.insert(self.index, remainder)

    # Funkcia parse_method_header() parsuje hlavicku metody a vracia dvojicu (selector, description).
    def parse_method_header(self, stripped):
        mm = self.method_header_re.match(stripped)
        if not mm:
            return None
        selector = mm.group(1)
        desc = mm.group(2) if mm.group(2) else ""
        return (selector, desc)

    # Funkcia parse_block_instructions() parsuje instrukcie v tele bloku.
    # Pred spracovanim kazdeho riadku kontroluje, ci ma parny pocet jednoduchych uvodzoviek.
    def parse_block_instructions(self, lines_in_block):
        instructions = []
        order = 1
        # Allow multiline matches; also note DOTALL so '.' can match across newlines
        assign_re = re.compile(r"^\s*([a-z_][A-Za-z0-9_]*)\s*:=\s*(.+?)\.\s*$", re.DOTALL)
        integer_re = re.compile(r"^[+-]?\d+$")

        # We'll accumulate lines until we see a trailing period, then parse that chunk
        combined_lines = []
        current_line = ""

        # First, check quotes on each line (as before), but don’t parse them yet.
        for line in lines_in_block:
            # If the count of non-escaped quotes isn’t 0 or 2, error:
            if (line.count("'") - line.count("\\'")) not in (0, 2):
                sys.exit(ErrorType.LEX_ERR_INPUT.value)

            # Append this line (stripped) to current_line
            if current_line:
                current_line += " " + line.strip()
            else:
                current_line = line.strip()

            # If this combined text ends with a period, treat it as a full assignment
            if current_line.endswith("."):
                combined_lines.append(current_line)
                current_line = ""

        # If there's leftover text not ending with a period, push it anyway
        if current_line:
            combined_lines.append(current_line)

        # Now parse each combined line with your original logic
        for line in combined_lines:
            # Try matching var := something.
            m = assign_re.match(line.strip())
            if not m:
                # If it doesn't match at all, either skip or raise an error
                # (Skipping is typical if there's leftover blank lines, etc.)
                continue

            var_name = m.group(1)
            if not re.fullmatch(r"[a-z_][A-Za-z0-9]*", var_name):
                sys.exit(ErrorType.LEX_ERR_INPUT.value)

            expr_str = m.group(2).strip()
            clean_expr = self.strip_parentheses(expr_str)

            # Then do your usual literal/var/block parse:
            if clean_expr.startswith("[") and clean_expr.endswith("]") and "|" in clean_expr:
                param_part = clean_expr[1:clean_expr.index("|")].strip()
                params = []
                if param_part:
                    for token in param_part.split():
                        if token.startswith(":"):
                            params.append(token[1:])
                block_node = {"type": "block", "arity": len(params), "parameters": params, "instructions": []}
                instr = {"type": "assign", "order": order, "var": var_name, "expr": block_node}

            elif clean_expr.startswith("[") and clean_expr.endswith("]"):
                block_node = {"type": "block", "arity": 0, "parameters": [], "instructions": []}
                instr = {"type": "assign", "order": order, "var": var_name, "expr": block_node}

            elif integer_re.fullmatch(clean_expr):
                instr = {
                    "type": "assign",
                    "order": order,
                    "var": var_name,
                    "expr": {"type": "literal", "class": "Integer", "value": clean_expr}
                }

            elif clean_expr == "nil":
                instr = {
                    "type": "assign",
                    "order": order,
                    "var": var_name,
                    "expr": {"type": "literal", "class": "Nil", "value": "nil"}
                }

            elif clean_expr == "true":
                instr = {
                    "type": "assign",
                    "order": order,
                    "var": var_name,
                    "expr": {"type": "literal", "class": "True", "value": "true"}
                }

            elif clean_expr == "false":
                instr = {
                    "type": "assign",
                    "order": order,
                    "var": var_name,
                    "expr": {"type": "literal", "class": "False", "value": "false"}
                }

            elif clean_expr.startswith("'") and clean_expr.endswith("'"):
                value = clean_expr[1:-1]
                validate_string_literal(value)
                value = value.replace("\\'", "\\&apos;")
                instr = {
                    "type": "assign",
                    "order": order,
                    "var": var_name,
                    "expr": {"type": "literal", "class": "String", "value": value}
                }

            else:
                node = self.parse_expr(clean_expr)
                if node is None:
                    sys.exit(ErrorType.LEX_ERR_INPUT.value)
                instr = {"type": "assign", "order": order, "var": var_name, "expr": node}

            instructions.append(instr)
            order += 1

        return instructions

    # Funkcia store_method() ulozi aktualnu metodu do current_class a resetuje pomocne premenne.
    def store_method(self):
        if not self.current_method:
            return
        instructions = self.parse_block_instructions(self.block_body_lines)
        block = {"arity": len(self.block_params), "parameters": self.block_params, "instructions": instructions}
        self.current_method["block"] = block
        self.current_class["methods"].append(self.current_method)
        self.current_method = None
        self.in_block = False
        self.block_params = []
        self.block_body_lines = []

    # Funkcia parse_main() prechadza vsetky vstupne riadky a parsuje triedy, metody a bloky.
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
                if not self.in_block:
                    if "[" in stripped and "]" in stripped:
                        idx_open = stripped.find("[")
                        idx_close = stripped.find("]")
                        block_literal = stripped[idx_open:idx_close + 1]
                        trailing = stripped[idx_close + 1:].strip()
                        self.in_block = True
                        self.block_params = []
                        self.block_body_lines = []
                        no_comm_block = self.remove_comments(block_literal)
                        if "|" in no_comm_block:
                            left = no_comm_block[1:no_comm_block.index("|")].strip()
                            if left:
                                for t in left.split():
                                    if t.startswith(":"):
                                        self.block_params.append(t[1:])
                            right = no_comm_block[no_comm_block.index("|") + 1:-1].strip()
                            if right:
                                self.block_body_lines.append(right)
                        self.store_method()
                        if trailing:
                            if trailing.strip() == "=":
                                pass
                            else:
                                comment_text = self.extract_first_trailing_comment(trailing)
                                if (comment_text and self.program_description is None and self.current_class and
                                        self.current_class["name"] == "Main"):
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
                                for t in left.split():
                                    if t.startswith(":"):
                                        self.block_params.append(t[1:])
                            right = no_comm[no_comm.index("|") + 1:].strip()
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
                                for t in left.split():
                                    if t.startswith(":"):
                                        self.block_params.append(t[1:])
                            right = no_comm[no_comm.index("|") + 1:].strip()
                            if right:
                                self.block_body_lines.append(right)
                        else:
                            if no_comm.strip():
                                self.block_body_lines.append(no_comm)

    # Funkcia check_main() overuje, ci bola deklarovana trieda Main a metoda run.
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


# Semanticka kontrola: overuje definovane metody a inicializaciu premennych.
# Tiez kontroluje, ci su definovane vsetky rodicovske triedy (super triedy) pre user-defined triedy.
def semantic_check(classes):
    # Define built-in classes and their allowed methods.
    builtin = {
        "Integer": {"from:", "new", "plus:"},
        "String": {"plus:"},
        "Object": set()
    }
    class_methods = {}
    # Initialize built-in classes.
    for k, v in builtin.items():
        class_methods[k] = set(v)
    # Add methods for user-defined classes.
    for cls in classes:
        if cls["parent"] and cls["parent"] not in class_methods:
            sys.exit(ErrorType.SEM_UNDEFINED.value)
        if cls["name"] not in class_methods:
            class_methods[cls["name"]] = set()
        for m in cls["methods"]:
            class_methods[cls["name"]].add(m["selector"])
    # Propagate inheritance.
    changed = True
    while changed:
        changed = False
        for cls in classes:
            if cls["parent"]:
                parent = cls["parent"]
                if parent in class_methods:
                    before = len(class_methods[cls["name"]])
                    class_methods[cls["name"]].update(class_methods[parent])
                    if len(class_methods[cls["name"]]) > before:
                        changed = True

    # check_expr recursively verifies that every variable is defined and that message sends are valid.
    def check_expr(expr, defined_vars):
        if expr["type"] == "literal":
            return
        elif expr["type"] == "var":
            if expr["name"] not in defined_vars:
                sys.exit(ErrorType.SEM_UNDEFINED.value)
        elif expr["type"] == "send":
            # Check the receiver expression.
            rec = expr["expr"]
            if rec["type"] == "literal" and rec.get("class") == "class":
                cls_name = rec["value"]
                if cls_name not in class_methods or expr["selector"] not in class_methods[cls_name]:
                    sys.exit(ErrorType.SEM_UNDEFINED.value)
            else:
                check_expr(rec, defined_vars)
            # Check all arguments.
            for arg in expr.get("args", []):
                check_expr(arg["expr"], defined_vars)
        elif expr["type"] == "block":
            # New block scope: parameters become defined in the block.
            new_defined = set(expr.get("parameters", []))
            # (No further checking inside the block here.)
            return

    # For each method in each class, verify that every used variable is defined.
    for cls in classes:
        for m in cls["methods"]:
            # Start with the block's parameters plus the implicit "self".
            defined = set(m["block"].get("parameters", []))
            defined.add("self")
            for instr in m["block"].get("instructions", []):
                check_expr(instr["expr"], defined)
                defined.add(instr["var"])




def build_expr_xml(expr, parent):
    if expr["type"] == "literal":
        lit_elem = SubElement(parent, "literal")
        lit_elem.attrib["class"] = expr["class"]
        lit_elem.attrib["value"] = expr["value"]
    elif expr["type"] == "var":
        var_elem = SubElement(parent, "var")
        var_elem.attrib["name"] = expr["name"]
    elif expr["type"] == "send":
        send_elem = SubElement(parent, "send")
        send_elem.attrib["selector"] = expr["selector"]
        inner_expr_elem = SubElement(send_elem, "expr")
        build_expr_xml(expr["expr"], inner_expr_elem)
        for arg in expr.get("args", []):
            arg_elem = SubElement(send_elem, "arg")
            arg_elem.attrib["order"] = str(arg["order"])
            arg_expr_elem = SubElement(arg_elem, "expr")
            build_expr_xml(arg["expr"], arg_expr_elem)
    elif expr["type"] == "block":
        block_elem = SubElement(parent, "block")
        block_elem.attrib["arity"] = str(expr["arity"])
        for idx, par in enumerate(expr["parameters"], start=1):
            param_elem = SubElement(block_elem, "parameter")
            param_elem.attrib["order"] = str(idx)
            param_elem.attrib["name"] = par

# Modified build_xml using build_expr_xml for expressions.
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
                    build_expr_xml(instr["expr"], expr_elem)
    return root


# Hlavna funkcia main() - nacita vstup, spusti parsovanie, vykona semanticku kontrolu,
# vybuduje XML vystup a vypise ho.
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
        sys.exit(ErrorType.SEM_IN_MAIN.value)  # Ked je prazdny vstup, chyba SEM_IN_MAIN
    parser = Parser(lines)
    parser.parse_main()
    if parser.current_class is not None or parser.in_block or parser.current_method is not None:
        sys.exit(ErrorType.SYN_ERR_INPUT.value)
    parser.check_main()
    # Semanticka kontrola: overi undefined metody a neinicializovane premenne.
    semantic_check(parser.classes)
    root = build_xml(parser.classes, parser.program_description)
    #print(root, file=sys.stderr)
    dom = xml.dom.minidom.parseString(tostring(root, encoding="utf-8"))
    pretty_xml = dom.toprettyxml(indent="    ", encoding="UTF-8")
    pretty_str = pretty_xml.decode("utf-8")
    pretty_str = pretty_str.replace("&amp;#10;", "&#10;")
    pretty_str = pretty_str.replace("&amp;nbsp;", "&nbsp;")
    pretty_str = pretty_str.replace("&amp;apos;", "&apos;")
    pretty_str = pretty_str.replace("\\\\\\&apos;", "\\\\&apos;")
    sys.stdout.write(pretty_str)




# Spustenie hlavnej funkcie main().
if __name__ == "__main__":
    main()
