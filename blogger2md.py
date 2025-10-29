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
CONSENT = {"CONSENT": "YES+1"}  # bypass interstitial EU

def bs(html: str):
    try:
        # se hai lxml installato è più solido
        from lxml import etree  # noqa
        return BeautifulSoup(html, "lxml")
    except Exception:
        return BeautifulSoup(html, "html.parser")

def fetch_html(url: str) -> str:
    r = requests.get(url, timeout=25, headers=UA, cookies=CONSENT)
    r.raise_for_status()
    return r.text

def get_soup_with_fallback(url: str):
    html = fetch_html(url)
    soup = bs(html)
    if body_has_text(soup, strict=False):
        return soup, url, html

    murl = url if url.endswith("?m=1") else (url + ("&m=1" if "?" in url else "?m=1"))
    html_m = fetch_html(murl)
    soup_m = bs(html_m)
    if body_has_text(soup_m, strict=False):
        return soup_m, murl, html_m

    return soup, url, html  # ultimo fallback

def body_has_text(soup: BeautifulSoup, strict: bool = True) -> bool:
    el, _sel = rough_find_body(soup)
    if not el: 
        return False
    txt = el.get_text(" ", strip=True)
    return bool(txt and len(txt) >= (180 if strict else 40))

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
    """
    1) [id^="post-body-"] — pattern Blogger
    2) varianti comuni
    3) main
    4) euristica (contenitore più verboso)
    5) fallback body
    """
    for sel in [
        '[id^="post-body-"]',
        '.post-body.entry-content',
        '.post-body',
        '[itemprop="articleBody"]',
        'article .entry-content',
        'article .post-content',
        'article',
        'main',
        '.post'
    ]:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            return el, sel

    best = None; best_score = 0
    for c in soup.find_all(["div","section"], recursive=True):
        txt = c.get_text(" ", strip=True)
        if not txt or len(txt) < 120:
            continue
        link_density = len(c.find_all("a")) / max(len(txt), 1)
        score = len(txt) - (link_density * 400)
        if score > best_score:
            best = c; best_score = score
    if best:
        return best, "heuristic(div/section)"
    return (soup.body or soup), "fallback(<body>)"

def clean_inside(el: BeautifulSoup):
    for sel in [
        ".share-buttons",".post-footer",".comments",".post-meta",
        "script","style","noscript","iframe","form","ins",".ads","[aria-label='Ads']"
    ]:
        for t in el.select(sel):
            t.decompose()

def absolutize(el: BeautifulSoup, base: str):
    def pick_biggest_from_srcset(srcset: str) -> str:
        # es: "https://.../foo.jpg 320w, https://.../foo_big.jpg 1600w"
        best = None; best_w = -1
        for part in srcset.split(","):
            part = part.strip()
            if not part:
                continue
            bits = part.split()
            url = bits[0]
            w = 0
            if len(bits) > 1 and bits[1].endswith("w"):
                try:
                    w = int(bits[1][:-1])
                except:
                    w = 0
            if w > best_w:
                best, best_w = url, w
        return best or None

    def fix_blogger_img_url(u: str) -> str:
        # forza https per domini Blogger/Google
        u = re.sub(r"^http://", "https://", u)
        # normalizza dimensioni: /s72/ -> /s1600/  |  =s72-c -> =s1600
        u = re.sub(r"/s\d{2,4}(/|$)", r"/s1600\1", u)
        u = re.sub(r"=s\d{2,4}(-[a-z])?", "=s1600", u)
        return u

    # IMG: prendi data-src/srcset/src in ordine di “ricchezza”
    for img in el.select("img"):
        src = None

        # 1) srcset / data-srcset → scegli la più grande
        srcset = img.get("srcset") or img.get("data-srcset")
        if srcset:
            src = pick_biggest_from_srcset(srcset)

        # 2) data-src / data-original come fallback “ricco”
        if not src:
            src = img.get("data-src") or img.get("data-original")

        # 3) src “normale”
        if not src:
            src = img.get("src")

        if not src:
            # ancora niente -> l’immagine è davvero vuota: rimuovi
            img.decompose()
            continue

        # NON rimuovere la query (!) — serve per taglia/host
        full = urljoin(base, src)

        # fix specifici Blogger
        full = fix_blogger_img_url(full)

        # applica src definitivo
        img["src"] = full

        # togli attributi pigri che alcuni viewer ignorano
        for lazy_attr in ["srcset","data-srcset","data-src","data-original","decoding","loading"]:
            if lazy_attr in img.attrs:
                del img.attrs[lazy_attr]

        # alt generico se mancante
        if not img.get("alt"):
            img["alt"] = "fig"

    # Link assoluti (lascia query intatta)
    for a in el.select("a[href]"):
        a["href"] = urljoin(base, a["href"])

def html_to_md(el: BeautifulSoup) -> str:
    m = md(str(el), heading_style="ATX")
    return re.sub(r"\n{3,}", "\n\n", m).strip()

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

def process_one(line: str, outdir: pathlib.Path, debug: bool = False):
    if "|" not in line:
        print(f"! Riga senza '|': {line}"); return
    url, date_text = [x.strip() for x in line.split("|", 1)]

    soup, used_url, raw_html = get_soup_with_fallback(url)
    title = pick_title(soup)

    body, used_sel = rough_find_body(soup)
    if debug:
        dbgdir = pathlib.Path("_debug"); dbgdir.mkdir(exist_ok=True, parents=True)
        (dbgdir / "raw.html").write_text(raw_html, encoding="utf-8")
        (dbgdir / "used_url.txt").write_text(used_url + "\n", encoding="utf-8")

    clean_inside(body)
    absolutize(body, used_url)
    md_body = html_to_md(body)

    if len(md_body) < 180:
        fallback = soup.select_one("article") or soup.body or soup
        clean_inside(fallback)
        absolutize(fallback, used_url)
        md_body = html_to_md(fallback)
        used_sel += " -> fallback(article/body)"

    date_iso = parse_it_date(date_text)
    path = save_md(title, md_body, url, date_iso, outdir)

    if debug:
        (dbgdir / "body.html").write_text(str(body), encoding="utf-8")
        (dbgdir / "body.md").write_text(md_body, encoding="utf-8")
        (dbgdir / "selector.txt").write_text(used_sel + "\n", encoding="utf-8")

    print(f"✓ {path}  ({date_iso})  [{len(md_body)} chars]  via {used_url}  sel={used_sel}")

def main():
    if len(sys.argv) < 2:
        print("Uso:")
        print("  blogger2md.py --batch file.txt [--debug]")
        print("  blogger2md.py 'URL | DATA_ORIG_ITA' [--debug]")
        sys.exit(1)

    debug = False
    args = sys.argv[1:]
    if "--debug" in args:
        debug = True
        args.remove("--debug")

    outdir = pathlib.Path("_perladieta")
    if args[0] == "--batch":
        lines = pathlib.Path(args[1]).read_text(encoding="utf-8").splitlines()
        for line in lines:
            if line.strip(): process_one(line, outdir, debug=debug)
    else:
        process_one(" ".join(args), outdir, debug=debug)

if __name__ == "__main__":
    main()
