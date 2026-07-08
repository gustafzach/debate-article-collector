# Debattöversikt

Det här repot samlar in debattartiklar från svenska nyhetssajter och gör två filer:

- en CSV-fil som kan öppnas i Excel, Google Sheets eller Numbers
- en Markdown-rapport som är lätt att läsa direkt i GitHub

Verktyget hämtar artiklar från följande debattsidor:

- DN Debatt
- Expressen Debatt
- Aftonbladet Debatt
- SvD Debatt
- Di Debatt
- GP Debatt
- Sydsvenskan Debatt/Opinion

Som standard täcker varje körning:

- artiklar publicerade i dag
- artiklar publicerade i går från och med kl. 17:55

Datum och tid tolkas i svensk tid, alltså `Europe/Stockholm`.

## Alternativ 1: Kör online i GitHub

Det här är det rekommenderade sättet för kollegor som bara vill få fram dagens debattöversikt.

### Kör dagens insamling

1. Gå till repot på GitHub: `gustafzach/debate-article-collector`.
2. Klicka på fliken **Actions**.
3. Klicka på arbetsflödet **Collect debate articles** i vänstermenyn.
4. Klicka på **Run workflow**.
5. Lämna datumfältet tomt om du vill köra för dagens datum.
6. Klicka på den gröna knappen **Run workflow**.
7. Vänta tills körningen får en grön bock.

När insamlingen är klar startar arbetsflödet **Render debate report** automatiskt. Det gör om CSV-filen till en läsbar Markdown-rapport.

### Kör för ett annat datum

Om du vill köra för ett visst datum fyller du i datum i formatet:

```text
2026-07-08
```

Använd samma format varje gång: år, månad, dag.

Om du kör **Render debate report** manuellt måste motsvarande CSV-fil redan finnas i mappen `outputs`. Exempel:

```text
outputs/debate_articles_2026-07-08.csv
```

### Läs rapporten i GitHub

När båda arbetsflödena är klara:

1. Gå till mappen `outputs`.
2. Öppna filen som slutar på `.md`, till exempel:

```text
outputs/debate_articles_2026-07-08.md
```

GitHub visar Markdown-filen som en vanlig läsbar textöversikt i webbläsaren.

CSV-filen finns på samma plats om du vill öppna underlaget i ett kalkylprogram:

```text
outputs/debate_articles_2026-07-08.csv
```

Du kan också ladda ner filerna från själva Actions-körningen under rubriken **Artifacts**.

### Automatisk daglig körning

Arbetsflödet **Collect debate articles** är schemalagt till:

```text
07:00 UTC
```

Det motsvarar normalt:

- 09:00 svensk sommartid
- 08:00 svensk vintertid

Den schemalagda körningen använder dagens datum i svensk tid och tar med gårdagens artiklar från kl. 17:55. Den hittar de artiklar som finns publicerade när körningen sker.

## Alternativ 2: Kör lokalt på egen dator

Det här alternativet passar om du vill köra verktyget på en egen Mac eller Windows-dator. Du behöver internetanslutning, eftersom skriptet hämtar artiklar från nyhetssajterna.

### Förbered datorn

1. Installera Python 3 om det inte redan finns på datorn.
2. Ladda ner repot från GitHub med **Code** och sedan **Download ZIP**.
3. Packa upp ZIP-filen.
4. Öppna Terminal på Mac eller PowerShell på Windows.
5. Gå till den uppackade mappen.

Skripten använder bara Pythons standardbibliotek. Du behöver alltså inte installera extra Python-paket.

### Kör på Mac

Byt ut datumet mot det datum du vill använda:

```bash
python3 collect_debate_articles.py --date 2026-07-08 --output outputs/debate_articles_2026-07-08.csv --verbose
python3 render_debate_report.py --date 2026-07-08
```

Efteråt finns rapporten här:

```text
outputs/debate_articles_2026-07-08.md
```

CSV-filen finns här:

```text
outputs/debate_articles_2026-07-08.csv
```

### Kör på Windows

Byt ut datumet mot det datum du vill använda:

```powershell
py collect_debate_articles.py --date 2026-07-08 --output outputs/debate_articles_2026-07-08.csv --verbose
py render_debate_report.py --date 2026-07-08
```

Efteråt finns rapporten här:

```text
outputs/debate_articles_2026-07-08.md
```

CSV-filen finns här:

```text
outputs/debate_articles_2026-07-08.csv
```

### Om du inte anger datum

Om `--date` utelämnas använder skripten dagens datum i svensk tid.

För tydlighet rekommenderas ändå att ange datum explicit när du kör lokalt, särskilt om du vill dela resultatet med andra.

## Vad rapporten innehåller

Markdown-rapporten innehåller:

- övergripande antal artiklar
- antal artiklar per publikation
- läsordning med de senaste artiklarna först
- separat lista för repliker och slutrepliker
- artikelavsnitt per debattsida
- titel, publiceringstid, ingress, författare/avsändare och länk

När titel eller ingress innehåller `replik` eller `slutreplik` läggs artikeln i en separat replikdel. Syftet är att nya debattartiklar ska vara lättare att hitta först.

## Filer

De viktigaste filerna är:

- `collect_debate_articles.py`: hämtar artiklar och skapar CSV
- `render_debate_report.py`: gör om CSV till Markdown
- `.github/workflows/collect-debate-articles.yml`: GitHub Actions-flöde för insamlingen
- `.github/workflows/render-debate-report.yml`: GitHub Actions-flöde för rapporten
- `outputs/`: mapp där CSV- och Markdown-filer sparas

## Begränsningar

Nyhetssajter ändrar ibland sina sidor, metadata eller betalväggar. Om en publicist inte visar fullständig författarinformation i den öppna HTML-koden kan verktyget bara använda den information som finns tillgänglig.

## Upphov

Repo och arbetsflöde skapades av Gustaf Zachrisson den 08 juli 2026.
