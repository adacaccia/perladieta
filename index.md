---
layout: default
title: "Per la dieta — Archivio restaurato"
---

# 🥗 Per la dieta — Archivio restaurato
_Serie originale (date storiche) con versione 2025-ready su GitHub Pages._

> Questo archivio conserva i testi originali di *Per la dieta*  
> (data e contenuti “core” invariati) con epurazione tecnica da Blogger  
> e aggiornamenti minimi di citazioni scientifiche.  
> Per la versione originale online: vedi il link “Originale”.

---

<p><small>build: {{ site.time | date: "%Y-%m-%d %H:%M:%S %z" }} · rev: {{ site.github.build_revision | slice: 0,7 }}</small></p>

{% comment %}
Compatibilità Jekyll:
Se non vuoi usare una collection dedicata (`perladieta`), i post in `_posts/` sono
già accessibili come `site.posts`.  
Se invece usi una collection, assicurati che `_config.yml` contenga:

collections:
  perladieta:
    output: true
    permalink: /:collection/:name/
defaults:
  - scope:
      path: "_posts"
      type: perladieta
    values:
      layout: post
{% endcomment %}

{% assign items = site.posts | sort: "date" | reverse %}

{% if items == empty %}
_Ancora nessun articolo importato._  
Metti i file Markdown in `_posts/` con front matter tipo:
```yaml
---
layout: post
title: "La verità sulla vitamina D"
date: 2012-06-15
original_url: "https://perladieta.blogspot.com/2012/06/la-verita-sulla-vitamina-d.html"
tags:
  - vitamina D
  - luce
  - metabolismo
---

```html
<p><small>Post trovati: {{ site.posts | size }}</small></p>
