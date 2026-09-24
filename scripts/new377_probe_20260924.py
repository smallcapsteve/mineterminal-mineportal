#!/usr/bin/env python3
"""Read-only probe for the 377 companies added 2026-09-23 (MinePortal companies.id > 1105).

Writes nothing. Two modes:
  new377_probe_20260924.py desc N     descriptions, part N of 3 (ticker|exchange|primary commodity|text)
  new377_probe_20260924.py meta       conventions for officers / SEDAR ids, what the CSE listing
                                      pages hold for the 25 new CSE companies, commodity labels,
                                      and the SEDAR+ filings store's state
"""
import glob
import json
import re
import sqlite3
import subprocess
import sys
import time
import urllib.request

MP = "/opt/mineportal/mining_portal.db"
UA = "Mozilla/5.0 (compatible; MineTerminalPro/1.0; +https://mineterminalpro.com)"


def ro(path):
    return sqlite3.connect("file:%s?mode=ro" % path, uri=True, timeout=10)


mp = ro(MP)
mp.row_factory = sqlite3.Row
new = [dict(r) for r in mp.execute(
    "SELECT id, ticker, exchange, name, description, officers, sedar_profile_id "
    "FROM companies WHERE id > 1105 AND COALESCE(listing_status,'active')='active' ORDER BY ticker")]

comm = {}
for p in glob.glob("/root/minetracker/*/company_commodities.json") + glob.glob("/root/minetracker/*/*/company_commodities.json"):
    try:
        d = json.load(open(p))
        d = d.get("companies", d) if isinstance(d, dict) else d
        if isinstance(d, dict) and len(d) > 500:
            comm = d
            comm_path = p
            break
    except Exception:
        pass


def prim(t):
    r = comm.get(t) or {}
    return (r.get("primary") or r.get("commodity") or "?") if isinstance(r, dict) else str(r)


mode = sys.argv[1] if len(sys.argv) > 1 else "meta"

if mode == "desc":
    part = int(sys.argv[2])
    n = len(new)
    chunk = new[(part - 1) * n // 3: part * n // 3]
    for r in chunk:
        d = re.sub(r"\s+", " ", r["description"] or "").strip()
        print("%s|%s|%s|%s" % (r["ticker"], r["exchange"], prim(r["ticker"]), d[:230]))
    sys.exit(0)

# ---- meta
print("new active:", len(new))
print("commodity file:", comm_path if comm else "NOT FOUND")
if comm:
    sample_key = next(iter(comm))
    print("commodity record shape:", json.dumps(comm[sample_key])[:300])
    uns = [r["ticker"] for r in new if prim(r["ticker"]) in ("Unspecified", "?", "", None)]
    print("new with Unspecified primary (%d): %s" % (len(uns), " ".join(uns)))

print("\n== conventions on older rows")
for col in ("officers_source", "sedar_source"):
    print(col, [tuple(x) for x in mp.execute(
        "SELECT %s, COUNT(*) FROM companies WHERE %s IS NOT NULL GROUP BY 1" % (col, col))])
for r in mp.execute("SELECT ticker, exchange, officers, officers_updated_at, sedar_profile_id, sedar_updated_at "
                    "FROM companies WHERE officers_source='cse' AND officers IS NOT NULL LIMIT 2"):
    o = json.loads(r["officers"])
    print("sample", r["ticker"], r["exchange"], "officers_updated_at=%s sedar=%s sedar_updated_at=%s" % (
        r["officers_updated_at"], r["sedar_profile_id"], r["sedar_updated_at"]))
    print("   first 2 officers:", json.dumps(o[:2]))
print("role_type values:", sorted({(x.get("role_type") if isinstance(x, dict) else None)
                                   for (s,) in mp.execute("SELECT officers FROM companies WHERE officers IS NOT NULL")
                                   for x in (json.loads(s) or [])}, key=str))

print("\n== CSE listing pages for the new CSE companies")
for r in new:
    if r["exchange"] != "CSE":
        continue
    t = r["ticker"]
    try:
        req = urllib.request.Request("https://thecse.com/s/%s/" % t, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=25) as h:
            url, raw = h.geturl(), h.read()
        m = re.search(rb'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', raw, re.S)
        pp = json.loads(m.group(1))["props"]["pageProps"]
        s = pp.get("staticCompanyInfo") or {}
        md = ((pp.get("staticCompanyData") or {}).get("metadata") or {})
        sf = md.get("sedar_filings") or ""
        pid = re.search(r"(\d{6,12})\.json", str(sf))
        offs = s.get("companyOfficers") or []
        print("%-6s slug=%s status=%s officers=%d sedar=%s  e.g. %s" % (
            t, s.get("slug"), s.get("status"), len(offs), pid.group(1) if pid else "-",
            "; ".join("%s (%s)" % (o.get("name"), o.get("title")) for o in offs[:2])))
    except Exception as e:
        print("%-6s ERROR %s" % (t, str(e)[:100]))
    time.sleep(0.3)

print("\n== CSE slug maps")
for p in ("/root/minetracker/tools/cse_slugmap.tsv", "/root/minetracker/tools/cse_recovered.tsv"):
    try:
        lines = open(p).read().splitlines()
        print(p, len(lines), "lines; last:", lines[-1][:80] if lines else "")
    except Exception as e:
        print(p, e)

print("\n== SEDAR+ filings store")
tf = ro("/root/minetracker/data/tmx_filings.db")
print("tables:", [x[0] for x in tf.execute("SELECT name FROM sqlite_master WHERE type='table'")])
print("coverage cols:", [x[1] for x in tf.execute("PRAGMA table_info(coverage)")])
try:
    print("coverage sample:", [tuple(x) for x in tf.execute("SELECT * FROM coverage LIMIT 2")])
    print("coverage rows by year:", [tuple(x) for x in tf.execute(
        "SELECT year, COUNT(*) FROM coverage GROUP BY year ORDER BY 1")][:20])
except Exception as e:
    print("coverage:", e)
for cmd in ("systemctl list-timers --all --no-pager | grep -i -E 'tmx|cse|commod' | cut -c1-160",
            "ls -la /run/lock/mtp-tmx-filings.lock 2>&1 | cut -c1-120",
            "systemctl list-units --no-pager --state=running | grep -i -E 'tmx|filings|backfill' | cut -c1-120"):
    print("$", cmd.split("|")[0].strip())
    print(subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip())
