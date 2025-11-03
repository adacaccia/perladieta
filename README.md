# Per la dieta 🥗

Backup evolutivo del blog [perladieta.blogspot.com](https://perladieta.blogspot.com)  
Pubblicato come mirror statico su [https://adacaccia.github.io/perladieta/](https://adacaccia.github.io/perladieta/)

---

## 📦 Struttura
- `_posts/` – tutti i post convertiti da Blogger in Markdown (con front matter YAML)
- `_assets/` – immagini locali scaricate dai post originali
- `_layouts/` – configurazione layout pagine per Jekill
- `_includes/` - file di supporto per layout Jekill
- `_config.yml` – configurazione Jekyll per GitHub Pages
- `tools/` – script di conversione, aggiornamento e gestione posts
- `index.md` – indice navigabile dei post

---

## ⚙️ Conversione manuale

```bash
BLOGGER_FEED_URL="https://perladieta.blogspot.com/feeds/posts/default?alt=rss" \
OUT_DIR="_posts" \
DOWNLOAD_MEDIA=1 \
python tools/blogger2md.py

