#!/usr/bin/env python3
"""
Populate band tour dates in data.json.

Sources (in order):
  1. Bandsintown public API (set BANDSINTOWN_APP_ID if the default is rejected)
  2. DuckDuckGo web search snippet parsing
  3. Wikipedia tour pages (concert tables)
"""

from __future__ import annotations

import json
import os
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from html import unescape
from typing import Any

DATA_FILE = "data.json"
BANDSINTOWN_BASE = "https://rest.bandsintown.com/artists"
WIKI_API = "https://en.wikipedia.org/w/api.php"
APP_ID = os.environ.get("BANDSINTOWN_APP_ID", "metal-site")
HEADERS = {"User-Agent": "MetalSiteProject/1.0 (tour-agent@local)"}
MAX_TOURS = 3
WIKI_PAUSE_SEC = 1.2

MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE

DATE_IN_TEXT = re.compile(
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}"
    r"|\d{4}-\d{2}-\d{2}",
    re.I,
)
DATE_ROW = re.compile(r'!\s*scope="row"[^|]*\|\s*([^|<{]+)')
FULL_DATE_ROW = re.compile(r"^\|\s*(\d{1,2}\s+\w+\s+\d{4})\s*$")
DATE_SECTION = re.compile(r"Date\s*\((\d{4})\)", re.I)
WIKI_LINK = re.compile(r"\[\[(?:[^\]|]+\|)?([^\]]+)\]\]")
KNOWN_TOUR_PAGES = {
    "Black Sabbath": "The End Tour",
}


def load_bands(path: str) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_bands(path: str, bands: list[dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(bands, f, indent=2, ensure_ascii=False)
        f.write("\n")


def parse_date_string(raw: str) -> date | None:
    raw = raw.strip()
    if not raw:
        return None

    iso = re.match(r"^(\d{4})-(\d{2})-(\d{2})", raw)
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            return None

    text = re.sub(r"(\d{1,2})(st|nd|rd|th)", r"\1", raw, flags=re.I)
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y", "%d %B %Y", "%B %d %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_wiki_day_month(raw: str, year: int) -> date | None:
    cleaned = re.sub(r"\{\{.*", "", raw, flags=re.S).strip()
    cleaned = re.sub(r"[^A-Za-z0-9 ]", " ", cleaned).strip()
    for fmt in ("%d %B %Y", "%B %d %Y"):
        try:
            return datetime.strptime(f"{cleaned} {year}", fmt).date()
        except ValueError:
            continue
    return None


def event_to_tour(event: dict[str, Any]) -> dict[str, str] | None:
    when = event.get("starts_at") or event.get("datetime") or ""
    show_date = parse_date_string(str(when))
    if not show_date:
        return None

    venue = event.get("venue") or {}
    city = (venue.get("city") or "").strip()
    region = (venue.get("region") or "").strip()
    country = (venue.get("country") or "").strip()
    location = (venue.get("location") or "").strip()

    if not city and location:
        city = location.split(",")[0].strip()
    if region and city and region not in city:
        city = f"{city}, {region}"
    elif country and city and country not in city:
        city = f"{city}, {country}"

    return {
        "date": show_date.isoformat(),
        "city": city or "Unknown",
        "venue": (venue.get("name") or "Unknown venue").strip(),
    }


def fetch_bandsintown_events(artist_name: str, date_filter: str) -> list[dict[str, Any]]:
    encoded = urllib.parse.quote(artist_name, safe="")
    query = urllib.parse.urlencode({"app_id": APP_ID, "date": date_filter})
    url = f"{BANDSINTOWN_BASE}/{encoded}/events?{query}"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, context=SSL_CONTEXT, timeout=20) as res:
            payload = json.loads(res.read())
    except urllib.error.HTTPError as exc:
        print(f"  Bandsintown HTTP {exc.code} for {artist_name} ({date_filter})")
        return []
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
        print(f"  Bandsintown error for {artist_name} ({date_filter}): {exc}")
        return []

    if isinstance(payload, dict):
        if payload.get("error") or payload.get("Message"):
            print(f"  Bandsintown: {payload.get('error') or payload.get('Message')}")
        return []
    if not isinstance(payload, list):
        return []
    return payload


def _dedupe_and_pick(
    entries: list[tuple[date, dict[str, str]]],
    *,
    prefer_future: bool = True,
) -> list[dict[str, str]]:
    today = date.today()
    seen: set[tuple[str, str, str]] = set()
    unique: list[tuple[date, dict[str, str]]] = []

    for show_date, tour in sorted(entries, key=lambda item: item[0]):
        key = (tour["date"], tour["city"].lower(), tour["venue"].lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append((show_date, tour))

    if prefer_future:
        pool = [(d, t) for d, t in unique if d >= today]
        pool.sort(key=lambda item: item[0])
    else:
        pool = [(d, t) for d, t in unique if d < today]
        pool.sort(key=lambda item: item[0], reverse=True)

    return [tour for _, tour in pool[:MAX_TOURS]]


def select_tours(events: list[dict[str, Any]], *, prefer_future: bool) -> list[dict[str, str]]:
    today = date.today()
    tours: list[tuple[date, dict[str, str]]] = []

    for event in events:
        tour = event_to_tour(event)
        if not tour:
            continue
        show_date = parse_date_string(tour["date"])
        if not show_date:
            continue
        tours.append((show_date, tour))

    if prefer_future:
        future = [(d, t) for d, t in tours if d >= today]
        future.sort(key=lambda item: item[0])
        chosen = future[:MAX_TOURS]
    else:
        past = [(d, t) for d, t in tours if d < today]
        past.sort(key=lambda item: item[0], reverse=True)
        chosen = past[:MAX_TOURS]

    return [tour for _, tour in chosen]


def bandsintown_tours(artist_name: str) -> list[dict[str, str]]:
    upcoming = fetch_bandsintown_events(artist_name, "upcoming")
    tours = select_tours(upcoming, prefer_future=True)
    if tours:
        return tours

    print(f"  No upcoming shows on Bandsintown for {artist_name}; checking past events...")
    past = fetch_bandsintown_events(artist_name, "past")
    return select_tours(past, prefer_future=False)


def _parse_nearby_venue_city(context: str) -> tuple[str, str]:
    patterns = [
        re.compile(
            r"at\s+(?P<venue>[^,]+?)\s+in\s+(?P<city>[A-Za-zÀ-ÿ .'-]+?)(?:\s*,\s*[A-Za-z .'-]+)?\s+on\s+",
            re.I,
        ),
        re.compile(
            r"at\s+(?P<venue>[^,]+?)\s+in\s+(?P<city>[A-Za-zÀ-ÿ .'-]+)",
            re.I,
        ),
        re.compile(
            r"(?P<venue>[^,]+?)\s+in\s+(?P<city>[A-Za-zÀ-ÿ .'-]+?)(?:\s*,|\s+after|\s+and|\.)",
            re.I,
        ),
    ]
    for pattern in patterns:
        match = pattern.search(context)
        if match:
            return (
                match.group("city").strip(" ."),
                match.group("venue").strip(" ."),
            )
    return ("Unknown", "TBA")


def extract_tours_from_text(text: str) -> list[tuple[date, dict[str, str]]]:
    text = unescape(re.sub(r"<[^>]+>", " ", text))
    text = re.sub(r"\s+", " ", text)
    found: list[tuple[date, dict[str, str]]] = []

    for date_match in DATE_IN_TEXT.finditer(text):
        raw_date = date_match.group(0)
        show_date = parse_date_string(raw_date)
        if not show_date:
            continue

        start = max(0, date_match.start() - 220)
        end = min(len(text), date_match.end() + 120)
        context = text[start:end]
        city, venue = _parse_nearby_venue_city(context)

        found.append(
            (
                show_date,
                {
                    "date": show_date.isoformat(),
                    "city": city,
                    "venue": venue,
                },
            )
        )

    structured_patterns = [
        re.compile(
            r"(?P<month>[A-Za-z]+)\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?,?\s+(?P<year>\d{4}),?\s+"
            r"in\s+(?P<city>[^,]+(?:,\s*[^,]+)?),?\s+(?:at\s+(?:the\s+)?)?(?P<venue>[^.;]+)",
            re.I,
        ),
        re.compile(
            r"(?P<month>[A-Za-z]+)\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?,?\s+(?P<year>\d{4})\s+"
            r"at\s+(?P<venue>[^,]+)\s+in\s+(?P<city>[^.;]+)",
            re.I,
        ),
    ]

    for pattern in structured_patterns:
        for match in pattern.finditer(text):
            month_raw = match.group("month")
            day_raw = match.group("day")
            year_raw = match.group("year")
            city = (match.groupdict().get("city") or "").strip(" .")
            venue = (match.groupdict().get("venue") or "TBA").strip(" .")
            month_num = MONTHS.get(month_raw[:3].lower())
            if not month_num:
                continue
            try:
                show_date = date(int(year_raw), month_num, int(day_raw))
            except ValueError:
                continue
            found.append(
                (
                    show_date,
                    {
                        "date": show_date.isoformat(),
                        "city": city or "Unknown",
                        "venue": venue or "TBA",
                    },
                )
            )

    return found


def ddg_search_html(query: str) -> str:
    payload = urllib.parse.urlencode({"q": query})
    req = urllib.request.Request(
        "https://html.duckduckgo.com/html/",
        data=payload.encode(),
        method="POST",
        headers=HEADERS,
    )
    with urllib.request.urlopen(req, context=SSL_CONTEXT, timeout=20) as res:
        return res.read().decode("utf-8", errors="replace")


def web_search_tours(artist_name: str) -> list[dict[str, str]]:
    queries = [
        f'"{artist_name}" upcoming tour dates venue {date.today().year}',
        f"{artist_name} concert at stadium in city on {date.today().year}",
    ]
    combined: list[tuple[date, dict[str, str]]] = []

    for query in queries:
        try:
            html = ddg_search_html(query)
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"  Web search failed for {artist_name}: {exc}")
            continue

        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, re.S)
        combined.extend(extract_tours_from_text(" ".join(snippets)))
        time.sleep(1.5)

    upcoming = _dedupe_and_pick(combined, prefer_future=True)
    if upcoming:
        return upcoming

    print(f"  No future dates from web search for {artist_name}; trying past tours...")
    try:
        past_html = ddg_search_html(f'"{artist_name}" last concert tour date venue')
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"  Past tour web search failed for {artist_name}: {exc}")
        return []

    past_snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', past_html, re.S)
    return _dedupe_and_pick(
        extract_tours_from_text(" ".join(past_snippets)),
        prefer_future=False,
    )


def wiki_api(params: dict[str, str]) -> dict[str, Any]:
    time.sleep(WIKI_PAUSE_SEC)
    url = f"{WIKI_API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, context=SSL_CONTEXT, timeout=20) as res:
        return json.loads(res.read())


def find_wikipedia_tour_page(artist_name: str) -> str | None:
    if artist_name in KNOWN_TOUR_PAGES:
        return KNOWN_TOUR_PAGES[artist_name]

    data = wiki_api(
        {
            "action": "query",
            "list": "search",
            "srsearch": f"{artist_name} concert tour",
            "format": "json",
            "srlimit": "8",
        }
    )
    generic_title = f"{artist_name} Tour"
    candidates: list[str] = []
    for item in data.get("query", {}).get("search", []):
        title = item.get("title", "")
        if title.startswith("List of "):
            continue
        if re.search(r"tour", title, re.I):
            candidates.append(title)

    world_tours = [t for t in candidates if t != generic_title and "World Tour" in t]
    if world_tours:
        return world_tours[0]
    if candidates:
        return candidates[0]
    return None


def fetch_wikipedia_wikitext(title: str) -> str:
    data = wiki_api(
        {
            "action": "parse",
            "page": title,
            "prop": "wikitext",
            "format": "json",
        }
    )
    return data["parse"]["wikitext"]["*"]


def _parse_wiki_cell(line: str) -> str | None:
    stripped = line.strip()
    if not stripped.startswith("|") or stripped.startswith("|}"):
        return None
    if stripped == "|-":
        return None

    content = stripped.lstrip("|").strip()
    if not content or content.startswith("!"):
        return None

    if content.startswith(("rowspan", "colspan")):
        link = WIKI_LINK.search(content)
        if link:
            return link.group(1).strip()
        parts = [part.strip() for part in content.split("|") if part.strip()]
        for part in reversed(parts):
            if part.startswith(("rowspan", "colspan", "{{")):
                continue
            link = WIKI_LINK.search(part)
            if link:
                return link.group(1).strip()
            if _is_location_cell(part):
                return part
        return None

    content = re.sub(r"\{\{[^}]*\}\}", "", content).strip()
    link = WIKI_LINK.search(content)
    if link:
        return link.group(1).strip()
    return content if _is_location_cell(content) else None


def _is_location_cell(cell: str) -> bool:
    lowered = cell.lower()
    if parse_date_string(cell):
        return False
    if "rowspan" in lowered or "colspan" in lowered:
        return False
    if re.fullmatch(r"[\d,.$]+", cell.replace(" ", "")):
        return False
    if lowered in {"n/a", "tbd", "tba"}:
        return False
    return True


def _nearby_city_venue(lines: list[str], index: int) -> tuple[str | None, str | None]:
    city = venue = None

    for offset in range(1, 10):
        if index + offset >= len(lines):
            break
        cell = _parse_wiki_cell(lines[index + offset])
        if not cell or not _is_location_cell(cell):
            continue
        if not city:
            city = cell
        elif cell != city:
            venue = cell
            break

    if city and venue:
        return city, venue

    backward: list[str] = []
    for offset in range(1, 16):
        if index - offset < 0:
            break
        cell = _parse_wiki_cell(lines[index - offset])
        if cell and _is_location_cell(cell):
            backward.append(cell)

    if len(backward) >= 2:
        # rowspan tables list venue then city (venue appears first above dates)
        venue, city = backward[0], backward[1]
        return city, venue

    return city, venue


def parse_wikipedia_full_date_rows(wikitext: str) -> list[tuple[date, dict[str, str]]]:
    shows: list[tuple[date, dict[str, str]]] = []
    lines = wikitext.split("\n")

    for index, line in enumerate(lines):
        match = FULL_DATE_ROW.match(line.strip())
        if not match:
            continue

        show_date = parse_date_string(match.group(1))
        if not show_date:
            continue

        city, venue = _nearby_city_venue(lines, index)
        if not city or not venue or not _is_location_cell(city) or not _is_location_cell(venue):
            continue

        shows.append(
            (
                show_date,
                {
                    "date": show_date.isoformat(),
                    "city": city,
                    "venue": venue,
                },
            )
        )

    return shows


def parse_wikipedia_concert_tables(wikitext: str) -> dict[int, list[tuple[date, dict[str, str]]]]:
    sections: dict[int, list[tuple[date, dict[str, str]]]] = {}
    matches = list(DATE_SECTION.finditer(wikitext))
    if not matches:
        return sections

    for index, match in enumerate(matches):
        year = int(match.group(1))
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(wikitext)
        chunk = wikitext[start:end]
        shows: list[tuple[date, dict[str, str]]] = []

        lines = chunk.split("\n")
        line_no = 0
        while line_no < len(lines):
            row_match = DATE_ROW.search(lines[line_no])
            if not row_match:
                line_no += 1
                continue

            show_date = parse_wiki_day_month(row_match.group(1), year)
            if not show_date:
                line_no += 1
                continue

            cells: list[str] = []
            scan = line_no + 1
            while scan < len(lines) and len(cells) < 3:
                cell = _parse_wiki_cell(lines[scan])
                if cell and cell.lower() not in {"n/a", "tbd", "tba"}:
                    cells.append(cell)
                scan += 1

            if len(cells) >= 2:
                city = cells[0]
                venue = cells[2] if len(cells) >= 3 else cells[1]
                shows.append(
                    (
                        show_date,
                        {
                            "date": show_date.isoformat(),
                            "city": city,
                            "venue": venue,
                        },
                    )
                )
            line_no = scan

        if shows:
            sections[year] = shows

    return sections


def wikipedia_tours(artist_name: str) -> list[dict[str, str]]:
    page_title = find_wikipedia_tour_page(artist_name)
    if not page_title:
        print(f"  No Wikipedia tour page found for {artist_name}.")
        return []

    print(f"  Using Wikipedia page: {page_title}")
    try:
        wikitext = fetch_wikipedia_wikitext(page_title)
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, json.JSONDecodeError) as exc:
        print(f"  Wikipedia fetch failed for {artist_name}: {exc}")
        return []

    sections = parse_wikipedia_concert_tables(wikitext)
    all_shows: list[tuple[date, dict[str, str]]] = []
    for year_shows in sections.values():
        all_shows.extend(year_shows)

    if not all_shows:
        all_shows = parse_wikipedia_full_date_rows(wikitext)

    if not all_shows:
        print(f"  No concert tables parsed on Wikipedia for {artist_name}.")
        return []

    future = _dedupe_and_pick(all_shows, prefer_future=True)
    if future:
        return future

    print(f"  No upcoming Wikipedia dates for {artist_name}; using recent past shows...")
    return _dedupe_and_pick(all_shows, prefer_future=False)


def find_tours(artist_name: str) -> list[dict[str, str]]:
    tours = bandsintown_tours(artist_name)
    if tours:
        return tours

    print(f"  Falling back to web search for {artist_name}...")
    tours = web_search_tours(artist_name)
    if tours:
        return tours

    print(f"  Falling back to Wikipedia for {artist_name}...")
    return wikipedia_tours(artist_name)


def main() -> None:
    bands = load_bands(DATA_FILE)

    for band in bands:
        name = band.get("name", "Unknown")
        print(f"Fetching tours for {name}...")
        band["tours"] = find_tours(name)
        if band["tours"]:
            for show in band["tours"]:
                print(f"  - {show['date']} | {show['city']} | {show['venue']}")
        else:
            print(f"  No tour dates found for {name}.")
        time.sleep(1)

    save_bands(DATA_FILE, bands)
    print(f"\nDone. Updated {DATA_FILE}.")


if __name__ == "__main__":
    main()
