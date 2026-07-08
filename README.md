# Debate article CSV collector

This workspace contains a small standard-library Python script that collects debate/opinion articles published in this window:

- yesterday at or after `17:55`
- all of the target date

The window is interpreted in `Europe/Stockholm` unless another timezone is provided.

The configured publishers are:

- Sydsvenskan Opinion
- GP Debatt
- Dagens industri Debatt
- SvD Debatt
- Aftonbladet Debatt
- Expressen Debatt
- DN Debatt

Run it with:

```bash
python3 collect_debate_articles.py --date 2026-07-08 --output outputs/debate_articles_2026-07-08.csv --verbose
```

If `--date` is omitted, the script uses today in `Europe/Stockholm`.

To change the previous-day cutoff:

```bash
python3 collect_debate_articles.py --yesterday-after 18:30 --output outputs/debate_articles_today.csv --verbose
```

The CSV columns are:

- `site`
- `published_at`
- `title`
- `authors`
- `preamble`
- `link`

Author extraction uses visible byline patterns, lead-text "skriver ..." phrases, and publisher metadata. Where visible, the `authors` cell preserves role/title and affiliation, for example `Name, title, organisation`. If a publisher only exposes a generic phrase such as "three debaters" in the public HTML, the script keeps that phrase instead of inventing names.
