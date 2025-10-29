---
layout: default
title: "Per la dieta — Archivio restaurato"
---

# Per la dieta — Archivio restaurato
_Serie originale (date storiche) con versione 2025-ready su GitHub Pages._

> Questo archivio conserva i testi originali (data e contenuti core invariati) con epurazione tecnica da Blogger e minimi aggiornamenti di citazioni.
> Per la versione originale online: vedi il link “Originale”.

{% comment %}
Richiede in _config.yml:
collections:
  perladieta:
    output: true
    permalink: /:collection/:name/
defaults:
  - scope: { path: "_posts", type: perladieta }
    values: { layout: post }
{% endcomment %}

{% assign items = site.perladieta | sort: "date" | reverse %}

{% if items == empty %}
_Ancora nessun articolo importato. Metti i file Markdown in `posts/` con front-matter tipo:_
```yaml
---
title: "La verità sulla vitamina D"
date: 2012-06-15
original_url: "https://perladieta.blogspot.com/2012/06/la-verita-sulla-vitamina-d.html"
updated: 2025-10-29
tags: [vitamina D, luce, metabolismo]
---
```
{% endif %}

{% for p in items %}
- **{{ p.date | date: "%Y-%m-%d" }}** — [{{ p.title }}]({{ p.url | relative_url }})
  {% if p.updated %}<small>· aggiornato: {{ p.updated | date: "%Y-%m-%d" }}</small>{% endif %}
  {% if p.original_url %}<br/><small>Originale: <a href="{{ p.original_url }}" rel="noopener" target="_blank">{{ p.original_url }}</a></small>{% endif %}
{% endfor %}

---

## Note editoriali
- **Data**: è la _data storica_ del post (non la data di migrazione).
- **Aggiornato**: opzionale; indica la verifica 2025 (es. citazioni DOI/PMID).
- **Filiera**: contenuto “core” invariato; epurazione solo tecnica (layout, script, widget).
