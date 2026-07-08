#!/usr/bin/env python3
"""Collect recent debate/opinion articles from configured Swedish publishers.

The script intentionally uses only the Python standard library. It extracts
article candidates from each section page, fetches the articles, reads
structured metadata where possible, and writes a spreadsheet-friendly CSV.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import html
import json
import re
import sys
import time
import zlib
from dataclasses import dataclass
from datetime import date, datetime, time as datetime_time, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) debate-collector/0.1"
)


@dataclass(frozen=True)
class Site:
    name: str
    section_url: str
    include_prefixes: tuple[str, ...]
    exclude_fragments: tuple[str, ...] = ()
    require_section_terms: tuple[str, ...] = ()
    require_link_terms: tuple[str, ...] = ()


SITES: tuple[Site, ...] = (
    Site(
        name="Sydsvenskan Opinion",
        section_url="https://www.sydsvenskan.se/opinion",
        include_prefixes=("/opinion/",),
        exclude_fragments=(
            "/feeds/",
            "/opinion/ledare/",
            "/opinion/huvudledare/",
            "/opinion/kolumnen/",
            "/opinion/heidi-avellan/",
        ),
        require_section_terms=("aktuella frågor", "debatt"),
    ),
    Site(
        name="Altinget Debatt",
        section_url="https://www.altinget.se/debatt",
        include_prefixes=("/artikel/",),
        require_section_terms=("debatt",),
        require_link_terms=("debatt",),
    ),
    Site(
        name="GP Debatt",
        section_url="https://www.gp.se/debatt",
        include_prefixes=("/debatt/",),
        exclude_fragments=("/debatt/fria-ord",),
    ),
    Site(
        name="Dagens industri Debatt",
        section_url="https://www.di.se/debatt/",
        include_prefixes=("/debatt/",),
    ),
    Site(
        name="SvD Debatt",
        section_url="https://www.svd.se/debatt",
        include_prefixes=("/a/",),
        require_section_terms=("debatt",),
    ),
    Site(
        name="Aftonbladet Debatt",
        section_url="https://www.aftonbladet.se/debatt",
        include_prefixes=("/debatt/a/",),
    ),
    Site(
        name="Expressen Debatt",
        section_url="https://www.expressen.se/debatt/",
        include_prefixes=("/debatt/",),
    ),
    Site(
        name="DN Debatt",
        section_url="https://www.dn.se/debatt/",
        include_prefixes=("/debatt/",),
        exclude_fragments=("/rss/", "/fragor-och-svar-om-dn-debatt/"),
    ),
)


ROLE_WORDS = (
    "artist",
    "biskop",
    "chef",
    "debattör",
    "direktör",
    "director",
    "docent",
    "ekonom",
    "entreprenör",
    "forskare",
    "författare",
    "företrädare",
    "förbundsordförande",
    "förbundssekreterare",
    "finansregionråd",
    "generaldirektör",
    "generalsekreterare",
    "grundare",
    "gruppledare",
    "jurist",
    "kontorschef",
    "kommunalråd",
    "läkare",
    "lärare",
    "minister",
    "nordenchef",
    "näringspolitisk",
    "ordförande",
    "partiledare",
    "professor",
    "regionråd",
    "riksdagsledamot",
    "riksdagskandidat",
    "senior",
    "skribent",
    "talesperson",
    "visiting",
    "vd",
    "överdirektör",
)
ROLE_RE = re.compile(r"\b(?:" + "|".join(map(re.escape, ROLE_WORDS)) + r")\b", re.I)
WORD = r"[^\W\d_][^\W\d_'’.-]*"
NAME = rf"{WORD}(?:\s+(?:af|av|de|del|den|la|van|von|{WORD})){{1,4}}"
NAME_RE = re.compile(NAME)
NAME_BEFORE_ROLE_RE = re.compile(
    rf"({NAME})\s*,\s*(?:är\s+)?(?:[^,.;:]*\b)?(?:"
    + "|".join(map(re.escape, ROLE_WORDS))
    + r")\b",
    re.I,
)
SWEDISH_MONTH_NUMBERS = {
    "januari": 1,
    "februari": 2,
    "mars": 3,
    "april": 4,
    "maj": 5,
    "juni": 6,
    "juli": 7,
    "augusti": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "december": 12,
}


def fetch(url: str, timeout: int = 25) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        raw = response.read()
        encoding = (response.headers.get("content-encoding") or "").lower()
        if encoding == "gzip" or raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        elif encoding == "deflate":
            raw = zlib.decompress(raw)
        charset = response.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace")


def normalize_space(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def parse_attrs(tag: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for key, double_quoted, single_quoted, bare in re.findall(
        r"""([:\w.-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", tag
    ):
        attrs[key.lower()] = html.unescape(double_quoted or single_quoted or bare)
    return attrs


def extract_meta(document: str) -> dict[str, list[str]]:
    metadata: dict[str, list[str]] = {}
    for match in re.finditer(r"<meta\s+([^>]+)>", document, flags=re.I):
        attrs = parse_attrs(match.group(1))
        key = attrs.get("property") or attrs.get("name") or attrs.get("itemprop")
        value = attrs.get("content")
        if key and value:
            metadata.setdefault(key.lower(), []).append(normalize_space(value))
    return metadata


def first_meta(metadata: dict[str, list[str]], *keys: str) -> str:
    for key in keys:
        values = metadata.get(key.lower(), [])
        for value in values:
            if value:
                return value
    return ""


def extract_canonical(document: str, fallback: str) -> str:
    for match in re.finditer(r"<link\s+([^>]+)>", document, flags=re.I):
        attrs = parse_attrs(match.group(1))
        rel = attrs.get("rel", "").lower()
        href = attrs.get("href", "")
        if "canonical" in rel and href:
            return href.split("#", 1)[0].split("?", 1)[0]
    return fallback.split("#", 1)[0].split("?", 1)[0]


def flatten_json_ld(value: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if isinstance(value, list):
        for item in value:
            result.extend(flatten_json_ld(item))
    elif isinstance(value, dict):
        result.append(value)
        graph = value.get("@graph")
        if graph:
            result.extend(flatten_json_ld(graph))
    return result


def extract_json_ld(document: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    pattern = re.compile(
        r"""<script[^>]+type=["']application/ld\+json["'][^>]*>(.*?)</script>""",
        flags=re.I | re.S,
    )
    for match in pattern.finditer(document):
        payload = html.unescape(match.group(1)).strip()
        if not payload:
            continue
        try:
            records.extend(flatten_json_ld(json.loads(payload)))
        except json.JSONDecodeError:
            continue
    return records


def json_type(record: dict[str, Any]) -> str:
    value = record.get("@type", "")
    if isinstance(value, list):
        return " ".join(str(item) for item in value).lower()
    return str(value).lower()


def article_json_ld(records: list[dict[str, Any]]) -> dict[str, Any]:
    for record in records:
        kind = json_type(record)
        if "newsarticle" in kind or kind == "article":
            return record
    return {}


def extract_article_links(section_document: str, site: Site) -> list[str]:
    base = site.section_url
    base_host = urlparse(base).netloc.removeprefix("www.")
    section_path = urlparse(base).path.rstrip("/")
    links: list[str] = []
    for match in re.finditer(r"(?is)<a\b([^>]*)>(.*?)</a>", section_document):
        attrs = parse_attrs(match.group(1))
        href = attrs.get("href", "")
        if not href:
            continue
        link_text = normalize_space(re.sub(r"(?is)<[^>]+>", " ", match.group(2)))
        if site.require_link_terms and not any(
            re.search(rf"\b{re.escape(term)}\b", link_text, flags=re.I)
            for term in site.require_link_terms
        ):
            continue
        url = urljoin(base, href).split("#", 1)[0].split("?", 1)[0]
        parsed = urlparse(url)
        host = parsed.netloc.removeprefix("www.")
        path = parsed.path.rstrip("/")
        if parsed.scheme not in {"http", "https"} or host != base_host:
            continue
        if path == section_path:
            continue
        if not any(parsed.path.startswith(prefix) for prefix in site.include_prefixes):
            continue
        if any(fragment in parsed.path for fragment in site.exclude_fragments):
            continue
        if re.search(r"\.(?:jpg|jpeg|png|gif|webp|svg|pdf|xml)$", parsed.path, re.I):
            continue
        if url not in links:
            links.append(url)
    return links


def parse_published_at(value: str, target_tz: ZoneInfo) -> datetime | None:
    value = normalize_space(value)
    if not value:
        return None
    swedish_date = re.search(
        r"\b(\d{1,2})\s+([A-Za-zÅÄÖåäö]+)\s+(\d{4})"
        r"(?:\s+kl\.?\s+(\d{1,2})[:.](\d{2}))?\b",
        value,
        flags=re.I,
    )
    if swedish_date:
        month = SWEDISH_MONTH_NUMBERS.get(swedish_date.group(2).lower())
        if month:
            hour = int(swedish_date.group(4) or 0)
            minute = int(swedish_date.group(5) or 0)
            return datetime(
                int(swedish_date.group(3)),
                month,
                int(swedish_date.group(1)),
                hour,
                minute,
                tzinfo=target_tz,
            )
    if re.fullmatch(r"\d{12,}", value):
        return datetime.fromtimestamp(int(value) / 1000, tz=target_tz)
    if re.fullmatch(r"\d{9,11}", value):
        return datetime.fromtimestamp(int(value), tz=target_tz)
    candidate = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=target_tz)
    return parsed.astimezone(target_tz)


def get_published_at(
    article: dict[str, Any],
    metadata: dict[str, list[str]],
    document: str,
    target_tz: ZoneInfo,
) -> datetime | None:
    candidates: list[str] = []
    for key in ("datePublished", "dateCreated", "dateModified"):
        value = article.get(key)
        if isinstance(value, str):
            candidates.append(value)
    for key in (
        "article:published_time",
        "publishdate",
        "publisheddate",
        "date",
        "dc.date",
    ):
        candidates.extend(metadata.get(key, []))
    for value in candidates:
        parsed = parse_published_at(value, target_tz)
        if parsed:
            return parsed
    for block in extract_text_blocks(document)[:80]:
        parsed = parse_published_at(block, target_tz)
        if parsed:
            return parsed
    return None


def parse_hh_mm(value: str) -> datetime_time:
    try:
        hour_text, minute_text = value.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Expected HH:MM, for example 17:55.") from exc
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise argparse.ArgumentTypeError("Expected HH:MM with 00 <= HH <= 23 and 00 <= MM <= 59.")
    return datetime_time(hour, minute)


def collection_window(
    target_date: date,
    target_tz: ZoneInfo,
    yesterday_after: datetime_time,
) -> tuple[datetime, datetime]:
    start = datetime.combine(target_date - timedelta(days=1), yesterday_after, tzinfo=target_tz)
    end = datetime.combine(target_date + timedelta(days=1), datetime_time.min, tzinfo=target_tz)
    return start, end


def clean_title(value: str) -> str:
    value = normalize_space(value)
    value = re.sub(
        r"\s+[–|-]\s+(?:Altinget|DN|SvD|Sydsvenskan|Aftonbladet|Expressen|GP|Di).*$",
        "",
        value,
    )
    return value


def article_sections(article: dict[str, Any], metadata: dict[str, list[str]]) -> list[str]:
    values: list[str] = []
    section = article.get("articleSection")
    if isinstance(section, list):
        values.extend(str(item) for item in section)
    elif isinstance(section, str):
        values.append(section)
    values.extend(metadata.get("article:section", []))
    values.extend(metadata.get("lp:section", []))
    values.extend(metadata.get("bad:articletype", []))
    return [normalize_space(value).lower() for value in values if normalize_space(value)]


def is_required_section(
    site: Site,
    article: dict[str, Any],
    metadata: dict[str, list[str]],
) -> bool:
    if not site.require_section_terms:
        return True
    haystack = " | ".join(article_sections(article, metadata))
    if not haystack:
        return True
    return any(term.lower() in haystack for term in site.require_section_terms)


def extract_text_blocks(document: str) -> list[str]:
    clean = re.sub(
        r"(?is)<script.*?</script>|<style.*?</style>|<noscript.*?</noscript>|<svg.*?</svg>",
        " ",
        document,
    )
    blocks: list[str] = []
    for match in re.finditer(
        r"(?is)<(h1|h2|h3|h4|h5|p|figcaption|span|div)[^>]*>(.*?)</\1>",
        clean,
    ):
        raw = re.sub(r"(?is)<[^>]+>", " ", match.group(2))
        text = normalize_space(raw)
        if 10 <= len(text) <= 700 and text not in blocks:
            blocks.append(text)
    return blocks


def looks_like_boilerplate(text: str) -> bool:
    lowered = text.lower()
    blocked_terms = (
        "annons",
        "cookie",
        "det här är en debattartikel",
        "detta är en debattartikel",
        "detta är en opinionstext",
        "dela",
        "foto:",
        "hoppa till",
        "kopiera länk",
        "logga in",
        "lyssna på artikel",
        "publicerad",
        "spara",
        "uppdaterad",
    )
    if any(term in lowered for term in blocked_terms):
        return True
    if re.fullmatch(r"(?:\d{1,2}[:.]\d{2}|i dag|idag|i går|igår).*", lowered):
        return True
    if re.fullmatch(r"\d{1,2}\s+\w+\s+\d{4}.*", lowered):
        return True
    return False


def extract_visible_lead(document: str, title: str) -> str:
    blocks = extract_text_blocks(document)
    title_norm = normalize_space(title).removeprefix("DN Debatt. ")
    start = 0
    for index, block in enumerate(blocks):
        if title_norm and (block == title_norm or title_norm in block):
            start = index + 1
            break
    for block in blocks[start : start + 50]:
        if len(block) < 60:
            continue
        if title_norm and block == title_norm:
            continue
        if looks_like_boilerplate(block):
            continue
        return block
    return ""


def extract_preamble(
    document: str,
    article: dict[str, Any],
    metadata: dict[str, list[str]],
    title: str,
) -> str:
    structured = normalize_space(str(article.get("description", "")))
    if not structured:
        structured = first_meta(metadata, "og:description", "description", "twitter:description")
    visible = extract_visible_lead(document, title)
    if visible and (
        not structured
        or structured.endswith(("…", "..."))
        or len(visible) > len(structured) + 25
        and visible.lower().startswith(structured[:40].lower().rstrip("…."))  # type: ignore[index]
    ):
        return visible
    return structured


def author_names_from_ld(article: dict[str, Any]) -> list[str]:
    authors = article.get("author", [])
    if isinstance(authors, (str, dict)):
        authors = [authors]
    names: list[str] = []
    if isinstance(authors, list):
        for author in authors:
            if isinstance(author, str):
                name = author
            elif isinstance(author, dict):
                name = str(author.get("name", ""))
            else:
                continue
            name = normalize_space(name)
            if not name or is_generic_author(name):
                continue
            extracted = extract_person_names(name)
            if extracted:
                for extracted_name in extracted:
                    if extracted_name not in names:
                        names.append(extracted_name)
            elif name not in names:
                names.append(name)
    return names


def is_generic_author(name: str) -> bool:
    lowered = name.lower()
    generic = (
        "aftonbladet",
        "altinget",
        "dagens industri",
        "dagens nyheter",
        "debatt",
        "debattredaktionen",
        "expressen",
        "gp",
        "göteborgs-posten",
        "svenska dagbladet",
        "svd",
        "sydsvenskan",
    )
    return lowered in generic or "redaktionen" in lowered


def extract_person_names(text: str) -> list[str]:
    names: list[str] = []
    text = re.sub(r"\([A-Za-zÅÄÖåäö]{1,8}\)", " ", text)
    text = re.sub(r"\s+(?:och|samt|&)\s+", ", ", text, flags=re.I)
    name_particles = {"af", "av", "de", "del", "den", "la", "van", "von"}
    organization_tokens = {
        "arena",
        "centerpartiet",
        "di",
        "dn",
        "eu",
        "google",
        "handelskammaren",
        "linkedin",
        "moderaterna",
        "novus",
        "organic",
        "region",
        "socialdemokraterna",
        "stockholm",
        "sverige",
        "sweden",
        "universitet",
    }
    for segment in re.split(r"[,;]", text):
        for match in NAME_RE.finditer(segment):
            name = normalize_space(match.group(0))
            raw_tokens = [token.strip(".,:;") for token in name.split()]
            kept_tokens: list[str] = []
            for index, token in enumerate(raw_tokens):
                if not token:
                    continue
                lowered = token.lower()
                if index == 0:
                    if not token[:1].isupper():
                        break
                    kept_tokens.append(token)
                elif lowered in name_particles:
                    kept_tokens.append(token)
                elif token[:1].isupper():
                    kept_tokens.append(token)
                else:
                    break
            while kept_tokens and kept_tokens[-1].lower() in name_particles:
                kept_tokens.pop()
            tokens = [token.lower() for token in kept_tokens]
            if len(kept_tokens) < 2:
                continue
            if any(token in ROLE_WORDS for token in tokens):
                continue
            if any(token in organization_tokens for token in tokens):
                continue
            if any(token in {"debatt", "dn", "di", "gp", "svd", "och", "samt"} for token in tokens):
                continue
            person_name = " ".join(kept_tokens)
            if person_name not in names:
                names.append(person_name)
    return names


def clean_author_text(text: str) -> str:
    text = normalize_space(text)
    text = re.sub(r"\s+(?:Bild|Foto):.*$", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+,", ",", text)
    return text.strip(" .,:;")


def split_leading_person_name(text: str) -> tuple[str, str] | None:
    text = clean_author_text(text)
    if not text:
        return None
    name_particles = {"af", "av", "de", "del", "den", "la", "van", "von"}
    blocked_name_tokens = {
        "a",
        "annons",
        "arkivet",
        "avdelning",
        "chef",
        "debatt",
        "di",
        "dn",
        "e-dn",
        "e-tidning",
        "esvd",
        "dagens",
        "foto",
        "gp",
        "hej",
        "kund",
        "kundservice",
        "kultur",
        "ledare",
        "livet",
        "logga",
        "malmö",
        "men",
        "mest",
        "mitt",
        "nn",
        "nyheter",
        "näringsliv",
        "om",
        "opinion",
        "prenumerant",
        "prenumeration",
        "prenumerera",
        "sport",
        "start",
        "svd",
        "tipsa",
    }
    kept: list[str] = []
    name_end = 0
    for index, match in enumerate(re.finditer(r"\S+", text)):
        token = match.group(0)
        cleaned = token.strip(".,:;")
        if not cleaned:
            break
        if re.fullmatch(r"\([A-Za-zÅÄÖåäö]{1,8}\)", cleaned):
            break
        lowered = cleaned.lower()
        if index == 0:
            if not cleaned[:1].isupper():
                break
            kept.append(cleaned)
            name_end = match.end()
            if token.endswith(","):
                break
        elif lowered in name_particles:
            kept.append(cleaned)
            name_end = match.end()
            if token.endswith(","):
                break
        elif cleaned[:1].isupper():
            kept.append(cleaned)
            name_end = match.end()
            if token.endswith(","):
                break
        else:
            break
    while kept and kept[-1].lower() in name_particles:
        kept.pop()
    if len(kept) < 2:
        return None
    lowered_tokens = [token.lower() for token in kept]
    if any(token in blocked_name_tokens for token in lowered_tokens):
        return None
    if any(token.isupper() and len(token) > 1 for token in kept):
        return None
    name = " ".join(kept)
    if is_generic_author(name):
        return None
    return name, text[name_end:].strip()


def author_key(author_display: str) -> str:
    split = split_leading_person_name(author_display)
    if split:
        return split[0].lower()
    names = extract_person_names(author_display)
    return names[0].lower() if names else author_display.lower()


def looks_like_author_detail(display: str) -> bool:
    split = split_leading_person_name(display)
    if not split:
        return False
    _name, rest = split
    if not rest:
        return False
    lowered = display.lower()
    blocked = (
        "senaste nytt",
        "arkiv nyheter",
        "börsmorgon",
        "svd debatt",
        "mest läst",
        "följ ämnen",
        "läs fler",
        "relaterade",
        "har du upptäckt",
        "ansvariga",
        "chefredaktör",
        "webbredaktör",
    )
    if any(term in lowered for term in blocked):
        return False
    if "”" in display or '"' in display:
        return False
    return ROLE_RE.search(display) is not None


def format_author_detail(text: str) -> str:
    text = clean_author_text(text)
    split = split_leading_person_name(text)
    if not split:
        return ""
    name, rest = split
    if rest and not (
        re.match(r"^(?:,|är\b|ar\b|\([A-Za-zÅÄÖåäö]{1,8}\))", rest, flags=re.I)
        or ROLE_RE.search(rest)
    ):
        return ""
    party = ""
    party_match = re.match(r"\(([A-Za-zÅÄÖåäö]{1,8})\)\s*(.*)$", rest)
    if party_match:
        party = f" ({party_match.group(1)})"
        rest = party_match.group(2)
    rest = rest.strip(" ,")
    if rest.lower().startswith("är "):
        rest = rest[3:].strip()
    if rest.lower().startswith("ar "):
        rest = rest[3:].strip()
    rest = rest.strip(" .,:;")
    if not rest:
        return f"{name}{party}"
    return f"{name}{party}, {rest}"


def author_displays_from_phrase(phrase: str) -> list[str]:
    phrase = clean_fallback_author_phrase(phrase)
    if not phrase:
        return []
    shared = author_displays_from_shared_affiliation(phrase)
    if shared:
        return shared
    # Multiple named authors in a lead usually have no per-person role there.
    if re.search(r"\s+(?:och|samt|&)\s+", phrase, flags=re.I):
        return extract_person_names(phrase)
    detail = format_author_detail(phrase)
    if detail and looks_like_author_detail(detail):
        return [detail]
    return extract_person_names(phrase)


def author_displays_from_shared_affiliation(text: str) -> list[str]:
    text = clean_author_text(text)
    if "”" in text or '"' in text:
        return []
    before, separator, after = text.partition(",")
    if not separator or not re.search(r"\s+(?:och|samt|&)\s+", before, flags=re.I):
        return []
    names = extract_person_names(before)
    affiliation = after.strip(" .,:;")
    if len(names) < 2 or not affiliation or len(affiliation) > 140:
        return []
    lowered = affiliation.lower()
    if any(term in lowered for term in ("foto", "bild", "publicerad", "uppdaterad")):
        return []
    return [f"{name}, {affiliation}" for name in names]


def add_author_display(displays: list[str], seen: dict[str, int], display: str) -> None:
    display = clean_author_text(display)
    if not display:
        return
    key = author_key(display)
    if key not in seen:
        seen[key] = len(displays)
        displays.append(display)
        return
    existing_index = seen[key]
    existing = displays[existing_index]
    existing_has_detail = "," in existing
    new_has_detail = "," in display
    if new_has_detail and (not existing_has_detail or len(display) > len(existing)):
        displays[existing_index] = display


def extract_author_detail_lines(blocks: list[str]) -> list[str]:
    displays: list[str] = []
    seen: dict[str, int] = {}
    for block in blocks:
        if len(block) > 260:
            continue
        for display in author_displays_from_shared_affiliation(block):
            add_author_display(displays, seen, display)
        detail = format_author_detail(block)
        if detail and looks_like_author_detail(detail):
            add_author_display(displays, seen, detail)
    return displays


def is_person_name_only(text: str) -> str:
    text = clean_author_text(text)
    if len(text) > 80:
        return ""
    names = extract_person_names(text)
    if len(names) != 1:
        return ""
    return names[0] if names[0] == text else ""


def extract_adjacent_author_detail_lines(blocks: list[str]) -> list[str]:
    displays: list[str] = []
    seen: dict[str, int] = {}
    relevant_blocks = blocks[:60]
    for index, block in enumerate(relevant_blocks[:-1]):
        lowered = block.lower()
        if "detta är en opinionsartikel" in lowered or "ämnen i denna artikel" in lowered:
            break
        name = is_person_name_only(block)
        if not name:
            continue
        detail = clean_author_text(relevant_blocks[index + 1])
        detail_lowered = detail.lower()
        if not detail or len(detail) > 180:
            continue
        if any(term in detail_lowered for term in ("foto", "bild", "publicerad", "uppdaterad")):
            continue
        if not ROLE_RE.search(detail):
            continue
        add_author_display(displays, seen, f"{name}, {detail}")
    return displays


def extract_names_from_role_lines(blocks: list[str]) -> list[str]:
    names: list[str] = []
    for block in blocks:
        if len(block) > 320:
            continue
        if not block[:1].isupper():
            continue
        if "”" in block or '"' in block:
            continue
        if not ROLE_RE.search(block):
            continue
        if not re.match(rf"^\s*{NAME}\s*,", block):
            continue
        for match in NAME_BEFORE_ROLE_RE.finditer(block):
            name = normalize_space(match.group(1))
            if name and name not in names and not is_generic_author(name):
                names.append(name)
    return names


def clean_fallback_author_phrase(phrase: str) -> str:
    phrase = normalize_space(phrase)
    phrase = re.split(
        r"\s+(?:i|på)\s+"
        r"(?:Altinget|Di|DN|GP|SvD|Svenska Dagbladet|Aftonbladet|Expressen)\b",
        phrase,
    )[0]
    phrase = re.sub(r"\s+Foto:.*$", "", phrase, flags=re.I)
    phrase = phrase.strip(" .,:;")
    if phrase.lower() in {"undertecknarna", "artikelförfattarna"}:
        return ""
    return phrase


def extract_authors(
    document: str,
    article: dict[str, Any],
    metadata: dict[str, list[str]],
) -> str:
    blocks = extract_text_blocks(document)
    displays: list[str] = []
    seen: dict[str, int] = {}

    metadata_names = author_names_from_ld(article)
    if not metadata_names:
        for value in metadata.get("author", []) + metadata.get("article:author", []):
            value = normalize_space(value)
            if value and not is_generic_author(value):
                metadata_names.extend(extract_person_names(value) or [value])

    fallback = ""
    for block in blocks:
        for match in re.finditer(r"\bskriver\s+([^.\n]+)", block, flags=re.I):
            phrase = clean_fallback_author_phrase(match.group(1))
            phrase_displays = author_displays_from_phrase(phrase)
            if phrase_displays:
                for display in phrase_displays:
                    add_author_display(displays, seen, display)
            elif not fallback and phrase:
                fallback = phrase

    for detail in extract_author_detail_lines(blocks):
        add_author_display(displays, seen, detail)

    for detail in extract_adjacent_author_detail_lines(blocks):
        add_author_display(displays, seen, detail)

    if not displays:
        for name in metadata_names or extract_names_from_role_lines(blocks):
            add_author_display(displays, seen, name)

    if displays:
        return "; ".join(displays)
    return fallback


def collect_article(
    site: Site,
    url: str,
    target_tz: ZoneInfo,
    window_start: datetime,
    window_end: datetime,
) -> dict[str, str] | None:
    document = fetch(url)
    metadata = extract_meta(document)
    records = extract_json_ld(document)
    article = article_json_ld(records)

    if not is_required_section(site, article, metadata):
        return None

    published_at = get_published_at(article, metadata, document, target_tz)
    if not published_at or not (window_start <= published_at < window_end):
        return None

    canonical = extract_canonical(document, url)
    title = clean_title(
        normalize_space(str(article.get("headline", "")))
        or first_meta(metadata, "og:title", "twitter:title", "title")
    )
    preamble = extract_preamble(document, article, metadata, title)
    authors = extract_authors(document, article, metadata)

    if not title:
        return None

    return {
        "site": site.name,
        "published_at": published_at.isoformat(timespec="minutes"),
        "title": title,
        "authors": authors,
        "preamble": preamble,
        "link": canonical,
    }


def collect(
    sites: tuple[Site, ...],
    target_tz: ZoneInfo,
    window_start: datetime,
    window_end: datetime,
    *,
    max_articles_per_site: int,
    delay_seconds: float,
    verbose: bool,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for site in sites:
        if verbose:
            print(f"Scanning {site.name}: {site.section_url}", file=sys.stderr)
        try:
            section_document = fetch(site.section_url)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            print(f"WARNING: Could not fetch section {site.section_url}: {exc}", file=sys.stderr)
            continue
        links = extract_article_links(section_document, site)[:max_articles_per_site]
        if verbose:
            print(f"  {len(links)} candidate links", file=sys.stderr)
        for link in links:
            if link in seen_urls:
                continue
            seen_urls.add(link)
            try:
                row = collect_article(site, link, target_tz, window_start, window_end)
            except (HTTPError, URLError, TimeoutError, OSError) as exc:
                print(f"WARNING: Could not fetch article {link}: {exc}", file=sys.stderr)
                continue
            if row:
                rows.append(row)
                if verbose:
                    print(f"  kept: {row['title']}", file=sys.stderr)
            if delay_seconds:
                time.sleep(delay_seconds)
    rows.sort(key=lambda row: (row["site"], row["published_at"], row["title"]))
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Collect debate articles from yesterday after a configured time "
            "through the end of the target date into CSV."
        )
    )
    parser.add_argument(
        "--date",
        help="Target date in YYYY-MM-DD. Defaults to today's date in --timezone.",
    )
    parser.add_argument(
        "--timezone",
        default="Europe/Stockholm",
        help="Timezone used for the publication-time window. Default: Europe/Stockholm.",
    )
    parser.add_argument(
        "--yesterday-after",
        type=parse_hh_mm,
        default=parse_hh_mm("17:55"),
        metavar="HH:MM",
        help="Include articles from the day before --date at or after this time. Default: 17:55.",
    )
    parser.add_argument(
        "--output",
        default="outputs/debate_articles_today.csv",
        help="CSV output path. Default: outputs/debate_articles_today.csv.",
    )
    parser.add_argument(
        "--max-articles-per-site",
        type=int,
        default=80,
        help="Maximum article candidates fetched from each section page. Default: 80.",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=0.15,
        help="Delay between article fetches. Default: 0.15.",
    )
    parser.add_argument("--verbose", action="store_true", help="Print progress to stderr.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target_tz = ZoneInfo(args.timezone)
    target_date = (
        date.fromisoformat(args.date)
        if args.date
        else datetime.now(target_tz).date()
    )
    window_start, window_end = collection_window(target_date, target_tz, args.yesterday_after)
    rows = collect(
        SITES,
        target_tz,
        window_start,
        window_end,
        max_articles_per_site=args.max_articles_per_site,
        delay_seconds=args.delay_seconds,
        verbose=args.verbose,
    )
    fieldnames = ("site", "published_at", "title", "authors", "preamble", "link")
    with open(args.output, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} articles to {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
