#!/usr/bin/env python3
"""Read-only: where do the tickers NFG and LEO appear across the box's SQLite
databases and JSON caches? Used to size a ticker rename (NFG->NFGC, LEO->LCU)
before doing it. Opens every database read-only; prints counts only."""
import glob
import json
import os
import sqlite3

OLD = ["NFG", "LEO"]
NEW = ["NFGC", "LCU"]
ROOTS = ["/opt/mineportal", "/opt/mnt/app", "/opt/sedi", "/root/minetracker/data",
         "/opt/msp/app/data", "/var/lib/mnt-portal"]
KEYCOLS = {"ticker", "symbol", "company_ticker", "tkr", "issuer_symbol", "main_symbol"}


def variants(t):
    return [t, t + ".V", t + ".TO", t + ".CN", t + ".NE", t + ":CA"]


dbs = []
for r in ROOTS:
    for pat in ("*.db", "*/*.db", "*/*/*.db", "*.sqlite", "*/*.sqlite"):
        dbs += glob.glob(os.path.join(r, pat))
dbs = sorted(set(p for p in dbs if "backup" not in p and "/venv" not in p and "/.venv" not in p))

for path in dbs:
    try:
        con = sqlite3.connect("file:%s?mode=ro" % path, uri=True, timeout=5)
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    except Exception as e:
        print("ERR", path, str(e)[:80])
        continue
    for t in tables:
        try:
            cols = [r[1] for r in con.execute('PRAGMA table_info("%s")' % t)]
        except Exception:
            continue
        for c in cols:
            if c.lower() not in KEYCOLS:
                continue
            out = []
            for tk in OLD + NEW:
                v = variants(tk)
                q = 'SELECT COUNT(*) FROM "%s" WHERE UPPER("%s") IN (%s)' % (t, c, ",".join("?" * len(v)))
                try:
                    n = con.execute(q, v).fetchone()[0]
                except Exception:
                    n = "?"
                if n:
                    out.append("%s=%s" % (tk, n))
            if out:
                print("%s | %s.%s | %s" % (path, t, c, " ".join(out)))
    con.close()

for jp in ["/opt/mnt/app/data/tickers.json", "/var/lib/mnt-portal/universe.json",
           "/tmp/mtp-tmx-quotes.json", "/tmp/mtp-cse-quotes.json"]:
    try:
        s = open(jp).read()
    except Exception:
        continue
    hits = []
    for tk in OLD + NEW:
        n = sum(s.count('"%s"' % x) for x in variants(tk))
        if n:
            hits.append("%s=%d" % (tk, n))
    print("json", jp, " ".join(hits) or "none")
