import os, re, json, hashlib, datetime, requests, feedparser
from bs4 import BeautifulSoup
from slugify import slugify
from markdownify import markdownify as md

FEED_URL = os.environ.get("BLOGGER_FEED_URL", "https://perladieta.blogspot.com/feeds/posts/default?alt=rss")
OUT_DIR = os.environ.get("OUT_DIR", "_posts")
ASSETS_DIR = os.path.join(OUT_DIR, "_assets")
CACHE_FEED = "data/feed.xml"
MEDIA_MAP = "data/media_map.json"
DOWNLOAD_MEDIA = os.environ.get("DOWNLOAD_MEDIA", "0") == "1"

def ensure_dirs():
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs("data", exist_ok=True)
    if DOWNLOAD_MEDIA:
        os.makedirs(ASSETS_DIR, exist_ok=True)

def load_media_map():
    if os.path.exists(MEDIA_MAP):
        return json.load(open(MEDIA_MAP, "r", encoding="utf-8"))
    return {}

def save_media_map(m):
    json.dump(m, open(MEDIA_MAP, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

def fetch_feed():
    r = requests.get(FEED_URL, timeout=30)
    r.raise_for_status()
    with open(CACHE_FEED, "wb") as f:
        f.write(r.content)
    return feedparser.parse(r.content)

def sanitize_html_to_md(html):
    # opzionale: micro-fix prima della conversione
    return md(html, strip=["script", "style"])

def localize_images_and_links(html, media_map):
    soup = BeautifulSoup(html, "html.parser")
    changed = False

    for img in soup.find_all("img"):
        src = img.get("src")
        if not src: 
            continue
        if DOWNLOAD_MEDIA:
            if src not in media_map:
                # scarica
                fn = hashlib.sha1(src.encode("utf-8")).hexdigest() + os.path.splitext(src.split("?")[0])[-1]
                local_path = os.path.join(ASSETS_DIR, fn)
                try:
                    resp = requests.get(src, timeout=30)
                    resp.raise_for_status()
                    with open(local_path, "wb") as f:
                        f.write(resp.content)
                    media_map[src] = f"_assets/{fn}"
                    changed = True
                except Exception:
                    # fallback: lascia URL originale
                    pass
            # usa path locale se presente
            if src in media_map:
                img["src"] = media_map[src]
                changed = True

    # altri fix link se vuoi…

    return str(soup), changed

def write_post(entry, media_map):
    title = entry.get("title", "Senza titolo")
    dt = entry.get("published_parsed") or entry.get("updated_parsed")
    if dt:
        date = datetime.datetime(*dt[:6])
    else:
        date = datetime.datetime.now()

    slug = slugify(title) or hashlib.sha1(title.encode("utf-8")).hexdigest()[:8]
    y = str(date.year)
    md_name = f"{date:%Y-%m-%d}-{slug}.md"
    out_dir = os.path.join(OUT_DIR, y)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, md_name)

    original_url = entry.get("link", "")
    tags = [t["term"] for t in entry.get("tags", [])] if "tags" in entry else []

    content_html = entry.get("content", [{}])[0].get("value", entry.get("summary", ""))
    content_html, changed_media = localize_images_and_links(content_html, media_map)
    body_md = sanitize_html_to_md(content_html).strip()

    safe_title = title.replace('"', "'")
    front_matter = (
        "---\n"
        f'title: "{safe_title}"\n'
        f"date: {date.isoformat()}\n"
        f"slug: \"{slug}\"\n"
        f"tags: {tags}\n"
        f"original_url: \"{original_url}\"\n"
        "draft: false\n"
        "---\n\n"
    )

    new_text = front_matter + body_md + "\n"
    old_text = open(out_path, "r", encoding="utf-8").read() if os.path.exists(out_path) else None
    if old_text != new_text:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(new_text)
        return True, changed_media
    return False, changed_media

def main():
    ensure_dirs()
    media_map = load_media_map()
    feed = fetch_feed()
    changed_any = False
    changed_media = False
    for entry in feed.entries:
        chg, chg_media = write_post(entry, media_map)
        changed_any |= chg
        changed_media |= chg_media
    if changed_media:
        save_media_map(media_map)
    print("DONE; changes:", changed_any)

if __name__ == "__main__":
    main()
