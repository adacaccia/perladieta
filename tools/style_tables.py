#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, re, shutil, sys, argparse

POSTS_DIR = "_posts"
BACKUP_DIR = "data/styled_backups"

CATEGORIES = {
    "verdura":  "type-verdura",
    "verdure":  "type-verdura",
    "frutta":   "type-frutta",
    "legumi":   "type-legumi",
    "cereali":  "type-cereali",
    "semi":     "type-semi",
    "semi oleaginosi": "type-semi",
    "noci":     "type-noci",
    "frutta secca": "type-noci",
}

X_PAT = re.compile(r'[xX×✕✖︎]', re.U)

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

def split_table_row(line: str):
    core = line.strip()
    if '|' not in core: return None
    if core.startswith('|'): core = core[1:]
    if core.endswith('|'): core = core[:-1]
    return [c.strip() for c in core.split('|')]

def detect_category_from_header_first_cell(header_line: str) -> str | None:
    cells = split_table_row(header_line) or []
    if not cells: return None
    first = re.sub(r'(\*\*|__|\*|_)', '', cells[0]).strip().lower()
    for key, cls in CATEGORIES.items():
        if key in first:
            return cls
    return None

def nearest_category_above(lines, start_idx):
    for k in range(start_idx-1, max(-1, start_idx-6), -1):
        text = lines[k].strip().lower()
        if not text:
            continue
        t = re.sub(r'^[#>\*\s]+', '', text)
        for label, cls in CATEGORIES.items():
            if label in t:
                return cls
        m = re.search(r'<!--\s*type:\s*([a-z\- ]+)\s*-->', text)
        if m:
            custom = m.group(1).strip()
            for label, cls in CATEGORIES.items():
                if label in custom:
                    return cls
            return f"type-{custom.replace(' ','-')}"
    return None

def sanitize_cell_text_for_x(s: str) -> str:
    """
    Normalizza il contenuto della cella per rilevare la presenza di 'X'
    anche se formattata (bold/italic) o racchiusa in HTML.
    """
    # rimuovi tag HTML semplici
    s2 = re.sub(r'<[^>]+>', '', s)
    # rimuovi enfasi markdown ** __ * _
    s2 = re.sub(r'(\*\*|__|\*|_)', '', s2)
    # trim
    return s2.strip()

def process_seasons_tables(body: str, debug=False, file_path="") -> tuple[str, bool]:
    lines = body.splitlines(keepends=False)
    out = []
    i = 0
    changed = False
    tbl_idx = 0

    while i < len(lines):
        line = lines[i]
        if '|' in line and i+1 < len(lines) and is_md_table_sep(lines[i+1]):
            header = line
            sep = lines[i+1]
            rows = []
            j = i+2
            while j < len(lines) and '|' in lines[j]:
                rows.append(lines[j]); j += 1
            # ... dopo:
            # header = line
            # sep = lines[i+1]
            # rows = [...]  (già raccolte)

            # ❶ Se l'header è “vuoto”, promuovi la prima riga di rows a header
            hdr_cells = split_table_row(header) or []
            if hdr_cells and all(c.strip() == "" for c in hdr_cells):
                if rows:
                    header = rows[0]
                    rows = rows[1:]
                    hdr_cells = split_table_row(header) or []
                    if debug:
                        print(f"[DBG]  -> empty header fixed: new header={hdr_cells!r}")

            tbl_idx += 1
            hdr_cells = split_table_row(header) or []
            if debug:
                print(f"[DBG] {file_path} table#{tbl_idx}: header={hdr_cells!r}")

            # categoria dalla 1ª cella dell'header, altrimenti cerca sopra
            cat_cls = detect_category_from_header_first_cell(header)
            if not cat_cls:
                cat_cls = current_cat
                if debug:
                    print(f"[DBG]  -> category from above: {cat_cls}")
            if not cat_cls:
                if debug:
                    print(f"[DBG]  -> skip: no category detected")
                out.append(line); i += 1; continue

            # wrappa X (colonne dalla 2 in poi)
            new_rows = []
            x_hits = 0
            for r in rows:
                cells = split_table_row(r) or []
                if not cells:
                    new_rows.append(r); continue
                for idx in range(1, len(cells)):
                    probe = sanitize_cell_text_for_x(cells[idx])  # togli markup
                    if X_PAT.search(probe):  # CERCA (non fullmatch)
                        cells[idx] = '<span class="in-season">X</span>'
                        x_hits += 1
                new_rows.append("| " + " | ".join(cells) + " |")
            rows = new_rows

            if x_hits == 0 and debug:
                print(f"[DBG]  -> no X found in rows (still adding class)")

            out.append(header)
            out.append(sep)
            out.extend(rows)
            out.append("{:.table-seasons " + cat_cls + "}")
            changed = True
            if debug:
                print(f"[DBG]  -> styled with class: .table-seasons {cat_cls}, x_cells={x_hits}")
            i = j
            continue

        out.append(line); i += 1

    return ("\n".join(out), changed)

def process_file(path: str, debug=False) -> bool:
    with open(path, "r", encoding="utf-8") as f:
        full = f.read()
    fm, body = split_front_matter(full)
    new_body, chg = process_seasons_tables(body, debug=debug, file_path=path)
    if chg and new_body != body:
        backup_path = os.path.join(BACKUP_DIR, os.path.relpath(path, POSTS_DIR))
        os.makedirs(os.path.dirname(backup_path), exist_ok=True)
        shutil.copy2(path, backup_path)
        with open(path, "w", encoding="utf-8") as f:
            f.write(fm + new_body)
        return True
    return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--debug", action="store_true", help="stampa dettagli sulle tabelle rilevate")
    ap.add_argument("paths", nargs="*", help="file o directory da processare (default: _posts)")
    args = ap.parse_args()

    targets = []
    if args.paths:
        for p in args.paths:
            if os.path.isdir(p):
                for root, _, files in os.walk(p):
                    for fn in files:
                        if fn.endswith(".md"):
                            targets.append(os.path.join(root, fn))
            elif p.endswith(".md"):
                targets.append(p)
    else:
        for root, _, files in os.walk(POSTS_DIR):
            for fn in files:
                if fn.endswith(".md"):
                    targets.append(os.path.join(root, fn))

    os.makedirs(BACKUP_DIR, exist_ok=True)
    scanned = changed = 0
    for path in sorted(targets):
        scanned += 1
        if process_file(path, debug=args.debug):
            changed += 1

    print(f"[STYLE] scanned={scanned} changed={changed} backups_dir={BACKUP_DIR}")

if __name__ == "__main__":
    main()
