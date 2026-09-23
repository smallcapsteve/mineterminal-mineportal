#!/usr/bin/env python3
"""MP_ADD_COVERAGE_GAPS_20260923 - add 401 mining companies to MinePortal.

Source list: claude/MTP_COVERAGE_GAPS_2026-09-23.csv (Justin chose "miners only":
producers, royalty/streaming, explorers and developers; drillers, bullion
trusts, investors and tech firms left out). SPAR, CEXY and IRON are left out
because they are renames of DG, BFG and BOLT, which MinePortal already has.

What it does
  * For each company, reads the exchange's own profile: TMX Money GraphQL for
    TSX/TSXV, the CSE listing page for CSE. Takes the exchange's name,
    description and website. Cached to fetched.json so --apply reuses the
    exact text the dry run showed.
  * Skips any ticker already in `companies`, whatever its listing_status
    (hidden rows are reported, never duplicated or un-hidden).
  * --apply: backs up the database first (sqlite backup API, outside
    /opt/mineportal), inserts every row in ONE transaction using only columns
    admin_create() also accepts, checks the row count, and marks matching
    pending rows in company_candidates as 'promoted'.
  * Never touches existing rows, properties or any other table.

Undo: the --apply output prints the backup path and the highest company id
before the run; DELETE FROM companies WHERE id > <that id> removes exactly the
new rows.

Usage
  python3 add_companies_20260923.py            # dry run: fetch + report, no writes
  python3 add_companies_20260923.py --apply    # write
"""
import json
import os
import re
import socket
import sqlite3
import sys
import time
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DB = "/opt/mineportal/mining_portal.db"
DATA = os.path.join(HERE, "add_companies_20260923.json")
CACHE = os.path.join(HERE, "fetched.json")
EXPECTED_HOST = "mnt-scraper-01"
UA = "Mozilla/5.0 (compatible; MineTerminalPro/1.0; +https://mineterminalpro.com)"
NO_DESC = {"AUMN"}  # TMX shows another company's description for Golden Minerals
TMX_Q = ("query getQuoteBySymbol($symbol: String, $locale: String) { "
         "getQuoteBySymbol(symbol: $symbol, locale: $locale) { symbol name "
         "exShortName longDescription website } }")
SHARE_CLASS = re.compile(
    r"\s+(Ordinary [Ss]hares|Class [AB]\b.*|Common Shares.*|Subordinate Voting.*|Trust Units)$")


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def http(url, data=None, headers=None, timeout=25):
    h = {"User-Agent": UA}
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.geturl(), r.read()


def fetch_tmx(sym):
    body = json.dumps({"operationName": "getQuoteBySymbol",
                       "variables": {"symbol": sym, "locale": "en"},
                       "query": TMX_Q}).encode()
    _, _, raw = http("https://app-money.tmx.com/graphql", body,
                     {"Content-Type": "application/json", "locale": "en",
                      "Origin": "https://money.tmx.com", "Referer": "https://money.tmx.com/"})
    q = (json.loads(raw).get("data") or {}).get("getQuoteBySymbol")
    if not q:
        return None
    return {"name": q.get("name"), "description": q.get("longDescription"),
            "website": q.get("website"), "exchange_seen": q.get("exShortName")}


def fetch_cse(sym):
    _, url, raw = http("https://thecse.com/s/%s/" % urllib.request.quote(sym))
    m = re.search(rb'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', raw, re.S)
    if not m:
        return None
    s = (json.loads(m.group(1)).get("props", {}).get("pageProps", {})
         .get("staticCompanyInfo") or {})
    if not s:
        return None
    return {"name": s.get("title"), "description": s.get("companyDescription"),
            "website": s.get("url"), "exchange_seen": s.get("exchange"),
            "slug": s.get("slug"), "status": s.get("status")}


def clean(text):
    if not text:
        return None
    t = re.sub(r"\s+", " ", str(text)).strip()
    return None if t in ("", "NA", "N/A") else t


def main():
    apply = "--apply" in sys.argv
    host = socket.gethostname()
    if host != EXPECTED_HOST:
        sys.exit("refusing: this is %s, not %s" % (host, EXPECTED_HOST))
    if not os.path.exists(DB):
        sys.exit("refusing: %s not found" % DB)

    rows = json.load(open(DATA))
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    existing = {r["ticker"].upper(): dict(r) for r in con.execute(
        "SELECT id, ticker, name, exchange, listing_status FROM companies")}

    to_add, skipped, fetch_fail, name_diff = [], [], [], []
    for r in rows:
        t = r["ticker"]
        if t.upper() in existing:
            e = existing[t.upper()]
            skipped.append("%s (already id %s, %s, status=%s)" % (
                t, e["id"], e["name"], e["listing_status"] or "active"))
            continue
        key = r["exchange"] + ":" + t
        if key not in cache:
            try:
                cache[key] = (fetch_cse(t) if r["exchange"] == "CSE" else fetch_tmx(t)) or {}
            except Exception as ex:  # network error: record, keep going
                cache[key] = {"error": str(ex)[:120]}
            time.sleep(0.25)
        f = cache[key]
        if not f or f.get("error") or not f.get("name"):
            fetch_fail.append("%s:%s %s" % (r["exchange"], t, (f or {}).get("error", "no profile")))
        name = clean(SHARE_CLASS.sub("", f.get("name") or "")) or r["name"]
        if name.lower().rstrip(".") != r["name"].lower().rstrip("."):
            name_diff.append("%s: %s -> %s" % (t, r["name"], name))
        desc = None if t in NO_DESC else clean(f.get("description"))
        to_add.append({
            "ticker": t,
            "name": name,
            "exchange": r["exchange"],
            "description": desc,
            "description_source": (("cse" if r["exchange"] == "CSE" else "tmx") if desc else None),
            "description_updated_at": now() if desc else None,
            "website": clean(f.get("website")),
        })

    json.dump(cache, open(CACHE, "w"), indent=0)

    by_ex = {}
    for a in to_add:
        by_ex[a["exchange"]] = by_ex.get(a["exchange"], 0) + 1
    no_desc = [a["ticker"] for a in to_add if not a["description"]]

    print("mode:", "APPLY" if apply else "dry run")
    print("list: %d  to add: %d  skipped (already in MinePortal): %d" % (len(rows), len(to_add), len(skipped)))
    print("to add by exchange:", by_ex)
    print("with description: %d  without: %d -> %s" % (len(to_add) - len(no_desc), len(no_desc), " ".join(no_desc)))
    print("with website: %d" % sum(1 for a in to_add if a["website"]))
    for s in skipped:
        print("  skip", s)
    for s in fetch_fail:
        print("  no-profile", s)
    print("exchange name differs from list name: %d" % len(name_diff))
    for s in name_diff[:40]:
        print("  name", s)

    if not apply:
        print("dry run: nothing written")
        return

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup = "/root/mineportal-backup-add401-%s.db" % stamp
    dst = sqlite3.connect(backup)
    con.backup(dst)
    dst.close()
    print("backup:", backup, os.path.getsize(backup), "bytes")

    before = con.execute("SELECT COUNT(*), MAX(id) FROM companies").fetchone()
    cols = ["ticker", "name", "exchange", "description", "description_source",
            "description_updated_at", "website"]
    try:
        con.execute("BEGIN")
        for a in to_add:
            con.execute("INSERT INTO companies (%s) VALUES (%s)" % (
                ",".join(cols), ",".join("?" * len(cols))), [a[c] for c in cols])
        after = con.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
        if after != before[0] + len(to_add):
            raise RuntimeError("count check failed: %d + %d != %d" % (before[0], len(to_add), after))
        promoted = con.execute(
            "UPDATE company_candidates SET status='promoted', reviewed_at=?, "
            "note='added by MP_ADD_COVERAGE_GAPS_20260923' "
            "WHERE status='pending' AND UPPER(ticker) IN (%s)" % ",".join("?" * len(to_add)),
            [now()] + [a["ticker"].upper() for a in to_add]).rowcount
        con.commit()
    except Exception as ex:
        con.rollback()
        sys.exit("ROLLED BACK, nothing written: %s" % ex)

    print("inserted: %d  companies %d -> %d  highest id before run: %d" % (
        len(to_add), before[0], after, before[1]))
    print("candidates promoted:", promoted)
    active = con.execute(
        "SELECT COUNT(*) FROM companies WHERE COALESCE(listing_status,'active')='active'").fetchone()[0]
    print("active companies now:", active)
    print("undo: DELETE FROM companies WHERE id > %d   (or restore %s with mineportal stopped)" % (before[1], backup))


if __name__ == "__main__":
    main()
