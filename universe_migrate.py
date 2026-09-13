#!/usr/bin/env python3
"""MP_UNIVERSE_V1 migration — one-time, idempotent, reversible.

Three things, in this order:

  1. Add the new nullable columns and the candidates table (universe.py owns
     the definitions; this only calls them).
  2. Backfill `symbol`, `news_source` and `news_source_params` from MNT's
     tickers.json, matched on the bare ticker. This is the step that lets
     tickers.json stop being the universe: everything in it that is not a
     company name moves onto the company row.
  3. Insert the 15 screened mining companies MNT/SediTracker had and MinePortal
     did not (claude/UNIVERSE_SYNC_SCREEN_106_2026-09-13.md).

Run with --dry-run first. The dry run opens the database read-only and writes
nothing at all — including no schema — so it can be trusted as a rehearsal.

    python3 universe_migrate.py --dry-run
    python3 universe_migrate.py --apply
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
from datetime import datetime

DB = "/opt/mineportal/mining_portal.db"
TICKERS = "/opt/mnt/app/tickers.json"
EXPECT_HOST = "mnt-scraper-01"
BACKUP_ROOT = "/root"          # outside the tree being edited, per the runbook

# Screened 2026-09-13. Verified against the actual listing, not against the
# name MNT had stored — several of those named a different company outright.
NEW_COMPANIES = [
    # ticker, name,                            exchange, symbol
    ("TECK", "Teck Resources Limited",          "TSX",  "TECK.B.TO"),
    ("URC",  "Uranium Royalty Corp.",           "TSX",  "URC.TO"),
    ("MSV",  "Minco Silver Corporation",        "TSX",  "MSV.TO"),
    ("AERO", "Aero Energy Limited",             "TSXV", "AERO.V"),
    ("FEO",  "Oceanic Iron Ore Corp.",          "TSXV", "FEO.V"),
    ("GGA",  "Goldgroup Mining Inc.",           "TSXV", "GGA.V"),
    ("GX",   "Guardian Exploration Inc.",       "TSXV", "GX.V"),
    ("HI",   "Highland Copper Company Inc.",    "TSXV", "HI.V"),
    ("KRY",  "Koryx Copper Inc.",               "TSXV", "KRY.V"),
    ("MEX",  "Mexican Gold Mining Corp.",       "TSXV", "MEX.V"),
    ("NOAL", "NOA Lithium Brines Inc.",         "TSXV", "NOAL.V"),
    ("NRN",  "Northern Shield Resources Inc.",  "TSXV", "NRN.V"),
    ("TIN",  "Tincorp Metals Inc.",             "TSXV", "TIN.V"),
    ("BRU",  "Brutus Mining Inc.",              "CSE",  "BRU.CN"),
    ("EVR",  "Evolve Royalties Ltd.",           "CSE",  "EVR.CN"),
]


def die(msg: str) -> None:
    print(f"ABORT: {msg}", file=sys.stderr)
    sys.exit(2)


def guard() -> None:
    host = socket.gethostname()
    if host != EXPECT_HOST:
        die(f"wrong machine: this is {host!r}, expected {EXPECT_HOST!r}")
    if not os.path.exists(DB):
        die(f"no database at {DB}")
    if not os.path.exists(TICKERS):
        die(f"no tickers.json at {TICKERS} — nothing to backfill from")


def backup() -> str:
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    dest_dir = os.path.join(BACKUP_ROOT, f"mineportal-universe-backup-{stamp}")
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, "mining_portal.db")
    # .backup, never cp — a live WAL database copied with cp can be torn.
    subprocess.run(["sqlite3", DB, f".backup {dest}"], check=True)
    shutil.copy2(TICKERS, os.path.join(dest_dir, "tickers.json"))
    size = os.path.getsize(dest)
    print(f"  backup:        {dest}  ({size:,} bytes)")
    if size < 1_000_000:
        die("backup looks too small — refusing to continue")
    return dest_dir


def load_tickers() -> dict[str, dict]:
    """bare ticker -> the scraper config MNT held for it."""
    by_bare: dict[str, dict] = {}
    for r in json.load(open(TICKERS)):
        if not isinstance(r, dict):
            continue
        sym = (r.get("ticker") or "").strip().upper()
        if not sym:
            continue
        bare = sym.split(".")[0]
        # tickers.json can hold a bare ticker twice (a .V and a .TO line). Keep
        # the first; the duplicates measured on 2026-09-13 were 14 of 1,154 and
        # all were the same company on two venues.
        by_bare.setdefault(bare, {
            "symbol": sym,
            "name": r.get("name"),
            "source": r.get("source"),
            "params": r.get("source_params"),
        })
    return by_bare


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.apply == args.dry_run:
        die("pass exactly one of --apply or --dry-run")

    guard()
    tj = load_tickers()
    print(f"MP_UNIVERSE_V1 migration  ({'APPLY' if args.apply else 'DRY RUN'})")
    print(f"  tickers.json:  {len(tj):,} unique bare tickers")

    if args.apply:
        backup_dir = backup()
        con = sqlite3.connect(DB)
    else:
        # Read-only URI: a dry run that creates tables is not a dry run.
        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        backup_dir = "(none — dry run)"
    con.row_factory = sqlite3.Row

    existing = {
        r["ticker"].strip().upper(): r
        for r in con.execute("SELECT id, ticker, name, exchange FROM companies")
    }
    print(f"  MinePortal:    {len(existing):,} companies before")

    # ---- 1. schema -------------------------------------------------------
    if args.apply:
        sys.path.insert(0, "/opt/mineportal")
        from universe import init_universe_schema
        added = init_universe_schema(con)
        print(f"  schema added:  {', '.join(added)}")
    else:
        cols = {r[1] for r in con.execute("PRAGMA table_info(companies)")}
        want = {"symbol", "news_source", "news_source_params",
                "news_source_updated_at"}
        print(f"  schema would add: {', '.join(sorted(want - cols)) or '(nothing)'}")

    # ---- 2. backfill source config --------------------------------------
    matched = sum(1 for t in existing if t in tj)
    with_source = sum(1 for t in existing if tj.get(t, {}).get("source"))
    print(f"  backfill:      {matched:,} companies matched in tickers.json, "
          f"{with_source:,} carry a news source")

    if args.apply:
        n = 0
        for bare, row in existing.items():
            cfg = tj.get(bare)
            if not cfg:
                continue
            con.execute(
                "UPDATE companies SET symbol = COALESCE(symbol, ?), "
                "news_source = ?, news_source_params = ?, "
                "news_source_updated_at = ? WHERE id = ?",
                (
                    cfg["symbol"],
                    cfg["source"],
                    json.dumps(cfg["params"]) if cfg["params"] else None,
                    datetime.utcnow().isoformat() + "Z",
                    row["id"],
                ),
            )
            n += 1
        con.commit()
        print(f"  backfilled:    {n:,} rows")

    # ---- 3. the 15 screened additions ------------------------------------
    to_add = [c for c in NEW_COMPANIES if c[0] not in existing]
    skipped = [c[0] for c in NEW_COMPANIES if c[0] in existing]
    print(f"  additions:     {len(to_add)} to insert"
          + (f", {len(skipped)} already present ({', '.join(skipped)})" if skipped else ""))

    if args.apply:
        for ticker, name, exchange, symbol in to_add:
            cfg = tj.get(ticker, {})
            con.execute(
                "INSERT OR IGNORE INTO companies "
                "(ticker, name, exchange, symbol, news_source, "
                " news_source_params, news_source_updated_at, listing_status) "
                "VALUES (?,?,?,?,?,?,?,'active')",
                (
                    ticker, name, exchange, symbol,
                    cfg.get("source"),
                    json.dumps(cfg["params"]) if cfg.get("params") else None,
                    datetime.utcnow().isoformat() + "Z",
                ),
            )
            print(f"    + {symbol:<12} {name}")
        con.commit()

    # ---- verify ----------------------------------------------------------
    total = con.execute(
        "SELECT COUNT(*) FROM companies "
        "WHERE COALESCE(listing_status,'active')='active'"
    ).fetchone()[0]
    print(f"  MinePortal:    {total:,} active companies after")

    if args.apply:
        sourced = con.execute(
            "SELECT COUNT(*) FROM companies WHERE news_source IS NOT NULL"
        ).fetchone()[0]
        nosym = con.execute(
            "SELECT COUNT(*) FROM companies WHERE symbol IS NULL "
            "AND COALESCE(listing_status,'active')='active'"
        ).fetchone()[0]
        print(f"  with source:   {sourced:,}")
        print(f"  no symbol:     {nosym:,}  (these fall back to exchange-derived)")
        print(f"\n  UNDO: systemctl stop mineportal && "
              f"cp {backup_dir}/mining_portal.db {DB} && systemctl start mineportal")

    con.close()
    print("  done.")


if __name__ == "__main__":
    main()
