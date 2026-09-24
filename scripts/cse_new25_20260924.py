#!/usr/bin/env python3
"""Management, SEDAR+ profile and CSE lookup for the 25 CSE companies added 2026-09-23.

Justin (2026-09-24): "The 25 CSE companies ... Adding them would bring in management, CSE
filings, SEDAR+ and share counts."

For each active CSE company with MinePortal id > 1105 it reads the CSE's own listing page
(https://thecse.com/s/<SYMBOL>/ -> __NEXT_DATA__), the same page the 2026-09-10 officers and
SEDAR loads read, and takes:
  * staticCompanyInfo.companyOfficers -> companies.officers (JSON [{name, title, role_type:
    "officer"}], the format the 328 existing CSE rows use), officers_source='cse'
  * staticCompanyData.metadata.sedar_filings -> the 9-digit SEDAR profile id ->
    companies.sedar_profile_id, sedar_source='cse'
  * slug -> tools/cse_recovered.tsv for any ticker missing from both CSE slug maps
    (only AZCU on 2026-09-24: the CSE still files it under blade-resources-inc)

Rules
  * Writes a column only where it is NULL today; never overwrites.
  * Drops placeholder officers ("Not Applicable", "N/A", "TBD", "Vacant", blank).
  * --apply: sqlite backup of MinePortal first, all row updates in ONE transaction, backup of
    cse_recovered.tsv before appending; then queues the CSE filings collector for these
    tickers and an early CSE quotes/share-count run (both as transient systemd units), and
    sends MTP's cache-clear.
  * Without --apply: fetch and report only.

Undo: restore the printed MinePortal backup (or UPDATE the listed ids back to NULL), and
restore cse_recovered.tsv from its printed backup.
"""
import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone

DB = "/opt/mineportal/mining_portal.db"
SLUGMAP = "/root/minetracker/tools/cse_slugmap.tsv"
RECOVERED = "/root/minetracker/tools/cse_recovered.tsv"
HOST = "mnt-scraper-01"
UA = "Mozilla/5.0 (compatible; MineTerminalPro/1.0; +https://mineterminalpro.com)"
PLACEHOLDER = re.compile(r"^(not applicable|n/?a|tbd|vacant|none|-+)?$", re.I)


def fetch(sym):
    req = urllib.request.Request("https://thecse.com/s/%s/" % sym, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as h:
        raw = h.read()
    m = re.search(rb'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', raw, re.S)
    pp = json.loads(m.group(1))["props"]["pageProps"]
    s = pp.get("staticCompanyInfo") or {}
    md = (pp.get("staticCompanyData") or {}).get("metadata") or {}
    pid = re.search(r"(\d{6,12})\.json", str(md.get("sedar_filings") or ""))
    offs = []
    for o in s.get("companyOfficers") or []:
        name = re.sub(r"\s+", " ", str(o.get("name") or "")).strip()
        title = re.sub(r"\s+", " ", str(o.get("title") or "")).strip()
        if PLACEHOLDER.match(name):
            continue
        offs.append({"name": name, "title": title, "role_type": "officer"})
    return {"slug": s.get("slug"), "status": s.get("status"), "officers": offs,
            "sedar": pid.group(1) if pid else None}


def slug_tickers():
    have = set()
    for p in (SLUGMAP, RECOVERED):
        try:
            for ln in open(p):
                if ln.strip() and not ln.startswith("#"):
                    have.add(ln.split("\t")[0].strip().upper())
        except FileNotFoundError:
            pass
    return have


def main():
    apply = "--apply" in sys.argv
    if socket.gethostname() != HOST:
        sys.exit("refusing: not %s" % HOST)
    con = sqlite3.connect(DB, timeout=30)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(
        "SELECT id, ticker, officers, sedar_profile_id FROM companies WHERE id > 1105 "
        "AND exchange='CSE' AND COALESCE(listing_status,'active')='active' ORDER BY ticker")]
    print("new CSE companies:", len(rows))
    slugs = slug_tickers()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    plan_off, plan_sedar, plan_slug = [], [], []
    for r in rows:
        t = r["ticker"]
        try:
            f = fetch(t)
        except Exception as e:
            print("%-6s FETCH FAILED %s" % (t, str(e)[:80]))
            continue
        if f["officers"] and not r["officers"]:
            plan_off.append((r["id"], t, f["officers"]))
        if f["sedar"] and not r["sedar_profile_id"]:
            plan_sedar.append((r["id"], t, f["sedar"]))
        if t.upper() not in slugs and f["slug"]:
            plan_slug.append((t, f["slug"]))
        print("%-6s status=%-9s officers=%d sedar=%s slug=%s%s" % (
            t, f["status"], len(f["officers"]), f["sedar"] or "-", f["slug"],
            "" if t.upper() in slugs else "  (NOT on slug map)"))
        time.sleep(0.3)

    print("\nwill set officers on %d, SEDAR profile on %d, add %d slug(s): %s" % (
        len(plan_off), len(plan_sedar), len(plan_slug), plan_slug))
    tickers = ",".join(r["ticker"] for r in rows)
    if not apply:
        print("dry run: nothing written")
        return

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup = "/root/mineportal-backup-cse25-%s.db" % stamp
    dst = sqlite3.connect(backup)
    con.backup(dst)
    dst.close()
    print("backup:", backup, os.path.getsize(backup), "bytes")
    try:
        con.execute("BEGIN IMMEDIATE")
        n_o = n_s = 0
        for cid, t, offs in plan_off:
            n_o += con.execute(
                "UPDATE companies SET officers=?, officers_source='cse', officers_updated_at=? "
                "WHERE id=? AND officers IS NULL", (json.dumps(offs, ensure_ascii=False), now, cid)).rowcount
        for cid, t, pid in plan_sedar:
            n_s += con.execute(
                "UPDATE companies SET sedar_profile_id=?, sedar_source='cse', sedar_updated_at=? "
                "WHERE id=? AND sedar_profile_id IS NULL", (pid, now, cid)).rowcount
        if n_o != len(plan_off) or n_s != len(plan_sedar):
            raise RuntimeError("row count %d/%d officers, %d/%d sedar" % (n_o, len(plan_off), n_s, len(plan_sedar)))
        con.commit()
    except Exception as e:
        con.rollback()
        sys.exit("ROLLED BACK, nothing written: %s" % e)
    print("officers set: %d  SEDAR profile set: %d  (ids: %s)" % (
        n_o, n_s, " ".join(str(x[0]) for x in plan_off + plan_sedar)))

    if plan_slug:
        rb = RECOVERED + ".bak-cse25-" + stamp
        shutil.copy2(RECOVERED, rb)
        with open(RECOVERED, "a") as fh:
            for t, slug in plan_slug:
                fh.write("%s\thttps://thecse.com/listings/%s/\n" % (t, slug))
        print("cse_recovered.tsv: appended %d (backup %s)" % (len(plan_slug), rb))

    for unit, cmd in (
            ("mtp-cse-filings-new25", ["/usr/bin/env", "python3",
                                       "/root/minetracker/scripts/cse_filings_refresh.py", "--only", tickers]),):
        r = subprocess.run(["systemd-run", "--unit=" + unit, "--collect",
                            "--working-directory=/root/minetracker"] + cmd, capture_output=True, text=True)
        print("started %s: rc=%s %s" % (unit, r.returncode, (r.stderr or r.stdout).strip()[:160]))
    r = subprocess.run(["systemctl", "start", "--no-block", "mtp-cse-refresh.service"], capture_output=True, text=True)
    print("mtp-cse-refresh queued early: rc=%s" % r.returncode)
    r = subprocess.run(["/opt/mineportal/venv/bin/python", "-c",
                        "import mtp_notify; mtp_notify._send('admin.admin_bulk_create', table='companies')"],
                       cwd="/opt/mineportal", capture_output=True, text=True)
    print("MTP cache-clear sent: rc=%s" % r.returncode)


if __name__ == "__main__":
    main()
