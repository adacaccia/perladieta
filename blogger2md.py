#!/usr/bin/env python3
# blogger2md.py — Scarica una o più pagine Blogger, epura rumore, estrae il BODY
# e salva Markdown con front-matter YAML (data originale).
# Input consigliato (batch): righe "URL | DATA_ORIG_ITA"
# Esempio: https://.../la-verita-sulla-vitamina-d.html | sabato 21 gennaio 2012

import sys, re, datetime, pathlib
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from slugify import slugify
from markdownify import markdownify as md

IT_MONTHS = {
    "gennaio":1, "febbraio":2, "marzo":3, "aprile":4, "maggio":5, "giugno":6,
    "luglio":7, "agosto":8, "settembre":9, "ottobre":10, "novembre":11, "dicembre":12
}
IT_TRASH = {"lunedì","martedì","mercoledì","giovedì","venerdì","sabato","domenica",
            "lunedi","martedi","mercoledi","giovedi","venerdi",
            "di","del","de","il","la","le","lo","i","gli","–","-"}

def parse_it_date(s: str) -> str:
    """'sabato 21 gennaio 2012' -> '2012-01-21' (fallback a oggi se non interpretabile)."""
    if not s:
        return datetime.date.today().isoformat()
    t = re.sub(r"[,\.\u00A0]", " ", s.strip().lower())
    parts = [p for p in t.split() if p and p not in IT_TRASH]
    day = month = year = None

    # pattern tipici: 21 gennaio 2012  |  5 maggio 2013
    for i, tok in enumerate(parts):
        if tok.isdigit() and 1 <= len(tok) <= 2 and day is None:
            # es: 21 gennaio 2012
            if i+2 < len(parts) and parts[i+1] in IT_MONTHS and re.fullmatch(r"\d{4}", parts[i+2]):
                day = int(tok); month = IT_MONTHS[parts[i+1]]; year = int(parts[i+2]); break
        if tok in IT_MONTHS and i > 0 and parts[i-1].isdigit() and i+1 < len(parts) and re.fullmatch(r"\d{4}", parts[i+1]):
            # es: 5 maggio 2013
            day = int(parts[i-1]); month = IT_MONTHS[tok]; year = int(parts[i+1]); break

    try:
        return datetime.date(year, month, day).isoformat()
    except Exception:
        # fallback robusto
        yy = next((int(x) for x in parts if re.fullmatch(r"\d{4}", x)), datetime.date.today().year)
        mm = next((IT_MONTHS[x] for x in parts if x in IT_MONTHS), 1)
        dd = next((int(x) for x in parts if x.isdigit() and 1 <= int(x) <= 31), 1)
        try:
            return datetime.date(yy, mm, dd).isoformat()
        except Exception:
            return datetime.date.today().isoformat()

def fetch(url:str)->str:
    r = requests.get(url, timeout=25, headers={"User-Agent":"Mozilla/5.0"})
    r.raise_for_status()
    return r.text

def remove_noise(soup: BeautifulSoup):
    # rimuovi elementi rumorosi noti (Blogger) a livello documento
    for sel in [
        "header","nav","footer","aside",".sidebar",".widget",".comments",
        ".post-meta",".share-buttons",".post-footer",".blog-pager",
        "script","style","noscript","iframe","form","ins","ads","advert"
    ]:
        for tag in soup.select(sel):
            tag.decompose()

def pick_title(soup: BeautifulSoup) -> str:
    cand = soup.select_one("h1.post-title, h2.post-title, h3.post-title")
    if cand: 
        t = cand.get_text(" ", strip=True)
        if t: return t
    if soup.title and soup.title.string:
        return soup.title.get_text(" ", strip=True)
    return "Senza titolo"

def find_body_container(soup: BeautifulSoup) -> BeautifulSoup:
    """
    Selezione robusta del corpo:
    1) .post-body (Blogger classico)
    2) .post-body.entry-content / article
    3) main
    4) ultimo grande container con testo (heuristic)
    5) fallback: <body> intero epurato
    """
    for sel in [".post-body", ".post-body.entry-content", "article", "main"]:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            return el

    # Heuristica: il div con più testo utile
    candidates = soup.find_all(["div","section"], recursive=True)
    best = None; best_len = 0
    for c in candidates:
        txt = c.get_text(" ", strip=True)
        # scarta contenitori troppo generici
        if not txt or len(txt) < 200:  # evita frammenti microscopici
            continue
        # penalizza se contiene molte liste di link
        link_density = len(c.find_all("a")) / max(len(txt), 1)
        score = len(txt) - (link_density * 500)
        if score > best_len:
            best = c; best_len = score
    if best:
        return best

    # Ultimo fallback: body
    return soup.body or soup

def absolutize_links(el: BeautifulSoup, base: str):
    # immagini
    for img in el.select("img"):
        src = img.get("src") or img.get("data-src")
        if not src: 
            img.decompose(); continue
        img["src"] = urljoin(base, src.split("?")[0])
        if not img.get("alt"): img["alt"] = "fig"
    # link
    for a in el.select("a[href]"):
        a["href"] = urljoin(base, a["href"])

def html_to_markdown(el: BeautifulSoup) -> str:
    # Converti a Markdown senza strip dei link
    m = md(str(el), heading_style="ATX")
    # pulizia righe in eccesso
    m = re.sub(r"\n{3,}", "\n\n", m).strip()
    return m

def save_md(title, md_body, original_url, date_iso, outdir: pathlib.Path):
    slug = slugify(title)[:80] or "post"
    front_yaml = f"""---
layout: post
title: "{title.replace('"', '\\"')}"
date: {date_iso}
original_url: "{original_url}"
tags:
  - restauro
  - perladieta
---
"""
    content = f"{front_yaml}\n{md_body}\n"
    outdir.mkdir(exist_ok=True, parents=True)
    outpath = outdir / f"{slug}.md"
    outpath.write_text(content, encoding="utf-8")
    return outpath

def process_one(url: str, date_text: str, outdir: pathlib.Path):
    html = fetch(url)
    soup = BeautifulSoup(html, "html.parser")

    # 1) titolo
    title = pick_title(soup)

    # 2) epura rumore e trova body
    remove_noise(soup)
    body = find_body_container(soup)

    # 3) normalizza risorse
    absolutize_links(body, url)

    # 4) html -> md
    md_body = html_to_markdown(body)

    # 5) se ancora vuoto, fallback brutale: usa <article> o <body> crude
    if not md_body or len(md_body) < 120:
        fallback = soup.select_one("article") or soup.body or soup
        absolutize_links(fallback, url)
        md_body = html_to_markdown(fallback)

    # 6) parse data ITA
    date_iso = parse_it_date(date_text)

    # 7) salva
    path = save_md(title, md_body, url, date_iso, outdir)
    print(f"✓ {path}  ({date_iso})  [{len(md_body)} chars]")

def main():
    if len(sys.argv) < 2:
        print("Uso:")
        print("  blogger2md.py --batch file.txt   # righe: URL | DATA_ORIG_ITA")
        print("  blogger2md.py 'URL | DATA_ORIG_ITA'  # singolo")
        sys.exit(1)

    outdir = pathlib.Path("_perladieta")  # << collection Jekyll
    if sys.argv[1] == "--batch":
        lines = pathlib.Path(sys.argv[2]).read_text(encoding="utf-8").splitlines()
        for line in lines:
            if not line.strip(): 
                continue
            if "|" not in line:
                print(f"! Riga senza '|': {line}"); 
                continue
            url, date_text = [x.strip() for x in line.split("|", 1)]
            process_one(url, date_text, outdir)
    else:
        line = " ".join(sys.argv[1:])
        if "|" not in line:
            print("Errore: passa 'URL | DATA_ORIG_ITA' oppure usa --batch file.txt")
            sys.exit(2)
        url, date_text = [x.strip() for x in line.split("|", 1)]
        process_one(url, date_text, outdir)

if __name__ == "__main__":
    main()
