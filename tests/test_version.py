# tests/test_version.py
#
# Версия бандла (2026-08-07): номер + автоматический отпечаток исходников.

import re

from app.version import VERSION, banner, source_fingerprint


def test_fingerprint_stable_and_hexlike():
    a, b = source_fingerprint(), source_fingerprint()
    assert a == b                                  # детерминирован
    assert re.fullmatch(r"[0-9a-f]{8}", a)


def test_banner_carries_version_and_fingerprint():
    s = banner("critic")
    assert s.startswith("critic: версия " + VERSION)
    assert source_fingerprint() in s
