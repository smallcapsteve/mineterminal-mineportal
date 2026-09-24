#!/usr/bin/env python3
"""Read-only coverage audit for the companies added by MP_ADD_COVERAGE_GAPS_20260923
(MinePortal companies.id > 1105). For every data source a company page draws on,
reports how many of the new companies it holds, next to the same figure for the
older companies, so a gap reads as "new companies lack X" rather than "X is thin".
Writes nothing except its own report file next to this script."""
import glob
import json
import os
import re
import sqlite3
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
MP = "/opt/mineportal/mining_portal.db"
SUFFIX = re.compile(r"\.(CN|V|TO|TSX|VN|NE|H)$")


def bare(t):
    t = str(t or "").upper().strip()
    t = re.sub(r":CA$", "", t)
    for _ in range(2):
        t = SUFFIX.sub("", t)
    return t


def ro(path):
    return sqlite3.connect("file:%s?mode=ro" % path, uri=True, timeout=10)


mp = ro(MP)
mp.row_factory = sqlite3.Row
rows = [dict(r) for r in mp.execute(
    "SELECT id, ticker, exchange, description, website, officers, sedar_profile_id, news_source "
    "FROM companies WHERE COALESCE(listing_status,'active')='active'")]
new = {bare(r["ticker"]): r for r in rows if r["id"] > 1105}
old = {bare(r["ticker"]): r for r in rows if r["id"] <= 1105}
NEW, OLD = set(new), set(old)
by_ex = defaultdict(set)
for t, r in new.items():
    by_ex[r["exchange"]].add(t)

out = []


def line(label, have_new, have_old, note=""):
    hn = len(set(have_new) & NEW)
    ho = len(set(have_old) & OLD)
    out.append("%-46s new %4d/%-4d (%3d%%)   older %4d/%-4d (%3d%%) %s" % (
        label, hn, len(NEW), 100 * hn // max(1, len(NEW)), ho, len(OLD), 100 * ho // max(1, len(OLD)), note))
    return set(have_new) & NEW


out.append("new companies: %d  (%s)   older active: %d" % (
    len(NEW), ", ".join("%s %d" % (k, len(v)) for k, v in sorted(by_ex.items())), len(OLD)))
out.append("")
out.append("== MinePortal row")
line("description", {t for t, r in new.items() if r["description"]}, {t for t, r in old.items() if r["description"]})
line("website", {t for t, r in new.items() if r["website"]}, {t for t, r in old.items() if r["website"]})
line("officers (CSE officer list)", {t for t, r in new.items() if r["officers"]}, {t for t, r in old.items() if r["officers"]})
line("sedar_profile_id", {t for t, r in new.items() if r["sedar_profile_id"]}, {t for t, r in old.items() if r["sedar_profile_id"]})
line("news_source set", {t for t, r in new.items() if r["news_source"]}, {t for t, r in old.items() if r["news_source"]})
props = {bare(r[0]) for r in mp.execute(
    "SELECT DISTINCT c.ticker FROM companies c LEFT JOIN property_companies pc ON pc.company_id=c.id "
    "LEFT JOIN properties p ON (p.company_id=c.id OR p.id=pc.property_id) WHERE p.id IS NOT NULL")}
line("has a property (Mining Data map/list)", props, props)

out.append("")
out.append("== JSON caches (keys or rows naming a ticker)")


def tickers_in(obj, depth=0):
    found = set()
    if depth > 3:
        return found
    if isinstance(obj, dict):
        keys = list(obj.keys())
        if keys and sum(1 for k in keys[:200] if re.fullmatch(r"[A-Z0-9.:\-]{1,14}", str(k))) > min(20, len(keys) * 0.8):
            found |= {bare(k) for k in keys}
        for k in ("data", "companies", "rows", "items", "quotes", "events", "tickers"):
            if k in obj:
                found |= tickers_in(obj[k], depth + 1)
    elif isinstance(obj, list):
        for it in obj[:50000]:
            if isinstance(it, dict):
                for k in ("ticker", "symbol", "t", "company_ticker"):
                    if it.get(k):
                        found.add(bare(it[k]))
                        break
    return found


paths = sorted(set(glob.glob("/tmp/mtp-*.json") + glob.glob("/root/minetracker/cache/*.json")
                   + glob.glob("/root/minetracker/data/*.json") + glob.glob("/root/minetracker/public/data/*.json")))
for p in paths:
    try:
        if os.path.getsize(p) > 150_000_000:
            continue
        d = json.load(open(p))
    except Exception:
        continue
    ts = tickers_in(d)
    if len(ts & (NEW | OLD)) < 20:
        continue
    line(os.path.basename(p), ts, ts)

out.append("")
out.append("== SQLite stores (rows keyed by ticker)")
DBS = {
    "MTP tmx_filings (SEDAR+ for TSX/TSXV)": "/root/minetracker/data/tmx_filings.db",
    "MTP cse_filings (CSE Filings tab)": "/root/minetracker/data/cse_filings.db",
    "MNT portal.db": "/opt/mnt/app/portal/portal.db",
    "MNT exchange_news.db": "/opt/mnt/app/data/exchange_news.db",
    "SediTracker sedi.db": "/opt/sedi/app/portal/sedi.db",
    "MSP msp.db": "/opt/msp/app/data/msp.db",
}
SKIP = {"pageviews", "fx_records", "events_fts", "stock_quotes"}
for label, path in DBS.items():
    if not os.path.exists(path):
        out.append("%s: missing" % label)
        continue
    try:
        con = ro(path)
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    except Exception as e:
        out.append("%s: %s" % (label, e))
        continue
    for t in tables:
        if t in SKIP or t.startswith("sqlite_") or "_fts" in t or "legacy" in t:
            continue
        try:
            cols = [r[1] for r in con.execute('PRAGMA table_info("%s")' % t)]
        except Exception:
            continue
        col = next((c for c in cols if c.lower() in ("ticker", "symbol")), None)
        if not col:
            continue
        try:
            ts = {bare(r[0]) for r in con.execute('SELECT DISTINCT "%s" FROM "%s"' % (col, t)) if r[0]}
        except Exception:
            continue
        if len(ts & (NEW | OLD)) < 5:
            continue
        line("%s :: %s" % (label.split(" (")[0], t), ts, ts)
    con.close()

# depth of SEDAR+ history for the new TSX/TSXV names
try:
    con = ro("/root/minetracker/data/tmx_filings.db")
    mins = {r[0]: (r[1], r[2]) for r in con.execute(
        "SELECT ticker, MIN(filing_date), COUNT(*) FROM filings GROUP BY ticker")}
    cov = Counter()
    for t in NEW:
        if t in mins:
            cov["since " + mins[t][0][:4]] += 1
    out.append("new companies' SEDAR+ history starts: %s" % dict(sorted(cov.items())))
    oldmins = Counter(mins[t][0][:4] for t in OLD if t in mins)
    out.append("older companies' SEDAR+ history starts: %s" % dict(sorted(oldmins.items())[:6]))
except Exception as e:
    out.append("tmx depth: %s" % e)

# CSE slug map coverage for new CSE names (the CSE Filings tab needs a slug)
slugs = set()
for p in ("/root/minetracker/tools/cse_slugmap.tsv", "/root/minetracker/tools/cse_recovered.tsv"):
    try:
        for ln in open(p):
            if ln.strip() and not ln.startswith("#"):
                slugs.add(ln.split("\t")[0].strip().upper())
    except Exception:
        pass
cse_new = by_ex.get("CSE", set())
out.append("new CSE companies on the CSE slug map: %d/%d  missing: %s" % (
    len(cse_new & slugs), len(cse_new), " ".join(sorted(cse_new - slugs))))

txt = "\n".join(out)
open(os.path.join(HERE, "coverage_report.txt"), "w").write(txt + "\n")
print(txt)
