# Per la dieta 🥗

Backup evolutivo del blog [perladieta.blogspot.com](https://perladieta.blogspot.com)  
Pubblicato come mirror statico su [https://adacaccia.github.io/perladieta/](https://adacaccia.github.io/perladieta/)

---

## 📦 Struttura
- `_includes/` - file di supporto per layout Jekill
- `_layouts/` – configurazione layout pagine per Jekill
- `_posts/` – tutti i post convertiti da Blogger in Markdown (con front matter YAML)
- `assets/` – immagini locali scaricate dai post originali
- `tools/` – script di conversione, aggiornamento e gestione posts
- `_config.yml` – configurazione Jekyll per GitHub Pages
- `index.md` – indice navigabile dei post
- `requirements.txt` – elenco dipendenze per gli script Python

---

## ⚙️ Conversione manuale

```bash
BLOGGER_FEED_URL="https://perladieta.blogspot.com/feeds/posts/default?alt=rss" \
OUT_DIR="_posts" \
DOWNLOAD_MEDIA=1 \
python tools/blogger2md.py
```
---

# QA e manutenzione di *Per la Dieta*

Il controllo qualità e la manutenzione dei post sono gestiti tramite gli script Python nella directory `tools/`.

---

## 🧪 Verifica completa dei post

```bash
python tools/qa_compare.py "https://perladieta.blogspot.com/feeds/posts/default?alt=rss"
```

Confronta ogni post del mirror con la versione originale Blogger, verificando:

- presenza e correttezza delle immagini (download e mapping da `media_map.json`);
- aggiornamento dei link interni (da `url_map.json`);
- eventuali errori di parsing HTML.

---

## 🔗 Riparazione automatica dei link

```bash
python tools/repair_links.py
```

Riscrive i link interni nei file `.md` in base alla mappa aggiornata (`data/url_map.json`).

---

## 🎨 Aggiornamento degli stili (post-processor)

```bash
python tools/style_tables.py
```

Applica classi e formattazione alle tabelle per PRAL, stagioni e nutrienti, mantenendo un backup in `data/styled_backups/`.

---

## ✅ Verifica finale

```bash
grep -R "perladieta.blogspot" -n _posts | grep -v "original_url" || echo "OK: nessun link esterno residuo"
```

---

## 🔁 Rebuild

Dopo modifiche sostanziali:

```bash
git add -A && git commit -m "Aggiornamento QA" && git push
```

GitHub Pages rigenera automaticamente il sito in 1–2 minuti.
