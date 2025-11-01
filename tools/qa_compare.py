#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re, sys, csv, time, requests
from urllib.parse import urlsplit
from bs4 import BeautifulSoup
import json, os

MEDIA_MAP_PATH = "data/media_map.json"
def load_media_map():
    try:
        with open(MEDIA_MAP_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

URL_MAP_PATH = "data/url_map.json"
def load_url_map():
    try:
        with open(URL_MAP_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "perladieta-qa/1.0"

def is_small_or_ui_image(url: str) -> bool:
    u = url.lower()
    if any(k in u for k in ["favicon", "sprite", "banner", "header", "logo"]):
        return True
    # pattern dimensioni blogger: w72-h72, s48-c, ecc.
    if re.search(r'(w\d+-h\d+)|(s\d+(-[a-z])?)', u):
        # scarta miniature e iconcine (sotto ~120px)
        dims = re.findall(r'w(\d+)-h(\d+)', u)
        if dims:
            w, h = map(int, dims[0])
            if w < 120 and h < 120:
                return True
        s = re.findall(r's(\d+)', u)
        if s and int(s[0]) <= 128:
            return True
    return False

def extract_images_all(html):
    """Estrae TUTTE le immagini “visibili o nascoste”: <img>, style background, attr background, link nudi a .jpg/png/..."""
    soup = BeautifulSoup(html, "html.parser")
    urls = set()

    # <img>
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-original") or img.get("data-lazy-src")
        if not src and img.get("srcset"):
            try:
                candidates = [s.strip() for s in img["srcset"].split(",")]
                pairs = []
                for c in candidates:
                    parts = c.split()
                    url = parts[0]; w = 0
                    if len(parts) > 1 and parts[1].endswith("w"):
                        try: w = int(parts[1][:-1])
                        except: pass
                    pairs.append((w,url))
                pairs.sort(reverse=True)
                src = pairs[0][1] if pairs else None
            except: pass
        if src: urls.add(src)

    # style="background-image:url(...)"
    for el in soup.find_all(style=True):
        style = el.get("style") or ""
        for u in re.findall(r'url\((?:["\']?)(.*?)(?:["\']?)\)', style, flags=re.I):
            urls.add(u)

    # background="..."
    for el in soup.find_all(["td","tr","table"]):
        bg = el.get("background")
        if bg: urls.add(bg)

    # <a href="...jpg|png|gif|webp|svg">
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if re.search(r'\.(?:jpe?g|png|gif|webp|svg)(?:\?.*)?$', href, flags=re.I):
            urls.add(href)

    return sorted(urls)

def fetch(url):
    r = SESSION.get(url, timeout=30)
    r.raise_for_status()
    return r.text

def guess_pages_url_from_blogger(blog_url, base="https://adacaccia.github.io/perladieta"):
    """
    1) Prova la url_map (deterministica).
    2) Se manca, fallback euristico provando tutti i giorni 01..31 (compat retro).
    """
    url_map = load_url_map()

    # normalizza a path-only: /YYYY/MM/slug.html
    path_only = re.sub(r"^https?://perladieta\.blogspot\.[^/]+", "", blog_url, flags=re.I).rstrip("/")
    # prova prima path-only
    if path_only in url_map:
        return "https://adacaccia.github.io" + url_map[path_only]

    # prova chiavi complete (tld/scheme vari)
    if blog_url.rstrip("/") in url_map:
        return "https://adacaccia.github.io" + url_map[blog_url.rstrip("/")]

    # Fallback storico: tenta 01..31
    m = re.search(r'/(\d{4})/(\d{2})/([a-z0-9\-]+)\.html$', blog_url)
    if not m:
        return None
    y, mm, slug = m.groups()
    for dd in [f"{d:02d}" for d in range(1, 32)]:
        test = f"{base}/{y}/{mm}/{dd}/{slug}.html"
        try:
            r = SESSION.head(test, timeout=10, allow_redirects=True)
            if r.status_code == 200:
                return test
        except:
            pass
    return None

def http_ok(url):
    try:
        r = SESSION.head(url, timeout=15, allow_redirects=True)
        return 200 <= r.status_code < 300
    except:
        return False

def run_check(blog_url, pages_url=None, csv_out=None):
    if not pages_url:
        pages_url = guess_pages_url_from_blogger(blog_url)
    if not pages_url:
        print(f"[ERR] Non trovo la URL Pages per {blog_url}. "
             f"Assicurati che {URL_MAP_PATH} esista (lanciando blogger2md.py) "
             "oppure passa l’URL Pages esplicitamente.")
        sys.exit(1)
        
    print(f"[CHK] Blogger: {blog_url}")
    print(f"[CHK]   Pages: {pages_url}")

    # src_html = fetch(blog_url)
    src_html_full = fetch(blog_url)
    soup_src = BeautifulSoup(src_html_full, "html.parser")
    # selettori tipici di Blogger:
    main = (soup_src.select_one(".post-body") or
        soup_src.select_one(".entry-content") or
        soup_src.select_one(".post") or
        soup_src.select_one("#Blog1") or
        soup_src)
    src_html = str(main)
    dst_html = fetch(pages_url)
    media_map = load_media_map()
    dst_soup = BeautifulSoup(dst_html, "html.parser")
    dst_imgs = extract_images_all(dst_html)

    # normalizza: considera valide solo le immagini pubblicate nel tuo sito
    dst_imgs_local = [u for u in dst_imgs if "/perladieta/assets/" in u or u.startswith("/perladieta/assets/")]

    src_imgs_all = extract_images_all(src_html)
    src_imgs = [u for u in src_imgs_all if not is_small_or_ui_image(u)]
    dst_imgs = extract_images_all(dst_html)

    print(f"[IMG] Blogger: {len(src_imgs)}  | Pages: {len(dst_imgs)}")

    # link interni ancora a blogspot?
    blogspot_links = re.findall(r'https?://perladieta\.blogspot\.[a-z]+/[^\s"\'<>]+', dst_html, flags=re.I)
    if blogspot_links:
        print(f"[LINK] Rimasti link a blogspot: {len(blogspot_links)}")
        for l in blogspot_links[:5]:
            print("   -", l)
    else:
        print("[LINK] OK: nessun link a blogspot nel render Pages")

    # Blogger originals che NON risultano presenti su Pages secondo media_map
    mapped_urls = set(media_map.get(u, "") for u in src_imgs)
    mapped_urls = {m for m in mapped_urls if m}  # non vuoti

    present = 0
    for m in mapped_urls:
        # Pages può mostrale come relative o assolute
        if m in dst_imgs_local or ("https://adacaccia.github.io" + m) in dst_imgs:
            present += 1

    missing_count = max(0, len(mapped_urls) - present)
    print(f"[IMG] Blogger (filtrate): {len(src_imgs)} | Pages (local): {len(dst_imgs_local)} | Mapped present: {present}")

    if missing_count > 0:
        print(f"[MISS] Immagini presenti su Blogger ma non (ancora) su Pages: {missing_count}")
        # opzionale: stampa qualche originale non trovato
        not_found = [u for u in src_imgs if media_map.get(u, "") not in dst_imgs_local]
        for u in not_found[:5]:
            print("   -", u)
    else:
        print("[MISS] OK: nessuna immagine mancante (tra quelle del corpo post)")

    # check HTTP 200 su immagini Pages (solo un sample)
    bad_dst = []
    for u in dst_imgs:
        # Se è relativo /perladieta/assets/..., promuovi a URL assoluto
        if u.startswith("/"):
            u_abs = "https://adacaccia.github.io" + u
        else:
            u_abs = u
        if not http_ok(u_abs):
            bad_dst.append(u)
    if bad_dst:
        print(f"[HTTP] Immagini Pages non raggiungibili: {len(bad_dst)} (prime 5)")
        for u in bad_dst[:5]:
            print("   -", u)
    else:
        print("[HTTP] OK: immagini Pages rispondono")

    # CSV opzionale
    if csv_out:
        with open(csv_out, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["kind","url"])
            for u in src_imgs: w.writerow(["blogger_img", u])
            for u in dst_imgs: w.writerow(["pages_img", u])
            for u in blogspot_links: w.writerow(["pages_blogspot_link", u])
        print(f"[CSV] Scritto: {csv_out}")

if __name__ == "__main__":
    import os
    if len(sys.argv) < 2:
        print("Uso: python tools/qa_compare.py <blogger_url> [pages_url] [csv_out]")
        sys.exit(1)
    blog = sys.argv[1]
    pages = sys.argv[2] if len(sys.argv) >= 3 else None
    csv_out = sys.argv[3] if len(sys.argv) >= 4 else None
    run_check(blog, pages, csv_out)
