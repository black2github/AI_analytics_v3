# tests/test_source_coverage_id_over_word.py
"""source_coverage: явный идентификатор базового контракта сильнее слова «заморожено» в основании
(постановка 2026-11-09, П-5; КК SVFE-002/003, 2184432769/2184432768: основание «метка «заморожено
GBO-70412» — наследие 05.10» уводило строку в «заморожено»)."""
from pathlib import Path

from app.scripts.CI import source_coverage as sc

SLUGS = {"bc-a"}


def cls(tmp_path: Path, target: str, basis: str, req_type: str = "integration", parent: str = "Раздел"):
    p = tmp_path / "p1.md"
    p.write_text("---\ntitle: 'Метод'\nconfluence_page_id: '1'\n---\n\nтекст страницы\n", encoding="utf-8")
    inv = {"1": {"title": "Метод", "parent": parent, "req_type": req_type, "target": target,
                 "basis": basis}}
    return sc.classify("1", p, inv, SLUGS, "srs/bc-a/")


def test_base_contract_id_beats_frozen_word_in_basis(tmp_path):
    assert cls(tmp_path, "вне SRS: базовый контракт EXTINT-SVFE-002",
               "метка «заморожено GBO-70412» — наследие 05.10") == sc.BASE_CONTRACT


def test_base_contract_id_in_basis_beats_frozen_word_in_basis(tmp_path):
    assert cls(tmp_path, "вне SRS", "базовый контракт EXTINT-SVFE-003; было заморожено GBO-70412") \
        == sc.BASE_CONTRACT


def test_frozen_word_without_id_still_frozen(tmp_path):
    # НЕсрабатывание изменения: идентификатора нет — слово в основании действует, как прежде
    assert cls(tmp_path, "вне SRS", "заморожено GBO-70412") == sc.FROZEN


def test_frozen_in_target_is_classification(tmp_path):
    # «заморожено» в целевом типе — классификация, сильнее идентификатора в основании
    assert cls(tmp_path, "заморожено (GBO-70412)", "базовый контракт EXTINT-SVFE-002") == sc.FROZEN


def test_frozen_in_req_type_and_parent_unchanged(tmp_path):
    assert cls(tmp_path, "вне SRS: базовый контракт EXTINT-SVFE-002", "текст",
               req_type="frozen") == sc.FROZEN
    assert cls(tmp_path, "вне SRS: базовый контракт EXTINT-SVFE-002", "текст",
               parent="заморожено (GBO-1)") == sc.FROZEN
