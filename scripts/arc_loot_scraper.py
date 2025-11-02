#!/usr/bin/env python3
import argparse
import csv
import json
import os
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "ArcLootBot/1.0 (+github action; contact via repo issues)",
})

PRICE_PATTERNS = [
    re.compile(r"Sell\s*Price\s*[:]?\\s*(\\d+)", re.I),
    re.compile(r"Price\s*[:]?\\s*(\\d+)", re.I),
    re.compile(r"Coins?\s*[:]?\\s*(\\d+)", re.I),
]

LINK_RE = re.compile(r"^/wiki/", re.I)

CACHE_DIR = Path(".cache/arc_loot")
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def cached_get(url: str, force: bool = False, sleep: float = 0.5) -> str:
    """Fetch a page with optional caching."""
    fname = CACHE_DIR / (re.sub(r"[^a-zA-Z0-9]+", "_", url.strip("/")) + ".html")
    if fname.exists() and not force:
        return fname.read_text(encoding="utf-8", errors="ignore")
    r = SESSION.get(url, timeout=30)
    r.raise_for_status()
    text = r.text
    fname.write_text(text, encoding="utf-8")
    time.sleep(sleep)
    return text


def parse_price_from_soup(soup: BeautifulSoup) -> int | None:
    """Try to extract a sell price from a wiki item page."""
    # 1) Check infobox entries
    for dt in soup.select(".infobox dt, table.infobox th"):
        if re.search(r"Sell\\s*Price|Price", dt.get_text(" ", strip=True), re.I):
            dd = dt.find_next(["dd", "td"]) if dt else None
            if dd:
                m = re.search(r"(\\d+)", dd.get_text(" ", strip=True))
                if m:
                    return int(m.group(1))
    # 2) Fallback to searching the text
    text = soup.get_text("\\n", strip=True)
    for pat in PRICE_PATTERNS:
        m = pat.search(text)
        if m:
            return int(m.group(1))
    return None


def extract_table_rows(soup: BeautifulSoup):
    """Extract the main loot table and parse cell + link data."""
    table = soup.find("table")
    if not table:
        raise RuntimeError("No table found on Loot page")

    headers = [th.get_text(" ", strip=True) for th in table.find_all("th")]
    rows = []

    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if not tds:
            continue
        cells = [td.get_text(" ", strip=True) for td in tds]

        link_cells = []
        for td in tds:
            links = []
            for a in td.find_all("a", href=True):
                href = a["href"].strip()
                if LINK_RE.search(href):
                    links.append({
                        "title": a.get_text(" ", strip=True),
                        "href": href
                    })
            link_cells.append(links)

        rows.append({
            "cells": cells,
            "links": link_cells
        })

    return headers, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--loot-path", required=True)
    ap.add_argument("--out-json", required=True)
    ap.add_argument("--out-csv", required=True)
    ap.add_argument("--out-md", required=True)
    args = ap.parse_args()

    force = (os.getenv("FORCE_REFETCH", "false").lower() == "true")

    loot_url = f"{args.base_url}{args.loot_path}"
    loot_html = cached_get(loot_url, force=force)
    loot_soup = BeautifulSoup(loot_html, "lxml")

    headers, rows = extract_table_rows(loot_soup)

    try:
        name_idx = next(i for i, h in enumerate(headers) if h.lower().startswith("item"))
    except StopIteration:
        name_idx = 0

    sell_idx = None
    for i, h in enumerate(headers):
        if re.search(r"sell\\s*price|price", h, re.I):
            sell_idx = i
            break

    recycles_idx = None
    for i, h in enumerate(headers):
        if re.search(r"recycles\\s*to", h, re.I):
            recycles_idx = i
            break

    out_headers = list(headers)
    if "Recycled Sell Price" not in out_headers:
        out_headers.append("Recycled Sell Price")
    if "Decision (Recycle/Sell)" not in out_headers:
        out_headers.append("Decision (Recycle/Sell)")

    data = []

    for row in rows:
        cells = row["cells"]
        links = row["links"]
        name = cells[name_idx] if name_idx < len(cells) else ""
        sell_price = None
        if sell_idx is not None and sell_idx < len(cells):
            m = re.search(r"(\\d+)", cells[sell_idx])
            if m:
                sell_price = int(m.group(1))

        recycled_sum = 0
        found_any = False
        if recycles_idx is not None and recycles_idx < len(links):
            for lk in links[recycles_idx]:
                item_url = f"{args.base_url}{lk['href']}"
                html = cached_get(item_url, force=force)
                s = BeautifulSoup(html, "lxml")
                p = parse_price_from_soup(s)
                if p is not None:
                    recycled_sum += p
                    found_any = True

        recycled_price = recycled_sum if found_any else None

        decision = "Unknown"
        if sell_price is not None and recycled_price is not None:
            decision = "Recycle" if recycled_price > sell_price else "Sell"

        out_cells = list(cells)
        out_cells += [
            str(recycled_price) if recycled_price is not None else "",
            decision
        ]

        data.append({
            "Item": name,
            "row": out_cells
        })

    Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)

    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump({
            "headers": out_headers,
            "rows": [d["row"] for d in data],
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }, f, ensure_ascii=False, indent=2)

    with open(args.out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(out_headers)
        for d in data:
            w.writerow(d["row"])

    with open(args.out_md, "w", encoding="utf-8") as f:
        f.write("| " + " | ".join(out_headers) + " |\\n")
        f.write("|" + "---|" * len(out_headers) + "\\n")
        for d in data:
            f.write("| " + " | ".join(c if isinstance(c, str) else str(c) for c in d["row"]) + " |\\n")

    print(f"Wrote {args.out_json}, {args.out_csv}, {args.out_md}")


if __name__ == "__main__":
    sys.exit(main())
