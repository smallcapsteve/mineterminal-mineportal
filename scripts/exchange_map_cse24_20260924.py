#!/usr/bin/env python3
"""Add the new CSE companies to MTP's exchange map (public/exchange-map.js).

Why: a company page decides "CSE" from window.MTP_EXCHANGE (MTP_EXCHANGE_LABEL_FIX_V1) unless
TMX lists the ticker. The map was generated on 2026-09-09 and has none of the 25 CSE companies
added on 2026-09-23, so their pages say "TSXV" and hide the CSE Filings tab, the CSE Listing
button and the SEDAR+ profile line, although the data behind them is loaded.

What it does: for every active CSE company in MinePortal with id > 1105 that is NOT already in
the map and NOT listed by TMX (/tmp/mtp-tmx-quotes.json data[T].exchange TSX/TSXV - GEN is, and
TMX's label wins there), adds  "T": "CSE". Existing entries are never changed. Keeps the file's
header comment, appends the new keys at the end, adds a one-line note.

--apply: copies the file to /root/mtp-backup-exmap-<stamp>/ first, writes atomically. The server
re-reads the file and re-versions the script URL on its own; nothing to restart.
Without --apply: reports only.
Undo: copy the backup back over public/exchange-map.js.
"""
import json
import os
import re
import shutil
import socket
import sqlite3
import sys
from datetime import datetime, timezone

MAP = "/root/minetracker/public/exchange-map.js"
DB = "/opt/mineportal/mining_portal.db"
TMX = "/tmp/mtp-tmx-quotes.json"
HOST = "mnt-scraper-01"
RX = re.compile(r"^(?P<head>.*?)window\.MTP_EXCHANGE = (?P<obj>\{.*\});\s*$", re.S)


def main():
    apply = "--apply" in sys.argv
    if socket.gethostname() != HOST:
        sys.exit("refusing: not %s" % HOST)
    text = open(MAP, encoding="utf-8").read()
    m = RX.match(text)
    if not m:
        sys.exit("refusing: exchange-map.js is not in the expected shape")
    cur = json.loads(m.group("obj"))
    tmx = (json.load(open(TMX)) or {}).get("data") or {}
    con = sqlite3.connect("file:%s?mode=ro" % DB, uri=True)
    new = [r[0] for r in con.execute(
        "SELECT ticker FROM companies WHERE id > 1105 AND exchange='CSE' "
        "AND COALESCE(listing_status,'active')='active' ORDER BY ticker")]
    add, skip = {}, []
    for t in new:
        if t in cur:
            skip.append("%s(already %s)" % (t, cur[t]))
        elif (tmx.get(t) or {}).get("exchange") in ("TSX", "TSXV"):
            skip.append("%s(TMX lists it on %s)" % (t, tmx[t]["exchange"]))
        else:
            add[t] = "CSE"
    print("map entries: %d  new CSE companies: %d  to add: %d" % (len(cur), len(new), len(add)))
    print("add:", " ".join(add))
    print("skip:", " ".join(skip) or "none")
    if not apply or not add:
        print("dry run: nothing written" if not apply else "nothing to add")
        return
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    bdir = "/root/mtp-backup-exmap-%s" % stamp
    os.makedirs(bdir)
    shutil.copy2(MAP, bdir)
    cur.update(add)
    head = m.group("head").rstrip("\n") + (
        "\n/* 2026-09-24: +%d CSE companies added to MinePortal on 2026-09-23 "
        "(scripts/exchange_map_cse24_20260924.py) */\n" % len(add))
    out = head + "window.MTP_EXCHANGE = " + json.dumps(cur) + ";\n"
    assert json.loads(RX.match(out).group("obj")) == cur
    tmp = MAP + ".tmp24"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(out)
    os.replace(tmp, MAP)
    print("backup:", bdir)
    print("wrote %s: %d entries" % (MAP, len(cur)))


if __name__ == "__main__":
    main()
