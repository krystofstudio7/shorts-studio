# Shorts Studio

Výrobní linka pro kanály **What If Institute**, **Stoic Ember** a **Mind Mites**. Z textového souboru s epizodou udělá hotový Short (hlas, animace, titulky, hudba) a z hotových Shorts dlouhé video s kapitolami. Všechno běží zdarma: hlas Kokoro, grafika kreslená kódem, render na GitHub Actions.

## Jak to funguje

```
episodes/<kanál>/<epizoda>.yaml   ->  render.py   ->  out/<kanál>/<epizoda>.mp4 (+ .json popisek, .srt titulky)
hotové Shorts                     ->  compile.py  ->  out/long/<kanál>_<název>.mp4 (+ kapitoly)
hotové video                      ->  upload_youtube.py  ->  YouTube jako VEŘEJNÉ video
```

1. Epizodu napíše Claude jako soubor v `episodes/` a přidá ji do repozitáře.
2. Po přidání epizody ji GitHub Actions jen vyrenderuje jako náhled (workflow **Render videos**, video je ke stažení v sekci *Artifacts*).
3. Každý den v 15:00 UTC workflow vezme z každého kanálu další nezveřejněnou epizodu (podle názvu souboru), vyrenderuje ji a nahraje na YouTube jako veřejnou. Epizoda s `publish_after: 2026-11-05` počká do toho dne. Fronta: `python next_episodes.py`.
   Ruční spuštění **Render videos** nabízí *episodes* (due, all, nebo soubory) a *Upload to YouTube*: public, private nebo none.
4. Každé nahrání se zapíše do `published/<kanál>/<epizoda>.json`, takže se stejná epizoda nikdy nenahraje dvakrát.
5. Dlouhé video: workflow **Long-form compilation** (kanál, seznam epizod v pořadí kapitol, název).

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
Kamera: každá scéna má pomalý nájezd (`push`, výchozí 0.06, 0 vypne), `shake: true` pro otřes při nárazu, `pan_y` pro posun.
Zvukové efekty (whoosh mezi scénami, pop u textů, ding u správné odpovědi, tikání odpočtu) se přidávají samy podle scén.
Podle kanálu navíc:

- **What If Institute:** `bg` (space, descent, surface, dark), `planet` (earth, jupiter, mars, moon), `scout` (pose: float, fall, wave, stand, sit)
- **Stoic Ember:** `setting` (city, island, sea, shipwreck, camp, room, night, black), `figures` (pose: standing, seated, writing, walking, lying), `rain`, `embers`, `fire`, `fog`, `rays`
- **Mind Mites:** `bg` (dark), `icons` (bat, ball, tag), `mite` (mood: happy, sad, shock, waiting, smug)

## Kontrola kvality a výkon

- `python check_episodes.py FILES` (nebo `--all`): ohodnotí mluvený i textový hook (0–100), odhadne délku podle tempa našeho hlasu, upozorní na hook delší než 3 s, dlouhé statické záběry, chybějící smyčku na konci a AI fráze. Chyba (neviditelné znaky, pozdrav, „stop scrolling“, „follow for more“) shodí check, zbytek jsou rady. Běží automaticky na každém PR s epizodami (workflow **Check episodes**).
- Popisky pro Facebook a Instagram se čistí automaticky: max. 5 hashtagů (limit Instagramu), bez tagů jiných platforem (#learnontiktok), bez pomlček a neviditelných znaků.
- `python performance.py`: každé pondělí v 6:00 UTC (workflow **Performance report**) seřadí zveřejněná videa podle násobku mediánu kanálu a sdílení na 1 000 dosahu a porovná nejlepší a nejhorší třetinu (hook, délka, smyčka). Výsledek je v `reports/performance.md`. Instagram potřebuje u system user tokenu oprávnění `instagram_manage_insights`, YouTube podíl sledování potřebuje zapnuté YouTube Analytics API.
- Části v `quality/` jsou převzaté z [instagram-agent-skill](https://github.com/Jakeschincariol/instagram-agent-skill) (licence MIT).

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
- Dokud Google neschválí audit YouTube API, YouTube nahraná videa zamkne jako soukromá, i když chceme veřejná. Po schválení auditu začnou být veřejná bez dalších změn.
- GitHub Actions má u soukromého repozitáře 2 000 minut měsíčně zdarma. Jeden Short trvá zhruba 2–3 minuty.
