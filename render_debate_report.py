#!/usr/bin/env python3
"""Render a debate-article CSV as a GitHub-readable Swedish Markdown brief."""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time as datetime_time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


FIELDNAMES = ("site", "published_at", "title", "authors", "preamble", "link")
REPORT_SITE_ORDER = (
    ("DN Debatt", "DN Debatt"),
    ("Expressen Debatt", "Expressen Debatt"),
    ("Aftonbladet Debatt", "Aftonbladet Debatt"),
    ("SvD Debatt", "SvD Debatt"),
    ("Dagens industri Debatt", "Di Debatt"),
    ("GP Debatt", "GP Debatt"),
    ("Sydsvenskan Opinion", "Sydsvenskan Debatt"),
    ("Altinget Debatt", "Altinget Debatt"),
)
REPORT_SITE_LABELS = dict(REPORT_SITE_ORDER)
SWEDISH_MONTHS = {
    1: "januari",
    2: "februari",
    3: "mars",
    4: "april",
    5: "maj",
    6: "juni",
    7: "juli",
    8: "augusti",
    9: "september",
    10: "oktober",
    11: "november",
    12: "december",
}
REPLY_RE = re.compile(r"\b(?:slutreplik|replik)\b", re.I)


@dataclass(frozen=True)
class Article:
    site: str
    published_at: datetime
    title: str
    authors: str
    preamble: str
    link: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Render outputs/csv/debate_articles_YYYYMMDD.csv as a Swedish Markdown policy brief."
        )
    )
    parser.add_argument(
        "--date",
        help="Report date in YYYY-MM-DD. Defaults to today's date in --timezone.",
    )
    parser.add_argument(
        "--timezone",
        default="Europe/Stockholm",
        help="Timezone used when --date is omitted. Default: Europe/Stockholm.",
    )
    parser.add_argument(
        "--input",
        help="CSV input path. Defaults to outputs/csv/debate_articles_YYYYMMDD.csv.",
    )
    parser.add_argument(
        "--output",
        help="Markdown output path. Defaults to outputs/markdown/debate_articles_YYYYMMDD.md.",
    )
    return parser.parse_args()


def markdown_escape(value: str) -> str:
    value = value.strip()
    value = value.replace("\\", "\\\\")
    value = value.replace("[", "\\[")
    value = value.replace("]", "\\]")
    value = value.replace("|", "\\|")
    return value


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def format_datetime(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M")


def format_time(value: datetime) -> str:
    return value.strftime("%H:%M")


def format_swedish_date(value: date) -> str:
    return f"{value.day:02d} {SWEDISH_MONTHS[value.month]} {value.year}"


def format_queue_time(value: datetime, target_date: date) -> str:
    if value.date() == target_date:
        return value.strftime("%H:%M")
    return value.strftime("%d/%m %H:%M")


def compact(value: str, limit: int = 160) -> str:
    value = normalize_space(value)
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "..."


def collection_window(target_date: date, timezone: ZoneInfo) -> tuple[datetime, datetime]:
    start = datetime.combine(
        target_date - timedelta(days=1),
        datetime_time(17, 55),
        tzinfo=timezone,
    )
    end = datetime.combine(target_date + timedelta(days=1), datetime_time.min, tzinfo=timezone)
    return start, end


def site_label(site: str) -> str:
    return REPORT_SITE_LABELS.get(site, site)


def ordered_sites(sites: set[str]) -> list[str]:
    ordered = [site for site, _label in REPORT_SITE_ORDER if site in sites]
    remaining = sorted(site for site in sites if site not in set(ordered))
    return ordered + remaining


def is_reply_article(article: Article) -> bool:
    return bool(REPLY_RE.search(f"{article.title} {article.preamble}"))


def newest_first(articles: list[Article]) -> list[Article]:
    return sorted(
        articles,
        key=lambda article: (article.published_at, article.site, article.title),
        reverse=True,
    )


def render_queue_table(articles: list[Article], target_date: date) -> list[str]:
    lines = [
        "| Tidpunkt | Publikation | Artikel | Författare/avsändare |",
        "|---|---|---|---|",
    ]
    if not articles:
        lines.append("| - | - | Inga artiklar | - |")
        return lines
    for article in newest_first(articles):
        title = markdown_escape(article.title)
        authors = markdown_escape(compact(article.authors or "Ej angivet"))
        site = markdown_escape(site_label(article.site))
        lines.append(
            f"| {format_queue_time(article.published_at, target_date)} | {site} | "
            f"[{title}]({article.link}) | {authors} |"
        )
    return lines


def render_article_note(article: Article, heading_level: int = 4) -> list[str]:
    heading = "#" * heading_level
    return [
        f"{heading} [{markdown_escape(article.title)}]({article.link})",
        "",
        f"**Publicerad:** {format_datetime(article.published_at)}",
        "",
        f"**Ingress:** {markdown_escape(article.preamble)}",
        "",
        f"**Författare/avsändare:** {markdown_escape(article.authors or 'Ej angivet')}",
        "",
        f"**Länk:** <{article.link}>",
        "",
    ]


def read_articles(path: Path) -> list[Article]:
    if not path.exists():
        raise FileNotFoundError(f"CSV file does not exist: {path}")

    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [field for field in FIELDNAMES if field not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"CSV is missing required column(s): {', '.join(missing)}")

        articles: list[Article] = []
        for row in reader:
            published_at = datetime.fromisoformat(row["published_at"])
            articles.append(
                Article(
                    site=normalize_space(row["site"]),
                    published_at=published_at,
                    title=normalize_space(row["title"]),
                    authors=normalize_space(row["authors"]),
                    preamble=normalize_space(row["preamble"]),
                    link=normalize_space(row["link"]),
                )
            )

    articles.sort(key=lambda article: (article.published_at, article.site, article.title))
    return articles


def render_report(articles: list[Article], target_date: date, timezone: ZoneInfo) -> str:
    window_start, window_end = collection_window(target_date, timezone)
    site_counts = Counter(article.site for article in articles)
    by_site: dict[str, list[Article]] = defaultdict(list)
    for article in articles:
        by_site[article.site].append(article)

    generated_at = datetime.now(timezone)
    new_articles = [article for article in articles if not is_reply_article(article)]
    reply_articles = [article for article in articles if is_reply_article(article)]
    lines: list[str] = []
    lines.append(f"# Debattöversikt: {format_swedish_date(target_date)}")
    lines.append("")
    lines.append(
        f"**Täckningsperiod:** {format_datetime(window_start)} till "
        f"{format_datetime(window_end)} Europe/Stockholm"
    )
    lines.append("")
    lines.append(f"**Genererad:** {format_datetime(generated_at)} Europe/Stockholm")
    lines.append("")
    lines.append("## Översikt")
    lines.append("")
    lines.append(f"- **Artiklar:** {len(articles)}")
    lines.append(f"- **Publikationer:** {len(site_counts)}")
    if articles:
        lines.append(
            f"- **Publiceringsspann:** {format_datetime(articles[0].published_at)} till "
            f"{format_datetime(articles[-1].published_at)}"
        )
    lines.append("")

    lines.append("## Antal per publikation")
    lines.append("")
    lines.append("| Publikation | Artiklar |")
    lines.append("|---|---:|")
    for site in ordered_sites(set(site_counts)):
        lines.append(f"| {markdown_escape(site_label(site))} | {site_counts[site]} |")
    lines.append("")

    lines.append("## Läsordning")
    lines.append("")
    lines.append("### Nya debattartiklar")
    lines.append("")
    lines.extend(render_queue_table(new_articles, target_date))
    lines.append("")
    lines.append("### Repliker och slutrepliker")
    lines.append("")
    lines.extend(render_queue_table(reply_articles, target_date))
    lines.append("")

    lines.append("## Artiklar")
    lines.append("")
    for site in ordered_sites(set(by_site)):
        lines.append(f"### {markdown_escape(site_label(site))}")
        lines.append("")
        site_new_articles = [article for article in by_site[site] if not is_reply_article(article)]
        site_reply_articles = [article for article in by_site[site] if is_reply_article(article)]
        for article in newest_first(site_new_articles):
            lines.extend(render_article_note(article))
        if site_reply_articles:
            lines.append("#### Repliker och slutrepliker")
            lines.append("")
            for article in newest_first(site_reply_articles):
                lines.extend(render_article_note(article, heading_level=5))

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    args = parse_args()
    timezone = ZoneInfo(args.timezone)
    target_date = (
        date.fromisoformat(args.date)
        if args.date
        else datetime.now(timezone).date()
    )

    date_stamp = f"{target_date:%Y%m%d}"
    input_path = Path(args.input or f"outputs/csv/debate_articles_{date_stamp}.csv")
    output_path = Path(args.output or f"outputs/markdown/debate_articles_{date_stamp}.md")

    articles = read_articles(input_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_report(articles, target_date, timezone), encoding="utf-8")

    print(f"Wrote {len(articles)} articles to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
