#!/usr/bin/env python3
# blogger2md.py — versione robusta con fallback ?m=1 e selettori estesi BODY
import sys, re, datetime, pathlib
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from slugify import slugify
from markdownify import markdownify as md

IT_MONTHS = {
    "gennaio":1,"febbraio":2,"marzo":3,"aprile":4,"maggio":5,"giugno":6,
    "luglio":7,"agosto":8,"settembre":9,"ottobre":10,"novembre":11,"dicembre":12
}
IT_TRASH = {"lunedì","martedì","mercoledì","giovedì","venerdì","sabato","domenica",
            "lunedi","martedi","mercoledi","giovedi","venerdi","di","del","de",
            "il","la","le","lo","i","gli","–","-"}

def parse_it_date(s: str) -> str:
    if not s: return datetime.date.today().isoformat()
    t = re.sub(r"[,\.\u00A0]", " ", s.strip().lower())
    parts = [p for p in t.split() if p and p not in IT_TRASH]
    day = month = year = None
    for i, tok in enumerate(parts):
        if tok.isdigit() and 1 <= len(tok) <= 2 and i+2 < len(parts):
            if parts[i+1] in IT_MONTHS and re.fullmatch(r"\d{4}", parts[i+2]):
                day = int(tok); month = IT_MONTHS[parts[i+1]]; year = int(parts[i+2]); break
        if tok in IT_MONTHS and i>0 and parts[i-1].isdigit() and i+1 < len(parts) and re.fullmatch(r"\d{4}", parts[i+1]):
            day = int(parts[i-1]); month = IT_MONTHS[tok]; year = int(parts[i+1]); break
    try:
        return datetime.date(year, month, day).isoformat()
    except Exception:
        yy = next((int(x) for x in parts if re.fullmatch(r"\d{4}", x)), datetime.date.today().year)
        mm = next((IT_MONTHS[x] for x in parts if x in IT_MONTHS), 1)
        dd = next((int(x) for x in parts if x.isdigit() and 1 <= int(x) <= 31), 1)
        try: return datetime.date(yy, mm, dd).isoformat()
        except Exception: return datetime.date.today().isoformat()

UA = {"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/119 Safari/537.36"}

def fetch_html(url:str)->str:
    r = requests.get(url, timeout=25, headers=UA)
    r.raise_for_status()
    return r.text

def get_soup_with_fallback(url: str) -> tuple[BeautifulSoup, str]:
    # 1) prova URL originale
    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")
    if body_has_text(soup): 
        return soup, url
    # 2) fallback: versione mobile statica
    murl = url if url.endswith("?m=1") else (url + ("&m=1" if "?" in url else "?m=1"))
    html_m = fetch_html(murl)
    soup_m = BeautifulSoup(html_m, "html.parser")
    return (soup_m, murl) if body_has_text(soup_m) else (soup, url)

def body_has_text(soup: BeautifulSoup) -> bool:
    el = rough_find_body(soup)
    return bool(el and el.get_text(strip=True) and len(el.get_text()) > 120)

def remove_noise(soup: BeautifulSoup):
    for sel in [
        "header","nav","footer","aside",".sidebar",".widget",".comments",
        ".post-meta",".share-buttons",".post-footer",".blog-pager",
        "script","style","noscript","iframe","form","ins",".ads","[aria-label='Ads']"
    ]:
        for tag in soup.select(sel):
            tag.decompose()

def pick_title(soup: BeautifulSoup) -> str:
    for sel in ["h1.post-title","h2.post-title","h3.post-title",".entry-title","h1.title"]:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True): return el.get_text(" ", strip=True)
    return soup.title.get_text(" ", strip=True) if soup.title else "Senza titolo"

def rough_find_body(soup: BeautifulSoup):
    # Selettori più comuni Blogger / varianti
    for sel in [
        ".post-body.entry-content",".post-body","[itemprop='articleBody']",
        "article .entry-content","article .post-content","article",
        "#post-body-1","#post-body-0",".post"
    ]:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True): return el
    # fallback: main
    el = soup.select_one("main")
    if el and el.get_text(strip=True): return el
    # heuristica: div/section più “verboso”
    best = None; best_len = 0
    for c in soup.find_all(["div","section"], recursive=True):
        txt = c.get_text(" ", strip=True)
        if not txt or len(txt) < 200: continue
        link_density = len(c.find_all("a")) / max(len(txt), 1)
        score = len(txt) - (link_density * 500)
        if score > best_len: best = c; best_len = score
    return best or soup.body or soup

def absolutize(el: BeautifulSoup, base: str):
    for img in el.select("img"):
        src = img.get("src") or img.get("data-src")
        if not src: img.decompose(); continue
        img["src"] = urljoin(base, src.split("?")[0])
        if not img.get("alt"): img["alt"] = "fig"
    for a in el.select("a[href]"):
        a["href"] = urljoin(base, a["href"])

def html_to_md(el: BeautifulSoup) -> str:
    m = md(str(el), heading_style="ATX")  # NON strip dei link
    m = re.sub(r"\n{3,}", "\n\n", m).strip()
    return m

def save_md(title, md_body, original_url, date_iso, outdir: pathlib.Path):
    slug = slugify(title)[:80] or "post"
    front = f"""---
layout: post
title: "{title.replace('"','\\"')}"
date: {date_iso}
original_url: "{original_url}"
tags:
  - restauro
  - perladieta
---
"""
    outdir.mkdir(exist_ok=True, parents=True)
    p = outdir / f"{slug}.md"
    p.write_text(front + "\n" + md_body + "\n", encoding="utf-8")
    return p

def process_one(line: str, outdir: pathlib.Path):
    if "|" not in line:
        print(f"! Riga senza '|': {line}"); return
    url, date_text = [x.strip() for x in line.split("|", 1)]
    soup, used_url = get_soup_with_fallback(url)
    remove_noise(soup)
    body = rough_find_body(soup)
    absolutize(body, used_url)
    md_body = html_to_md(body)
    # fallback finale: se ancora corto, prendi direttamente <article> o <body> non puliti
    if len(md_body) < 200:
        fallback = soup.select_one("article") or soup.body or soup
        absolutize(fallback, used_url)
        md_body = html_to_md(fallback)
    title = pick_title(soup)
    date_iso = parse_it_date(date_text)
    path = save_md(title, md_body, url, date_iso, outdir)
    print(f"✓ {path}  ({date_iso})  [{len(md_body)} chars]  via {used_url}")

def main():
    if len(sys.argv) < 2:
        print("Uso:")
        print("  blogger2md.py --batch file.txt   # righe: URL | DATA_ORIG_ITA")
        print("  blogger2md.py 'URL | DATA_ORIG_ITA'  # singolo")
        sys.exit(1)
    outdir = pathlib.Path("_perladieta")
    if sys.argv[1] == "--batch":
        lines = pathlib.Path(sys.argv[2]).read_text(encoding="utf-8").splitlines()
        for line in lines:
            if line.strip(): process_one(line, outdir)
    else:
        process_one(" ".join(sys.argv[1:]), outdir)

if __name__ == "__main__":
    main()
