# tests/test_title_uniqueness_dictionaries.py
"""Пакет П3 ОНБ-В, п. 4 (решение владельца 2026-11-09): ⚠ «одинаковые названия разных
артефактов одного типа» остаётся ⚠; не дубль — группа из одних файлов `dictionaries.md`
(справочники подсервисов с заголовком шаблона `data-model.md`). `dictionaries.md` в группе с
карточкой другого имени и две карточки с одинаковым title — по-прежнему строка."""
from pathlib import Path

from app.scripts.CI.kitcheck.checks.content import check_title_uniqueness

T = "Справочники и параметры модели данных"


def test_dictionaries_of_subservices_not_duplicates(tmp_path):
    docs = tmp_path
    titles = {docs / "srs/a/data-model/dictionaries.md": ("data-model", T, "DM-003"),
              docs / "srs/b/data-model/dictionaries.md": ("data-model", T, "DM-005")}
    assert check_title_uniqueness(docs, titles) == []


def test_dictionaries_with_entity_still_duplicate(tmp_path):
    """НЕсрабатывание исключения: справочник и сущность с одним названием (стенд DM-001 / ENT-005)."""
    docs = tmp_path
    titles = {docs / "srs/data-model/dictionaries.md": ("data-model", "[КК] 2FA операция", "DM-001"),
              docs / "srs/data-model/ent-005-2fa.md": ("data-model", "[КК] 2FA операция", "ENT-005")}
    assert len(check_title_uniqueness(docs, titles)) == 1


def test_two_cards_same_title_still_duplicate(tmp_path):
    docs = tmp_path
    titles = {docs / "srs/contract-call/external/call-ext-011.md": ("contract-call", "Вызов", "CALL-EXT-011"),
              docs / "srs/contract-call/external/call-ext-036.md": ("contract-call", "Вызов", "CALL-EXT-036")}
    out = check_title_uniqueness(docs, titles)
    assert len(out) == 1 and "CALL-EXT-011, CALL-EXT-036" in out[0]
