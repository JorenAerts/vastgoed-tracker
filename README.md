# vastgoed-tracker

Dagelijkse wijzigingsmonitor voor ~42 vastgoedkantoren rond Hasselt. Een
GitHub Actions job checkt elke dag alle sites, publiceert wijzigingen als
RSS-items in `docs/feed.xml`, en GitHub Pages serveert die feed publiek.
Abonneer via [Blogtrottr](https://blogtrottr.com) op de feed-URL voor een
dagelijkse digest-mail.

## Setup (eenmalig)

1. **Pages aanzetten**: repo-instellingen op github.com -> **Pages** ->
   "Deploy from a branch" -> branch `main`, map `/docs` -> Save.
   Feed komt dan op `https://<gebruiker>.github.io/<repo>/feed.xml`.
2. **Blogtrottr**: nieuwe feed toevoegen met die URL, "daily digest" kiezen,
   e-mailadres bevestigen.
3. Workflow draait automatisch elke dag (~07-08u Belgische tijd), of
   handmatig via het "Run workflow"-knopje onder Actions.

## Lokaal draaien

```bash
pip install -r requirements.txt
python scripts/check_sites.py
```

Eerste run per site slaat enkel een baseline op (geen RSS-item). Vanaf de
tweede run genereert een gewijzigde site een item in `docs/feed.xml`.

## Site toevoegen of verwijderen

Bewerk `sites.json` (lijst van `{"name": ..., "url": ...}`). Nieuwe sites
krijgen bij de eerstvolgende run automatisch een baseline-entry in
`state/snapshots.json`, zonder meteen een RSS-item te triggeren.

## Bekende beperkingen

- Sommige sites blokkeren scraping (bv. Cloudflare-bescherming). Dat uit
  zich als een herhaalde "kon ... niet meer bereiken"-melding na 3
  opeenvolgende mislukte dagen, niet als een crash van het script.
- Dit is een **publieke** repo (vereist voor gratis GitHub Pages). De
  kantorenlijst en feed zijn dus door iedereen met de URL te vinden, al
  wordt de repo nergens gelinkt.
- Items ouder dan 60 dagen worden automatisch uit de feed opgeruimd.
