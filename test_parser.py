#!/usr/bin/env python3
import os
import re
import subprocess
import sys

GREEN = "\033[92m"
RED = "\033[91m"
BLUE = "\033[94m"
RESET = "\033[0m"

def numeric_key(filename):
    """
    Vrati tuple, ktory pouzijeme na triedenie podla cisla v nazve suboru,
    napr. test12.in => (12, '')
    test9.in => (9, '')
    test10.in => (10, '')
    Ak by sa tam vyskytovali dodatocne znaky, tie sluzia ako tie-break.
    """
    core = filename
    if core.startswith('test'):
        core = core[4:]  # odstranime 'test'
    if core.endswith('.in'):
        core = core[:-3]  # odstranime '.in'

    m = re.match(r'^(\d+)(.*)', core)
    if m:
        number = int(m.group(1))
        rest = m.group(2)
        return (number, rest)
    else:
        return (999999999, core)

def normalize_xml(xml_str):
    # Odstrani prazdne riadky a orezava medzery na zaciatkoch a koncoch riadkov
    lines = xml_str.strip().splitlines()
    normalized_lines = [line.strip() for line in lines if line.strip() != ""]
    return "\n".join(normalized_lines)

def run_file_tests():
    tests_dir = "tests"
    # Najdeme vsetky subory s priponou .in (okrem param. testov)
    test_files = [f for f in os.listdir(tests_dir)
                  if f.endswith(".in") and not f.startswith("test0_")]
    # Zoradime podla cisla
    test_files.sort(key=numeric_key)

    total = len(test_files)
    passed = 0
    if total:
        print("File-based tests:")

    previous_test_number = None
    for in_file in test_files:
        current_number, _ = numeric_key(in_file)
        # Ak existuje medzera v ciselnom poradi, vlozime oddeľovač
        if previous_test_number is not None and current_number != previous_test_number + 1:
            print("\033[94m-------------------------\033[0m")
        previous_test_number = current_number

        test_name = in_file[:-3]  # odstranime ".in"
        out_file = test_name + ".out"
        rc_file = test_name + ".rc"
        in_path = os.path.join(tests_dir, in_file)
        out_path = os.path.join(tests_dir, out_file)
        rc_path = os.path.join(tests_dir, rc_file)

        expected_rc = 0
        if os.path.exists(rc_path):
            with open(rc_path, "r") as f:
                try:
                    expected_rc = int(f.read().strip())
                except ValueError:
                    print(f"{RED}Test {test_name}: Chyba vo formate .rc suboru!{RESET}")
                    continue

        expected_output = ""
        if os.path.exists(out_path):
            with open(out_path, "r", encoding="utf-8") as f:
                expected_output = f.read()

        cmd = ["python3", "parse25.py"]
        with open(in_path, "r", encoding="utf-8") as inp:
            process = subprocess.Popen(cmd, stdin=inp, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, text=True)
            stdout, stderr = process.communicate()
        actual_rc = process.returncode

        if actual_rc != expected_rc:
            print(f"{RED}Test {test_name}: FAIL (RC {actual_rc} != {expected_rc}){RESET}")
            print("----- STDERR -----")
            print(stderr)
            print("------------------")
            continue

        if expected_rc != 0:
            print(f"{GREEN}Test {test_name}: OK (expected RC = {expected_rc}){RESET}")
            passed += 1
            continue

        norm_stdout = normalize_xml(stdout)
        norm_expected = normalize_xml(expected_output)
        if norm_stdout == norm_expected:
            print(f"{GREEN}Test {test_name}: OK{RESET}")
            passed += 1
        else:
            print(f"{RED}Test {test_name}: FAIL (output mismatch){RESET}")
            print("\033[94m----- Expected output -----\033[0m")
            print(norm_expected)
            print("\033[94m----- Actual output -----\033[0m")
            print(norm_stdout)
            print("-------------------------")

    if total:
        print(f"File tests: {passed}/{total} passed.\n")
    return passed, total

def run_param_tests():
    param_tests = [
        {"name": "test0_1", "args": ["--hekp"], "expected_rc": 10},
        {"name": "test0_2", "args": ["--help", "asd"], "expected_rc": 10},
        {"name": "test0_3", "args": ["--help", "--help"], "expected_rc": 10},
        {"name": "test0_4", "args": ["--unknown"], "expected_rc": 10},
        {"name": "test0_5", "args": ["--helpasd"], "expected_rc": 10},
        {"name": "test0_6", "args": ["--help", "--unknown"], "expected_rc": 10},
        {"name": "test0_7", "args": ["-help"], "expected_rc": 10},
        {"name": "test0_8", "args": ["help"], "expected_rc": 10},
        {"name": "test0_9", "args": ["--Help"], "expected_rc": 10},
    ]
    print("Parameter tests:")
    total = len(param_tests)
    passed = 0
    for test in param_tests:
        name = test["name"]
        args = test["args"]
        expected_rc = test["expected_rc"]
        cmd = ["python3", "parse25.py"] + args
        process = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True)
        stdout, stderr = process.communicate(input="")
        actual_rc = process.returncode
        if actual_rc != expected_rc:
            print(f"{RED}{name}: FAIL (RC {actual_rc} != {expected_rc}){RESET}")
            print("----- STDERR -----")
            print(stderr)
            print("------------------")
        else:
            print(f"{GREEN}{name}: OK{RESET}")
            passed += 1
    print(f"Parameter tests: {passed}/{total} passed.\n")
    return passed, total

def main():
    param_passed, param_total = run_param_tests()
    file_passed, file_total = run_file_tests()
    total_passed = file_passed + param_passed
    total_tests = file_total + param_total
    print("========================================")
    print(f"Total: {total_passed}/{total_tests} tests passed.")
    if total_passed == total_tests:
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
