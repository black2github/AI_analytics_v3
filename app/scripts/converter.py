# app/scripts/converter.py
"""
Confluence to Clean Markdown Converter
- Иерархическая структура папок (исправлено дублирование корневой папки)
- Вложения рядом с каждой страницей (папка _files создаётся только при наличии вложений)
- Относительные ссылки между страницами (поиск по названию и замена обычных HTML-ссылок)
- Корректная обработка сложных таблиц (colspan/rowspan, списки)
- Подробное логирование ссылок и создания папок
- Обработка таймаутов
"""

import os, re, sys, traceback, time
import requests
from requests.auth import HTTPBasicAuth
from bs4 import BeautifulSoup, NavigableString
import html2text
from pathlib import Path
from urllib.parse import urlparse, unquote
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime

from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

# ============ НАСТРОЙКИ ============
CONFLUENCE_URL = 'https://confluence.gboteam.ru'
JIRA_USERNAME = ''
JIRA_PASSWORD = ''
HEADERS = {'Content-Type': 'application/json'}
DEFAULT_OUTPUT_PATH = r'C:\Users\gpbuser\Documents\Confluence_export'
# ==================================

@dataclass
class ConfluencePage:
    id: str
    title: str
    url: str
    level: int = 0
    parent_id: Optional[str] = None
    children: List['ConfluencePage'] = None
    def __post_init__(self):
        if self.children is None:
            self.children = []

TRANSLIT_DICT = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
    'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'E',
    'Ж': 'Zh', 'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M',
    'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U',
    'Ф': 'F', 'Х': 'Kh', 'Ц': 'Ts', 'Ч': 'Ch', 'Ш': 'Sh', 'Щ': 'Shch',
    'Ъ': '', 'Ы': 'Y', 'Ь': '', 'Э': 'E', 'Ю': 'Yu', 'Я': 'Ya',
    ' ': '-', '/': '-', '\\': '-', ':': '-', '*': '-', '?': '-',
    '"': '-', '<': '-', '>': '-', '|': '-', '—': '-', '–': '-'
}

def transliterate(text):
    result = []
    for char in text:
        result.append(TRANSLIT_DICT.get(char, char))
    translit = ''.join(result)
    translit = re.sub(r'-+', '-', translit)
    translit = translit.strip('-')
    return translit.lower()

def safe_filename(title):
    t = transliterate(title)
    safe = re.sub(r'[^\w\s-]', '', t)
    safe = re.sub(r'[-\s]+', '-', safe).strip('-')
    if len(safe) > 80: safe = safe[:80]
    return f"{safe}.md"

class ConfluenceWorker(QThread):
    progress = Signal(str)
    error = Signal(str)
    finished = Signal(dict)
    file_downloaded = Signal(str, str)

    def __init__(self):
        super().__init__()
        self.page_url = ""
        self.space_key = ""
        self.tree_url = ""
        self.output_path = ""
        self.export_type = "single"
        self.log_file = None
        self.structure_mode = ""

    def run(self):
        log_path = Path(self.output_path) / 'export_log.txt'
        try:
            self.log_file = open(log_path, 'w', encoding='utf-8')
            self.log_file.write(f"=== Confluence Export Log ===\nStarted: {datetime.now()}\nOutput: {self.output_path}\n\n")
        except Exception as e:
            self.progress.emit(f"⚠️ Не удалось создать лог-файл: {e}")

        try:
            if self.export_type == "single":
                self._log("🔍 Получение информации о странице...")
                page_id = self.extract_page_id(self.page_url)
                if page_id: self.export_single_page(page_id)
                else: self._log("❌ Не удалось извлечь ID страницы из URL")
            elif self.export_type == "space":
                self._log(f"📚 Начинаем экспорт пространства {self.space_key}...")
                self.export_space(self.space_key)
            elif self.export_type == "tree":
                self._log("🌳 Начинаем экспорт дерева страниц...")
                self.export_tree(self.tree_url)
            elif self.export_type == "original_html":
                self._log("📄 Сохранение исходного HTML...")
                page_id = self.extract_page_id(self.page_url)
                if page_id: self.save_original_html(page_id)
                else: self._log("❌ Не удалось извлечь ID страницы из URL")
            elif self.export_type == "processed_html":
                self._log("📝 Сохранение обработанного HTML...")
                page_id = self.extract_page_id(self.page_url)
                if page_id: self.save_processed_html(page_id)
                else: self._log("❌ Не удалось извлечь ID страницы из URL")
            elif self.export_type == "structure":
                self._log("📋 Формирование структуры...")
                self.export_structure()
        except Exception as e:
            err = f"❌ Критическая ошибка: {str(e)}\n{traceback.format_exc()}"
            self._log(err)
            self.error.emit(err)
        finally:
            if self.log_file:
                self.log_file.close()
                self._log(f"Лог сохранён: {log_path}")

    def _log(self, message):
        self.progress.emit(message)
        if self.log_file:
            self.log_file.write(message + '\n')
            self.log_file.flush()

    def extract_page_id(self, url):
        patterns = [r'/pages/(\d+)', r'pageId=(\d+)', r'/(\d+)(?:\?|$)']
        for p in patterns:
            m = re.search(p, url)
            if m: return m.group(1)
        return None

    # ---------- Page map building ----------
    def build_page_map_for_tree(self, root_id):
        tree = self._build_tree_light(root_id)
        if not tree:
            self._log("❌ build_page_map_for_tree: не удалось построить лёгкое дерево")
            return None
        page_map = {}
        root_safe = safe_filename(tree['title']).replace('.md', '')
        root_rel = f"{root_safe}/index.md"
        page_map[str(tree['id'])] = {'title': tree['title'], 'relative_path': root_rel, 'is_folder': True}
        self._add_to_page_map(tree['children'], root_safe + '/', page_map)
        self._log(f"📋 Page map для дерева построен, страниц: {len(page_map)}")
        return page_map

    def _add_to_page_map(self, children, parent_rel_dir, page_map):
        for child in children:
            safe = safe_filename(child['title']).replace('.md', '')
            if child['children']:
                rel_dir = f"{parent_rel_dir}{safe}/"
                page_map[str(child['id'])] = {
                    'title': child['title'],
                    'relative_path': f"{rel_dir}index.md",
                    'is_folder': True
                }
                self._add_to_page_map(child['children'], rel_dir, page_map)
            else:
                rel_path = f"{parent_rel_dir}{safe}.md"
                page_map[str(child['id'])] = {
                    'title': child['title'],
                    'relative_path': rel_path,
                    'is_folder': False
                }

    def build_page_map_for_space(self, space_key):
        pages = self._fetch_space_pages(space_key)
        if pages is None:
            self._log("❌ build_page_map_for_space: не удалось получить страницы")
            return None
        page_map = {}
        for p in pages:
            fname = safe_filename(p['title'])
            page_map[str(p['id'])] = {
                'title': p['title'],
                'relative_path': fname,
                'is_folder': False
            }
        self._log(f"📋 Page map для пространства построен, страниц: {len(page_map)}")
        return page_map

    # ---------- Экспорт с page_map ----------
    def export_tree(self, root_url):
        root_id = self.extract_page_id(root_url)
        if not root_id: self.error.emit("Не удалось извлечь ID страницы"); return
        root_page = self.build_page_tree(root_id)
        if not root_page: self.error.emit("Не удалось построить дерево"); return
        pages_count = self.count_pages(root_page)
        self._log(f"📊 Найдено страниц: {pages_count}")
        page_map = self.build_page_map_for_tree(root_id)
        self._log(f"📋 Page map для экспорта дерева: {'None' if page_map is None else f'содержит {len(page_map)} записей'}")
        converter = ConfluenceToMarkdown(self.output_path, self._log, self.file_downloaded.emit, self.log_file, page_map=page_map)
        results = converter.convert_page_tree(root_page, Path(self.output_path))
        successful = sum(1 for r in results if 'error' not in r)
        total_files = sum(r.get('files_count',0) for r in results if 'error' not in r)
        self.finished.emit({'type':'tree','root_title':root_page.title,
                            'pages_count':pages_count,'successful':successful,'total_files':total_files,'results':results})

    def export_space(self, space_key):
        page_map = self.build_page_map_for_space(space_key)
        self._log(f"📋 Page map для экспорта пространства: {'None' if page_map is None else f'содержит {len(page_map)} записей'}")
        converter = ConfluenceToMarkdown(self.output_path, self._log, self.file_downloaded.emit, self.log_file, page_map=page_map)
        results = converter.convert_space(space_key)
        self.finished.emit({'type':'space','space_key':space_key,
                            'pages_count':len(results),'results':results})

    def export_single_page(self, page_id):
        converter = ConfluenceToMarkdown(self.output_path, self._log, self.file_downloaded.emit, self.log_file)
        result = converter.convert_page(page_id, section_name='pages')
        self.finished.emit({'type':'page','title':result['title'],
                            'md_file':str(result['md_file']),
                            'assets_dir':str(result['assets_dir']),
                            'files_count':result['files_count']})

    def build_page_tree(self, root_id, visited=None, level=0):
        if visited is None: visited = set()
        if root_id in visited: return None
        visited.add(root_id)
        converter = ConfluenceToMarkdown(self.output_path, self._log, self.file_downloaded.emit, self.log_file)
        pd = converter.get_page_content(root_id)
        if not pd: return None
        page = ConfluencePage(id=root_id, title=pd['title'],
                              url=f"{CONFLUENCE_URL}/pages/viewpage.action?pageId={root_id}", level=level)
        for child in converter.get_child_pages(root_id):
            cp = self.build_page_tree(child['id'], visited, level+1)
            if cp: page.children.append(cp)
        return page

    def count_pages(self, page):
        return 1 + sum(self.count_pages(c) for c in page.children)

    # ---------- HTML saving (unchanged) ----------
    def _get_raw_html(self, page_id):
        url = f'{CONFLUENCE_URL}/rest/api/content/{page_id}?expand=body.storage,version,space'
        try:
            r = requests.get(url, auth=HTTPBasicAuth(JIRA_USERNAME, JIRA_PASSWORD), headers=HEADERS, timeout=30)
            r.raise_for_status()
            data = r.json()
            return data.get('body', {}).get('storage', {}).get('value', ''), data.get('title', '')
        except Exception as e:
            self._log(f"❌ Ошибка получения страницы: {e}")
            return None, None

    def save_original_html(self, page_id):
        html, title = self._get_raw_html(page_id)
        if not html: self.error.emit("Не удалось получить HTML страницы"); return
        safe_name = safe_filename(title).replace('.md', '')
        filepath = Path(self.output_path) / f"{safe_name}_original.html"
        try:
            filepath.write_text(html, encoding='utf-8')
            self._log(f"✅ Исходный HTML сохранён: {filepath}")
            self.finished.emit({'type':'html_original', 'title':title, 'file_path':str(filepath)})
        except Exception as e:
            self._log(f"❌ Ошибка сохранения исходного HTML: {e}")

    def save_processed_html(self, page_id):
        html, title = self._get_raw_html(page_id)
        if not html: self.error.emit("Не удалось получить HTML страницы"); return
        processed = self._process_html_for_preview(html, title)
        safe_name = safe_filename(title).replace('.md', '')
        filepath = Path(self.output_path) / f"{safe_name}_processed.html"
        try:
            filepath.write_text(processed, encoding='utf-8')
            self._log(f"✅ Обработанный HTML сохранён: {filepath}")
            self.finished.emit({'type':'html_processed', 'title':title, 'file_path':str(filepath)})
        except Exception as e:
            self._log(f"❌ Ошибка сохранения обработанного HTML: {e}")

    def _process_html_for_preview(self, html, page_title):
        soup = BeautifulSoup(html, 'html.parser')
        for pm in soup.find_all('ac:structured-macro', {'ac:name':['plantuml','uml']}):
            body = pm.find('ac:plain-text-body') or pm.find('ac:rich-text-body')
            if body:
                content = body.get_text().strip()
                title_tag = pm.find('ac:parameter', {'ac:name':'title'})
                title = title_tag.get_text(strip=True) if title_tag else 'PlantUML'
                pm.replace_with(BeautifulSoup(f'<div><strong>{title}</strong><pre>{content[:200]}</pre></div>', 'html.parser'))
        for cm in soup.find_all('ac:structured-macro', {'ac:name':['code','code-block','noformat']}):
            body = cm.find('ac:plain-text-body') or cm.find('ac:rich-text-body')
            if body:
                code = body.get_text().strip()
                cm.replace_with(BeautifulSoup(f'<pre>{code[:200]}</pre>', 'html.parser'))
        for vf in soup.find_all('ac:structured-macro', {'ac:name':'view-file'}):
            ra = vf.find('ri:attachment')
            fname = ra.get('ri:filename','') if ra else 'file'
            vf.replace_with(BeautifulSoup(f'<span>📎 {fname}</span>', 'html.parser'))
        for img in soup.find_all('ac:image'):
            ra = img.find('ri:attachment')
            fname = ra.get('ri:filename','') if ra else 'image'
            alt_tag = img.find('ac:alt')
            alt = alt_tag.get_text(strip=True) if alt_tag else fname
            img.replace_with(BeautifulSoup(f'<span>🖼️ {alt}</span>', 'html.parser'))
        for macro in soup.find_all('ac:structured-macro'):
            if macro.get('ac:name','').lower() in ('jira','jiraissue'):
                issue_key = None
                for param in macro.find_all('ac:parameter'):
                    if param.get('ac:name','').lower() in ('jiraissue','issuekey','key'):
                        issue_key = param.get_text(strip=True)
                        break
                if not issue_key:
                    m = re.search(r'([A-Z]+-\d+)', macro.get_text())
                    if m: issue_key = m.group(1)
                if issue_key:
                    a_tag = soup.new_tag('a', href=f'{CONFLUENCE_URL}/browse/{issue_key}')
                    a_tag.string = issue_key
                    macro.replace_with(a_tag)
        return str(soup)

    # ---------- Structure (TOC) ----------
    def export_structure(self):
        if self.structure_mode == "tree":
            root_id = self.extract_page_id(self.tree_url)
            if not root_id:
                self.error.emit("Не удалось извлечь ID корневой страницы"); return
            self._log("🌳 Построение дерева для структуры...")
            tree = self._build_tree_light(root_id)
            if not tree:
                self.error.emit("Не удалось построить дерево страниц"); return
            md_content = self._generate_tree_markdown(tree)
            safe_root = safe_filename(tree['title']).replace('.md', '')
            filepath = Path(self.output_path) / f"structure_{safe_root}.md"
        elif self.structure_mode == "space":
            pages = self._fetch_space_pages(self.space_key)
            if pages is None:
                self.error.emit("Не удалось получить список страниц пространства"); return
            md_content = self._generate_space_markdown(self.space_key, pages)
            filepath = Path(self.output_path) / f"structure_{self.space_key}.md"
        else:
            self.error.emit("Неизвестный режим структуры"); return

        try:
            filepath.write_text(md_content, encoding='utf-8')
            self._log(f"✅ Структура сохранена: {filepath}")
            self.finished.emit({'type': 'structure', 'title': self.structure_mode, 'file_path': str(filepath)})
        except Exception as e:
            self._log(f"❌ Ошибка сохранения структуры: {e}")
            self.error.emit(str(e))

    def _api_get(self, url):
        try:
            r = requests.get(url, auth=HTTPBasicAuth(JIRA_USERNAME, JIRA_PASSWORD), headers=HEADERS, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            self._log(f"❌ API error: {e}")
            return None

    def _fetch_page_title(self, page_id):
        url = f'{CONFLUENCE_URL}/rest/api/content/{page_id}?expand=body.storage'
        data = self._api_get(url)
        if data:
            return data.get('title', f'Page-{page_id}')
        return None

    def _fetch_child_pages(self, page_id):
        children = []
        start = 0
        limit = 100
        while True:
            url = f'{CONFLUENCE_URL}/rest/api/content/{page_id}/child/page?expand=version&limit={limit}&start={start}'
            data = self._api_get(url)
            if not data: break
            results = data.get('results', [])
            for item in results:
                children.append({'id': str(item['id']), 'title': item['title']})
            if len(results) < limit: break
            start += limit
        return children

    def _build_tree_light(self, page_id, visited=None):
        if visited is None: visited = set()
        if page_id in visited: return None
        visited.add(page_id)
        title = self._fetch_page_title(page_id)
        if not title: return None
        node = {'id': page_id, 'title': title, 'children': []}
        for child in self._fetch_child_pages(page_id):
            child_node = self._build_tree_light(child['id'], visited)
            if child_node:
                node['children'].append(child_node)
        return node

    def _fetch_space_pages(self, space_key, limit=100):
        pages = []
        start = 0
        while True:
            url = f'{CONFLUENCE_URL}/rest/api/content?spaceKey={space_key}&expand=version&limit={limit}&start={start}&status=current'
            data = self._api_get(url)
            if not data: break
            results = data.get('results', [])
            for item in results:
                pages.append({'id': str(item['id']), 'title': item['title']})
            if len(results) < limit: break
            start += limit
        return pages

    def _generate_tree_markdown(self, node):
        lines = []
        root_safe = safe_filename(node['title']).replace('.md', '')
        lines.append(f'# Структура раздела: "{node["title"]}"\n')
        lines.append(f'## Папка: `{root_safe}/` (ID: {node["id"]})\n')
        lines.append(f'  - 📄 `index.md` (ID: {node["id"]}) — {node["title"]}')
        for child in node['children']:
            self._append_node_markdown(lines, child, depth=1)
        return '\n'.join(lines)

    def _append_node_markdown(self, lines, node, depth):
        prefix = '  ' * depth
        safe_name = safe_filename(node['title']).replace('.md', '')
        if node['children']:
            folder_name = safe_name
            lines.append(f'{prefix}- 📂 Подраздел: `{folder_name}/` (ID: {node["id"]})')
            lines.append(f'{prefix}  - 📄 `index.md` (ID: {node["id"]}) — {node["title"]}')
            for child in node['children']:
                self._append_node_markdown(lines, child, depth + 1)
        else:
            lines.append(f'{prefix}- 📄 `{safe_name}.md` (ID: {node["id"]}) — {node["title"]}')

    def _generate_space_markdown(self, space_key, pages):
        lines = [f'# Структура пространства: "{space_key}"\n']
        lines.append('## Файлы (будут сохранены в корень папки сохранения):\n')
        for p in pages:
            fname = safe_filename(p['title'])
            lines.append(f'- 📄 `{fname}` (ID: {p["id"]}) — {p["title"]}')
        return '\n'.join(lines)


class ConfluenceToMarkdown:
    def __init__(self, output_path, progress_callback=None, file_callback=None, log_file=None, page_map=None):
        self.output_path = Path(output_path)
        self.progress_callback = progress_callback or (lambda x: None)
        self.file_callback = file_callback or (lambda x,y: None)
        self.log_file = log_file
        self.page_map = page_map
        self.current_md_path = None

        self.confluence_url = CONFLUENCE_URL
        self.auth = HTTPBasicAuth(JIRA_USERNAME, JIRA_PASSWORD)
        self.session = requests.Session()
        self.session.auth = self.auth
        self.session.headers.update(HEADERS)

        self.html_converter = html2text.HTML2Text()
        self.html_converter.body_width = 0
        self.html_converter.ignore_links = False
        self.html_converter.ignore_images = False
        self.html_converter.images_to_alt = False
        self.html_converter.unicode_snob = True
        self.html_converter.mark_code = True
        self.html_converter.protect_links = True
        self.html_converter.use_automatic_links = False
        self.html_converter.default_image_alt = 'image'
        self.html_converter.bypass_tables = True

        self.stats = {'total_attachments':0,'downloaded_attachments':0,
                      'failed_attachments':0,'processed_images':0,'processed_links':0}

    def log(self, message, level="INFO"):
        self.progress_callback(message)
        if self.log_file:
            self.log_file.write(f"[{level}] {message}\n")
            self.log_file.flush()

    def log_debug(self, msg): self.log(msg, "DEBUG")

    def transliterate_filename(self, filename):
        name, ext = os.path.splitext(filename)
        t = transliterate(name) or re.sub(r'[^\w\s-]', '', name)
        return f"{t}{ext}".lower()

    def safe_filename(self, title):
        return safe_filename(title)

    def authorized_request(self, method, url, params=None, json_data=None, timeout=30):
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if method == 'GET':
                    r = self.session.get(url, params=params, timeout=timeout)
                elif method == 'POST':
                    r = self.session.post(url, json=json_data, timeout=timeout)
                elif method == 'PUT':
                    r = self.session.put(url, json=json_data, timeout=timeout)
                elif method == 'DELETE':
                    r = self.session.delete(url, json=json_data, timeout=timeout)
                else:
                    return None
                if r.status_code == 401:
                    self.log("❌ Ошибка авторизации!", "ERROR")
                    return None
                r.raise_for_status()
                return r
            except requests.exceptions.Timeout as e:
                self.log(f"⏳ Таймаут запроса (попытка {attempt+1}/{max_retries}): {e}", "WARNING")
                if attempt < max_retries - 1:
                    time.sleep(2 * (attempt + 1))
                else:
                    self.log(f"❌ Исчерпаны попытки запроса: {e}", "ERROR")
                    return None
            except requests.exceptions.ConnectionError as e:
                self.log(f"🔌 Ошибка соединения (попытка {attempt+1}/{max_retries}): {e}", "WARNING")
                if attempt < max_retries - 1:
                    time.sleep(2 * (attempt + 1))
                else:
                    self.log(f"❌ Исчерпаны попытки соединения: {e}", "ERROR")
                    return None
            except Exception as e:
                self.log(f"❌ Ошибка запроса: {e}", "ERROR")
                return None

    def get_page_content(self, page_id):
        url = f'{self.confluence_url}/rest/api/content/{page_id}?expand=body.storage,version,space'
        r = self.authorized_request('GET', url)
        if not r: return None
        d = r.json()
        return {'id':page_id, 'title':d.get('title',f'Page-{page_id}'),
                'html':d.get('body',{}).get('storage',{}).get('value','')}

    def get_child_pages(self, page_id):
        url = f'{self.confluence_url}/rest/api/content/{page_id}/child/page'
        params = {'expand':'version','limit':100}
        children = []; start = 0
        while True:
            params['start'] = start
            r = self.authorized_request('GET', url, params=params)
            if not r: break
            data = r.json(); results = data.get('results',[])
            children.extend(results)
            if len(results) < params['limit']: break
            start += params['limit']
        return children

    def get_attachments(self, page_id):
        url = f'{self.confluence_url}/rest/api/content/{page_id}/child/attachment'
        params = {'expand':'version','limit':100}
        attachments = []; start = 0
        while True:
            params['start'] = start
            r = self.authorized_request('GET', url, params=params)
            if not r: break
            data = r.json(); results = data.get('results',[])
            attachments.extend(results)
            if len(results) < params['limit']: break
            start += params['limit']
        self.stats['total_attachments'] = len(attachments)
        return attachments

    def download_attachment(self, attachment, download_path):
        try:
            url = self.confluence_url + attachment['_links']['download']
            r = self.session.get(url, stream=True, timeout=30); r.raise_for_status()
            original = self.extract_filename(r, url, attachment)
            filename = self.transliterate_filename(original)
            filepath = download_path / filename
            with open(filepath, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk: f.write(chunk)
            self.stats['downloaded_attachments'] += 1
            self.file_callback(filename, "downloaded")
            return filename, filepath, original
        except Exception:
            self.stats['failed_attachments'] += 1
            return None, None, None

    def extract_filename(self, response, download_url, attachment):
        cd = response.headers.get('content-disposition')
        if cd:
            m = re.search(r'filename="(.+)"', cd) or re.search(r"filename=(.+)", cd)
            if m: return m.group(1).strip('"\'')
        if 'title' in attachment: return attachment['title']
        if download_url:
            fn = unquote(urlparse(download_url).path.split('/')[-1])
            if fn and fn != 'download': return fn
        return f"attachment-{attachment['id']}"

    # ---------- Page link helpers ----------
    def _find_page_by_title(self, title):
        if not self.page_map or not title:
            return None
        normalized_title = title.strip().lower()
        for page_id_str, info in self.page_map.items():
            if info.get('title', '').strip().lower() == normalized_title:
                return page_id_str
        return None

    def _resolve_page_link(self, page_id):
        if not self.page_map or page_id not in self.page_map:
            return f"{self.confluence_url}/pages/viewpage.action?pageId={page_id}"
        target = self.page_map[page_id]
        target_rel = target['relative_path']
        if self.current_md_path:
            current_dir = self.current_md_path.parent
            target_abs = Path(self.output_path) / target_rel
            try:
                rel = os.path.relpath(target_abs, current_dir).replace('\\', '/')
                return rel
            except ValueError:
                return target_rel.replace('\\', '/')
        else:
            return target_rel.replace('\\', '/')

    # ---------- Table handling ----------
    def expand_table_cells(self, soup):
        for table in soup.find_all('table'):
            rows = table.find_all('tr')
            if not rows: continue
            grid = []
            max_cols = 0
            for row_idx, tr in enumerate(rows):
                grid.append([])
                col_idx = 0
                for cell in tr.find_all(['td','th']):
                    while col_idx < len(grid[row_idx]) and grid[row_idx][col_idx] is not None:
                        col_idx += 1
                    colspan = int(cell.get('colspan',1))
                    rowspan = int(cell.get('rowspan',1))
                    for r in range(row_idx, row_idx+rowspan):
                        while len(grid) <= r: grid.append([])
                        while len(grid[r]) < col_idx+colspan: grid[r].append(None)
                        for c in range(col_idx, col_idx+colspan):
                            if r == row_idx and c == col_idx:
                                grid[r][c] = {'cell':cell, 'rowspan':rowspan, 'colspan':colspan}
                            else:
                                grid[r][c] = None
                    col_idx += colspan
            max_cols = max(len(row) for row in grid) if grid else 0
            new_table = soup.new_tag('table')
            for r in range(len(grid)):
                if all(cell is None or (cell['cell'] and not cell['cell'].get_text(strip=True)) for cell in grid[r]):
                    continue
                new_tr = soup.new_tag('tr')
                for c in range(max_cols):
                    cell_info = grid[r][c] if c < len(grid[r]) else None
                    new_td = soup.new_tag('td')
                    if cell_info and cell_info['cell']:
                        for content in cell_info['cell'].contents:
                            new_td.append(content)
                    else:
                        new_td.append(' ')
                    new_tr.append(new_td)
                new_table.append(new_tr)
            table.replace_with(new_table)

    def _render_cell_to_inline_md(self, element):
        if isinstance(element, NavigableString):
            return element.get_text().replace('\n', ' ').replace('\r', ' ')
        if element.name in ('strong', 'b'):
            return '**' + ''.join(self._render_cell_to_inline_md(c) for c in element.children) + '**'
        if element.name in ('em', 'i'):
            return '*' + ''.join(self._render_cell_to_inline_md(c) for c in element.children) + '*'
        if element.name == 'a':
            href = element.get('href', '')
            text = ''.join(self._render_cell_to_inline_md(c) for c in element.children)
            return f'[{text}]({href})'
        if element.name == 'img':
            alt = element.get('alt', '')
            src = element.get('src', '')
            return f'![{alt}]({src})'
        if element.name in ('ul', 'ol'):
            items = []
            for li in element.find_all('li', recursive=False):
                item_text = ''.join(self._render_cell_to_inline_md(c) for c in li.children).strip()
                items.append(item_text)
            if element.name == 'ol':
                return '; '.join(f'{i+1}. {t}' for i, t in enumerate(items))
            else:
                return '; '.join(f'• {t}' for t in items)
        if element.name == 'br':
            return ' '
        return ''.join(self._render_cell_to_inline_md(c) for c in element.children)

    def convert_table_to_markdown(self, table):
        rows = table.find_all('tr')
        if not rows:
            return ''
        max_cols = max(len(row.find_all(['td','th'])) for row in rows)
        md_rows = []
        for row in rows:
            cells = row.find_all(['td','th'])
            md_cells = []
            for cell in cells:
                cell_md = self._render_cell_to_inline_md(cell).strip()
                cell_md = cell_md.replace('|', '\\|')
                md_cells.append(cell_md)
            while len(md_cells) < max_cols:
                md_cells.append(' ')
            md_rows.append('| ' + ' | '.join(md_cells) + ' |')
        if md_rows:
            delimiter = '|' + '|'.join([' --- '] * max_cols) + '|'
            md_rows.insert(1, delimiter)
        return '\n'.join(md_rows) + '\n'

    def _process_tables_in_soup(self, soup):
        table_md_list = []
        for idx, table in enumerate(soup.find_all('table')):
            md_table = self.convert_table_to_markdown(table)
            table_md_list.append(md_table)
            marker = soup.new_tag('p')
            marker.string = f'%%TABLE_{idx}%%'
            table.replace_with(marker)
        return table_md_list

    def _insert_tables_into_markdown(self, text, table_md_list):
        for idx, md_table in enumerate(table_md_list):
            marker = f'%%TABLE_{idx}%%'
            text = text.replace(marker, md_table)
        return text

    # ---------- Macros & content processing ----------
    def simplify_jira_macros(self, soup):
        for macro in soup.find_all('ac:structured-macro'):
            if macro.get('ac:name','').lower() in ('jira','jiraissue'):
                issue_key = None
                for param in macro.find_all('ac:parameter'):
                    if param.get('ac:name','').lower() in ('jiraissue','issuekey','key'):
                        issue_key = param.get_text(strip=True)
                        break
                if not issue_key:
                    m = re.search(r'([A-Z]+-\d+)', macro.get_text())
                    if m: issue_key = m.group(1)
                if issue_key:
                    href = f"{self.confluence_url}/browse/{issue_key}"
                    a_tag = soup.new_tag('a', href=href)
                    a_tag.string = issue_key
                    macro.replace_with(a_tag)

    def simplify_jira_links(self, soup):
        for a in soup.find_all('a', href=True):
            href = a['href']; text = a.get_text()
            m = re.search(r'([A-Z][A-Z]+-\d+)', href) or re.search(r'([A-Z][A-Z]+-\d+)', text)
            if m:
                key = m.group(1)
                new_a = soup.new_tag('a', href=href)
                new_a.string = key
                a.replace_with(new_a)

    def clean_empty_emphasis(self, soup):
        for tag in soup.find_all(['strong','em','b','i']):
            if not tag.get_text(strip=True):
                tag.unwrap()

    def _replace_plain_confluence_links(self, soup):
        """Заменяет обычные HTML-ссылки на относительные MD-ссылки, если целевая страница есть в page_map."""
        if not self.page_map:
            return
        self.log_debug("🔍 Ищем обычные HTML-ссылки на Confluence...")
        for a in soup.find_all('a', href=True):
            href = a['href']
            # Пропускаем уже относительные ссылки или внешние URL не с нашего confluence
            if not href.startswith(('http://', 'https://')):
                continue
            if not href.startswith(self.confluence_url):
                continue

            page_id = None
            # Извлекаем pageId из URL
            m = re.search(r'pageId=(\d+)', href)
            if m:
                page_id = m.group(1)
            else:
                # Может быть ссылка вида /display/SPACEKEY/Title
                m = re.search(r'/display/([^/]+)/', href)
                if m:
                    # В этом случае page_id не извлечь, попробуем через текст
                    pass

            resolved_id = None
            if page_id and page_id in self.page_map:
                resolved_id = page_id
            else:
                # Пытаемся найти по названию страницы (текст ссылки)
                text = a.get_text().strip()
                if text:
                    resolved_id = self._find_page_by_title(text)

            if resolved_id:
                new_url = self._resolve_page_link(resolved_id)
                a['href'] = new_url
                self.log_debug(f"  Обычная ссылка заменена на относительную: [{a.get_text()}]({new_url})")

    def process_attachments_in_content(self, html_content, page_title, attachments):
        if not self.current_md_path:
            raise Exception("current_md_path не установлен")
        assets_dir_name = f"{self.current_md_path.stem}_files"
        assets_article_path = self.current_md_path.parent / assets_dir_name
        assets_dir_created = False

        def ensure_assets_dir():
            nonlocal assets_dir_created
            if not assets_dir_created:
                assets_article_path.mkdir(parents=True, exist_ok=True)
                assets_dir_created = True
                self.log_debug(f"📁 Создана папка для вложений: {assets_article_path}")

        processed_files = set()
        soup = BeautifulSoup(html_content, 'html.parser')

        # PlantUML
        for pm in soup.find_all('ac:structured-macro', {'ac:name':['plantuml','uml']}):
            try:
                body = pm.find('ac:plain-text-body') or pm.find('ac:rich-text-body')
                if body:
                    content = body.get_text().strip()
                    title_tag = pm.find('ac:parameter', {'ac:name':'title'})
                    title = title_tag.get_text(strip=True) if title_tag else 'PlantUML диаграмма'
                    fname = f"diagram-{len(processed_files)+1}.puml"
                    ensure_assets_dir()
                    (assets_article_path/fname).write_text(content, encoding='utf-8')
                    processed_files.add(fname)
                    md = f'**{title}**\n\n[📊 Исходный код PlantUML](./{assets_dir_name}/{fname})\n\n```plantuml\n{chr(10).join(content.splitlines()[:10])}\n```\n'
                    pm.replace_with(BeautifulSoup(md, 'html.parser'))
            except Exception as e: self.log_debug(f"PlantUML error: {e}")

        # Code blocks
        for cm in soup.find_all('ac:structured-macro', {'ac:name':['code','code-block','noformat']}):
            try:
                lang_tag = cm.find('ac:parameter', {'ac:name':'language'})
                lang = lang_tag.get_text(strip=True) if lang_tag else 'text'
                if cm.get('ac:name') == 'noformat': lang = 'text'
                title_tag = cm.find('ac:parameter', {'ac:name':'title'})
                title = title_tag.get_text(strip=True) if title_tag else ''
                body = cm.find('ac:plain-text-body') or cm.find('ac:rich-text-body')
                if body:
                    code = body.get_text().strip()
                    md = f'```{lang}\n{code}\n```\n'
                    if title: md = f'**{title}**\n\n{md}'
                    cm.replace_with(BeautifulSoup(md, 'html.parser'))
            except Exception as e: self.log_debug(f"Code block error: {e}")

        # view-file
        for vf in soup.find_all('ac:structured-macro', {'ac:name':'view-file'}):
            ra = vf.find('ri:attachment')
            if ra:
                fname = ra.get('ri:filename','')
                att = next((a for a in attachments if a.get('title')==fname), None)
                if att:
                    ensure_assets_dir()
                    fname, _, _ = self.download_attachment(att, assets_article_path)
                    if fname:
                        processed_files.add(fname)
                        icon = self.get_file_icon(os.path.splitext(fname)[1].lower())
                        vf.replace_with(BeautifulSoup(f'[{icon} {fname}](./{assets_dir_name}/{fname})', 'html.parser'))

        # Images
        for img in soup.find_all('ac:image'):
            ra = img.find('ri:attachment')
            if ra:
                fname = ra.get('ri:filename','')
                att = next((a for a in attachments if a.get('title')==fname), None)
                if att:
                    ensure_assets_dir()
                    fname, _, _ = self.download_attachment(att, assets_article_path)
                    if fname:
                        processed_files.add(fname)
                        alt_tag = img.find('ac:alt')
                        alt = alt_tag.get_text(strip=True) if alt_tag else ''
                        img.replace_with(BeautifulSoup(f'![{alt}](./{assets_dir_name}/{fname})', 'html.parser'))
                        self.stats['processed_images'] += 1

        # Links (internal & external)
        self.log_debug("🔗 Начинаем обработку ac:link...")
        for alink in soup.find_all('ac:link'):
            ra = alink.find('ri:attachment')
            if ra:
                fname = ra.get('ri:filename','')
                att = next((a for a in attachments if a.get('title')==fname), None)
                if att:
                    ensure_assets_dir()
                    fname, _, oname = self.download_attachment(att, assets_article_path)
                    if fname:
                        processed_files.add(fname)
                        icon = self.get_file_icon(os.path.splitext(fname)[1].lower())
                        text_tag = alink.find('ac:plain-text-link-body')
                        text = text_tag.get_text(strip=True) if text_tag else (oname or fname)
                        alink.replace_with(BeautifulSoup(f'[{icon} {text}](./{assets_dir_name}/{fname})', 'html.parser'))
                        self.stats['processed_links'] += 1
                continue

            rp = alink.find('ri:page')
            if rp:
                page_id = rp.get('ri:content-entity-id','')
                page_title_link = rp.get('ri:content-title','')
                space_key = rp.get('ri:space-key','')
                text_tag = alink.find('ac:plain-text-link-body')
                link_text = text_tag.get_text(strip=True) if text_tag else (page_title_link or 'Страница')

                self.log_debug(f"  Найдена ссылка на страницу: page_id='{page_id}', title='{page_title_link}', link_text='{link_text}'")

                url = None
                resolved_page_id = None

                # 1. Try by page_id
                if self.page_map and page_id:
                    page_id_str = str(page_id)
                    if page_id_str in self.page_map:
                        resolved_page_id = page_id_str
                        self.log_debug(f"  Найден по page_id: {resolved_page_id}")
                    else:
                        self.log_debug(f"  page_id '{page_id_str}' не найден в page_map")

                # 2. Try by title
                if not resolved_page_id and self.page_map and page_title_link:
                    self.log_debug(f"  Пытаемся найти по названию: '{page_title_link}'")
                    found_id = self._find_page_by_title(page_title_link)
                    if found_id:
                        resolved_page_id = found_id
                        self.log_debug(f"  Найден по названию: {resolved_page_id} ({self.page_map[resolved_page_id]['title']})")
                    else:
                        self.log_debug(f"  По названию '{page_title_link}' ничего не найдено")

                if resolved_page_id:
                    url = self._resolve_page_link(resolved_page_id)
                else:
                    if page_id:
                        url = f"{self.confluence_url}/pages/viewpage.action?pageId={page_id}"
                    elif page_title_link and space_key:
                        url = f"{self.confluence_url}/display/{space_key}/{page_title_link.replace(' ','+')}"
                    self.log_debug(f"  Используем абсолютную ссылку: {url}")

                if url:
                    alink.replace_with(BeautifulSoup(f'[{link_text}]({url})', 'html.parser'))
                else:
                    alink.replace_with(BeautifulSoup(link_text, 'html.parser'))
                self.stats['processed_links'] += 1
                continue

            ru = alink.find('ri:url')
            if ru:
                url = ru.get('ri:value','')
                if url:
                    text_tag = alink.find('ac:plain-text-link-body')
                    text = text_tag.get_text(strip=True) if text_tag else url
                    alink.replace_with(BeautifulSoup(f'[{text}]({url})', 'html.parser'))
                    self.stats['processed_links'] += 1
                continue

        # Замена обычных HTML-ссылок Confluence на относительные
        self._replace_plain_confluence_links(soup)

        self.simplify_jira_macros(soup)
        self.simplify_jira_links(soup)
        self.clean_empty_emphasis(soup)
        return str(soup), assets_article_path if assets_dir_created else None, len(processed_files)

    def get_file_icon(self, ext):
        icons = {
            '.pdf':'📄','.doc':'📝','.docx':'📝','.xls':'📊','.xlsx':'📊',
            '.ppt':'📽️','.pptx':'📽️','.txt':'📃','.xml':'🔧','.sql':'🗄️',
            '.json':'📋','.py':'🐍','.js':'📜','.html':'🌐','.css':'🎨',
            '.zip':'📦','.rar':'📦','.7z':'📦','.jpg':'🖼️','.jpeg':'🖼️',
            '.png':'🖼️','.gif':'🖼️','.svg':'🖼️','.mp4':'🎬','.mp3':'🎵',
            '.exe':'⚙️','.dll':'🔧'
        }
        return icons.get(ext, '📎')

    # ========== TREE EXPORT (fixed duplicate root folder) ==========
    def convert_page_tree(self, root_page, base_path):
        results = []
        root_safe = self.safe_filename(root_page.title).replace('.md', '')

        def process_page(page, current_dir, is_root=False):
            pd = self.get_page_content(page.id)
            if not pd:
                return
            safe_name = self.safe_filename(pd['title']).replace('.md', '')
            has_children = len(page.children) > 0

            if is_root and has_children:
                # Root section: create folder inside base_path
                folder_path = base_path / root_safe
                folder_path.mkdir(parents=True, exist_ok=True)
                md_path = folder_path / 'index.md'
                next_dir = folder_path
            elif is_root and not has_children:
                # Root page without children (rare): just .md in base_path
                md_path = base_path / f"{safe_name}.md"
                next_dir = base_path
            elif has_children:
                # Child section: subfolder inside current_dir
                folder_path = current_dir / safe_name
                folder_path.mkdir(parents=True, exist_ok=True)
                md_path = folder_path / 'index.md'
                next_dir = folder_path
            else:
                # Regular page: .md file in current_dir
                md_path = current_dir / f"{safe_name}.md"
                next_dir = current_dir

            # Ensure unique filename
            c = 1
            orig_path = md_path
            while md_path.exists():
                stem = orig_path.stem
                suffix = orig_path.suffix
                md_path = orig_path.parent / f"{stem}-{c}{suffix}"
                c += 1

            self.current_md_path = md_path
            atts = self.get_attachments(page.id)
            html, assets_dir, files = self.process_attachments_in_content(pd['html'], pd['title'], atts)
            soup = BeautifulSoup(html, 'html.parser')
            self.expand_table_cells(soup)
            table_md_list = self._process_tables_in_soup(soup)
            body_md = self.html_converter.handle(str(soup))
            body_md = self._insert_tables_into_markdown(body_md, table_md_list)
            full_md = f"# {pd['title']}\n\n{body_md}"
            md_path.write_text(full_md, encoding='utf-8')
            results.append({
                'title': pd['title'],
                'md_file': md_path,
                'files_count': files,
                'level': page.level
            })

            if has_children:
                for child in page.children:
                    process_page(child, next_dir)

        process_page(root_page, base_path, is_root=True)
        return results

    # ========== SINGLE PAGE EXPORT ==========
    def convert_page(self, page_id, target_path=None, section_name=None):
        self.stats = {k:0 for k in self.stats}
        pd = self.get_page_content(page_id)
        if not pd: raise Exception(f"Не удалось получить страницу {page_id}")
        atts = self.get_attachments(page_id)
        save_path = Path(target_path) if target_path else self.output_path
        save_path.mkdir(parents=True, exist_ok=True)
        fname = self.safe_filename(pd['title'])
        md_path = save_path / fname
        c = 1; orig = fname
        while md_path.exists():
            n, e = os.path.splitext(orig)
            md_path = save_path / f"{n}-{c}{e}"
            c += 1
        self.current_md_path = md_path
        html, assets_dir, files = self.process_attachments_in_content(pd['html'], pd['title'], atts)
        soup = BeautifulSoup(html, 'html.parser')
        self.expand_table_cells(soup)
        table_md_list = self._process_tables_in_soup(soup)
        body_md = self.html_converter.handle(str(soup))
        body_md = self._insert_tables_into_markdown(body_md, table_md_list)
        full = f"# {pd['title']}\n\n{body_md}"
        md_path.write_text(full, encoding='utf-8')
        self.log(f"✅ Сохранено: {fname}")
        return {'title':pd['title'],'md_file':md_path,'assets_dir':assets_dir,'files_count':files}

    # ========== SPACE EXPORT ==========
    def convert_space(self, space_key, limit=50):
        url = f"{self.confluence_url}/rest/api/content"
        params = {'spaceKey':space_key,'expand':'version','limit':limit,'status':'current'}
        r = self.authorized_request('GET', url, params=params)
        if not r: raise Exception("Не удалось получить список страниц")
        pages = r.json().get('results',[])
        self.log(f"📄 Найдено страниц: {len(pages)}")
        results = []
        for i,p in enumerate(pages,1):
            try:
                self.log(f"[{i}/{len(pages)}] 📄 {p['title']}")
                results.append(self.convert_page(p['id'], section_name=space_key.lower()))
            except Exception as e:
                self.log(f"❌ Ошибка: {e}")
                results.append({'title':p['title'],'error':str(e)})
        return results


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.worker = None

    def init_ui(self):
        self.setWindowTitle("Confluence to Markdown Converter")
        self.setMinimumSize(1000, 800)
        layout = QVBoxLayout()

        title = QLabel("📥 Confluence → Markdown")
        title.setStyleSheet("font-size: 24px; font-weight: bold; padding: 10px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        conn = QLabel(f"✅ Подключение: {CONFLUENCE_URL}")
        conn.setStyleSheet("color: green; padding: 5px;")
        conn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(conn)

        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("📁 Папка для сохранения:"))
        self.path_edit = QLineEdit(DEFAULT_OUTPUT_PATH)
        path_layout.addWidget(self.path_edit)
        browse_btn = QPushButton("Обзор...")
        browse_btn.clicked.connect(self.browse_path)
        path_layout.addWidget(browse_btn)
        layout.addLayout(path_layout)

        type_group = QGroupBox("Тип экспорта")
        type_layout = QVBoxLayout()
        self.single_radio = QRadioButton("📄 Одна страница")
        self.single_radio.setChecked(True)
        type_layout.addWidget(self.single_radio)
        self.tree_radio = QRadioButton("🌳 Дерево страниц (раздел)")
        type_layout.addWidget(self.tree_radio)
        self.space_radio = QRadioButton("📚 Все пространство")
        type_layout.addWidget(self.space_radio)
        type_group.setLayout(type_layout)
        layout.addWidget(type_group)

        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://confluence.gboteam.ru/pages/viewpage.action?pageId=...")
        layout.addWidget(QLabel("🔗 URL страницы / Корень дерева:"))
        layout.addWidget(self.url_edit)

        self.space_edit = QLineEdit()
        self.space_edit.setPlaceholderText("например: GBOTEST")
        self.space_edit.setEnabled(False)
        layout.addWidget(QLabel("🏢 Ключ пространства:"))
        layout.addWidget(self.space_edit)

        self.single_radio.toggled.connect(self.toggle_export_type)
        self.tree_radio.toggled.connect(self.toggle_export_type)
        self.space_radio.toggled.connect(self.toggle_export_type)

        self.export_btn = QPushButton("🚀 Экспорт в Markdown")
        self.export_btn.setStyleSheet("""
            QPushButton { background-color: #27ae60; color: white; font-size: 16px; font-weight: bold; padding: 12px; border-radius: 5px; }
            QPushButton:hover { background-color: #2ecc71; }
        """)
        self.export_btn.clicked.connect(self.start_export)
        layout.addWidget(self.export_btn)

        self.original_html_btn = QPushButton("📄 Сохранить исходный HTML")
        self.original_html_btn.setStyleSheet("""
            QPushButton { background-color: #2980b9; color: white; font-size: 14px; font-weight: bold; padding: 10px; border-radius: 5px; }
            QPushButton:hover { background-color: #3498db; }
        """)
        self.original_html_btn.clicked.connect(self.save_original_html)
        layout.addWidget(self.original_html_btn)

        self.processed_html_btn = QPushButton("📝 Сохранить обработанный HTML")
        self.processed_html_btn.setStyleSheet("""
            QPushButton { background-color: #2980b9; color: white; font-size: 14px; font-weight: bold; padding: 10px; border-radius: 5px; }
            QPushButton:hover { background-color: #3498db; }
        """)
        self.processed_html_btn.clicked.connect(self.save_processed_html)
        layout.addWidget(self.processed_html_btn)

        self.structure_btn = QPushButton("📋 Сформировать структуру (оглавление)")
        self.structure_btn.setStyleSheet("""
            QPushButton { background-color: #2980b9; color: white; font-size: 14px; font-weight: bold; padding: 10px; border-radius: 5px; }
            QPushButton:hover { background-color: #3498db; }
        """)
        self.structure_btn.clicked.connect(self.generate_structure)
        layout.addWidget(self.structure_btn)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Courier", 9))
        layout.addWidget(self.log_text)

        self.results_table = QTableWidget()
        self.results_table.setColumnCount(4)
        self.results_table.setHorizontalHeaderLabels(["Страница", "Файлов", "Статус", "Файл"])
        self.results_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.results_table)

        self.setLayout(layout)
        self.toggle_export_type()

    def toggle_export_type(self):
        is_single = self.single_radio.isChecked()
        self.url_edit.setEnabled(not self.space_radio.isChecked())
        self.space_edit.setEnabled(self.space_radio.isChecked())
        if self.tree_radio.isChecked():
            self.url_edit.setPlaceholderText("URL корневой страницы раздела")
        else:
            self.url_edit.setPlaceholderText("URL страницы")
        self.structure_btn.setEnabled(not is_single)

    def browse_path(self):
        path = QFileDialog.getExistingDirectory(self, "Выберите папку для сохранения", self.path_edit.text())
        if path: self.path_edit.setText(path)

    def validate_inputs(self, require_url=True, require_space=False):
        if not self.path_edit.text():
            QMessageBox.warning(self, "Ошибка", "Укажите папку для сохранения"); return False
        if require_url and not self.url_edit.text():
            QMessageBox.warning(self, "Ошибка", "Введите URL страницы"); return False
        if require_space and not self.space_edit.text():
            QMessageBox.warning(self, "Ошибка", "Введите ключ пространства"); return False
        return True

    def set_buttons_enabled(self, enabled):
        self.export_btn.setEnabled(enabled)
        self.original_html_btn.setEnabled(enabled)
        self.processed_html_btn.setEnabled(enabled)
        self.structure_btn.setEnabled(enabled)
        if enabled:
            self.toggle_export_type()

    def start_export(self):
        if not self.validate_inputs(require_url=(self.single_radio.isChecked() or self.tree_radio.isChecked()),
                                    require_space=self.space_radio.isChecked()): return
        self.worker = ConfluenceWorker()
        self.worker.output_path = self.path_edit.text().strip()
        if self.single_radio.isChecked():
            self.worker.export_type = "single"
            self.worker.page_url = self.url_edit.text().strip()
        elif self.tree_radio.isChecked():
            self.worker.export_type = "tree"
            self.worker.tree_url = self.url_edit.text().strip()
        else:
            self.worker.export_type = "space"
            self.worker.space_key = self.space_edit.text().strip()
        self._run_worker()

    def save_original_html(self):
        if not self.single_radio.isChecked():
            QMessageBox.warning(self, "Не поддерживается", "Сохранение HTML доступно только для режима «Одна страница».")
            return
        if not self.validate_inputs(require_url=True): return
        self.worker = ConfluenceWorker()
        self.worker.output_path = self.path_edit.text().strip()
        self.worker.export_type = "original_html"
        self.worker.page_url = self.url_edit.text().strip()
        self._run_worker()

    def save_processed_html(self):
        if not self.single_radio.isChecked():
            QMessageBox.warning(self, "Не поддерживается", "Сохранение HTML доступно только для режима «Одна страница».")
            return
        if not self.validate_inputs(require_url=True): return
        self.worker = ConfluenceWorker()
        self.worker.output_path = self.path_edit.text().strip()
        self.worker.export_type = "processed_html"
        self.worker.page_url = self.url_edit.text().strip()
        self._run_worker()

    def generate_structure(self):
        if self.single_radio.isChecked():
            QMessageBox.warning(self, "Не поддерживается", "Формирование структуры доступно только для «Дерево страниц» и «Все пространство».")
            return
        if self.tree_radio.isChecked():
            if not self.validate_inputs(require_url=True): return
            self.worker = ConfluenceWorker()
            self.worker.output_path = self.path_edit.text().strip()
            self.worker.export_type = "structure"
            self.worker.structure_mode = "tree"
            self.worker.tree_url = self.url_edit.text().strip()
        elif self.space_radio.isChecked():
            if not self.validate_inputs(require_space=True): return
            self.worker = ConfluenceWorker()
            self.worker.output_path = self.path_edit.text().strip()
            self.worker.export_type = "structure"
            self.worker.structure_mode = "space"
            self.worker.space_key = self.space_edit.text().strip()
        self._run_worker()

    def _run_worker(self):
        self.worker.progress.connect(self.log_text.append)
        self.worker.error.connect(self.handle_error)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.file_downloaded.connect(self.file_downloaded)
        self.worker.start()
        self.progress_bar.setVisible(True)
        self.results_table.setRowCount(0)
        self.log_text.clear()
        self.set_buttons_enabled(False)

    def handle_error(self, msg):
        self.log_text.append(f"❌ {msg}")
        QMessageBox.critical(self, "Ошибка", msg)
        self.progress_bar.setVisible(False)
        self.set_buttons_enabled(True)

    def file_downloaded(self, filename, status):
        if status == "downloaded":
            self.log_text.append(f"  ✅ Скачан: {filename}")

    def on_worker_finished(self, result):
        self.progress_bar.setVisible(False)
        self.set_buttons_enabled(True)
        log_path = Path(self.worker.output_path) / 'export_log.txt'

        if result['type'] in ('html_original', 'html_processed'):
            self.log_text.append(f"✅ HTML сохранён: {result['file_path']}")
            QMessageBox.information(self, "Готово",
                f"HTML страница сохранена:\n{result['file_path']}\n\nЛог: {log_path}")
        elif result['type'] == 'structure':
            self.log_text.append(f"✅ Структура сохранена: {result['file_path']}")
            QMessageBox.information(self, "Готово",
                f"Структура сохранена:\n{result['file_path']}\n\nЛог: {log_path}")
        else:
            def add_row(title, files, status, filename):
                row = self.results_table.rowCount()
                self.results_table.insertRow(row)
                self.results_table.setItem(row, 0, QTableWidgetItem(title))
                self.results_table.setItem(row, 1, QTableWidgetItem(str(files)))
                self.results_table.setItem(row, 2, QTableWidgetItem(status))
                self.results_table.setItem(row, 3, QTableWidgetItem(filename))

            if result['type'] == 'page':
                add_row(result['title'], result['files_count'], "✅ Успешно", Path(result['md_file']).name)
                QMessageBox.information(self, "Готово",
                    f"Страница экспортирована:\n{Path(result['md_file']).name}\n\nЛог: {log_path}")
            elif result['type'] == 'tree':
                for r in result['results']:
                    status = "✅ Успешно" if 'error' not in r else "❌ Ошибка"
                    fname = Path(r['md_file']).name if 'md_file' in r else ""
                    add_row(r['title'], r.get('files_count',0), status, fname)
                QMessageBox.information(self, "Готово",
                    f"Раздел экспортирован в папку:\n{result['root_title']}\n\nЛог: {log_path}")
            elif result['type'] == 'space':
                for r in result['results']:
                    status = "✅ Успешно" if 'error' not in r else "❌ Ошибка"
                    fname = Path(r['md_file']).name if 'md_file' in r else ""
                    add_row(r['title'], r.get('files_count',0), status, fname)
                QMessageBox.information(self, "Готово",
                    f"Экспорт пространства завершён\n\nЛог: {log_path}")


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()