#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Blogger → Markdown (backup evolutivo per Jekyll/GitHub Pages)

Funzioni principali:
- Paginazione completa del feed Blogger (start-index / max-results)
- Front matter YAML compatibile con il tuo formato:
    layout, title, date (YYYY-MM-DD), original_url, tags (lista)
- Struttura output: _posts/<YYYY>/<YYYY-MM-DD-slug>.md
- Download immagini in una cartella configurabile (default: assets/ a livello repo)
- Riscrittura <img src="..."> verso path locali
- Log dettagliato:
    [FEED] page X (posts A–B) …
    [POST] <url> -> <path> | body=…B imgs_html=… saved=YES/NO
- Riepilogo finale: Changed: True/False
"""

import os
import re
import json
import yaml
import time
import hashlib
import datetime
import requests
import feedparser
import urllib.parse
from typing import Tuple
from slugify import slugify
from bs4 import BeautifulSoup
from urllib.parse import urlsplit
from markdownify import markdownify as md

# ----------------------------
# Config tramite env vars
# ----------------------------
FEED_URL = os.environ.get(
    "BLOGGER_FEED_URL",
    "https://perladieta.blogspot.com/feeds/posts/default?alt=rss"
)

# Dove scrivere i post convertiti (Jekyll): di default _posts
OUT_DIR = os.environ.get("OUT_DIR", "_posts")

# Directory in cui salvare le immagini scaricate (default: "assets" a livello repo)
# Consigliato: una cartella SENZA underscore, es. "assets"
ASSETS_DIR = os.environ.get("ASSETS_DIR", "assets")

# Base URL (nel sito) per referenziare le immagini
# Se ASSETS_DIR="assets" a livello repo, usare "/assets"
ASSETS_URL_BASE = os.environ.get("ASSETS_URL_BASE", "/perladieta/assets")

# Attiva/Disattiva download media
DOWNLOAD_MEDIA = os.environ.get("DOWNLOAD_MEDIA", "0") == "1"

# Paginazione feed
# max-results: Blogger supporta fino a 500; 50 è un buon compromesso
FEED_MAX_RESULTS = int(os.environ.get("FEED_MAX_RESULTS", "50"))

# Pausa tra pagine del feed (gentilezza verso Blogger)
FEED_SLEEP_SECONDS = float(os.environ.get("FEED_SLEEP_SECONDS", "0.5"))

# Cache e mappe
CACHE_DIR = "data"
CACHE_FEED_LATEST = os.path.join(CACHE_DIR, "feed_latest.xml")
MEDIA_MAP_PATH = os.path.join(CACHE_DIR, "media_map.json")
URL_MAP_PATH = os.path.join(CACHE_DIR, "url_map.json")

# Force overwrite
FORCE_OVERWRITE = os.environ.get("FORCE_OVERWRITE", "0") == "1"

BLOGGER_REDIRECTS_PATH = os.path.join(CACHE_DIR, "blogger_redirects.json")

REDIR_CACHE = None  # caricato in main()

# ----------------------------
# Utility
# ----------------------------
def resolve_blogger_path(url_or_path: str) -> str:
    """
    Prende un URL completo o un path Blogspot, segue i redirect e ritorna il path canonico
    tipo /YYYY/MM/slug.html (senza query/fragment/slash).
    Usa una cache su disco per non ripetere richieste.
    """
    global REDIR_CACHE
    if REDIR_CACHE is None:
        REDIR_CACHE = load_redirect_cache()

    # normalizza a URL completo per la richiesta
    if url_or_path.startswith("/"):
        probe = "https://perladieta.blogspot.com" + url_or_path
    else:
        probe = url_or_path

    key = probe.rstrip("/")
    if key in REDIR_CACHE:
        return REDIR_CACHE[key]

    try:
        r = requests.head(probe, timeout=15, allow_redirects=True)
        final = r.url
    except Exception:
        # in caso di errore usa l’input
        final = probe

    # estrai path, togli query/fragment/slash finale
    from urllib.parse import urlsplit
    path = urlsplit(final).path
    path = path.split("#", 1)[0].split("?", 1)[0].rstrip("/")

    REDIR_CACHE[key] = path
    return path

def load_redirect_cache():
    try:
        with open(BLOGGER_REDIRECTS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_redirect_cache(cache: dict):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(BLOGGER_REDIRECTS_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
def ensure_dirs():
    os.makedirs(CACHE_DIR, exist_ok=True)
    os.makedirs(OUT_DIR, exist_ok=True)
    if DOWNLOAD_MEDIA:
        # Se ASSETS_DIR è relativo, crealo relativo alla root repo
        os.makedirs(ASSETS_DIR, exist_ok=True)

def load_media_map() -> dict:
    if os.path.exists(MEDIA_MAP_PATH):
        try:
            with open(MEDIA_MAP_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_media_map(m: dict):
    with open(MEDIA_MAP_PATH, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)

def build_url_map(posts_dir=OUT_DIR, base_prefix="/perladieta"):
    """
    Scansiona _posts/YYYY/YYYY-MM-DD-slug.md, legge original_url dal front matter YAML e
    costruisce la URL Pages: /perladieta/YYYY/MM/DD/slug.html
    Scrive data/url_map.json.
    """
    url_map = {}
    files_scanned = 0
    with_orig = 0
    missing_orig = []

    for root, _, files in os.walk(posts_dir):
        for fn in files:
            if not fn.endswith(".md"):
                continue
            files_scanned += 1

            m = re.match(r"(\d{4})-(\d{2})-(\d{2})-(.+)\.md$", fn)
            if not m:
                continue
            yyyy, mm, dd, slug = m.groups()
            md_path = os.path.join(root, fn)

            # --- estrai front-matter YAML in modo robusto ---
            original_url = None
            try:
                with open(md_path, "r", encoding="utf-8") as f:
                    text = f.read()
                if text.lstrip().startswith("---"):
                    # prendi tra i primi due delimitatori ---
                    parts = text.split("\n", 1)[1].split("\n---", 1)
                    fm_text = parts[0]
                    data = yaml.safe_load(fm_text) or {}
                    # chiave accettata in varianti
                    for key in ("original_url", "original-url", "originalUrl"):
                        if key in data and data[key]:
                            original_url = str(data[key]).strip()
                            break
            except Exception as e:
                # front matter illeggibile: ignora silenziosamente
                pass

            if not original_url:
                missing_orig.append(md_path)
                continue
            with_orig += 1

            pages_url = f"{base_prefix}/{yyyy}/{mm}/{dd}/{slug}.html"

            # --- NORMALIZZA PATH BASE (senza dominio, query, fragment, slash) ---
            orig_norm = re.sub(r"^https?://perladieta\.blogspot\.[^/]+", "", original_url, flags=re.I)
            orig_norm = orig_norm.split("#", 1)[0].split("?", 1)[0].rstrip("/")

            # chiave PRINCIPALE: path-only pulito
            url_map[orig_norm] = pages_url

            # varianti utili (robuste, ma opzionali)
            tlds = ["com", "it", "co.uk", "de", "fr", "es", "pt", "nl", "ro", "gr"]
            for tld in tlds:
                for scheme in ("http", "https"):
                    full = f"{scheme}://perladieta.blogspot.{tld}{orig_norm}"
                    url_map[full] = pages_url
                    url_map[full + "/"] = pages_url
                    url_map[full + "?m=1"] = pages_url

    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(URL_MAP_PATH, "w", encoding="utf-8") as f:
        json.dump(url_map, f, ensure_ascii=False, indent=2)

    print(f"[MAP] scanned={files_scanned} with_original_url={with_orig} url_map entries={len(url_map)}")
    if missing_orig:
        # log sintetico (prime 5) per capire se qualche file non ha original_url
        print(f"[MAP] missing original_url in {len(missing_orig)} files (esempio):")
        for p in missing_orig[:5]:
            print("   -", p)

    return url_map

def load_url_map():
    try:
        with open(URL_MAP_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def fix_internal_links(html, url_map=None):
    if url_map is None:
        url_map = load_url_map()
    full_pat = re.compile(r'https?://perladieta\.blogspot\.[a-z.]+/[^\s"\'<>]+', re.I)
    path_pat = re.compile(r'/\d{4}/\d{2}/[a-z0-9\-]+\.html(?:[?#][^\s"\'<>]*)?', re.I)
    rewrites = 0

    def norm_to_path(u: str) -> str:
        # prima prova risoluzione via redirect
        try:
            return resolve_blogger_path(u)
        except Exception:
            pass
        # fallback: strip schema+dominio+query+fragment
        u2 = re.sub(r"^https?://perladieta\.blogspot\.[^/]+", "", u, flags=re.I)
        u2 = u2.split("#", 1)[0].split("?", 1)[0]
        return u2.rstrip("/")

    def repl(m):
        nonlocal rewrites
        p = norm_to_path(m.group(0))
        if p in url_map:
            rewrites += 1
            return url_map[p]
        return m.group(0)

    html = full_pat.sub(repl, html)
    html = path_pat.sub(lambda m: (url_map.get(norm_to_path(m.group(0)), m.group(0))), html)
    if rewrites:
        print(f"[LINK] rewrites={rewrites}")
    return html

def fix_internal_links_in_markdown(md_text: str, url_map: dict) -> str:
    full_pat = re.compile(r'https?://perladieta\.blogspot\.[^/\s"]+/\d{4}/\d{2}/[a-z0-9\-]+\.html(?:[?#][^\s"\'\)]*)?', re.I)
    path_pat = re.compile(r'/\d{4}/\d{2}/[a-z0-9\-]+\.html(?:[?#][^\s"\'\)]*)?', re.I)

    def norm_to_path(u: str) -> str:
        try:
            return resolve_blogger_path(u)
        except Exception:
            u2 = re.sub(r'^https?://perladieta\.blogspot\.[^/]+', '', u, flags=re.I)
            u2 = u2.split('#', 1)[0].split('?', 1)[0]
            return u2.rstrip('/')

    def repl_full(m):
        p = norm_to_path(m.group(0))
        return url_map.get(p, m.group(0))

    def repl_path(m):
        p = norm_to_path(m.group(0))
        return url_map.get(p, m.group(0))

    md_text2 = full_pat.sub(repl_full, md_text)
    md_text2 = path_pat.sub(repl_path, md_text2)
    return md_text2

def sanitize_html_to_md(html: str) -> str:
    # Converti HTML a Markdown con cleanup base
    return md(html, strip=["script", "style"])


def _guess_ext(url: str) -> str:
    path = urlsplit(url).path
    ext = os.path.splitext(path)[1].lower()
    if ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"):
        return ext
    return ".jpg"


def _asset_filename(url: str) -> str:
    # Nome stabile: sha1 dei byte dell'URL + estensione
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    return f"{h}{_guess_ext(url)}"

def localize_images_and_links(html: str, media_map: dict, url_map: dict) -> Tuple[str, bool, int]:
    soup = BeautifulSoup(html, "html.parser")
    changed = False

    def download_and_map(src: str) -> str:
        nonlocal changed
        if not src:
            return src

        # HIT in media_map: verifica che il file locale esista, altrimenti riscarica
        if src in media_map:
            site_url = media_map[src]
            try:
                from urllib.parse import urlsplit
                fn = os.path.basename(urlsplit(site_url).path)
                local_fs_path = os.path.join(ASSETS_DIR, fn)
            except Exception:
                local_fs_path = None

            if DOWNLOAD_MEDIA and local_fs_path and not os.path.exists(local_fs_path):
                try:
                    resp = requests.get(src, timeout=30)
                    resp.raise_for_status()
                    os.makedirs(ASSETS_DIR, exist_ok=True)
                    with open(local_fs_path, "wb") as f:
                        f.write(resp.content)
                except Exception:
                    pass  # fallback: mantieni site_url anche se non sei riuscito a riscaricare
            return site_url

        # MISS in media_map: scarica e mappa
        if DOWNLOAD_MEDIA:
            try:
                fn = _asset_filename(src)
                local_fs_path = os.path.join(ASSETS_DIR, fn)
                if not os.path.exists(local_fs_path):
                    resp = requests.get(src, timeout=30)
                    resp.raise_for_status()
                    os.makedirs(ASSETS_DIR, exist_ok=True)
                    with open(local_fs_path, "wb") as f:
                        f.write(resp.content)
                site_url = f"{ASSETS_URL_BASE}/{fn}"
                media_map[src] = site_url
                changed = True
                return site_url
            except Exception:
                return src  # fallback: lascia URL originale
        return src

    # 1) <img> standard (+ semplice lazy/srcset)
    img_tags = soup.find_all("img")
    for img in img_tags:
        src = img.get("src")
        if not src:
            # lazy comuni
            src = img.get("data-src") or img.get("data-original") or img.get("data-lazy-src")
        # srcset (scegli la più larga)
        if (not src) and img.get("srcset"):
            try:
                candidates = [s.strip() for s in img["srcset"].split(",")]
                pairs = []
                for c in candidates:
                    parts = c.split()
                    url = parts[0]
                    w = 0
                    if len(parts) > 1 and parts[1].endswith("w"):
                        try:
                            w = int(parts[1][:-1])
                        except:
                            pass
                    pairs.append((w, url))
                pairs.sort(reverse=True)
                src = pairs[0][1] if pairs else None
            except Exception:
                pass
        if not src:
            continue
        img["src"] = download_and_map(src)

    # 2) background-image: url(...) nello style
    for el in soup.find_all(style=True):
        style = el.get("style") or ""
        urls = re.findall(r'url\((?:["\']?)(.*?)(?:["\']?)\)', style)
        if not urls:
            continue
        first = urls[0]
        local = download_and_map(first)
        if local and local != first:
            el["style"] = style.replace(first, local)
            if not el.find("img"):
                el.insert(0, soup.new_tag("img", src=local))

    # 3) attributo background="..." (table/tr/td)
    for el in soup.find_all(["td", "tr", "table"]):
        bg = el.get("background")
        if not bg:
            continue
        local = download_and_map(bg)
        if local:
            if "background" in el.attrs:
                del el["background"]
            if not el.find("img"):
                el.insert(0, soup.new_tag("img", src=local))
            existing = el.get("style", "")
            if local not in existing:
                el["style"] = (existing + f"; background-image:url({local})").strip("; ")

    # 4) <a href="...jpg|png|gif|webp|svg"> senza <img> → inserisci <img>
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if re.search(r'\.(?:jpe?g|png|gif|webp|svg)(?:\?.*)?$', href, flags=re.I):
            if not a.find("img"):
                local = download_and_map(href)
                a.insert(0, soup.new_tag("img", src=local))

    # 5) Tabelle decorative -> sostituisci con <figure><img><figcaption?>
    def extract_first_img_url(el):
        imgtag = el.find("img")
        if imgtag and imgtag.get("src"):
            return imgtag.get("src")
        for node in el.find_all(style=True):
            st = node.get("style") or ""
            urls = re.findall(r'url\((?:["\']?)(.*?)(?:["\']?)\)', st)
            if urls:
                return urls[0]
        for node in el.find_all(["table", "tr", "td"]):
            if node.get("background"):
                return node.get("background")
        for a in el.find_all("a", href=True):
            if re.search(r'\.(?:jpe?g|png|gif|webp|svg)(?:\?.*)?$', a["href"], flags=re.I):
                return a["href"]
        return None

    for tbl in soup.find_all("table"):
        src = extract_first_img_url(tbl)
        if not src:
            continue
        local = download_and_map(src)
        caption_txt = tbl.get_text(" ", strip=True)
        figcap = None
        if caption_txt and not re.fullmatch(r'[-| ]*', caption_txt):
            figcap = soup.new_tag("figcaption")
            figcap.string = caption_txt

        figure = soup.new_tag("figure")
        figure.append(soup.new_tag("img", src=local))
        if figcap:
            figure.append(figcap)

        tbl.replace_with(figure)
        changed = True

    img_count_html = len(soup.find_all("img"))
    return str(soup), changed, img_count_html

# ----------------------------
# Feed (paginazione completa)
# ----------------------------
def fetch_feed_page(base_url: str, start_index: int = 1, max_results: int = 50):
    """
    Scarica una pagina del feed Blogger con start-index/max-results.
    """
    # Unisci parametri con eventuale query presente in FEED_URL
    url_parts = urllib.parse.urlsplit(base_url)
    q = dict(urllib.parse.parse_qsl(url_parts.query))
    # settaggi/override
    q.setdefault("alt", "rss")
    q["start-index"] = str(start_index)
    q["max-results"] = str(max_results)

    new_query = urllib.parse.urlencode(q)
    page_url = urllib.parse.urlunsplit(
        (url_parts.scheme, url_parts.netloc, url_parts.path, new_query, url_parts.fragment)
    )

    r = requests.get(page_url, timeout=30)
    r.raise_for_status()
    content = r.content
    feed = feedparser.parse(content)
    return feed, content, page_url


def fetch_all_entries(base_url: str, max_results: int = FEED_MAX_RESULTS):
    """
    Paginazione completa: ritorna la lista di tutte le entry del feed.
    """
    all_entries = []
    start = 1
    page = 1

    while True:
        feed, raw, page_url = fetch_feed_page(base_url, start_index=start, max_results=max_results)
        entries = feed.entries or []
        a = start
        b = start + max_results - 1
        print(f"[FEED] page {page}  (posts {a}–{b})  url={page_url}  got={len(entries)}")

        if page == 1:
            # salviamo l'ultima pagina scaricata come snapshot
            try:
                with open(CACHE_FEED_LATEST, "wb") as f:
                    f.write(raw)
            except Exception:
                pass

        if not entries:
            break

        all_entries.extend(entries)
        if len(entries) < max_results:
            break

        start += max_results
        page += 1
        time.sleep(FEED_SLEEP_SECONDS)

    print(f"[FEED] total entries: {len(all_entries)}")
    return all_entries


# ----------------------------
# Core: scrittura post
# ----------------------------
def write_post(entry, media_map: dict, url_map: dict) -> Tuple[bool, bool]:
    """
    Converte una singola entry in Markdown con front matter e media localizzati.
    Ritorna (changed_file, changed_media_map)
    """
    # --- estrazione campi base ---
    title = entry.get("title", "Senza titolo")
    dt = entry.get("published_parsed") or entry.get("updated_parsed")
    if dt:
        date = datetime.datetime(*dt[:6])
    else:
        date = datetime.datetime.now()

    slug = slugify(title) or hashlib.sha1(title.encode("utf-8")).hexdigest()[:8]
    y = str(date.year)
    md_name = f"{date:%Y-%m-%d}-{slug}.md"
    out_dir = os.path.join(OUT_DIR, y)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, md_name)

    original_url = entry.get("link", "")
    tags = [t["term"] for t in entry.get("tags", [])] if "tags" in entry else []

    # --- contenuto (robusto per Atom/RSS) ---
    def get_entry_html(e):
        v = (e.get("content") or [{}])[0].get("value")
        if v: return v
        v = (e.get("summary_detail") or {}).get("value")
        if v: return v
        v = e.get("description")
        if v: return v
        v = e.get("summary")
        if v: return v
        media = e.get("media_content") or []
        if media:
            imgs = [m.get("url") for m in media
                    if m.get("url") and (m.get("medium") == "image" or m.get("type","").startswith("image/"))]
            if imgs:
                return "".join(f'<p><img src="{u}"/></p>' for u in imgs)
        return ""

    content_html = get_entry_html(entry)

    # 1) localizza immagini
    content_html_local, changed_media, img_count_html = localize_images_and_links(content_html, media_map, url_map)

    # 2) riscrivi i link interni blogspot -> pages (PRIMA della conversione a MD)
    content_html_local = fix_internal_links(content_html_local, url_map=url_map)

    # 3) converti in Markdown
    body_md = sanitize_html_to_md(content_html_local).strip()
    body_md = fix_internal_links_in_markdown(body_md, url_map)

    # --- FRONT MATTER ---
    safe_title = (title or "").replace('"', "'")
    date_str = date.strftime("%Y-%m-%d")
    tags_yaml = "\n".join([f"  - {t}" for t in tags]) if tags else "  - perladieta"

    front_matter = (
        "---\n"
        "layout: post\n"
        f'title: "{safe_title}"\n'
        f"date: {date_str}\n"
        f'original_url: "{original_url}"\n'
        "tags:\n"
        f"{tags_yaml}\n"
        "---\n\n"
    )

    new_text = front_matter + body_md + "\n"
    old_text = None
    if os.path.exists(out_path):
        with open(out_path, "r", encoding="utf-8") as f:
            old_text = f.read()

    changed_file = FORCE_OVERWRITE or (old_text != new_text)
    if changed_file:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(new_text)

    size_bytes = len(body_md.encode("utf-8"))
    print(f"[POST] {original_url}  ->  {out_path}  | body={size_bytes}B  imgs_html={img_count_html}  saved={'YES' if changed_file else 'NO'}")

    return changed_file, changed_media

# ----------------------------
# Main
# ----------------------------
def main():
    ensure_dirs()
    media_map = load_media_map()
    url_map = build_url_map(OUT_DIR, base_prefix="/perladieta")

    entries = fetch_all_entries(FEED_URL, max_results=FEED_MAX_RESULTS)

    changed_any = False
    changed_media_any = False

    for entry in entries:
        chg, chg_media = write_post(entry, media_map, url_map)
        changed_any |= chg
        changed_media_any |= chg_media

    if changed_media_any:
        save_media_map(media_map)

    print("Changed:", changed_any)

    if REDIR_CACHE is not None:
        save_redirect_cache(REDIR_CACHE)
    
if __name__ == "__main__":
    main()
