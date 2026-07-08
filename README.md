# Dagens debattare och ledare

Det här repot samlar in debattartiklar och ledartexter från svenska nyhetssajter och genererar två filtyper:

- en Markdown-rapport som är lätt att läsa direkt i GitHub
- en CSV-fil som kan öppnas i Excel, Google Sheets eller Numbers

## Senaste rapporter

Markdown-rapporterna hamnar i dessa GitHub-mappar:



- [Senaste debattöversikter](https://github.com/gustafzach/debate-article-collector/tree/main/outputs/debattartiklar/md)
- [Senaste ledaröversikter](https://github.com/gustafzach/debate-article-collector/tree/main/outputs/ledartexter/md)

Byt ut `OWNER/REPO` mot rätt GitHub-repo när repot är publicerat.

## Källor

Som standard täcker varje körning:

- artiklar publicerade i dag
- artiklar publicerade i går från och med kl. 17:55

Datum och tid tolkas i svensk tid. 

### Debattartiklar

Debattflödet hämtar artiklar från:

- DN Debatt
- Expressen Debatt
- Aftonbladet Debatt
- SvD Debatt
- Di Debatt
- GP Debatt
- Sydsvenskan Debatt/Opinion
- Altinget Debatt

### Ledartexter

Ledarflödet hämtar texter från:

- DN Ledare: `https://www.dn.se/ledare/`
- SvD Ledare: `https://www.svd.se/ledare`
- Di Ledare: `https://www.di.se/ledare/`
- Expressen Ledare: `https://www.expressen.se/ledare/`
- Aftonbladet Ledare: `https://www.aftonbladet.se/ledare`
- GP Ledare: `https://www.gp.se/ledare`
- Sydsvenskan Huvudledare: `https://www.sydsvenskan.se/huvudledare`


## Alternativ 1: Kör online i GitHub

### Kör dagens insamling

1. Gå till fliken **Actions** i GitHub.
2. Välj önskat arbetsflöde.
3. Klicka på **Run workflow**.
4. Lämna datumfältet tomt för dagens datum i svensk tid, eller ange datum i formatet:

```text
2026-07-08
```

Om du kör ett renderingsflöde manuellt måste motsvarande CSV-fil redan finnas i rätt CSV-mapp.

### Automatisk daglig körning

Arbetsflödet **Step I: Collect debate articles** är schemalagt till:

```text
05:00 UTC
```

Under svensk sommartid motsvarar det:

- 07:00 svensk tid

Arbetsflödet **Step II: Render debate report** startar efter att insamlingen är klar. Vid den schemalagda morgonkörningen väntar det vid behov till 07:05 svensk tid innan rapporten skapas.

Den schemalagda körningen använder dagens datum i svensk tid och tar med gårdagens artiklar från kl. 17:55. Den hittar de artiklar som finns publicerade när insamlingen sker.

### Kör för ett annat datum

Om du vill köra för ett visst datum fyller du i datum i formatet:

```text
2026-07-08
```

Använd samma format varje gång: år, månad, dag.

Om du kör **Step II: Render debate report** manuellt måste motsvarande CSV-fil redan finnas i mappen `outputs/csv`. Exempel:

```text
outputs/csv/debate_articles_20260708.csv
```

### Läs rapporten i GitHub

När båda arbetsflödena är klara:

1. Gå till mappen `outputs/markdown`.
2. Öppna filen som slutar på `.md`, till exempel:

```text
outputs/markdown/debate_articles_20260708.md
```

GitHub visar Markdown-filen som en vanlig läsbar textöversikt i webbläsaren.

CSV-filen finns i `outputs/csv` om du vill öppna underlaget i ett kalkylprogram:

```text
outputs/csv/debate_articles_20260708.csv
```

Du kan också ladda ner filerna från själva Actions-körningen under rubriken **Artifacts**.


## Alternativ 2: Kör lokalt på egen dator

Det här alternativet passar om du vill köra verktyget på en egen Mac eller Windows-dator. Du behöver internetanslutning, eftersom skriptet hämtar artiklar från nyhetssajterna.

### Förbered datorn

1. Installera Python 3 om det inte redan finns på datorn.
2. Ladda ner repot från GitHub med **Code** och sedan **Download ZIP**.
3. Packa upp ZIP-filen.
4. Öppna Terminal på Mac eller PowerShell på Windows.
5. Gå till den uppackade mappen.

Skripten använder bara Pythons standardbibliotek. Du behöver alltså inte installera extra Python-paket.

### Val av datum

Byt ut datumet mot det datum du vill använda. Om `--date` utelämnas använder skripten dagens datum i svensk tid.

För tydlighet rekommenderas ändå att ange datum explicit när du kör lokalt, särskilt om du vill dela resultatet med andra.


### Debattartiklar

På Mac:

```bash
python3 collect_debate_articles.py --date 2026-07-08 --verbose
python3 render_debate_report.py --date 2026-07-08
```

På Windows:

```powershell
py collect_debate_articles.py --date 2026-07-08 --verbose
py render_debate_report.py --date 2026-07-08
```

Resultaten hamnar här:

```text
outputs/debattartiklar/csv/debate_articles_20260708.csv
outputs/debattartiklar/md/debate_articles_20260708.md
```

### Ledartexter

På Mac:

```bash
python3 collect_editorials.py --date 2026-07-08 --verbose
python3 render_editorial_report.py --date 2026-07-08
```

På Windows:

```powershell
py collect_editorials.py --date 2026-07-08 --verbose
py render_editorial_report.py --date 2026-07-08
```

Resultaten hamnar här:

```text
outputs/ledartexter/csv/editorials_20260708.csv
outputs/ledartexter/md/editorials_20260708.md
```

## Fält i CSV

Båda CSV-typerna använder samma grundfält:

- `site`
- `published_at`
- `title`
- `authors`
- `preamble`
- `link`

Det gör att filerna är enkla att analysera parallellt, trots att källorna och renderingen skiljer mellan debattartiklar och ledartexter.

## Begränsningar

Nyhetssajter ändrar ibland sina sidor, metadata eller betalväggar. Om en publicist inte visar fullständig författarinformation i den öppna HTML-koden kan verktyget bara använda den information som finns tillgänglig.

## Upphov

Repo och arbetsflöde skapades av Gustaf Zachrisson den 08 juli 2026.
