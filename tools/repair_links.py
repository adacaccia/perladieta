#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, re, json, sys
from urllib.parse import urlsplit
import requests

URL_MAP_PATH = "data/url_map.json"
CACHE_DIR = "data"
BLOGGER_REDIRECTS_PATH = os.path.join(CACHE_DIR, "blogger_redirects.json")

def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def resolve_blogger_path(u, cache):
    from urllib.parse import urlsplit
    if u.startswith("/"):
        probe = "https://perladieta.blogspot.com" + u
    else:
        probe = u
    key = probe.rstrip("/")
    if key in cache:
        return cache[key]
    try:
        # usa GET invece di HEAD: alcuni endpoint non gestiscono HEAD correttamente
        r = requests.get(probe, timeout=20, allow_redirects=True)
        final = r.url
    except Exception:
        final = probe
    path = urlsplit(final).path
    path = path.split("#",1)[0].split("?",1)[0].rstrip("/")
    cache[key] = path
    return path

def normalize_path(u):
    # fallback: togli dominio, query, frammento, slash finale
    u2 = re.sub(r"^https?://perladieta\.blogspot\.[^/]+", "", u, flags=re.I)
    u2 = u2.split("#",1)[0].split("?",1)[0].rstrip("/")
    return u2

def fix_in_markdown_text(md_text, url_map, redir_cache):
    changed = False

    # 1) link completi
    full_pat = re.compile(r'https?://perladieta\.blogspot\.[^/\s\)"]+/\d{4}/\d{2}/[a-z0-9\-]+\.html(?:[?#][^\s\)"]*)?', re.I)
    # 2) path nudi
    path_pat = re.compile(r'/\d{4}/\d{2}/[a-z0-9\-]+\.html(?:[?#][^\s\)"]*)?', re.I)

    def repl_full(m):
        nonlocal changed
        raw = m.group(0)
        try:
            p = resolve_blogger_path(raw, redir_cache)  # segue redirect → path canonico
        except Exception:
            p = normalize_path(raw)
        new = url_map.get(p, raw)
        if new != raw:
            changed = True
        return new

    def repl_path(m):
        nonlocal changed
        raw = m.group(0)
        try:
            p = resolve_blogger_path(raw, redir_cache)
        except Exception:
            p = normalize_path(raw)
        new = url_map.get(p, raw)
        if new != raw:
            changed = True
        return new

    md2 = full_pat.sub(repl_full, md_text)
    md2 = path_pat.sub(repl_path, md2)
    return md2, changed

def split_front_matter(text: str):
    """Ritorna (front_matter_incluso_delimitatori, body). Se non c'è FM, ritorna ("", text)."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return "", text
    # trova la seconda linea '---'
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            fm = "".join(lines[:i+1])   # include le due ---
            body = "".join(lines[i+1:])
            return fm, body
    # caso anomalo: solo apertura senza chiusura -> tratta come no-FM
    return "", text

def main():
    url_map = load_json(URL_MAP_PATH)
    redir_cache = load_json(BLOGGER_REDIRECTS_PATH)
    if not url_map:
        print(f"[ERR] {URL_MAP_PATH} mancante o vuota: lancialo con blogger2md.py prima.")
        sys.exit(1)

    total_files = 0
    changed_files = 0

    for root, _, files in os.walk("_posts"):
        for fn in files:
            if not fn.endswith(".md"):
                continue
            total_files += 1
            path = os.path.join(root, fn)
            with open(path, "r", encoding="utf-8") as f:
                full = f.read()

            fm, body = split_front_matter(full)
            body2, chg = fix_in_markdown_text(body, url_map, redir_cache)

            if chg and body2 != body:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(fm + body2)
                changed_files += 1

    save_json(BLOGGER_REDIRECTS_PATH, redir_cache)
    print(f"[REPAIR] scanned={total_files} changed_files={changed_files}")

if __name__ == "__main__":
    main()
