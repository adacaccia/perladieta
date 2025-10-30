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
import time
import hashlib
import datetime
import urllib.parse
from urllib.parse import urlsplit
from typing import Tuple

import requests
import feedparser
from bs4 import BeautifulSoup
from slugify import slugify
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
ASSETS_URL_BASE = os.environ.get("ASSETS_URL_BASE", "/assets")

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


# ----------------------------
# Utility
# ----------------------------
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


def localize_images_and_links(html: str, media_map: dict) -> Tuple[str, bool, int]:
    """
    Scarica immagini (se abilitato) e riscrive i src verso ASSETS_URL_BASE.
    Ritorna (html_riscritto, changed_media, img_count_html)
    """
    soup = BeautifulSoup(html, "html.parser")
    changed = False

    # Conta immagini prima di modificare
    img_tags = soup.find_all("img")
    img_count_html = len(img_tags)

    for img in img_tags:
        src = img.get("src")
        if not src:
            continue

        # Se già in mappa, sostituisci direttamente
        if src in media_map:
            img["src"] = media_map[src]
            changed = True
            continue

        # Download se attivo
        if DOWNLOAD_MEDIA:
            try:
                fn = _asset_filename(src)
                local_fs_path = os.path.join(ASSETS_DIR, fn)  # path sul filesystem
                if not os.path.exists(local_fs_path):
                    resp = requests.get(src, timeout=30)
                    resp.raise_for_status()
                    with open(local_fs_path, "wb") as f:
                        f.write(resp.content)
                # Map URL originale -> URL pubblico nel sito
                site_url = f"{ASSETS_URL_BASE}/{fn}"
                media_map[src] = site_url
                img["src"] = site_url
                changed = True
            except Exception:
                # In caso di errore, lascia l'URL originale
                pass

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
def write_post(entry, media_map: dict) -> Tuple[bool, bool]:
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

    # --- contenuto ---
    content_html = entry.get("content", [{}])[0].get("value", entry.get("summary", ""))

    # localizza immagini e link
    content_html_local, changed_media, img_count_html = localize_images_and_links(content_html, media_map)
    content_html_local = fix_internal_links(content_html_local)
    body_md = sanitize_html_to_md(content_html_local).strip()

    # --- FRONT MATTER (formato identico al tuo) ---
    safe_title = (title or "").replace('"', "'")
    date_str = date.strftime("%Y-%m-%d")
    if tags:
        tags_yaml = "\n".join([f"  - {t}" for t in tags])
    else:
        tags_yaml = "  - perladieta"

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

    changed_file = (old_text != new_text)
    if changed_file:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(new_text)

    # Log per post
    size_bytes = len(body_md.encode("utf-8"))
    print(
        f"[POST] {original_url}  ->  {out_path}  | body={size_bytes}B  "
        f"imgs_html={img_count_html}  saved={'YES' if changed_file else 'NO'}"
    )

    return changed_file, changed_media

import re

def fix_internal_links(html):
    # trova link tipo perladieta.blogspot...
    pattern = re.compile(r'https?://perladieta\.blogspot\.[a-z]+/(\d{4})/(\d{2})/(\d{2})/([^"]+)\.html')
    return pattern.sub(r'{{ "/\1/\2/\3/\4.html" | relative_url }}', html)

# ----------------------------
# Main
# ----------------------------
def main():
    ensure_dirs()
    media_map = load_media_map()

    entries = fetch_all_entries(FEED_URL, max_results=FEED_MAX_RESULTS)

    changed_any = False
    changed_media_any = False

    for entry in entries:
        chg, chg_media = write_post(entry, media_map)
        changed_any |= chg
        changed_media_any |= chg_media

    if changed_media_any:
        save_media_map(media_map)

    print("Changed:", changed_any)


if __name__ == "__main__":
    main()
