#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, json, re, sys
import yaml

URL_MAP_PATH = "data/url_map.json"

def split_front_matter(text: str):
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return "", text
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "".join(lines[:i+1]), "".join(lines[i+1:])
    return "", text

def load_url_map():
    with open(URL_MAP_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def restore_original_urls():
    url_map = load_url_map()
    if not url_map:
        print("[ERR] url_map.json vuota")
        sys.exit(1)
    # inverti: value (Pages URL) -> set(keys originali)
    inv = {}
    for k, v in url_map.items():
        inv.setdefault(v, set()).add(k)

    changed = 0
    scanned = 0
    for root, _, files in os.walk("_posts"):
        for fn in files:
            if not fn.endswith(".md"):
                continue
            scanned += 1
            path = os.path.join(root, fn)
            with open(path, "r", encoding="utf-8") as f:
                full = f.read()
            fm, body = split_front_matter(full)
            if not fm:
                continue
            # parse YAML
            fm_inner = fm.split("\n",1)[1].rsplit("\n---",1)[0]
            data = yaml.safe_load(fm_inner) or {}
            orig = data.get("original_url")

            # Caso da riparare: original_url è stato trasformato in /perladieta/....
            if isinstance(orig, str) and orig.startswith("/perladieta/"):
                pages_url = orig
                # prova a risalire alla chiave originale
                keys = sorted(inv.get(pages_url, []))
                # se troviamo una sola chiave 'path' (tipo /YYYY/MM/slug.html), ricostruiamo l'URL canonico .com
                key_path = None
                for k in keys:
                    if k.startswith("/"):
                        key_path = k
                        break
                if key_path:
                    data["original_url"] = f"https://perladieta.blogspot.com{key_path}"
                    # riscrivi il front matter conservando body
                    new_fm = "---\n" + yaml.safe_dump(data, allow_unicode=True, sort_keys=False) + "---\n"
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(new_fm + body)
                    changed += 1

    print(f"[RESTORE] scanned={scanned} fixed={changed}")

if __name__ == "__main__":
    restore_original_urls()
