#!/usr/bin/env python3
import os
import subprocess
import sys

GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"

def normalize_xml(xml_str):
    # Odstráni prázdne riadky a orezáva medzery na začiatkoch a koncoch riadkov.
    lines = xml_str.strip().splitlines()
    normalized_lines = [line.strip() for line in lines if line.strip() != ""]
    return "\n".join(normalized_lines)

def run_file_tests():
    tests_dir = "tests"
    # Vyberieme vsetky subory, ktore maju priponu ".in" a nepatria do parametrov (test0_*)
    test_files = sorted([f for f in os.listdir(tests_dir)
                         if f.endswith(".in") and not f.startswith("test0_")])
    total = len(test_files)
    passed = 0
    if total:
        print("File-based tests:")
    for in_file in test_files:
        test_name = in_file[:-3]  # odstranime priponu ".in"
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
            print("----- Expected output -----")
            print(norm_expected)
            print("----- Actual output -----")
            print(norm_stdout)
            print("-------------------------")
    if total:
        print(f"File tests: {passed}/{total} passed.\n")
    return passed, total

def run_param_tests():
    # Parametricke testy: test0_1 az test0_9
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
        # Pre parameter testy dodavame prazdny vstup
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
