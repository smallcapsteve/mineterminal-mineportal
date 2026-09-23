#!/usr/bin/env python3
"""Read-only. For every company added by MP_ADD_COVERAGE_GAPS_20260923
(id > 1105), look for an older row that is probably the same company under an
old ticker: same website domain, or a description that shares most of its
distinctive words. Prints candidate pairs only; writes nothing."""
import re
import sqlite3
from urllib.parse import urlparse

DB = "/opt/mineportal/mining_portal.db"
FIRST_NEW = 1106
STOP = set("""the a an and or of in to for on at by with from is are be its it as
company corporation corp inc ltd limited resources mining metals minerals mineral
exploration gold silver copper project projects property properties located focused
canada canadian british columbia ontario quebec nevada engaged acquisition
development developing advancing interest option company's tsx tsxv cse venture
exchange listed symbol trades trading shares""".split())


def domain(u):
    if not u:
        return None
    try:
        h = urlparse(u if "://" in u else "http://" + u).hostname or ""
    except Exception:
        return None
    h = h.lower()
    return h[4:] if h.startswith("www.") else (h or None)


def words(t):
    return {w for w in re.findall(r"[a-z][a-z0-9\-]{3,}", (t or "").lower()) if w not in STOP}


con = sqlite3.connect("file:%s?mode=ro" % DB, uri=True)
con.row_factory = sqlite3.Row
rows = [dict(r) for r in con.execute(
    "SELECT id, ticker, name, exchange, website, description, listing_status FROM companies")]
old = [r for r in rows if r["id"] < FIRST_NEW]
new = [r for r in rows if r["id"] >= FIRST_NEW]
by_dom = {}
for r in old:
    d = domain(r["website"])
    if d:
        by_dom.setdefault(d, []).append(r)
oldw = [(r, words(r["description"])) for r in old]

found = 0
for n in new:
    hits = []
    d = domain(n["website"])
    for o in by_dom.get(d, []) if d else []:
        hits.append(("website", o, 1.0))
    nw = words(n["description"])
    if len(nw) >= 8:
        for o, ow in oldw:
            if len(ow) < 8:
                continue
            j = len(nw & ow) / len(nw | ow)
            if j >= 0.45 and all(h[1]["id"] != o["id"] for h in hits):
                hits.append(("description %.2f" % j, o, j))
    for why, o, _ in hits:
        found += 1
        print("NEW %-7s %-40s | OLD %-7s %-40s status=%s | %s" % (
            n["ticker"], n["name"][:40], o["ticker"], o["name"][:40],
            o["listing_status"] or "active", why))
print("pairs:", found, "new rows checked:", len(new))
