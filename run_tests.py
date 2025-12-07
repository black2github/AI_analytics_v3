#!/usr/bin/env python3
# run_tests.py

import subprocess
import sys
import os


def run_tests():
    """Запуск всех тестов с различными опциями"""

    print("** Running Requirements Analyzer Tests")
    print("=" * 50)

    # Базовые тесты
    print("\n!!! Running unit tests...")
    result = subprocess.run([
        "python", "-m", "pytest",
        "tests/",
        "-v",
        "--tb=short",
        "--cov=app",
        "--cov-report=term-missing"
    ])

    if result.returncode != 0:
        print("X Unit tests failed!")
        return False

    print("V All tests passed!")

    # Генерация HTML отчета
    print("\n Generating coverage report...")
    subprocess.run([
        "python", "-m", "pytest",
        "tests/",
        "--cov=app",
        "--cov-report=html:htmlcov"
    ])

    print("!!! Coverage report generated in htmlcov/index.html")
    return True


def run_specific_tests(test_pattern):
    """Запуск конкретных тестов"""
    print(f"??? Running tests matching: {test_pattern}")
    result = subprocess.run([
        "python", "-m", "pytest",
        f"tests/{test_pattern}",
        "-v"
    ])
    return result.returncode == 0


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Запуск конкретных тестов
        test_pattern = sys.argv[1]
        success = run_specific_tests(test_pattern)
    else:
        # Запуск всех тестов
        success = run_tests()

    sys.exit(0 if success else 1)