#!/usr/bin/env python3

import os
import subprocess
import sys

# Voliteľné farby pre zrozumiteľnejší výstup
GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"

def main():
    # Adresár, kde sa nachádzajú testy:
    tests_dir = "tests"

    # Nájdem všetky súbory v 'tests/', ktoré končia na '.in'
    # a vytvorím z nich zoznam testov
    test_files = [f for f in os.listdir(tests_dir) if f.endswith(".in")]
    test_files.sort()  # nech idú v poradí test1.in, test2.in, ...

    total = len(test_files)
    passed = 0

    print(f"Načítaných testov: {total}")
    print("========================================")

    for in_file in test_files:
        # Napr. 'test1.in' -> test_name = 'test1'
        test_name = in_file[:-3]

        # Očakávaný výstup a kód
        out_file = test_name + ".out"
        rc_file = test_name + ".rc"

        # Cesty k súborom
        in_path = os.path.join(tests_dir, in_file)
        out_path = os.path.join(tests_dir, out_file)
        rc_path = os.path.join(tests_dir, rc_file)

        # Ak existuje .rc, prečítame z neho očakávaný návratový kód,
        # inak predpokladáme 0
        expected_rc = 0
        if os.path.exists(rc_path):
            with open(rc_path, "r") as f:
                # ostripovať a konvertovať na int
                try:
                    expected_rc = int(f.read().strip())
                except ValueError:
                    print(f"{RED}Test {test_name}: Chyba vo formáte .rc súboru!{RESET}")
                    continue

        # Ak existuje .out, prečítame očakávaný výstup, inak None
        expected_output = None
        if os.path.exists(out_path):
            with open(out_path, "r", encoding="utf-8") as f:
                expected_output = f.read()
        else:
            # Možno to je test, kde nepotrebujeme porovnávať výstup
            expected_output = ""

        # Spustíme parse25.py s presmerovaním vstupu
        cmd = ["python3", "parse25.py"]
        with open(in_path, "r", encoding="utf-8") as inp:
            process = subprocess.Popen(
                cmd,
                stdin=inp,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            stdout, stderr = process.communicate()

        actual_rc = process.returncode

        # Kontrola návratového kódu
        if actual_rc != expected_rc:
            print(f"{RED}Test {test_name}: FAIL (RC {actual_rc} != {expected_rc}){RESET}")
            print("----- STDERR -----")
            print(stderr)
            print("------------------")
            continue

        # Ak očakávame RC != 0, spravidla už neporovnávame výstup
        if expected_rc != 0:
            print(f"{GREEN}Test {test_name}: OK (očakávaný RC = {expected_rc}){RESET}")
            passed += 1
            continue

        # Porovnáme výstup
        # (Môžete použiť aj 'diff', tu to riešime priamo v Pythone)
        if stdout == expected_output:
            print(f"{GREEN}Test {test_name}: OK{RESET}")
            passed += 1
        else:
            print(f"{RED}Test {test_name}: FAIL (odlišný výstup){RESET}")
            # Vypíšeme rozdiel (hrubým porovnaním)
            print("----- Očakávaný výstup -----")
            print(expected_output)
            print("----- Skutočný výstup -----")
            print(stdout)
            print("----------------------------")

    print("========================================")
    print(f"Výsledok: {passed}/{total} testov OK.")

if __name__ == "__main__":
    main()
