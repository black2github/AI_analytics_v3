# app/scripts/debug_pagetree_http.py
"""
Диагностика HTTP-доступа к дереву дочерних страниц Confluence.

Перебирает несколько вариантов запроса дочерних страниц (page-tree endpoint
с разными параметрами + legacy children.action) и для каждого печатает:
  • HTTP-статус и длину ответа;
  • количество <a href>, из них со ссылкой, содержащей pageId;
  • примеры href (чтобы увидеть формат: с pageId или /display/SPACE/Title).

Дополнительно вытаскивает spaceKey и заголовок из самой страницы (viewpage),
т.к. некоторым вариантам endpoint нужен spaceKey.

Использование:
    python app/scripts/debug_pagetree_http.py <page_id>

Пример:
    python app/scripts/debug_pagetree_http.py 2166860477
"""

import sys
from bs4 import BeautifulSoup

from app.config import CONFLUENCE_BASE_URL
from app.page_cache import _confluence_http_get, _PAGE_ID_RE


def _extract_space_key(soup) -> str:
    """Пытается вытащить spaceKey из meta-тегов страницы Confluence."""
    for attrs in (
        {"id": "confluence-space-key"},
        {"name": "confluence-space-key"},
        {"name": "ajs-space-key"},
    ):
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            return tag["content"]
    return ""


def _report(label: str, url: str):
    print("=" * 78)
    print(f"[{label}]")
    print("URL:", url)
    response = _confluence_http_get(url)
    if response is None:
        print("  -> ОТВЕТ: None (запрос не прошёл)")
        return
    print("  HTTP status:", response.status_code,
          "| Content-Type:", response.headers.get("Content-Type"),
          "| длина:", len(response.text))

    soup = BeautifulSoup(response.text, "html.parser")
    anchors = soup.find_all("a", href=True)
    with_id = [a for a in anchors if _PAGE_ID_RE.search(a["href"])]
    print(f"  <a href>: всего={len(anchors)}, c pageId={len(with_id)}")

    # Печатаем до 12 примеров ссылок
    shown = 0
    seen = set()
    for a in anchors:
        href = a["href"]
        if href in seen:
            continue
        seen.add(href)
        m = _PAGE_ID_RE.search(href)
        marker = f"pageId={m.group(1)}" if m else "НЕТ pageId"
        text = a.get_text(strip=True)[:45]
        print(f"    [{marker:>14}] {href}   text='{text}'")
        shown += 1
        if shown >= 12:
            break

    # Если ссылок нет вовсе — покажем кусок HTML, чтобы понять структуру
    if not anchors:
        snippet = response.text.strip()[:800]
        print("  (ссылок нет; первые 800 символов ответа:)")
        print("  " + snippet.replace("\n", "\n  "))


def main():
    if len(sys.argv) < 2:
        print("Usage: python app/scripts/debug_pagetree_http.py <page_id>")
        sys.exit(1)

    page_id = sys.argv[1].strip()
    base = CONFLUENCE_BASE_URL.rstrip("/")

    # 1. Сначала тянем саму страницу — нужны spaceKey и заголовок.
    page_url = f"{base}/pages/viewpage.action?pageId={page_id}"
    print("Получаю страницу:", page_url)
    resp = _confluence_http_get(page_url)
    space_key = ""
    if resp is not None:
        psoup = BeautifulSoup(resp.text, "html.parser")
        space_key = _extract_space_key(psoup)
        title_tag = psoup.find(id="title-text")
        title = title_tag.get_text(strip=True) if title_tag else "(?)"
        print(f"  title='{title}'  spaceKey='{space_key}'")
    else:
        print("  Не удалось получить страницу — spaceKey неизвестен.")

    sk = f"&spaceKey={space_key}" if space_key else ""

    # 2. Перебираем варианты endpoint'ов получения детей.
    variants = {
        "naturalchildren (как сейчас)":
            f"{base}/plugins/pagetree/naturalchildren.action"
            f"?decorator=none&excerpt=false&sort=position&reverse=false"
            f"&disableLinks=false&expandCurrent=false&pageId={page_id}",

        "naturalchildren + spaceKey":
            f"{base}/plugins/pagetree/naturalchildren.action"
            f"?decorator=none&excerpt=false&sort=position&reverse=false"
            f"&disableLinks=false&expandCurrent=false&pageId={page_id}{sk}",

        "naturalchildren + treeId/treePageId/hasRoot + spaceKey":
            f"{base}/plugins/pagetree/naturalchildren.action"
            f"?decorator=none&excerpt=false&sort=position&reverse=false"
            f"&disableLinks=false&expandCurrent=true&hasRoot=true&treeId=0"
            f"&startDepth=1&mobile=false&treePageId={page_id}&pageId={page_id}{sk}",

        "pagetree.action (rootPageId)":
            f"{base}/plugins/pagetree/pagetree.action"
            f"?treeId=0&hasRoot=true&pageId={page_id}&treePageId={page_id}"
            f"&startDepth=1&clickableTitle=true&decorator=none{sk}",

        "legacy children.action":
            f"{base}/pages/children.action?pageId={page_id}",
    }

    for label, url in variants.items():
        _report(label, url)


if __name__ == "__main__":
    main()
