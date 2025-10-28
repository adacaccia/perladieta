#!/usr/bin/env python3
# blogger2md.py — pull HTML, epura parti Blogger, salva .md con data originale
import sys, re, datetime, pathlib, json
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from slugify import slugify
from markdownify import markdownify as md

IT_MONTHS = {
    "gennaio":1, "febbraio":2, "marzo":3, "aprile":4, "maggio":5, "giugno":6,
    "luglio":7, "agosto":8, "settembre":9, "ottobre":10, "novembre":11, "dicembre":12
}
# parole da ignorare (giorni settimana, preposizioni)
IT_TRASH = {"lunedì","martedì","mercoledì","giovedì","venerdì","sabato","domenica",
            "lunedi","martedi","mercoledi","giovedi","venerdi",
            "di","del","de","il","la","le","lo","i","gli","–","-"}

def parse_it_date(s: str) -> str:
    """Parsa date italiane tipo 'sabato 21 gennaio 2012' -> '2012-01-21'."""
    if not s:  # fallback oggi
        return datetime.date.today().isoformat()
    t = re.sub(r"[,\.\u00A0]", " ", s.strip().lower())
    parts = [p for p in t.split() if p and p not in IT_TRASH]
    # cerca pattern tipico: <giorno> <mese> <anno>
    day = month = year = None
    for i, token in enumerate(parts):
        if token.isdigit() and len(token) <= 2 and day is None:
            day = int(token)
            # mese dovrebbe seguire
            if i+1 < len(parts) and parts[i+1] in IT_MONTHS:
                month = IT_MONTHS[parts[i+1]]
                # anno dopo
                if i+2 < len(parts) and re.fullmatch(r"\d{4}", parts[i+2]):
                    year = int(parts[i+2])
                    break
        # gestisci formato “5 maggio 2013” (senza weekday)
        if token in IT_MONTHS and i>0 and parts[i-1].isdigit() and i+1 < len(parts) and re.fullmatch(r"\d{4}", parts[i+1]):
            day = int(parts[i-1]); month = IT_MONTHS[token]; year = int(parts[i+1]); break
    try:
        return datetime.date(year, month, day).isoformat()
    except Exception:
        # fallback: cerca qualunque anno, mese italiano e giorno
        yy = next((int(x) for x in parts if re.fullmatch(r"\d{4}", x)), datetime.date.today().year)
        mm = next((IT_MONTHS[x] for x in parts if x in IT_MONTHS), 1)
        dd = next((int(x) for x in parts if x.isdigit() and 1 <= int(x) <= 31), 1)
        try:
            return datetime.date(yy, mm, dd).isoformat()
        except Exception:
            return datetime.date.today().isoformat()

def fetch(url:str)->str:
    r = requests.get(url, timeout=20, headers={"User-Agent":"Mozilla/5.0"})
    r.raise_for_status()
    return r.text

def clean_to_md(html:str, base_url:str):
    soup = BeautifulSoup(html, "html.parser")
    title_el = soup.select_one("h1.post-title, h2.post-title, h3.post-title") or soup.title
    title = (title_el.get_text(strip=True) if title_el else "Senza titolo") or "Senza titolo"
    # corpo
    body = soup.select_one(".post-body, .post-body.entry-content, article") or soup.select_one("main") or soup
    # epurazione elementi rumorosi a livello generale
    for sel in ["header","nav","footer","aside",".sidebar",".widget",".comments",
                ".post-meta","script","style","noscript",".share-buttons",
                ".post-footer",".blog-pager"]:
        for tag in soup.select(sel):
            tag.decompose()
    # normalizza immagini nel corpo
    for img in body.select("img"):
        src = img.get("src") or img.get("data-src")
        if not src:
            img.decompose(); continue
        img["src"] = urljoin(base_url, src.split("?")[0])
        if not img.get("alt"): img["alt"] = "fig"
    # link assoluti
    for a in body.select("a[href]"):
        a["href"] = urljoin(base_url, a["href"])
    # html -> md
    md_body = md(str(body), heading_style="ATX", strip=["a"])
    md_body = re.sub(r"\n{3,}", "\n\n", md_body).strip()
    return title, md_body

def save_md(title:str, md_body:str, original_url:str, date_iso:str, outdir:pathlib.Path):
    slug = slugify(title)[:80] or "post"
    front = {
        "title": title,
        "date": date_iso,                 # << data ORIGINALE
        "original_url": original_url,     # per backlink all'articolo Blogger
        "layout": "post",
        "tags": ["restauro","perladieta"]
    }
    content = f"---\n{json.dumps(front, ensure_ascii=False, indent=2)}\n---\n\n{md_body}\n"
    outpath = outdir / f"{slug}.md"
    outdir.mkdir(exist_ok=True)
    outpath.write_text(content, encoding="utf-8")
    return outpath

def process_one(url:str, date_text:str, outdir:pathlib.Path):
    html = fetch(url)
    title, md_body = clean_to_md(html, url)
    date_iso = parse_it_date(date_text)
    path = save_md(title, md_body, url, date_iso, outdir)
    print(f"✓ {path}  ({date_iso})")

def main():
    if len(sys.argv) < 2:
        print("Uso:")
        print("  blogger2md.py --batch file.txt   # righe: URL | DATA_ORIG(IT)")
        print("  blogger2md.py URL | DATA_ORIG    # singolo, da stdin: 'URL | DATA'")
        sys.exit(1)

    outdir = pathlib.Path("export_md")
    if sys.argv[1] == "--batch":
        infile = pathlib.Path(sys.argv[2]).read_text(encoding="utf-8").splitlines()
        for line in infile:
            if not line.strip(): continue
            if "|" not in line:
                print(f"! Riga senza separatore '|': {line}"); continue
            url, date_text = [x.strip() for x in line.split("|", 1)]
            process_one(url, date_text, outdir)
    else:
        # modo rapido: passare tutta la riga "URL | DATA" come unico argomento
        line = " ".join(sys.argv[1:])
        if "|" not in line:
            print("Errore: passa 'URL | DATA_ORIG' oppure usa --batch file.txt")
            sys.exit(2)
        url, date_text = [x.strip() for x in line.split("|", 1)]
        process_one(url, date_text, outdir)

if __name__ == "__main__":
    main()
