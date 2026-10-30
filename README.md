# Shorts Studio

Výrobní linka pro kanály **What If Institute**, **Stoic Ember** a **Mind Mites**. Z textového souboru s epizodou udělá hotový Short (hlas, animace, titulky, hudba) a z hotových Shorts dlouhé video s kapitolami. Všechno běží zdarma: hlas Kokoro, grafika kreslená kódem, render na GitHub Actions.

## Jak to funguje

```
episodes/<kanál>/<epizoda>.yaml   ->  render.py   ->  out/<kanál>/<epizoda>.mp4 (+ .json popisek, .srt titulky)
hotové Shorts                     ->  compile.py  ->  out/long/<kanál>_<název>.mp4 (+ kapitoly)
hotové video                      ->  upload_youtube.py  ->  YouTube jako SOUKROMÉ video ke schválení
```

1. Epizodu napíše Claude jako soubor v `episodes/` a přidá ji do repozitáře.
2. GitHub Actions ji sám vyrenderuje (workflow **Render videos**). Hotová videa jsou ke stažení u běhu workflow v sekci *Artifacts*.
3. Ke schválení: spusť **Render videos** ručně a zaškrtni *Upload to YouTube*. Video se nahraje jako soukromé, v YouTube Studiu ho zkontroluješ a přepneš na veřejné nebo naplánuješ.
4. Dlouhé video: workflow **Long-form compilation** (kanál, seznam epizod v pořadí kapitol, název).

## Epizoda

Každý řádek je jedna věta hlasu. `scene` začíná novou scénu, `update` mění jen část té aktuální.

```yaml
channel: mind-mites
title: "Brain Test #1: Most people get this wrong"
hook: Most people get this wrong        # text přes první 2,4 s
lines:
  - text: A bat and a ball cost one dollar ten.
    caption: A bat and a ball cost $1.10.  # titulky se mohou lišit od výslovnosti
    scene:
      rows: [{l: TOGETHER, r: "$1.10"}, {l: BALL, r: "?", hl: true}]
      rows_shown: 1
      mite: {x: 860, y: 1660, s: 0.55, mood: waiting}
  - text: How much is the ball?
    update: {rows_shown: 2, countdown: 3}
    pause: 3.1
```

Prvky dostupné ve všech kanálech: `tag`, `big`, `stat`, `rows`, `countdown`, `quote`, `share`, `nocaptions`.
Podle kanálu navíc:

- **What If Institute:** `bg` (space, descent, surface, dark), `planet` (earth, jupiter, mars, moon), `scout` (pose: float, fall, wave, stand, sit)
- **Stoic Ember:** `setting` (city, island, sea, shipwreck, camp, room, night, black), `figures` (pose: standing, seated, writing, walking, lying), `rain`, `embers`, `fire`
- **Mind Mites:** `bg` (dark), `icons` (bat, ball, tag), `mite` (mood: happy, sad, shock, waiting, smug)

## Lokálně

```bash
pip install -r requirements.txt
./scripts/fetch_models.sh
python render.py --preview episodes/mind-mites/brain-test-001.yaml   # rychlý náhled jako obrázek
python render.py episodes/mind-mites/brain-test-001.yaml
python compile.py mind-mites --last 12 --title "12 Brain Tests Most People Fail"
```

## Tajné klíče (GitHub Secrets)

`YT_CLIENT_SECRET_JSON`, `YT_REFRESH_TOKEN_WHATIF`, `YT_REFRESH_TOKEN_STOIC`, `YT_REFRESH_TOKEN_MITES`. Refresh token se získá skriptem `tools/youtube_auth.py`. Klíče nikdy nepatří do kódu ani do chatu.

## Poznámky

- Fonty ve složce `fonts/` jsou z Google Fonts pod licencí SIL Open Font License, takže je smíme používat i komerčně.
- Dokud YouTube neschválí audit API, jsou nahraná videa vždy soukromá.
- GitHub Actions má u soukromého repozitáře 2 000 minut měsíčně zdarma. Jeden Short trvá zhruba 2–3 minuty.
