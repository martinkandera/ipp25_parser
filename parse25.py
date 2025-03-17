#!/usr/bin/env python3
import sys
import re
from enum import Enum
import xml.dom.minidom
from xml.etree.ElementTree import Element, SubElement, tostring

# Pomocna funkcia, ktora overuje, ci retazcovy literal obsahuje iba povolene escape sekvencie.
# Povolene escape sekvencie su: \' a \\.
# Ak spatne lomitko nie je nasledovane iba znakmi ' alebo \, alebo literal obsahuje skutocny znak noveho riadku,
# alebo obsahuje retazec "\n", program skonci s chybovym kodom 21.
def validate_string_literal(literal):
    i = 0
    # Prechadzame literal znak po znaku
    while i < len(literal):
        # Ak narazime na spatne lomitko a nasleduje pismeno n, ide o zakazany pripad
        if literal[i] == '\\' and literal[i+1] == 'n':
            sys.exit(ErrorType.LEX_ERR_INPUT.value)
        # Ak narazime na spatne lomitko nasledovane spatnym lomitkom
        if literal[i] == "\\" and literal[i + 1] == "\\":
            # Spatne lomitko nemoze byt poslednym znakom
            if i + 1 >= len(literal):
                sys.exit(ErrorType.LEX_ERR_INPUT.value)
            next_char = literal[i + 1]
            # Ak sa vyskytne dalsie spatne lomitko, posunieme sa o este jeden znak
            if next_char == "\\":
                next_char = literal[i + 2]
            # Ak dalsi znak nie je povoleny (apostrof, spatne lomitko alebo 'n'), skonci sa s chybou
            if next_char not in ["'", "\\", "n"]:
                sys.exit(ErrorType.LEX_ERR_INPUT.value)
            # Preskocime escape sekvenciu (3 znaky)
            i += 3
        else:
            i += 1

# Definicia chybovych kodov, ktore sa pouzivaju pri ukonceni programu
class ErrorType(Enum):
    NO_ERROR = 0          # Bez chyby
    MISSING_PARAM = 10    # Chyba: chyba parametra
    LEX_ERR_INPUT = 21    # Lexikalna chyba vo vstupnom kode
    SYN_ERR_INPUT = 22    # Syntakticka chyba vo vstupnom kode
    SEM_IN_MAIN = 31      # Semanticka chyba: chybaju trieda Main alebo metoda run
    SEM_UNDEFINED = 32    # Semanticka chyba: pouzita trieda, metoda alebo premenna nie je definovana
    SEM_MISSMATCH = 33    # Semanticka chyba: nespravny pocet argumentov
    SEM_COLLISION = 34    # Semanticka chyba: kolizia medzi formalnymi parametrami a lokalnymi premennymi
    SEM_OTHER = 35        # Ostatne semanticke chyby

# Funkcia show_help() vypise napovedu a skonci program
def show_help():
    print("Skript parse25.py parsuje zdrojovy kod jazyka SOL25 zo vstupu")
    print("a generuje XML reprezentaciu programu na vystup.")
    print("Pouzitie: python3 parse25.py < input_file > output_file")
    print("Parametre:")
    print("  --help        Vypise tuto napovedu a skonci.")
    sys.exit(ErrorType.NO_ERROR.value)

# Trieda Parser obsahuje vsetky metody pre lexikalnu a syntakticku analyzu vstupneho kodu.
class Parser:
    # Regularny vyraz pre hlavicku triedy:
    # Zachyti nazov triedy (zacina velkym pismenom), volitelne rodicovsku triedu a zacinajuci '{'
    class_header_re = re.compile(r"^class\s+([A-Z][A-Za-z0-9]*)\s*(?::\s*([A-Z][A-Za-z0-9]*))?\s*\{(.*)$")
    # Regularny vyraz pre hlavicku metody:
    # Zachyti selector (zacina malym pismenom) a volitelny popis v dvojitych uvodzovkach
    method_header_re = re.compile(r"^([a-z_][A-Za-z0-9_:]*)(?:\s+\"([^\"]+)\")?\s*$")

    # Konstruktor, ktory inicializuje Parser so zoznamom vstupnych riadkov
    def __init__(self, lines):
        self.lines = lines          # zoznam riadkov vstupneho kodu
        self.index = 0              # aktualna pozicia v zozname
        self.classes = []           # zoznam parsovanych tried
        self.current_class = None   # aktualne parsovana trieda
        self.current_method = None  # aktualne parsovana metoda
        self.in_block = False       # indikator, ci sa parsuje telo bloku
        self.block_params = []      # zoznam parametrov bloku (bez dvojtych bodiek)
        self.block_body_lines = []  # surove riadky tela bloku
        self.program_description = None  # popis programu (z metody run triedy Main)

    # Funkcia eof() vrati True, ak sme dosiahli koniec vstupnych riadkov
    def eof(self):
        return self.index >= len(self.lines)

    # Funkcia get_line() vrati aktualny riadok zo vstupu
    def get_line(self):
        if self.eof():
            return None
        return self.lines[self.index]

    # Funkcia advance() posunie index o 1 (prechod na dalsi riadok)
    def advance(self):
        self.index += 1

    # Funkcia remove_comments() odstrani komentarove casti z jedneho riadku.
    # Komentare su text medzi dvojitymi uvodzovkami.
    # Zachovava obsah v jednoduchych uvodzovkach.
    def remove_comments(self, line):
        result = ""
        i = 0
        in_single = False  # Indikator, ci sme v retazcovom literal v jednoduchych uvodzovkach
        while i < len(line):
            ch = line[i]
            # Ak narazime na apostrof a nie sme v literal, zacneme literal
            if ch == "'" and not in_single:
                in_single = True
                result += ch
                i += 1
            # Ak sme v literal a narazime na apostrof, ukoncime literal
            elif ch == "'" and in_single:
                in_single = False
                result += ch
                i += 1
            # Ak sme mimo literal a narazime na dvojite uvodzovky, preskocime text medzi nimi
            elif not in_single and ch == '"':
                j = i + 1
                while j < len(line) and line[j] != '"':
                    j += 1
                # Ak nie je najdeny zodpovedajuci zaviraci uvodzovky, chyba
                if j >= len(line):
                    sys.exit(ErrorType.LEX_ERR_INPUT.value)
                i = j + 1  # Preskocime cely komentar (otvarajuce aj zatvarajuce uvodzovky)
            else:
                result += ch
                i += 1
        return result

    # Funkcia remove_comments_multiline() odstrani komentarove casti z celeho textu,
    # ktory moze obsahovat viac riadkov.
    def remove_comments_multiline(self, text):
        result = ""
        i = 0
        in_single = False  # Indikator pre retazcovy literal v jednoduchych uvodzovkach
        while i < len(text):
            ch = text[i]
            if ch == "'" and not in_single:
                in_single = True
                result += ch
                i += 1
            elif ch == "'" and in_single:
                in_single = False
                result += ch
                i += 1
            # Ak sme mimo literal a narazime na dvojite uvodzovky, preskocime komentar
            elif not in_single and ch == '"':
                j = i + 1
                while j < len(text) and text[j] != '"':
                    j += 1
                if j >= len(text):
                    sys.exit(ErrorType.LEX_ERR_INPUT.value)
                i = j + 1  # Preskocime cely komentar
            else:
                result += ch
                i += 1
        return result

    # Funkcia extract_first_trailing_comment() extrahuje prvy trailing komentar z textu
    def extract_first_trailing_comment(self, text):
        m = re.search(r'"([^"]*)"', text)
        if not m:
            return None
        raw_comment = m.group(1)
        return self.transform_description(raw_comment)

    # Funkcia transform_description() transformuje popis.
    # Nahradi znak noveho riadku a retazec "\n" specialnymi symbolmi pre XML.
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

    # Funkcia strip_parentheses() odstrani vonkajsie zatvorky, ak su vyvazene
    def strip_parentheses(self, expr):
        expr = expr.strip()
        # Pockame, kym vyhovuje podmienka vyvazenosti a odstranime vonkajsie zatvorky
        while expr.startswith("(") and expr.endswith(")") and self.check_balanced(expr[1:-1]):
            expr = expr[1:-1].strip()
        return expr

    # Funkcia check_balanced() kontroluje, ci su zatvorky v retazci vyvazene.
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

    # Funkcia tokenize() rozdeluje retazec na tokeny.
    # Zachovava vnorenie zatvoriek a spracovava specialne znaky.
    def tokenize(self, s):
        tokens = []
        i = 0
        while i < len(s):
            if s[i].isspace():
                i += 1
                continue
            # Ak token zacina zatvorkou, najdeme cely blok
            if s[i] in "[(":
                open_char = s[i]
                close_char = "]" if open_char == "[" else ")"
                start = i
                depth = 1
                i += 1
                while i < len(s) and depth > 0:
                    if s[i] == open_char:
                        depth += 1
                    elif s[i] == close_char:
                        depth -= 1
                    i += 1
                tokens.append(s[start:i])
                continue
            # Ak token je dvojbodka, pripocitame ju k predchadzajucemu tokenu, ak nie je medzera
            if s[i] == ":":
                if i > 0 and not s[i - 1].isspace():
                    tokens[-1] += ":"
                else:
                    tokens.append(":")
                i += 1
                continue
            start = i
            # Citame token, kym nenarazime na medzeru alebo specialny znak
            while i < len(s) and (not s[i].isspace()) and s[i] not in "[]():":
                i += 1
            tokens.append(s[start:i])
        return tokens

    # Funkcia parse_inline_block() parsuje inline literal bloku.
    def parse_inline_block(self, block_str):
        # Odstranime vonkajsie zatvorky
        inner = block_str[1:-1].strip()
        params = []
        instr_str = ""
        # Ak obsahuje znak '|', rozdelime parameter cast a instrukcnu cast
        if "|" in inner:
            param_part, instr_str = inner.split("|", 1)
            param_part = param_part.strip()
            if param_part:
                for token in param_part.split():
                    if len(token) < 2:
                        sys.exit(ErrorType.SYN_ERR_INPUT.value)
                    # Kontrola, ci token zacina ':' a nasledne obsahuje povoleny identifikator
                    if re.fullmatch(r":[a-z_][A-Za-z0-9]*", token):
                        param_id = token[1:]
                        if param_id in {"class", "self", "super", "nil", "true", "false"}:
                            sys.exit(ErrorType.SYN_ERR_INPUT.value)
                        params.append(param_id)
                    else:
                        sys.exit(ErrorType.SYN_ERR_INPUT.value)
            instr_str = instr_str.strip()
        else:
            instr_str = inner
        # Ak instrukcna cast nema bodku na konci, pridame ju
        if instr_str and not instr_str.endswith("."):
            instr_str += "."
        # Rozdelime instrukcnu cast na surove instrukcie
        raw_instr = [s.strip() + "." for s in instr_str.split(".") if s.strip()]
        # Parsujeme instrukcie pomocou funkcie parse_block_instructions
        instructions = self.parse_block_instructions(raw_instr)
        return {"type": "block", "arity": len(params), "parameters": params, "instructions": instructions}

    # Funkcia parse_expr() parsuje vyraz a vracia stromovu reprezentaciu.
    def parse_expr(self, expr_str):
        expr_str = expr_str.strip()
        # Ak vyraz je blok, parsujeme inline block
        if expr_str.startswith("[") and expr_str.endswith("]"):
            return self.parse_inline_block(expr_str)
        # Odstranime vonkajsie zatvorky, ak su vyvazene
        expr_str = self.strip_parentheses(expr_str)
        # Overime, ci vyraz je cislo (s volitelnym predznakom)
        if expr_str and expr_str[0] in "+-" and not re.fullmatch(r"[+-]\d+", expr_str):
            sys.exit(ErrorType.LEX_ERR_INPUT.value)
        if re.fullmatch(r"[+-]?\d+", expr_str):
            return {"type": "literal", "class": "Integer", "value": expr_str}
        # Overime, ci ide o literal "nil", "true" alebo "false"
        if expr_str in ("nil", "true", "false"):
            lit_class = {"nil": "Nil", "true": "True", "false": "False"}[expr_str]
            return {"type": "literal", "class": lit_class, "value": expr_str}
        # Ak vyraz je retazcovy literal, parsujeme ho
        if expr_str.startswith("'") and expr_str.endswith("'"):
            value = expr_str[1:-1]
            if "\n" in value:
                sys.exit(ErrorType.LEX_ERR_INPUT.value)
            validate_string_literal(value)
            value = (value.replace("\\'", "\\&apos;")
                     .replace("<", "&lt;")
                     .replace(">", "&gt;")
                     .replace("&", "&amp;")
                     .replace('"', "&quot;"))
            return {"type": "literal", "class": "String", "value": value}
        # Rozdelime vyraz na tokeny
        tokens = self.tokenize(expr_str)
        # Overime, ci vsetky tokeny, ktore zacinu apostrofmi, su spravne ukoncene
        for t in tokens:
            if t.startswith("'") and not t.endswith("'"):
                sys.exit(ErrorType.LEX_ERR_INPUT.value)
        # Ak sa v tokenoch vyskytuje dvojbodka ako samostatny token, ide o chybu
        if ":" in tokens:
            sys.exit(ErrorType.SYN_ERR_INPUT.value)
        if len(tokens) == 0:
            return None
        if len(tokens) == 1:
            token = tokens[0].strip()
            if token.endswith(":"):
                token = token.rstrip(":").strip()
            if token == "":
                sys.exit(ErrorType.LEX_ERR_INPUT.value)
            # Ak token zacina velkym pismenom, ide o triedny literal
            if token[0].isupper():
                if not re.fullmatch(r"[A-Z][A-Za-z0-9]*", token):
                    sys.exit(ErrorType.LEX_ERR_INPUT.value)
                return {"type": "literal", "class": "class", "value": token}
            else:
                # Inak ide o premennu
                if token[0] not in "abcdefghijklmnopqrstuvwxyz_":
                    sys.exit(ErrorType.SYN_ERR_INPUT.value)
                if not re.fullmatch(r"[a-z_][A-Za-z0-9]*", token):
                    print("Problem token (variable):", token, file=sys.stderr)
                    sys.exit(ErrorType.LEX_ERR_INPUT.value)
                return {"type": "var", "name": token}
        # Parsovanie pre vyraz so dvoma tokenmi (jednoduchy send)
        if len(tokens) == 2:
            if tokens[1].strip().endswith(":"):
                sys.exit(ErrorType.SYN_ERR_INPUT.value)
            receiver = self.parse_expr(tokens[0])
            selector = tokens[1].strip()
            if not re.fullmatch(r"[a-z_][A-Za-z0-9]*", selector):
                sys.exit(ErrorType.SYN_ERR_INPUT.value)
            if selector in {"class", "self", "super", "nil", "true", "false"}:
                sys.exit(ErrorType.SYN_ERR_INPUT.value)
            return {"type": "send", "selector": selector, "expr": receiver, "args": []}
        # Parsovanie pre vyraz, kde selector obsahuje dvojtecky
        if len(tokens) > 2 and tokens[1].strip().endswith(":"):
            if len(tokens) % 2 == 0:
                sys.exit(ErrorType.LEX_ERR_INPUT.value)
            receiver = self.parse_expr(tokens[0])
            selector_parts = []
            args = []
            for i in range(1, len(tokens), 2):
                token_sel = tokens[i].strip()
                if not token_sel.endswith(":"):
                    sys.exit(ErrorType.SYN_ERR_INPUT.value)
                if not re.fullmatch(r"[A-Za-z0-9]+:$", token_sel):
                    sys.exit(ErrorType.LEX_ERR_INPUT.value)
                selector_parts.append(token_sel)
                if i + 1 < len(tokens):
                    arg_node = self.parse_expr(tokens[i + 1])
                    args.append({"order": len(args) + 1, "expr": arg_node})
            selector = "".join(selector_parts)
            if selector in {"class", "self", "super", "nil", "true", "false"}:
                sys.exit(ErrorType.SYN_ERR_INPUT.value)
            return {"type": "send", "selector": selector, "expr": receiver, "args": args}
        sys.exit(ErrorType.LEX_ERR_INPUT.value)

    # Funkcia parse_class_header() parsuje hlavicku triedy.
    def parse_class_header(self, stripped):
        m = self.class_header_re.match(stripped)
        if not m:
            sys.exit(ErrorType.SYN_ERR_INPUT.value)
        cls_name = m.group(1)
        parent = m.group(2) if m.group(2) else ""
        # Overime, ci nazov triedy zacina velkym pismenom
        if not re.fullmatch(r"[A-Z][A-Za-z0-9]*", cls_name):
            sys.exit(ErrorType.LEX_ERR_INPUT.value)
        remainder = m.group(3).strip()
        self.current_class = {"name": cls_name, "parent": parent, "methods": []}
        if remainder:
            self.lines.insert(self.index, remainder)

    # Funkcia parse_method_header() parsuje hlavicku metody a vracia tuple (selector, popis).
    def parse_method_header(self, stripped):
        mm = self.method_header_re.match(stripped)
        if not mm:
            return None
        selector = mm.group(1)
        if selector in {"class", "self", "super", "nil", "true", "false"}:
            sys.exit(ErrorType.SYN_ERR_INPUT.value)
        desc = mm.group(2) if mm.group(2) else ""
        return (selector, desc)

    # Funkcia parse_block_instructions() spoji vsetky riadky tela bloku, odstrani komentare,
    # a rozdelí text na top-level instrukcie. Instrukcie sa delia bodkou, ale iba ak sme na top-level.
    def parse_block_instructions(self, lines_in_block):
        all_text = "\n".join(lines_in_block)  # Spojime riadky s newline
        all_text = self.remove_comments_multiline(all_text)  # Odstranime komentare
        instructions = []
        current = ""
        bracket_depth = 0
        in_single_quote = False
        escape = False
        # Prechadzame text znak po znaku
        for ch in all_text:
            current += ch
            if in_single_quote:
                if escape:
                    escape = False
                elif ch == '\\':
                    escape = True
                elif ch == "'":
                    in_single_quote = False
                continue
            else:
                if ch == "'":
                    in_single_quote = True
                    continue
            # Zvysime alebo znizime hladinu vnorenia podla zatvoriek
            if ch == '[':
                bracket_depth += 1
            elif ch == ']':
                if bracket_depth > 0:
                    bracket_depth -= 1
            # Ak narazime na bodku a hladina vnorenia je 0, koniec instrukcie
            elif ch == '.' and bracket_depth == 0:
                instr = current.strip()
                if instr:
                    instructions.append(instr)
                current = ""
        if current.strip():
            instructions.append(current.strip())
        parsed_instructions = []
        order = 1
        assign_re = re.compile(r"^\s*([a-z_][A-Za-z0-9_]*)\s*:=\s*(.+?)\.\s*$", re.DOTALL)
        integer_re = re.compile(r"^[+-]?\d+$")
        # Prechadzame kazdu instrukciu a parsujeme ju
        for instr in instructions:
            m = assign_re.match(instr)
            if not m:
                sys.exit(ErrorType.SYN_ERR_INPUT.value)
            var_name = m.group(1)
            if not re.fullmatch(r"[a-z_][A-Za-z0-9]*", var_name):
                sys.exit(ErrorType.LEX_ERR_INPUT.value)
            # Kontrola rezervovanych identifikatorov pre premenne
            if var_name in {"self", "super", "true", "false", "nil", "class"}:
                sys.exit(ErrorType.SYN_ERR_INPUT.value)
            expr_str = m.group(2).strip()
            clean_expr = self.strip_parentheses(expr_str)
            # Ak ide o blok s parametrami (obsahuje '|'), rozdelime casti
            if clean_expr.startswith("[") and clean_expr.endswith("]") and "|" in clean_expr:
                param_part = clean_expr[1:clean_expr.index("|")].strip()
                params = []
                if param_part:
                    for token in param_part.split():
                        if token.startswith(":"):
                            params.append(token[1:])
                        else:
                            sys.exit(ErrorType.SYN_ERR_INPUT.value)
                instr_str = clean_expr[clean_expr.index("|") + 1:-1].strip()
                if instr_str and not instr_str.endswith("."):
                    instr_str += "."
                inner_instructions = self.parse_block_instructions([instr_str])
                parsed_instructions.append({
                    "type": "assign",
                    "order": order,
                    "var": var_name,
                    "expr": {
                        "type": "block",
                        "arity": len(params),
                        "parameters": params,
                        "instructions": inner_instructions
                    }
                })
            # Ak ide o prazdny blok
            elif clean_expr.startswith("[") and clean_expr.endswith("]"):
                parsed_instructions.append({
                    "type": "assign",
                    "order": order,
                    "var": var_name,
                    "expr": {"type": "block", "arity": 0, "parameters": [], "instructions": []}
                })
            # Ak ide o cislo
            elif integer_re.fullmatch(clean_expr):
                parsed_instructions.append({
                    "type": "assign",
                    "order": order,
                    "var": var_name,
                    "expr": {"type": "literal", "class": "Integer", "value": clean_expr}
                })
            # Literal "nil"
            elif clean_expr == "nil":
                parsed_instructions.append({
                    "type": "assign",
                    "order": order,
                    "var": var_name,
                    "expr": {"type": "literal", "class": "Nil", "value": "nil"}
                })
            # Literal "true"
            elif clean_expr == "true":
                parsed_instructions.append({
                    "type": "assign",
                    "order": order,
                    "var": var_name,
                    "expr": {"type": "literal", "class": "True", "value": "true"}
                })
            # Literal "false"
            elif clean_expr == "false":
                parsed_instructions.append({
                    "type": "assign",
                    "order": order,
                    "var": var_name,
                    "expr": {"type": "literal", "class": "False", "value": "false"}
                })
            # Retazcovy literal
            elif clean_expr.startswith("'") and clean_expr.endswith("'"):
                value = clean_expr[1:-1]
                validate_string_literal(value)
                value = value.replace("\\'", "\\&apos;")
                parsed_instructions.append({
                    "type": "assign",
                    "order": order,
                    "var": var_name,
                    "expr": {"type": "literal", "class": "String", "value": value}
                })
            else:
                node = self.parse_expr(clean_expr)
                if node is None:
                    sys.exit(ErrorType.LEX_ERR_INPUT.value)
                parsed_instructions.append({
                    "type": "assign",
                    "order": order,
                    "var": var_name,
                    "expr": node
                })
            order += 1
        return parsed_instructions

    # Funkcia store_method() ulozi parsovanu metodu do aktualnej triedy.
    # Ak je metoda 'run' triedy Main a prvy riadok tela bloku je komentar,
    # extrahuje jeho obsah ako popis programu a odstrani tento riadok z tela bloku.
    def store_method(self):
        if not self.current_method:
            return
        if (self.current_class["name"] == "Main" and
            self.current_method["selector"] == "run" and
            self.block_body_lines):
            first_line = self.block_body_lines[0].strip()
            if first_line.startswith('"') and first_line.endswith('"'):
                self.program_description = self.transform_description(first_line[1:-1])
                # Odstranime popisovy riadok z tela bloku
                self.block_body_lines.pop(0)
        instructions = self.parse_block_instructions(self.block_body_lines)
        block = {"arity": len(self.block_params), "parameters": self.block_params, "instructions": instructions}
        self.current_method["block"] = block
        self.current_class["methods"].append(self.current_method)
        self.current_method = None
        self.in_block = False
        self.block_params = []
        self.block_body_lines = []

    # Funkcia parse_main() riadi celkovu analyzu vstupneho kodu.
    # Parsuje triedy, metody a blokove literaly.
    def parse_main(self):
        while not self.eof():
            line = self.get_line()
            self.advance()
            if not line.strip():
                continue
            if self.current_class is None:
                # Parsovanie hlavicky triedy
                self.parse_class_header(line.strip())
            else:
                stripped = line.strip()
                if stripped.startswith("}"):
                    # Koniec tela triedy - ulozime ju a resetneme current_class
                    self.classes.append(self.current_class)
                    self.current_class = None
                    continue
                if self.current_method is None and not self.in_block:
                    # Parsovanie hlavicky metody
                    m_head = self.parse_method_header(stripped)
                    if m_head:
                        selector, desc = m_head
                        self.current_method = {"selector": selector, "description": desc}
                        if self.current_class["name"] == "Main" and selector == "run" and desc:
                            self.program_description = self.transform_description(desc)
                        continue
                    else:
                        # Ak riadok obsahuje blokovy literal, pokusime sa parsovat hlavicku a literal naraz
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
                    # Parsovanie blokovych literalov, ktore su na jednom riadku
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
                                    if len(t) < 2 or not t.startswith(":"):
                                        sys.exit(ErrorType.SYN_ERR_INPUT.value)
                                    param = t[1:]
                                    if param in {"class", "self", "super", "nil", "true", "false"}:
                                        sys.exit(ErrorType.SYN_ERR_INPUT.value)
                                    self.block_params.append(param)
                            right = no_comm_block[no_comm_block.index("|") + 1:-1].strip()
                            if right:
                                self.block_body_lines.append(right)
                        else:
                            sys.exit(ErrorType.SYN_ERR_INPUT.value)
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
                                    if len(t) < 2 or not t.startswith(":"):
                                        sys.exit(ErrorType.SYN_ERR_INPUT.value)
                                    param = t[1:]
                                    if param in {"class", "self", "super", "nil", "true", "false"}:
                                        sys.exit(ErrorType.SYN_ERR_INPUT.value)
                                    self.block_params.append(param)
                            right = no_comm[no_comm.index("|") + 1:].strip()
                            if right and right != "]":
                                self.block_body_lines.append(right)
                        else:
                            sys.exit(ErrorType.SYN_ERR_INPUT.value)
                    else:
                        no_comm = self.remove_comments(stripped)
                        if not no_comm.strip():
                            continue
                        sys.exit(ErrorType.SYN_ERR_INPUT.value)
                else:
                    if stripped == "]":
                        self.store_method()
                    else:
                        # V tele bloku nepridavame odstranenie komentaru pre kazdy riadok,
                        # iba surove riadky pridame do tela bloku
                        self.block_body_lines.append(stripped)

    # Funkcia check_main() overi, ci bola definovana trieda Main s metodou run.
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

# Funkcia semantic_check() vykonava semanticku kontrolu parsovaneho kodu.
# Overuje sa duplicitna definicia tried, metod, formalnych parametrov, circularne dedenie,
# undefined metody a premenne, aritmeticke chyby a kolizie.
def semantic_check(classes):
    # --- Preliminary checks pre kod 35 ---
    # Kontrola duplicitnej definicie tried
    seen_classes = set()
    for cls in classes:
        if cls["name"] in seen_classes:
            sys.exit(ErrorType.SEM_OTHER.value)
        seen_classes.add(cls["name"])
    # Kontrola duplicitnych metod v ramci triedy
    for cls in classes:
        seen_methods = set()
        for m in cls["methods"]:
            if m["selector"] in seen_methods:
                sys.exit(ErrorType.SEM_OTHER.value)
            seen_methods.add(m["selector"])
    # Kontrola duplicitnych formalnych parametrov
    for cls in classes:
        for m in cls["methods"]:
            params = m["block"].get("parameters", [])
            if len(params) != len(set(params)):
                sys.exit(ErrorType.SEM_OTHER.value)
    # Kontrola circularneho dedenia
    for cls in classes:
        visited = set()
        current = cls
        while current.get("parent"):
            parent_name = current["parent"]
            if parent_name in visited:
                sys.exit(ErrorType.SEM_OTHER.value)
            visited.add(parent_name)
            parent_cls = next((c for c in classes if c["name"] == parent_name), None)
            if parent_cls is None:
                break
            current = parent_cls
    # --- Kontrola undefined metod a premennych (kod 32) ---
    builtin = {
        "Integer": {"from:", "new", "plus:"},
        "String": {"plus:"},
        "Object": set()
    }
    class_methods = {}
    # Inicializacia vstavanych tried
    for k, v in builtin.items():
        class_methods[k] = set(v)
    # Pridanie metod pre pouzivatelsky definovane triedy
    for cls in classes:
        if cls["parent"] and cls["parent"] not in class_methods:
            sys.exit(ErrorType.SEM_UNDEFINED.value)
        if cls["name"] not in class_methods:
            class_methods[cls["name"]] = set()
        for m in cls["methods"]:
            class_methods[cls["name"]].add(m["selector"])
    # Propagacia dedenia
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
    # Funkcia check_expr() kontroluje kazdy vyraz
    def check_expr(expr, defined_vars):
        if expr["type"] == "literal":
            return
        elif expr["type"] == "var":
            if expr["name"] not in defined_vars:
                sys.exit(ErrorType.SEM_UNDEFINED.value)
        elif expr["type"] == "send":
            rec = expr["expr"]
            if rec["type"] == "literal" and rec.get("class") == "class":
                cls_name = rec["value"]
                if cls_name not in class_methods or expr["selector"] not in class_methods[cls_name]:
                    sys.exit(ErrorType.SEM_UNDEFINED.value)
            else:
                check_expr(rec, defined_vars)
            for arg in expr.get("args", []):
                check_expr(arg["expr"], defined_vars)
        elif expr["type"] == "block":
            new_defined = set(expr.get("parameters", []))
            return
    for cls in classes:
        for m in cls["methods"]:
            defined = set(m["block"].get("parameters", []))
            defined.add("self")
            for instr in m["block"].get("instructions", []):
                check_expr(instr["expr"], defined)
                # Kolizia premennej s formalnym parametrom je chyba 34
                if instr["var"] in m["block"].get("parameters", []):
                    sys.exit(ErrorType.SEM_COLLISION.value)
                defined.add(instr["var"])
    # --- Kontrola aritmetiky (kod 33) ---
    def build_method_arities(classes):
        builtin_arities = {
            "Integer": {"from:": 1, "new": 0, "plus:": 1},
            "String": {"plus:": 1},
            "Object": {}
        }
        method_arities = {}
        for cls_name, arities in builtin_arities.items():
            method_arities[cls_name] = dict(arities)
        for cls in classes:
            if cls["name"] not in method_arities:
                method_arities[cls["name"]] = {}
            for m in cls["methods"]:
                # V triede Main musi metoda run byt bez parametrov
                if cls["name"] == "Main" and m["selector"] == "run" and m["block"]["arity"] != 0:
                    sys.exit(ErrorType.SEM_MISSMATCH.value)
                method_arities[cls["name"]][m["selector"]] = m["block"]["arity"]
        changed = True
        while changed:
            changed = False
            for cls in classes:
                if cls["parent"]:
                    parent = cls["parent"]
                    for sel, arity in method_arities[parent].items():
                        if sel not in method_arities[cls["name"]]:
                            method_arities[cls["name"]][sel] = arity
                            changed = True
        return method_arities
    def check_expr_arity(expr, defined_vars, current_method_arities, method_arities):
        if expr["type"] == "literal":
            return
        elif expr["type"] == "var":
            return
        elif expr["type"] == "send":
            rec = expr["expr"]
            # Pripad: prijemca je literal triedy
            if rec["type"] == "literal" and rec.get("class") == "class":
                cls_name = rec["value"]
                if cls_name in method_arities and expr["selector"] in method_arities[cls_name]:
                    expected = method_arities[cls_name][expr["selector"]]
                    if len(expr.get("args", [])) != expected:
                        sys.exit(ErrorType.SEM_MISSMATCH.value)
            # Pripad: prijemca je implicitne "self"
            elif rec["type"] == "var" and rec["name"] == "self":
                if expr["selector"] in current_method_arities:
                    expected = current_method_arities[expr["selector"]]
                    if len(expr.get("args", [])) != expected:
                        sys.exit(ErrorType.SEM_MISSMATCH.value)
            else:
                check_expr_arity(rec, defined_vars, current_method_arities, method_arities)
            for arg in expr.get("args", []):
                check_expr_arity(arg["expr"], defined_vars, current_method_arities, method_arities)
        elif expr["type"] == "block":
            new_defined = set(expr.get("parameters", []))
            new_defined.update(defined_vars)
            return
    method_arities = build_method_arities(classes)
    for cls in classes:
        current_method_arities = method_arities[cls["name"]]
        for m in cls["methods"]:
            defined = set(m["block"].get("parameters", []))
            defined.add("self")
            for instr in m["block"].get("instructions", []):
                check_expr_arity(instr["expr"], defined, current_method_arities, method_arities)
    # --- Overenie, ci bola definovana trieda Main s metodou run ---
    main_found = False
    run_found = False
    for cls in classes:
        if cls["name"] == "Main":
            main_found = True
            for m in cls["methods"]:
                if m["selector"] == "run":
                    run_found = True
                    break
            break
    if not main_found or not run_found:
        sys.exit(ErrorType.SEM_IN_MAIN.value)

# Funkcia build_expr_xml() vytvara XML reprezentaciu vyrazu.
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
        # Ak blok obsahuje instrukcie, pridame ich do XML
        for instr in expr.get("instructions", []):
            if instr["type"] == "assign":
                assign_elem = SubElement(block_elem, "assign")
                assign_elem.attrib["order"] = str(instr["order"])
                var_elem = SubElement(assign_elem, "var")
                var_elem.attrib["name"] = instr["var"]
                expr_elem = SubElement(assign_elem, "expr")
                build_expr_xml(instr["expr"], expr_elem)

# Funkcia build_xml() vytvara XML reprezentaciu celeho programu.
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

# Hlavna funkcia main() nacita vstup, spusti parsovanie, vykona semanticku kontrolu,
# vytvori XML reprezentaciu programu a vypise ju.
def main():
    if len(sys.argv) != 1:
        if len(sys.argv) == 2 and sys.argv[1] == "--help":
            show_help()
        else:
            print("Neznamy parameter alebo zakazana kombinacia parametrov.", file=sys.stderr)
            sys.exit(ErrorType.MISSING_PARAM.value)
    lines = sys.stdin.read().splitlines()
    # Odstranime prazdne riadky na zaciatku vstupu
    while lines and not lines[0].strip():
        lines.pop(0)
    if not lines:
        sys.exit(ErrorType.SEM_IN_MAIN.value)  # Ak je vstup prazdny, skonci s chybou SEM_IN_MAIN
    parser = Parser(lines)
    parser.parse_main()
    # Overime, ci nezostali neparsovane casti
    if parser.current_class is not None or parser.in_block or parser.current_method is not None:
        sys.exit(ErrorType.SYN_ERR_INPUT.value)
    parser.check_main()
    # Semanticka kontrola: overi undefined metody a neinicializovane premenne.
    semantic_check(parser.classes)
    root = build_xml(parser.classes, parser.program_description)
    # Formatovanie XML vystupu s pomocou xml.dom.minidom
    dom = xml.dom.minidom.parseString(tostring(root, encoding="utf-8"))
    pretty_xml = dom.toprettyxml(indent="    ", encoding="UTF-8")
    pretty_str = pretty_xml.decode("utf-8")
    pretty_str = pretty_str.replace("&amp;#10;", "&#10;")
    pretty_str = pretty_str.replace("&amp;nbsp;", "&nbsp;")
    pretty_str = pretty_str.replace("&amp;apos;", "&apos;")
    pretty_str = pretty_str.replace("\\\\\\&apos;", "\\\\&apos;")
    sys.stdout.write(pretty_str)

# Spustenie hlavnej funkcie main()
if __name__ == "__main__":
    main()
