#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, re, shutil

POSTS_DIR = "_posts"
BACKUP_DIR = "data/styled_backups"

MONTHS_ORDER = ["mar","apr","mag","giu","lug","ago","set","ott","nov","dic","gen","feb"]
CATEGORIES = {
    "verdure": "type-verdure",
    "frutta": "type-frutta",
    "legumi": "type-legumi",
    "cereali": "type-cereali",
    "frutta secca": "type-frutta-secca",
    "semi oleaginosi": "type-semi-oleaginosi",
}

def nearest_category_above(lines, start_idx):
    """Cerca la categoria nel titolo/linea immediatamente sopra la tabella."""
    for k in range(start_idx-1, max(-1, start_idx-6), -1):
        text = lines[k].strip().lower()
        if not text:
            continue
        # header tipo ## Verdure o **Frutta**
        t = re.sub(r'^[#>\*\s]+', '', text)
        for label, cls in CATEGORIES.items():
            if label in t:
                return cls
        # commento manuale: <!-- type: verdure -->
        m = re.search(r'<!--\s*type:\s*([a-z\- ]+)\s*-->', text)
        if m:
            custom = m.group(1).strip()
            # mappa a classe nota se possibile
            for label, cls in CATEGORIES.items():
                if label in custom:
                    return cls
            # fallback: usa come classe così com'è
            return f"type-{custom.replace(' ','-')}"
    return None

def is_md_table_sep(line: str) -> bool:
    return bool(re.match(r'^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$', line))

def split_table_row(line: str):
    core = line.strip()
    if not ('|' in core): return None
    if core.startswith('|'): core = core[1:]
    if core.endswith('|'): core = core[:-1]
    return [c.strip() for c in core.split('|')]

def header_is_months(header_cells):
    cells = [c.lower() for c in header_cells]
    # deve contenere almeno 10-12 mesi della sequenza mar..feb
    found = 0
    for c in cells:
        m3 = c[:3]
        if m3 in MONTHS_ORDER:
            found += 1
    return found >= 10

def process_seasons_tables(body: str) -> str:
    lines = body.splitlines(keepends=False)
    out = []
    i = 0
    changed = False

    while i < len(lines):
        line = lines[i]
        if '|' in line and i+1 < len(lines) and is_md_table_sep(lines[i+1]):
            header = line
            sep = lines[i+1]
            rows = []
            j = i+2
            while j < len(lines) and '|' in lines[j]:
                rows.append(lines[j]); j += 1

            hdr = split_table_row(header) or []
            if not hdr:
                out.extend([line]); i += 1; continue

            # è una tabella stagioni se le intestazioni sono mesi (mar..feb)
            if not header_is_months(hdr[1:]):  # dalla 2ª col in poi
                out.extend([line]); i += 1; continue

            # deduci categoria
            cat_cls = nearest_category_above(lines, i) or "type-verdure"  # default sicuro

            # trasforma le X in <span class="in-season">X</span>
            new_rows = []
            for r in rows:
                cells = split_table_row(r) or []
                if not cells:
                    new_rows.append(r); continue
                # colonne 2..13 sono mesi
                for idx in range(1, min(len(cells), 13)):
                    if re.fullmatch(r'[xX×✕✖︎]\s*', cells[idx]):
                        cells[idx] = '<span class="in-season">X</span>'
                new_rows.append("| " + " | ".join(cells) + " |")
            rows = new_rows

            # emetti tabella + classi kramdown
            out.append(header)
            out.append(sep)
            out.extend(rows)
            out.append("{:.table-seasons " + cat_cls + "}")
            changed = True
            i = j
            continue

        out.append(line); i += 1

    if changed:
        return "\n".join(out)
    return body


def split_front_matter(text: str):
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return "", text
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "".join(lines[:i+1]), "".join(lines[i+1:])
    return "", text

def is_md_table_sep(line: str) -> bool:
    # | --- | :---: | ---: | etc.
    return bool(re.match(r'^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$', line))

def wrap_pral(val: str) -> str:
    s = val.strip()
    # accept comma as decimal
    try:
        x = float(s.replace(',', '.'))
    except Exception:
        return val  # not a number
    cls = "pos" if x > 0 else ("neg" if x < 0 else "zero")
    return f'<span class="pral {cls}">{s}</span>'

def main():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    scanned = changed = 0

    for root, _, files in os.walk(POSTS_DIR):
        for fn in files:
            if not fn.endswith(".md"): continue
            path = os.path.join(root, fn)
            scanned += 1
            with open(path, "r", encoding="utf-8") as f:
                full = f.read()
            fm, body = split_front_matter(full)

            new_body = process_seasons_tables(body)

            if new_body != body:
                # backup 1:1
                backup_path = os.path.join(BACKUP_DIR, os.path.relpath(path, POSTS_DIR))
                os.makedirs(os.path.dirname(backup_path), exist_ok=True)
                shutil.copy2(path, backup_path)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(fm + new_body)
                changed += 1

    print(f"[STYLE] scanned={scanned} changed={changed} backups_dir={BACKUP_DIR}")

if __name__ == "__main__":
    main()
