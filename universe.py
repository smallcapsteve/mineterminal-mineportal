#!/usr/bin/env python3
"""MP_UNIVERSE_V1 — the shared company universe.

One list of who exists, served to all three products. Before this, each site
decided for itself: MTP from a baked array plus a CSE allow-list, MNT from
tickers.json, SediTracker from a symlink to MNT's copy. They disagreed by 106
companies and by 251 names.

This module owns none of that data — it reads the `companies` table MinePortal
already had, and adds the two fields a consumer needs that the table lacked:
the exchange-suffixed market symbol, and where to look for the company's news.

Endpoints (localhost only — MinePortal binds 127.0.0.1:8090 and MTP's proxy
allow-lists /api/portal/{companies,properties} only, so nothing here is
reachable from the internet):

  GET  /api/v1/universe              the list
  GET  /api/v1/universe/healthz      counts, for monitoring
  POST /api/v1/universe/candidates   a scraper proposing a ticker it has seen

The POST is the replacement for a habit, not a feature. MNT's wire scrapers
used to append newly-seen tickers straight into tickers.json, "active
immediately", naming the company from the press-release headline. That is why
Teck Resources was filed as "Friday, September 11, 2026 - ZincX Resources
Corp". Discovery still happens; it now proposes instead of publishing.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from flask import Blueprint, current_app, g, jsonify, request

universe_bp = Blueprint("universe", __name__)

# Exchange -> the suffix the market data and news feeds use. Only consulted when
# a company has no explicit `symbol`; anything irregular (TECK.B.TO, COP.UN.TO,
# capital pools on .P, NEX names on .H) carries its real symbol in the column
# and never comes through here.
_SUFFIX = {
    "TSXV": ".V",
    "TSX-V": ".V",
    "CSE": ".CN",
    "TSX": ".TO",
    "NEO": ".NE",
}


def _db():
    """MinePortal's own connection helper, imported lazily to avoid a cycle."""
    from app import get_db
    return get_db()


def _symbol_for(ticker: str, exchange: str | None, stored: str | None) -> str:
    if stored:
        return stored
    return (ticker or "") + _SUFFIX.get((exchange or "").upper().strip(), "")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------
# schema
# --------------------------------------------------------------------------

def init_universe_schema(con: sqlite3.Connection) -> list[str]:
    """Additive only. Adds nullable columns and one new table; touches no
    existing column and rewrites no existing row. Returns what it did, so the
    migration can report it rather than claiming success blindly."""
    done = []
    cols = {r[1] for r in con.execute("PRAGMA table_info(companies)")}

    for name, decl in (
        ("symbol", "TEXT"),                 # exchange-suffixed market symbol
        ("news_source", "TEXT"),            # which collector handles this company
        ("news_source_params", "TEXT"),     # JSON blob, shape is per-source
        ("news_source_updated_at", "TEXT"),
    ):
        if name not in cols:
            con.execute(f"ALTER TABLE companies ADD COLUMN {name} {decl}")
            done.append(f"companies.{name}")

    con.execute("""
        CREATE TABLE IF NOT EXISTS company_candidates (
            id                INTEGER PRIMARY KEY,
            ticker            TEXT NOT NULL,
            symbol            TEXT,
            name              TEXT,
            exchange          TEXT,
            news_source       TEXT,
            news_source_params TEXT,
            discovered_by     TEXT,
            discovered_at     TEXT DEFAULT CURRENT_TIMESTAMP,
            evidence_url      TEXT,
            status            TEXT NOT NULL DEFAULT 'pending',
            reviewed_at       TEXT,
            note              TEXT,
            UNIQUE(ticker, discovered_by)
        )
    """)
    done.append("company_candidates")

    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_candidates_status "
        "ON company_candidates(status, discovered_at DESC)"
    )
    con.commit()
    return done


# --------------------------------------------------------------------------
# read
# --------------------------------------------------------------------------

_UNIVERSE_SQL = """
    SELECT id, ticker, symbol, name, exchange,
           news_source, news_source_params, listing_status
    FROM companies
    -- MP_LISTING_STATUS_V1: acquired / delisted / cease-traded companies stay
    -- in the table but leave every public list. Same rule /api/companies uses,
    -- deliberately: two endpoints disagreeing about who is listed is how the
    -- three sites drifted apart in the first place.
    WHERE COALESCE(listing_status, 'active') = 'active'
    ORDER BY ticker
"""


def _universe_rows(db) -> list[dict]:
    out = []
    for r in db.execute(_UNIVERSE_SQL):
        params = None
        if r["news_source_params"]:
            try:
                params = json.loads(r["news_source_params"])
            except (ValueError, TypeError):
                params = None   # a malformed blob must not take the list down
        out.append({
            "company_id": r["id"],
            "ticker": r["ticker"],
            "symbol": _symbol_for(r["ticker"], r["exchange"], r["symbol"]),
            "name": r["name"],
            "exchange": r["exchange"],
            "news_source": r["news_source"],
            "news_source_params": params,
        })
    return out


@universe_bp.route("/api/v1/universe")
def api_universe():
    rows = _universe_rows(_db())
    return jsonify({
        "version": 1,
        "generated_at": _now(),
        "count": len(rows),
        "companies": rows,
    })


@universe_bp.route("/api/v1/universe/healthz")
def api_universe_healthz():
    db = _db()
    total = db.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    active = db.execute(
        "SELECT COUNT(*) FROM companies "
        "WHERE COALESCE(listing_status,'active')='active'"
    ).fetchone()[0]
    sourced = db.execute(
        "SELECT COUNT(*) FROM companies WHERE news_source IS NOT NULL "
        "AND COALESCE(listing_status,'active')='active'"
    ).fetchone()[0]
    pending = db.execute(
        "SELECT COUNT(*) FROM company_candidates WHERE status='pending'"
    ).fetchone()[0]
    by_exchange = {
        (r[0] or "?"): r[1] for r in db.execute(
            "SELECT exchange, COUNT(*) FROM companies "
            "WHERE COALESCE(listing_status,'active')='active' GROUP BY 1"
        )
    }
    return jsonify({
        "status": "ok",
        "companies_total": total,
        "companies_active": active,
        "with_news_source": sourced,
        "candidates_pending": pending,
        "by_exchange": by_exchange,
        "generated_at": _now(),
    })


# --------------------------------------------------------------------------
# write — proposals only
# --------------------------------------------------------------------------

def _is_local() -> bool:
    return (request.remote_addr or "") in ("127.0.0.1", "::1", "localhost")


@universe_bp.route("/api/v1/universe/candidates", methods=["POST"])
def api_universe_candidate():
    """A collector reporting a ticker it saw that is not in the universe.

    Never writes `companies`. A person promotes a candidate, or it sits in the
    queue; nothing here can put a headline fragment on the public sites.
    """
    if not _is_local():
        return jsonify({"error": "forbidden"}), 403

    payload = request.get_json(silent=True) or {}
    ticker = (payload.get("ticker") or "").strip().upper()
    if not ticker:
        return jsonify({"error": "ticker required"}), 400
    bare = ticker.split(".")[0]

    db = _db()
    existing = db.execute(
        "SELECT id FROM companies WHERE UPPER(ticker) = ?", (bare,)
    ).fetchone()
    if existing:
        return jsonify({"status": "exists", "company_id": existing["id"]})

    params = payload.get("news_source_params")
    try:
        db.execute(
            "INSERT OR IGNORE INTO company_candidates "
            "(ticker, symbol, name, exchange, news_source, news_source_params, "
            " discovered_by, evidence_url) VALUES (?,?,?,?,?,?,?,?)",
            (
                bare,
                payload.get("symbol") or ticker,
                (payload.get("name") or "").strip()[:300] or None,
                payload.get("exchange"),
                payload.get("news_source"),
                json.dumps(params) if params is not None else None,
                payload.get("discovered_by") or "unknown",
                payload.get("evidence_url"),
            ),
        )
        db.commit()
    except sqlite3.Error as e:
        return jsonify({"error": str(e)[:200]}), 500

    return jsonify({"status": "queued", "ticker": bare})


@universe_bp.route("/api/v1/universe/candidates")
def api_universe_candidates_list():
    status = (request.args.get("status") or "pending").strip()
    rows = _db().execute(
        "SELECT * FROM company_candidates WHERE status = ? "
        "ORDER BY discovered_at DESC LIMIT 500", (status,)
    ).fetchall()
    return jsonify({"count": len(rows), "candidates": [dict(r) for r in rows]})
