# 📚 Standard Citazioni Perladieta v2.0

## 1. Struttura generale
Ogni citazione deve contenere:
- **Autore o Ente** — nome completo.
- **Anno di pubblicazione o aggiornamento.**
- **Titolo sintetico** — comprensibile e descrittivo.
- **Fonte o riferimento** — URL, DOI, o indicazione bibliografica verificabile.
- **Categoria di affidabilità** — A (istituzionale/scientifica), B (divulgativa solida), C (non raccomandata).
- **Data ultima verifica** — quando la fonte è stata controllata.

Esempio:
> *“Una dieta mediterranea ricca di verdure e legumi riduce il rischio cardiovascolare.”*  
> — Harvard T.H. Chan School of Public Health, 2023, *Healthy Eating Plate Guidelines*, [https://www.hsph.harvard.edu/nutritionsource/healthy-eating-plate](https://www.hsph.harvard.edu/nutritionsource/healthy-eating-plate)  
> Categoria: A | Ultima verifica: 2025-11-04  

---

## 2. Linee guida redazionali
- Le **citazioni brevi** (≤20 parole) restano in linea nel testo, seguite dal riferimento tra parentesi.  
- Le **citazioni lunghe o concettuali** vanno in blocco, come sopra.  
- Evitare formule enfatiche (“è dimostrato che...”) se la fonte non è meta-analitica.  
- Specificare sempre **la natura della fonte** (linea guida, revisione sistematica, studio singolo, articolo divulgativo, ecc.).

---

## 3. Criteri di selezione delle fonti
| Categoria | Tipo di fonte | Esempi | Validità |
|------------|----------------|---------|----------|
| **A** | Enti istituzionali, università, riviste peer-reviewed | WHO, EFSA, NIH, Nature, Lancet | ✅ Altissima |
| **B** | Divulgazione scientifica autorevole | Harvard Health, Mayo Clinic, BBC Science | ⚠️ Buona |
| **C** | Blog, social, siti commerciali, fonti senza peer review | MyFitnessPal blog, influencer | ❌ Scartare o sostituire |

---

## 4. Formato sintetico per database interni
```
AUTORE: ...
ANNO: ...
TITOLO: ...
URL/DOI: ...
TIPO_FONTE: ...
AFFIDABILITÀ: ...
ULTIMA_VERIFICA: YYYY-MM-DD
NOTE: ...
```

---

## 5. Controllo automatico (bozza di logica operativa)
**Obiettivo:** individuare citazioni da aggiornare o verificare periodicamente.

| Controllo | Regola | Azione |
|------------|--------|--------|
| Età della fonte | >5 anni dalla pubblicazione | ⚠️ Segnalare come "Da aggiornare" |
| Fonte non verificata | Campo “Ultima verifica” vuoto o >1 anno fa | 🔄 Segnalare come "Da ricontrollare" |
| Categoria C | Blog, influencer, siti non scientifici | ❌ Escludere o sostituire |
| Link non raggiungibile | HTTP 404 o redirect sospetto | 🚫 Segnalare per sostituzione |
| Assenza DOI o URL | Nessun riferimento diretto verificabile | ⚠️ Aggiungere fonte completa |

---

## 6. Aggiornamento periodico consigliato
- Revisione generale **ogni 6 mesi**.
- Aggiornamento automatico con script di verifica URL e anno di pubblicazione.
- Log delle modifiche salvato in `citazioni_log.md` con timestamp e autore revisione.

---

> **Versione:** 2.0  
> **Data:** 2025-11-04  
> **Autore redazionale:** Progetto *Perladieta*
