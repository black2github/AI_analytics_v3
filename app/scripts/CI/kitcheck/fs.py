# app/scripts/CI/kitcheck/fs.py
"""Файловый кэш прогона: каждый файл читается с диска один раз за прогон.

Кэш действует только внутри `session()` — её открывает прогон самопроверки
(`selfcheck.run`). Вне сессии `read_text` / `read_bytes` читают диск
напрямую, как `Path.read_text` / `Path.read_bytes`: тесты и утилиты,
вызывающие функции прибора по отдельности, поведения не меняют.

Совпадение с `Path.read_text` — до символа:
- хранятся байты, декодирование — по параметрам места вызова (`encoding`,
  `errors`): строгое декодирование падает тем же `UnicodeDecodeError`;
- текстовый режим переводит `\\r\\n` и `\\r` в `\\n` (универсальные переводы
  строк), как это делает `open()` без `newline=`;
- ошибка чтения (`OSError`) не кэшируется и повторяется при каждом вызове.

Внутри сессии файлы не записываются (прогон самопроверки read-only): отчёт,
журнал и состояние пишутся после прогона. Утилиты, которые пишут файлы между
прогонами (гейт переноса копирует комплект во временный каталог), открывают
новую сессию на каждый прогон — устаревшего содержимого кэш не отдаёт.
"""
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterator, Optional, Union

PathLike = Union[str, "os.PathLike[str]"]

_cache: Optional[Dict[str, bytes]] = None


@contextmanager
def session() -> Iterator[None]:
    """Кэш на время прогона. Вложенная сессия пользуется внешней."""
    global _cache
    outer = _cache is not None
    if not outer:
        _cache = {}
    try:
        yield
    finally:
        if not outer:
            _cache = None


def active() -> bool:
    return _cache is not None


def _key(path: PathLike) -> str:
    return os.path.abspath(os.fspath(path))


def read_bytes(path: PathLike) -> bytes:
    if _cache is None:
        return Path(path).read_bytes()
    k = _key(path)
    data = _cache.get(k)
    if data is None:
        data = Path(path).read_bytes()
        _cache[k] = data
    return data


def read_text(path: PathLike, encoding: Optional[str] = None,
              errors: Optional[str] = None) -> str:
    if _cache is None:
        return Path(path).read_text(encoding=encoding, errors=errors)
    text = read_bytes(path).decode(encoding or _default_encoding(), errors or "strict")
    if "\r" in text:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text


def _default_encoding() -> str:
    import locale
    return locale.getpreferredencoding(False)
