#!/usr/bin/env python3
"""MineTerminal - Mining Property Portal"""
from flask import Flask, jsonify, request, g
import sqlite3, os, json

from admin import admin_bp
app = Flask(__name__)
@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


def expand_resource_rows(rows):
    """Transform flat DB rows into category-specific rows for the frontend."""
    CATEGORIES = [
        ('Measured', 'measured_tonnes', 'measured_grade', 'measured_contained'),
        ('Indicated', 'indicated_tonnes', 'indicated_grade', 'indicated_contained'),
        ('Inferred', 'inferred_tonnes', 'inferred_grade', 'inferred_contained'),
        ('Proven', 'proven_tonnes', 'proven_grade', 'proven_contained'),
        ('Probable', 'probable_tonnes', 'probable_grade', 'probable_contained'),
    ]
    # Map commodity+grade_unit to the frontend field keys
    GRADE_FIELD_MAP = {
        ('Gold', 'g/t'): 'grade_au_gpt',
        ('Silver', 'g/t'): 'grade_ag_gpt',
        ('Platinum', 'g/t'): 'grade_pt_gpt',
        ('Copper', '%'): 'grade_cu_pct',
        ('CuEq', '%'): 'grade_cueq_pct',
        ('Zinc', '%'): 'grade_zn_pct',
        ('Nickel', '%'): 'grade_ni_pct',
        ('Cobalt', '%'): 'grade_co_pct',
        ('Lead', '%'): 'grade_pb_pct',
    ('Lithium', 'ppm Li'): 'grade_li_ppm',
    }
    CONTAINED_FIELD_MAP = {
        ('Gold', 'Moz'): 'contained_au_moz',
        ('CuEq', 'Mlbs'): 'contained_cueq_mlbs',
        ('Copper', 'Mlbs'): 'contained_cu_mlbs',
        ('Zinc', 'Mlbs'): 'contained_zn_mlbs',
        ('Silver', 'Moz'): 'contained_ag_moz',
    }
    # Fallback: map by grade_unit alone
    GRADE_UNIT_MAP = {
        'g/t': 'grade_au_gpt',
        '%': 'grade_cu_pct',
        'ppm': 'grade_au_gpt',
    }
    CONTAINED_UNIT_MAP = {
        'Moz': 'contained_au_moz',
        'Mlbs': 'contained_cu_mlbs',
        'tonnes LCE': 'contained_au_moz',
    }
    expanded = []
    for row in rows:
        commodity = (row.get('commodity') or '').strip()
        grade_unit = (row.get('grade_unit') or '').strip()
        contained_unit = (row.get('contained_unit') or '').strip()
        # Determine which frontend field to use
        gf = GRADE_FIELD_MAP.get((commodity, grade_unit)) or GRADE_UNIT_MAP.get(grade_unit)
        cf = CONTAINED_FIELD_MAP.get((commodity, contained_unit)) or CONTAINED_UNIT_MAP.get(contained_unit)
        found_any = False
        for cat_name, t_col, g_col, c_col in CATEGORIES:
            tonnes = row.get(t_col, 0) or 0
            grade = row.get(g_col, 0) or 0
            contained = row.get(c_col, 0) or 0
            if tonnes or grade or contained:
                found_any = True
                new_row = dict(row)
                new_row['category'] = cat_name
                new_row['tonnes_mt'] = tonnes
                new_row['grade'] = grade
                new_row['contained'] = contained
                new_row['estimate_type'] = row.get('compliance_code', '') or 'Resource Estimate'
                # Set metal-specific fields for the frontend
                if gf and grade:
                    new_row[gf] = grade
                if cf and contained:
                    new_row[cf] = contained
                expanded.append(new_row)
        if not found_any:
            new_row = dict(row)
            new_row['category'] = row.get('compliance_code', '') or 'Resource Estimate'
            new_row['tonnes_mt'] = 0
            new_row['grade'] = 0
            new_row['contained'] = 0
            new_row['estimate_type'] = row.get('compliance_code', '') or 'Resource Estimate'
            expanded.append(new_row)
    return expanded

app.register_blueprint(admin_bp)
DB_PATH = os.environ.get("DB_PATH", "/opt/mineportal/mining_portal.db")

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db: db.close()

# ============ API ENDPOINTS ============

@app.route('/api/companies')
def api_companies():
    db = get_db()
    rows = db.execute("""
        SELECT c.*, COUNT(DISTINCT CASE WHEN p.parent_property_id IS NULL THEN p.id END) as property_count,
               COUNT(DISTINCT dp.id) as program_count,
               COUNT(DISTINCT dr.id) as result_count
        FROM companies c
        LEFT JOIN property_companies pc ON pc.company_id = c.id
        LEFT JOIN properties p ON p.id = pc.property_id
        LEFT JOIN drill_programs dp ON dp.property_id = p.id
        LEFT JOIN drill_results dr ON dr.property_id = p.id
        GROUP BY c.id ORDER BY c.ticker
    """).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/companies/<int:cid>')
def api_company(cid):
    db = get_db()
    c = db.execute("SELECT * FROM companies WHERE id=?", (cid,)).fetchone()
    if not c: return jsonify({"error": "not found"}), 404
    props = db.execute("SELECT p.* FROM properties p JOIN property_companies pc ON pc.property_id = p.id WHERE pc.company_id=? ORDER BY p.name", (cid,)).fetchall()
    prop_ids = [p['id'] for p in props]
    resource_estimates = []
    if prop_ids:
        placeholders = ','.join('?' * len(prop_ids))
        resource_estimates = db.execute(f"SELECT re.*, p.name as property_name FROM resource_estimates re JOIN properties p ON re.property_id = p.id WHERE re.property_id IN ({placeholders}) ORDER BY re.estimate_date DESC", prop_ids).fetchall()
    return jsonify({"company": dict(c), "properties": [dict(p) for p in props], "resource_estimates": [dict(r) for r in resource_estimates]})

@app.route('/api/properties')
def api_properties():
    db = get_db()
    rows = db.execute("""
        SELECT p.*, c.ticker, c.name as company_name,
               COUNT(DISTINCT dp.id) as program_count,
               COUNT(DISTINCT dr.id) as result_count
        FROM properties p
        JOIN companies c ON p.company_id = c.id
        LEFT JOIN drill_programs dp ON dp.property_id = p.id
        LEFT JOIN drill_results dr ON dr.property_id = p.id
        GROUP BY p.id ORDER BY c.ticker, p.name
    """).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/properties/map')
def api_properties_map():
    db = get_db()
    rows = db.execute("""
        SELECT p.id, p.name, p.latitude, p.longitude, p.primary_metals, p.status,
               p.mineralization_type, c.ticker, c.name as company_name
        FROM properties p JOIN companies c ON p.company_id = c.id
        WHERE p.latitude IS NOT NULL AND p.longitude IS NOT NULL
    """).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/properties/<int:pid>')
def api_property(pid):
    db = get_db()
    prop = db.execute("""
        SELECT p.*, c.ticker, c.name as company_name
        FROM properties p JOIN companies c ON p.company_id = c.id WHERE p.id=?
    """, (pid,)).fetchone()
    if not prop: return jsonify({"error": "not found"}), 404
    # Check if this property has child properties (sub-zones)
    child_ids = [r[0] for r in db.execute("SELECT id FROM properties WHERE parent_property_id=?", (pid,)).fetchall()]
    all_pids = [pid] + child_ids
    placeholders = ','.join(['?'] * len(all_pids))
    if child_ids:
        programs = db.execute(f"SELECT dp.*, p.name as zone_name FROM drill_programs dp JOIN properties p ON dp.property_id = p.id WHERE dp.property_id IN ({placeholders}) ORDER BY CASE WHEN dp.year GLOB '[0-9]*' THEN CAST(dp.year AS INTEGER) ELSE 0 END DESC", all_pids).fetchall()
        results = db.execute(f"SELECT dr.*, p.name as zone_name FROM drill_results dr JOIN properties p ON dr.property_id = p.id WHERE dr.property_id IN ({placeholders}) ORDER BY dr.year DESC, dr.hole_id", all_pids).fetchall()
        resources = db.execute(f"SELECT re.*, p.name as zone_name FROM resource_estimates re JOIN properties p ON re.property_id = p.id WHERE re.property_id IN ({placeholders}) ORDER BY re.estimate_date DESC", all_pids).fetchall()
    else:
        programs = db.execute("SELECT * FROM drill_programs WHERE property_id=? ORDER BY CASE WHEN year GLOB '[0-9]*' THEN CAST(year AS INTEGER) ELSE 0 END DESC", (pid,)).fetchall()
        results = db.execute("SELECT * FROM drill_results WHERE property_id=? ORDER BY year DESC, hole_id", (pid,)).fetchall()
        resources = db.execute("SELECT * FROM resource_estimates WHERE property_id=? ORDER BY estimate_date DESC", (pid,)).fetchall()
    nearby = db.execute("SELECT * FROM nearby_mines WHERE property_id=?", (pid,)).fetchall()
    ownership = db.execute("SELECT * FROM ownership_history WHERE property_id=? ORDER BY sort_order", (pid,)).fetchall()
    exploration = db.execute("SELECT * FROM exploration_programs WHERE property_id=? ORDER BY year DESC", (pid,)).fetchall()
    linked_companies = db.execute("SELECT c.id, c.ticker, c.name FROM companies c JOIN property_companies pc ON pc.company_id = c.id WHERE pc.property_id=? ORDER BY c.ticker", (pid,)).fetchall()
    return jsonify({
        "property": dict(prop),
        "drill_programs": [dict(r) for r in programs],
        "drill_results": [dict(r) for r in results],
        "resource_estimates": expand_resource_rows([dict(r) for r in resources]),
        "nearby_mines": [dict(r) for r in nearby],
        "ownership_history": [dict(r) for r in ownership],
        "exploration_programs": [dict(r) for r in exploration],
        "linked_companies": [dict(r) for r in linked_companies],
        "economic_studies": [dict(r) for r in db.execute("SELECT * FROM economic_studies WHERE property_id=? ORDER BY study_date DESC", (pid,)).fetchall()],
    })

@app.route('/api/drill_programs/<int:dpid>')
def api_drill_program(dpid):
    db = get_db()
    prog = db.execute("SELECT * FROM drill_programs WHERE id=?", (dpid,)).fetchone()
    if not prog: return jsonify({"error": "not found"}), 404
    results = db.execute("SELECT * FROM drill_results WHERE drill_program_id=? ORDER BY hole_id", (dpid,)).fetchall()
    # Fallback: if no FK-linked results, match by property_id + year(s)
    if len(results) == 0 and prog['year']:
        year_str = str(prog['year'])
        if '-' in year_str:
            parts = year_str.split('-')
            year_start = parts[0].strip()
            year_end = parts[1].strip()
            results = db.execute("SELECT * FROM drill_results WHERE property_id=? AND (CAST(year AS TEXT) BETWEEN ? AND ?) ORDER BY year DESC, hole_id", (prog['property_id'], year_start, year_end)).fetchall()
        else:
            results = db.execute("SELECT * FROM drill_results WHERE property_id=? AND CAST(year AS TEXT)=? ORDER BY hole_id", (prog['property_id'], year_str)).fetchall()
    # If still no results, find sibling programs that DO have results
    siblings_with_data = []
    if len(results) == 0:
        sibs = db.execute("""
            SELECT dp.id, dp.program_name, dp.year, COUNT(dr.id) as result_count
            FROM drill_programs dp
            JOIN drill_results dr ON dr.drill_program_id = dp.id
            WHERE dp.property_id = ? AND dp.id != ?
            GROUP BY dp.id
        """, (prog['property_id'], dpid)).fetchall()
        if len(sibs) == 0:
            sibs = db.execute("""
                SELECT dp.id, dp.program_name, dp.year, COUNT(dr.id) as result_count
                FROM drill_programs dp
                JOIN drill_results dr ON dr.property_id = dp.property_id AND CAST(dr.year AS TEXT) = CAST(dp.year AS TEXT)
                WHERE dp.property_id = ? AND dp.id != ?
                GROUP BY dp.id
            """, (prog['property_id'], dpid)).fetchall()
        siblings_with_data = [dict(s) for s in sibs]
    return jsonify({"program": dict(prog), "results": [dict(r) for r in results], "siblings_with_data": siblings_with_data})

@app.route('/api/search')
def api_search():
    q = request.args.get('q', '').strip()
    if not q: return jsonify([])
    db = get_db()
    like = f"%{q}%"
    props = db.execute("""
        SELECT p.id, p.name, p.primary_metals, p.status, c.ticker, c.name as company_name, 'property' as type
        FROM properties p JOIN companies c ON p.company_id = c.id
        WHERE p.name LIKE ? OR p.primary_metals LIKE ? OR p.jurisdiction LIKE ? OR c.ticker LIKE ? OR c.name LIKE ?
        LIMIT 20
    """, (like, like, like, like, like)).fetchall()
    return jsonify([dict(r) for r in props])


# ============ ECONOMIC STUDIES API ==============
@app.route('/api/economic_studies')
def api_economic_studies():
    db = get_db()
    ticker = request.args.get('ticker')
    if ticker:
        studies = db.execute("SELECT es.*, p.name as property_name, c.ticker FROM economic_studies es JOIN properties p ON es.property_id = p.id LEFT JOIN property_companies pc ON p.id = pc.property_id LEFT JOIN companies c ON pc.company_id = c.id WHERE c.ticker=? ORDER BY es.study_date DESC", (ticker,)).fetchall()
    else:
        studies = db.execute("SELECT es.*, p.name as property_name, c.ticker FROM economic_studies es JOIN properties p ON es.property_id = p.id LEFT JOIN property_companies pc ON p.id = pc.property_id LEFT JOIN companies c ON pc.company_id = c.id ORDER BY es.study_date DESC").fetchall()
    return jsonify([dict(r) for r in studies])

@app.route('/api/economic_studies/<int:sid>')
def api_economic_study(sid):
    db = get_db()
    study = db.execute("SELECT es.*, p.name as property_name, c.ticker, c.name as company_name FROM economic_studies es JOIN properties p ON es.property_id = p.id LEFT JOIN property_companies pc ON p.id = pc.property_id LEFT JOIN companies c ON pc.company_id = c.id WHERE es.id=?", (sid,)).fetchone()
    if not study: return jsonify({"error": "not found"}), 404
    return jsonify(dict(study))

@app.route('/sensitivity/<int:study_id>')
def sensitivity_page(study_id):
    return open('/opt/mineportal/static/sensitivity.html').read()

# ============ FRONTEND ============

@app.route('/')
@app.route('/<path:path>')
def index(path=''):
    return HTML_PAGE

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MineTerminal - Property Portal</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
:root{--bg:#0a0e17;--bg2:#111827;--bg3:#1a2332;--border:#2a3444;--gold:#d4af37;--gold2:#f0d060;
--text:#e0e0e0;--text2:#8899aa;--green:#22c55e;--red:#ef4444;--blue:#3b82f6;--cyan:#06b6d4;}
*{margin:0;padding:0;box-sizing:border-box;}
body{font-family:'Inter','Segoe UI',system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;}
a{color:var(--gold);text-decoration:none;}a:hover{color:var(--gold2);}
.header{background:var(--bg2);border-bottom:1px solid var(--border);padding:12px 24px;display:flex;align-items:center;gap:16px;position:sticky;top:0;z-index:100;}
.logo{font-size:20px;font-weight:700;color:var(--gold);letter-spacing:1px;white-space:nowrap;}
.logo span{color:var(--text2);font-weight:400;font-size:14px;margin-left:8px;}
.search-box{flex:1;max-width:500px;position:relative;}
.search-box input{width:100%;padding:8px 12px 8px 36px;background:var(--bg);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:14px;outline:none;}
.search-box input:focus{border-color:var(--gold);}
.search-box svg{position:absolute;left:10px;top:50%;transform:translateY(-50%);width:16px;height:16px;fill:var(--text2);}
.search-results{position:absolute;top:100%;left:0;right:0;background:var(--bg2);border:1px solid var(--border);border-radius:0 0 6px 6px;max-height:300px;overflow-y:auto;display:none;z-index:200;}
.search-results.active{display:block;}
.sr-item{padding:10px 12px;cursor:pointer;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;}
.sr-item:hover{background:var(--bg3);}
.sr-item .ticker{color:var(--gold);font-weight:600;margin-right:8px;font-size:13px;}
.sr-item .metals{color:var(--text2);font-size:12px;}
.nav-tabs{display:flex;gap:4px;margin-left:auto;}
.nav-tabs button{padding:6px 16px;background:transparent;border:1px solid var(--border);border-radius:6px;color:var(--text2);font-size:13px;cursor:pointer;transition:all 0.2s;}
.nav-tabs button.active,.nav-tabs button:hover{background:var(--gold);color:var(--bg);border-color:var(--gold);}
.main{display:flex;height:calc(100vh - 52px);}
.sidebar{width:280px;min-width:280px;background:var(--bg2);border-right:1px solid var(--border);overflow-y:auto;padding:12px;}
.content{flex:1;overflow-y:auto;padding:20px;}
.company-group{margin-bottom:16px;}
.company-header{padding:8px 10px;font-size:13px;font-weight:600;color:var(--gold);cursor:pointer;display:flex;justify-content:space-between;align-items:center;border-radius:4px;}
.company-header:hover{background:var(--bg3);}
.company-header .count{background:var(--bg);padding:1px 6px;border-radius:10px;font-size:11px;color:var(--text2);font-weight:400;}
.prop-list{margin-left:12px;}
.prop-item.prop-child{padding-left:28px;font-size:0.82em;opacity:0.85;border-left:2px solid var(--gold);margin-left:12px;}.prop-item{padding:6px 10px;font-size:13px;color:var(--text2);cursor:pointer;border-radius:4px;display:flex;align-items:center;gap:6px;}
.prop-item:hover{background:var(--bg3);color:var(--text);}
.prop-item.active{background:var(--bg3);color:var(--gold);border-left:2px solid var(--gold);}
.prop-dot{width:6px;height:6px;border-radius:50%;flex-shrink:0;}
.prop-dot.has-coords{background:var(--green);}
.prop-dot.no-coords{background:var(--red);}
#map{width:100%;height:100%;border-radius:8px;}
.map-view{height:100%;}
.detail-view{max-width:1200px;}
.detail-header{margin-bottom:24px;}
.detail-header h1{font-size:24px;color:var(--gold);margin-bottom:4px;}
.detail-header .meta{color:var(--text2);font-size:14px;}
.detail-header .meta span{margin-right:16px;}
.detail-header .tag{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;margin-right:6px;}
.tag-metals{background:rgba(212,175,55,0.15);color:var(--gold);border:1px solid rgba(212,175,55,0.3);}
.tag-status{background:rgba(34,197,94,0.15);color:var(--green);border:1px solid rgba(34,197,94,0.3);}
.tag-status-optioned{background:rgba(59,130,246,0.15);color:#3b82f6;border:1px solid rgba(59,130,246,0.3);}
.tag-status-terminated{background:rgba(239,68,68,0.15);color:#ef4444;border:1px solid rgba(239,68,68,0.3);}
.tag-status-lapsed{background:rgba(245,158,11,0.15);color:#f59e0b;border:1px solid rgba(245,158,11,0.3);}
.tag-status-writtenoff{background:rgba(107,114,128,0.15);color:#6b7280;border:1px solid rgba(107,114,128,0.3);}
.tag-status-former{background:rgba(107,114,128,0.15);color:#6b7280;border:1px solid rgba(107,114,128,0.3);}
.tag-status-closed{background:rgba(107,114,128,0.15);color:#6b7280;border:1px solid rgba(107,114,128,0.3);}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;margin-bottom:24px;}
.card{background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:16px;}
.card h3{font-size:14px;color:var(--gold);margin-bottom:10px;display:flex;align-items:center;gap:6px;}
.card .stat{font-size:28px;font-weight:700;color:var(--text);}
.card .stat-label{font-size:12px;color:var(--text2);margin-top:2px;}
.section{background:var(--bg2);border:1px solid var(--border);border-radius:8px;margin-bottom:20px;overflow:hidden;}
.section-header{padding:12px 16px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;cursor:pointer;}
.section-header h2{font-size:15px;color:var(--gold);}
.section-header .badge{background:var(--bg);padding:2px 8px;border-radius:10px;font-size:12px;color:var(--text2);}
.section-body{padding:0;}
table{width:100%;border-collapse:collapse;font-size:13px;}
thead th{padding:8px 12px;text-align:left;font-weight:600;color:var(--text2);background:var(--bg3);border-bottom:1px solid var(--border);white-space:nowrap;position:sticky;top:0;}
tbody td{padding:6px 12px;border-bottom:1px solid rgba(42,52,68,0.5);vertical-align:top;}
tbody tr:hover{background:rgba(212,175,55,0.03);}
.num{text-align:right;font-variant-numeric:tabular-nums;}
.highlight-row{background:rgba(212,175,55,0.08)!important;}
.grade-high{color:var(--gold);font-weight:600;}
.empty-state{padding:40px;text-align:center;color:var(--text2);}
.mini-map{height:200px;border-radius:6px;margin-bottom:12px;overflow:hidden;}
.company-view .cards{grid-template-columns:repeat(auto-fit,minmax(180px,1fr));}
.loader{display:flex;justify-content:center;padding:40px;color:var(--text2);}
.home-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin-bottom:32px;}
.home-stat{background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:20px;text-align:center;}
.home-stat .val{font-size:36px;font-weight:700;color:var(--gold);}
.home-stat .label{font-size:13px;color:var(--text2);margin-top:4px;}
.scroll-table{max-height:500px;overflow:auto;}
@media(max-width:768px){.sidebar{display:none;}.main{flex-direction:column;}}

/* Drill Results Modal */
.modal-overlay{position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.92);z-index:1000;display:none;justify-content:center;align-items:center;}
.modal-overlay.active{display:flex;}
.modal-content{background:var(--bg2);border:1px solid var(--border);border-radius:12px;width:90%;max-width:1100px;max-height:85vh;overflow:hidden;display:flex;flex-direction:column;}
.modal-header{display:flex;justify-content:space-between;align-items:center;padding:16px 24px;border-bottom:1px solid var(--border);}
.modal-header h2{margin:0;font-size:18px;color:var(--gold);}
.modal-close{background:none;border:none;color:var(--text2);font-size:24px;cursor:pointer;padding:4px 8px;}
.modal-close:hover{color:var(--text);}
.modal-body{overflow-y:auto;padding:16px 24px;}
.modal-body table{width:100%;}
.modal-body .highlight-row{background:rgba(212,175,55,0.1);}
.modal-loading{text-align:center;padding:40px;color:var(--text2);}
.dp-clickable{cursor:pointer;transition:background 0.2s;}
.dp-clickable:hover{background:rgba(212,175,55,0.08);}

    /* Resource Estimate Modal */
    .re-modal-overlay{position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.92);z-index:1000;display:flex;align-items:center;justify-content:center;opacity:0;pointer-events:none;transition:opacity 0.2s}
    .re-modal-overlay.active{opacity:1;pointer-events:auto}
    .re-modal{background:#1a1f2e;border:1px solid var(--border);border-radius:12px;max-width:1100px;width:90%;max-height:85vh;overflow-y:auto;padding:28px 32px;position:relative;box-shadow:0 20px 60px rgba(0,0,0,0.5)}
    .re-modal h3{margin:0 0 4px 0;color:var(--accent);font-size:18px}
    .re-modal .re-modal-sub{color:var(--text2);font-size:13px;margin-bottom:20px}
    .re-modal .re-modal-close{position:absolute;top:12px;right:16px;background:none;border:none;color:var(--text2);font-size:22px;cursor:pointer;padding:4px 8px;border-radius:4px}
    .re-modal .re-modal-close:hover{background:rgba(255,255,255,0.1);color:var(--text)}
    .re-modal .re-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px 24px;margin-bottom:16px}
    .re-modal .re-grid-item{display:flex;flex-direction:column}
    .re-modal .re-grid-item .re-label{font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:2px}
    .re-modal .re-grid-item .re-value{font-size:15px;color:var(--text);font-weight:500}
    .re-modal .re-grid-item .re-value.accent{color:var(--accent)}
    .re-modal .re-divider{border:none;border-top:1px solid var(--border);margin:16px 0}
    .re-modal .re-notes{font-size:13px;color:var(--text2);line-height:1.5;margin-top:8px}
    .re-modal .re-source{margin-top:12px}
    .re-modal .re-source a{color:#d4a843;font-size:14px;text-decoration:none;font-weight:600}
    .re-modal .re-source a:hover{text-decoration:underline}


    /* Ownership Timeline */
    .ownership-timeline { margin-top: 8px; }
    .ownership-entry {
      display: grid; grid-template-columns: 220px 1fr; gap: 0;
      border-left: 2px solid var(--accent); margin-left: 12px; padding: 0 0 0 16px;
      position: relative; margin-bottom: 0;
    }
    .ownership-entry::before {
      content: ''; position: absolute; left: -5px; top: 8px;
      width: 8px; height: 8px; border-radius: 50%;
      background: var(--accent); border: 2px solid var(--bg);
    }
    .ownership-entry:last-child { border-left-color: transparent; }
    .own-period {
      font-size: 12px; color: var(--accent); font-weight: 600;
      padding: 6px 0;
    }
    .own-details { padding: 6px 0 12px 0; }
    .own-owner { font-size: 13px; font-weight: 600; color: var(--text); }
    .own-nature { font-size: 12px; color: var(--text-secondary); margin-top: 2px; }
    .own-terms { font-size: 11px; color: var(--text-secondary); margin-top: 4px; opacity: 0.8; }
    .own-source { font-size: 10px; color: var(--text-secondary); margin-top: 2px; opacity: 0.6; font-style: italic; }
    .own-current { background: rgba(76,175,80,0.08); border-radius: 6px; padding: 4px 8px; margin: -4px -8px; }
    .own-current .own-owner { color: #81c784; }

    .dr-mo{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.6);z-index:9999;justify-content:center;align-items:center}.dr-mo.active{display:flex}.dr-mb{background:var(--card-bg,#1a1a2e);border:1px solid var(--gold);border-radius:12px;max-width:90vw;max-height:80vh;overflow:auto;padding:24px;min-width:600px;box-shadow:0 20px 60px rgba(0,0,0,.5)}.dr-mb h3{color:var(--gold);margin:0 0 16px;font-size:16px;letter-spacing:.5px}.dr-mb table{width:100%;border-collapse:collapse;font-size:12px}.dr-mb th{padding:4px 8px;text-align:left;border-bottom:1px solid rgba(255,255,255,.15);color:var(--text2);font-size:11px}.dr-mb td{padding:4px 8px;border-bottom:1px solid rgba(255,255,255,.06)}.dr-mb .hl{background:rgba(212,175,55,.08)}
</style>
</head>
<body>
<div class="re-modal-overlay" id="reModalOverlay" onclick="if(event.target===this)closeREModal()">
  <div class="re-modal" id="reModalContent"></div>
</div>

<div class="header">
  <div class="logo">MINE<span style="color:var(--gold)">TERMINAL</span><span>Property Portal</span></div>
  <div class="search-box">
    <svg viewBox="0 0 24 24"><path d="M15.5 14h-.79l-.28-.27A6.47 6.47 0 0016 9.5 6.5 6.5 0 109.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>
    <input type="text" id="searchInput" placeholder="Search companies, properties, metals...">
    <div class="search-results" id="searchResults"></div>
  </div>
  <div class="nav-tabs">
    <button class="active" onclick="showView('home')">Dashboard</button>
    <button onclick="showView('map')">Map</button>
  </div>
</div>
<div class="main">
  <div class="sidebar" id="sidebar"></div>
  <div class="content" id="content"></div>
</div>
<script>
function statusCls(s){if(!s)return '';s=s.toLowerCase();if(s.includes('optioned'))return 'tag-status-optioned';if(s.includes('terminated'))return 'tag-status-terminated';if(s.includes('lapsed'))return 'tag-status-lapsed';if(s.includes('written'))return 'tag-status-writtenoff';if(s==='former')return 'tag-status-former';if(s==='closed')return 'tag-status-closed';return '';}
const state = {view:'home', companies:[], properties:[], currentProp:null};

async function fetchJSON(url){const r=await fetch(url);return r.json();}

async function init(){
  state.companies = await fetchJSON('/api/companies');
  state.properties = await fetchJSON('/api/properties');
  renderSidebar();
  showView('home');
}

function renderSidebar(){
  const sb=document.getElementById('sidebar');
  let html='';
  for(const c of state.companies){
    const props=state.properties.filter(p=>p.ticker===c.ticker);
    const topLevel=props.filter(p=>!p.parent_property_id);
    const children=props.filter(p=>p.parent_property_id);
    html+=`<div class="company-group">
      <div class="company-header" onclick="showCompany(${c.id})">
        <span>${c.ticker} - ${c.name}</span>
        <span class="count">${topLevel.length}</span>
      </div>
      <div class="prop-list">`;
    for(const p of topLevel){
      const hasCo=p.latitude?'has-coords':'no-coords';
      html+=`<div class="prop-item" data-pid="${p.id}" onclick="showProperty(${p.id})">
        <span class="prop-dot ${hasCo}"></span>${p.name}</div>`;
      const subs=children.filter(ch=>ch.parent_property_id===p.id);
      for(const s of subs){
        const subCo=s.latitude?'has-coords':'no-coords';
        html+=`<div class="prop-item prop-child" data-pid="${s.id}" onclick="showProperty(${s.id})">
        <span class="prop-dot ${subCo}"></span>${s.name}</div>`;
      }
    }
    html+=`</div></div>`;
  }
  sb.innerHTML=html;
}

function showView(view){
  state.view=view;
  document.querySelectorAll('.nav-tabs button').forEach(b=>b.classList.remove('active'));
  document.querySelectorAll('.nav-tabs button').forEach(b=>{if(b.textContent.toLowerCase().includes(view)||
    (view==='home'&&b.textContent==='Dashboard'))b.classList.add('active');});
  if(view==='home')renderHome();
  else if(view==='map')renderMap();
}

function renderHome(){
  const co=document.getElementById('content');
  const totalProps=state.properties.length;
  const totalProgs=state.properties.reduce((s,p)=>s+p.program_count,0);
  const totalResults=state.properties.reduce((s,p)=>s+p.result_count,0);
  const withCoords=state.properties.filter(p=>p.latitude).length;
  co.innerHTML=`<div class="detail-view">
    <h1 style="color:var(--gold);font-size:28px;margin-bottom:24px;">Mining Property Database</h1>
    <div class="home-stats">
      <div class="home-stat"><div class="val">${state.companies.length}</div><div class="label">Companies</div></div>
      <div class="home-stat"><div class="val">${totalProps}</div><div class="label">Properties</div></div>
      <div class="home-stat"><div class="val">${totalProgs}</div><div class="label">Exploration Programs</div></div>
      <div class="home-stat"><div class="val">${totalResults}</div><div class="label">Drill Results</div></div>
      <div class="home-stat"><div class="val">${withCoords}</div><div class="label">Mapped Locations</div></div>
    </div>
    <div class="section"><div class="section-header"><h2>All Companies</h2></div>
    <div class="section-body"><div class="scroll-table"><table>
    <thead><tr><th>Ticker</th><th>Company</th><th>Properties</th><th>Exploration Programs</th><th>Results</th></tr></thead>
    <tbody>${state.companies.map(c=>`<tr style="cursor:pointer" onclick="showCompany(${c.id})">
      <td style="color:var(--gold);font-weight:600">${c.ticker}</td><td>${c.name}</td>
      <td class="num">${c.property_count}</td><td class="num">${c.program_count}</td><td class="num">${c.result_count}</td>
    </tr>`).join('')}</tbody></table></div></div></div>
    <div class="section"><div class="section-header"><h2>All Properties</h2><span class="badge">${totalProps}</span></div>
    <div class="section-body"><div class="scroll-table"><table>
    <thead><tr><th>Ticker</th><th>Property</th><th>Jurisdiction</th><th>Metals</th><th>Status</th><th>Programs</th><th>Results</th></tr></thead>
    <tbody>${state.properties.map(p=>`<tr style="cursor:pointer" onclick="showProperty(${p.id})">
      <td style="color:var(--gold)">${p.ticker}</td><td>${p.name}</td>
      <td>${p.jurisdiction||p.country||'-'}</td><td>${p.primary_metals||p.mineralization_type||'-'}</td>
      <td>${p.status?'<span class="tag tag-status '+statusCls(p.status)+'">'+ p.status+'</span>':'-'}</td><td class="num">${p.program_count}</td><td class="num">${p.result_count}</td>
    </tr>`).join('')}</tbody></table></div></div></div>
  </div>`;
}

let map=null;
async function renderMap(){
  const co=document.getElementById('content');
  co.innerHTML='<div class="map-view"><div id="map"></div></div>';
  if(map){map.remove();map=null;}
  map=L.map('map',{zoomControl:true}).setView([50,-75],5);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',{
    attribution:'&copy; CartoDB',maxZoom:19
  }).addTo(map);
  const data=await fetchJSON('/api/properties/map');
  const bounds=[];
  for(const p of data){
    if(!p.latitude||!p.longitude)continue;
    const color=getMetalColor(p.primary_metals||p.mineralization_type||'');
    const marker=L.circleMarker([p.latitude,p.longitude],{
      radius:8,fillColor:color,color:'#fff',weight:1,opacity:0.8,fillOpacity:0.7
    }).addTo(map);
    marker.bindPopup(`<div style="font-family:sans-serif;min-width:200px">
      <div style="font-weight:700;color:#d4af37;font-size:14px;margin-bottom:4px">${p.name}</div>
      <div style="color:#666;font-size:12px;margin-bottom:8px">${p.ticker} - ${p.company_name}</div>
      <div style="font-size:12px">${p.primary_metals||p.mineralization_type||'N/A'}</div>
      <div style="margin-top:8px"><a href="#" onclick="event.preventDefault();showProperty(${p.id})" style="color:#d4af37;font-size:12px">View Details &rarr;</a></div>
    </div>`);
    bounds.push([p.latitude,p.longitude]);
  }
  if(bounds.length)map.fitBounds(bounds,{padding:[30,30]});
  setTimeout(()=>map.invalidateSize(),100);
}

function getMetalColor(metals){
  const m=metals.toLowerCase();
  if(m.includes('gold')||m.includes('au'))return '#d4af37';
  if(m.includes('copper')||m.includes('cu'))return '#b87333';
  if(m.includes('nickel')||m.includes('ni'))return '#8fce00';
  if(m.includes('zinc')||m.includes('zn'))return '#90caf9';
  if(m.includes('titanium')||m.includes('ti'))return '#e0e0e0';
  if(m.includes('lithium'))return '#ff6090';
  return '#06b6d4';
}

async function showCompany(cid){
  const co=document.getElementById('content');
  co.innerHTML='<div class="loader">Loading...</div>';
  const data=await fetchJSON(`/api/companies/${cid}`);
  const c=data.company, props=data.properties, allRE=data.resource_estimates||[];
  const propsWithData=state.properties.filter(p=>state.companies.find(cc=>cc.id===cid)?.ticker===p.ticker);
  co.innerHTML=`<div class="detail-view company-view">
    <div class="detail-header">
      <h1>${c.ticker} - ${c.name}</h1>
      <div class="meta"><span>${c.exchange}</span></div>
    </div>
    <div class="cards">
      <div class="card"><h3>Properties</h3><div class="stat">${props.length}</div></div>
      <div class="card"><h3>Exploration Programs</h3><div class="stat">${propsWithData.reduce((s,p)=>s+p.program_count,0)}</div></div>
      <div class="card"><h3>Drill Results</h3><div class="stat">${propsWithData.reduce((s,p)=>s+p.result_count,0)}</div></div>
    </div>
    ${(function(){
      if(!allRE||!allRE.length) return '';
      // Find headline commodity: prefer equivalents (CuEq, AuEq, AgEq, ZnEq), then most common
      var equivs=allRE.filter(function(r){return r.commodity&&(r.commodity.indexOf('Equivalent')>=0||r.commodity.indexOf('Eq')>=0);});
      var headline=null;
      if(equivs.length>0){headline=equivs[0];}
      if(!headline){
        // Count occurrences of each commodity
        var counts={};
        allRE.forEach(function(r){if(r.commodity){counts[r.commodity]=(counts[r.commodity]||0)+1;}});
        var maxC='',maxN=0;
        for(var k in counts){if(counts[k]>maxN){maxN=counts[k];maxC=k;}}
        headline={commodity:maxC};
      }
      var hCom=headline.commodity||'';
      // Filter RE to headline commodity only
      var hRE=allRE.filter(function(r){return r.commodity===hCom;});
      // Sum tonnages across all categories (measured, indicated, inferred)
      var totalT=0, totalContained=0, weightedGradeSum=0;
      hRE.forEach(function(r){
        var mt=(r.measured_tonnes||0), it=(r.indicated_tonnes||0), inf=(r.inferred_tonnes||0);
        var mg=(r.measured_grade||0), ig=(r.indicated_grade||0), infg=(r.inferred_grade||0);
        var mc=(r.measured_contained||0), ic=(r.indicated_contained||0), infc=(r.inferred_contained||0);
        totalT+=mt+it+inf;
        totalContained+=mc+ic+infc;
        weightedGradeSum+=(mt*mg)+(it*ig)+(inf*infg);
      });
      if(totalT===0) return '';
      var avgGrade=(weightedGradeSum/totalT);
      var gu=hRE[0]&&hRE[0].grade_unit?hRE[0].grade_unit:'';
      var cu=hRE[0]&&hRE[0].contained_unit?hRE[0].contained_unit:'';
      // Format numbers
      var fmtT=totalT.toFixed(2);
      var fmtG=avgGrade.toFixed(2);
      var fmtC=totalContained.toFixed(2);
    var optOutIds={};props.forEach(function(p){if(p.status==='Optioned Out')optOutIds[p.id]=true;});
    var hasOptOut=hRE.some(function(r){return optOutIds[r.property_id];});
    var footnote=hasOptOut?'<div style="color:#aaa;font-size:0.75rem;margin-top:0.5rem;font-style:italic;">* Includes resources from optioned-out properties</div>':'';
      return '<div class="section" style="margin-bottom:1.5rem;"><div style="background:linear-gradient(135deg,#1a1a2e,#16213e);border:1px solid var(--gold);border-radius:12px;padding:1.5rem;display:flex;align-items:center;gap:2rem;flex-wrap:wrap;"><div style="flex:1;min-width:200px;"><div style="color:var(--gold);font-size:0.85rem;text-transform:uppercase;letter-spacing:1px;margin-bottom:0.3rem;">Total Resource (M+I+Inf)</div><div style="font-size:2rem;font-weight:700;color:#fff;">'+fmtT+' Mt</div></div><div style="flex:1;min-width:200px;"><div style="color:var(--gold);font-size:0.85rem;text-transform:uppercase;letter-spacing:1px;margin-bottom:0.3rem;">Wtd. Avg Grade ('+hCom+')</div><div style="font-size:2rem;font-weight:700;color:#fff;">'+fmtG+' '+gu+'</div></div><div style="flex:1;min-width:200px;"><div style="color:var(--gold);font-size:0.85rem;text-transform:uppercase;letter-spacing:1px;margin-bottom:0.3rem;">Contained '+hCom+'</div><div style="font-size:2rem;font-weight:700;color:#fff;">'+fmtC+' '+cu+'</div></div></div>'+footnote+'</div>';
    })()}
    <div class="section"><div class="section-header"><h2>Properties</h2></div>
    <div class="section-body"><table>
    <thead><tr><th>Property</th><th>Jurisdiction</th><th>Metals</th><th>Status</th><th>Interest</th></tr></thead>
    <tbody>${props.map(p=>`<tr style="cursor:pointer" onclick="showProperty(${p.id})">
      <td style="color:var(--gold)">${p.name}</td><td>${p.jurisdiction||p.country||'-'}</td>
      <td>${p.primary_metals||p.mineralization_type||'-'}</td><td>${p.status?'<span class="tag tag-status '+statusCls(p.status)+'">'+ p.status+'</span>':'-'}</td>
      <td>${p.current_interest||'-'}</td>
    </tr>`).join('')}</tbody></table></div></div>
  </div>`;
}



function clearDT(){}
function hideDM(){document.getElementById('drM').classList.remove('active')}
function showDM(pid){
  clearDT();
  var rs=window._dr?window._dr.filter(function(r){return r.drill_program_id===pid}):[];
  if(!rs.length)return;
  var pname='Program';
  if(window._dp){for(var i=0;i<window._dp.length;i++){if(window._dp[i].id===pid){pname=window._dp[i].program_name||'Program';break}}}
  document.getElementById('drMT').textContent='DRILL RESULTS ('+rs.length+') \u2014 '+pname;
  var hA=rs.some(function(r){return r.au_gpt}),hG=rs.some(function(r){return r.ag_gpt}),hC=rs.some(function(r){return r.cu_pct}),hZ=rs.some(function(r){return r.zn_pct}),hN=rs.some(function(r){return r.ni_pct}),hO=rs.some(function(r){return r.co_pct}),hP=rs.some(function(r){return r.pb_pct}),hT=rs.some(function(r){return r.pt_gpt}),hE=rs.some(function(r){return r.cueq_pct});var hI=rs.some(function(r){return r.from_m!=null||r.to_m!=null||r.interval_m!=null});
  var th='<tr><th>Hole ID</th><th>Zone</th>';if(hI)th+='<th style="text-align:right">From</th><th style="text-align:right">To</th><th style="text-align:right">Int (m)</th>';th+='';
  if(hA)th+='<th style="text-align:right;color:var(--gold)">Au g/t</th>';
  if(hG)th+='<th style="text-align:right">Ag g/t</th>';
  if(hC)th+='<th style="text-align:right">Cu %</th>';
  if(hE)th+='<th style="text-align:right">CuEq %</th>';
  if(hZ)th+='<th style="text-align:right">Zn %</th>';
  if(hN)th+='<th style="text-align:right">Ni %</th>';
  if(hO)th+='<th style="text-align:right">Co %</th>';
  if(hP)th+='<th style="text-align:right">Pb %</th>';
  if(hT)th+='<th style="text-align:right">Pt g/t</th>';
  th+='<th>Notes</th></tr>';
  var rw=rs.map(function(r){var g='';
    if(hA)g+='<td style="text-align:right;'+(r.au_gpt&&r.highlight?'font-weight:700;color:var(--gold)':r.au_gpt?'color:var(--accent)':'')+'">'+(r.au_gpt?r.au_gpt.toFixed(2):'-')+'</td>';
    if(hG)g+='<td style="text-align:right">'+(r.ag_gpt?r.ag_gpt.toFixed(1):'-')+'</td>';
    if(hC)g+='<td style="text-align:right">'+(r.cu_pct?r.cu_pct.toFixed(2):'-')+'</td>';
    if(hE)g+='<td style="text-align:right">'+(r.cueq_pct?r.cueq_pct.toFixed(2):'-')+'</td>';
    if(hZ)g+='<td style="text-align:right">'+(r.zn_pct?r.zn_pct.toFixed(2):'-')+'</td>';
    if(hN)g+='<td style="text-align:right">'+(r.ni_pct?r.ni_pct.toFixed(3):'-')+'</td>';
    if(hO)g+='<td style="text-align:right">'+(r.co_pct?r.co_pct.toFixed(3):'-')+'</td>';
    if(hP)g+='<td style="text-align:right">'+(r.pb_pct?r.pb_pct.toFixed(2):'-')+'</td>';
    if(hT)g+='<td style="text-align:right">'+(r.pt_gpt?r.pt_gpt.toFixed(3):'-')+'</td>';
    return '<tr '+(r.highlight?'class="hl"':'')+'><td style="color:var(--gold);font-weight:600">'+(r.hole_id||'-')+'</td><td>'+(r.zone_target||'-')+'</td>'+(hI?'<td style="text-align:right">'+(r.from_m!=null?r.from_m.toFixed(1):'-')+'</td><td style="text-align:right">'+(r.to_m!=null?r.to_m.toFixed(1):'-')+'</td><td style="text-align:right;font-weight:600">'+(r.interval_m!=null?r.interval_m.toFixed(1):'-')+'</td>':'')+g+'<td style="font-size:11px;max-width:200px">'+(r.notes||'-')+'</td></tr>'}).join('');
  document.getElementById('drMB').innerHTML='<table><thead>'+th+'</thead><tbody>'+rw+'</tbody></table>';
  document.getElementById('drM').classList.add('active');
}
function showEP(pid){
  clearDT();
  var ep=(window._ep||[]).filter(function(e){return e.id===pid;});
  if(!ep.length) return;
  var e=ep[0];
  document.getElementById('drMT').textContent='EXPLORATION PROGRAM '+(e.year?('('+e.year+')'):'')+' — '+(e.program_name||'Program');
  var rows='';
  if(e.program_type) rows+='<tr><th style="text-align:left;color:var(--gold);width:140px">Type</th><td>'+e.program_type+'</td></tr>';
  if(e.operator) rows+='<tr><th style="text-align:left;color:var(--gold)">Operator</th><td>'+e.operator+'</td></tr>';
  if(e.description) rows+='<tr><th style="text-align:left;color:var(--gold);vertical-align:top">Description</th><td style="white-space:pre-wrap">'+e.description+'</td></tr>';
  if(e.results_summary) rows+='<tr><th style="text-align:left;color:var(--gold);vertical-align:top">Results</th><td style="white-space:pre-wrap">'+e.results_summary+'</td></tr>';
  if(e.expenditure) rows+='<tr><th style="text-align:left;color:var(--gold)">Expenditure</th><td>'+e.expenditure+'</td></tr>';
  if(e.source) rows+='<tr><th style="text-align:left;color:var(--gold)">Source</th><td>'+e.source+'</td></tr>';
  if(!rows) rows='<tr><td style="color:var(--text2)">No additional details recorded.</td></tr>';
  document.getElementById('drMB').innerHTML='<table style="width:100%">'+rows+'</table>';
  document.getElementById('drM').classList.add('active');
}


async function showProperty(pid){
  const co=document.getElementById('content');
  co.innerHTML='<div class="loader">Loading...</div>';
  document.querySelectorAll('.prop-item').forEach(el=>el.classList.remove('active'));
  document.querySelector(`.prop-item[data-pid="${pid}"]`)?.classList.add('active');

  const data=await fetchJSON(`/api/properties/${pid}`);
  const p=data.property;
  const dp=data.drill_programs;
window._dp=dp;
  const ep=data.exploration_programs;
  window._ep=ep;
  const dr=data.drill_results;
window._dr=dr;
          window._allDrillResults=dr;
    const _rc={};dr.forEach(r=>_rc[r.drill_program_id]=(_rc[r.drill_program_id]||0)+1);dp.forEach(d=>d.result_count=_rc[d.id]||0);
  const re=data.resource_estimates;
      cacheREData(data);
    const reCount=new Set(re.map(r=>r.estimate_date+r.estimate_type)).size;
  const nm=data.nearby_mines;

  let miniMap='';
  if(p.latitude&&p.longitude){
    miniMap=`<div class="mini-map" id="propMap"></div>`;
  }

  // Detect which metals to show as columns
  const metalCols=detectMetalColumns(dr);

  let html=`<div class="detail-view">
    <div class="detail-header">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
        ${(data.linked_companies||[{id:p.company_id,ticker:p.ticker}]).map(lc=>'<a href="#" onclick="event.preventDefault();showCompany('+lc.id+')" style="color:var(--text2);font-size:13px">'+lc.ticker+'</a>').join(' <span style="color:var(--text2)">/</span> ')}
        <span style="color:var(--text2)">/</span>
      </div>
      <h1>${p.name}</h1>
      <div class="meta">
        <span>${p.jurisdiction||p.country||''}</span>
        ${p.primary_metals?`<span class="tag tag-metals">${p.primary_metals}</span>`:''}
        ${p.status?`<span class="tag tag-status '+statusCls(p.status)+'">${p.status}</span>`:''}
      </div>
    </div>
    ${miniMap}
    <div class="cards">
      <div class="card"><h3>Exploration Programs</h3><div class="stat">${dp.length}</div></div>
      <div class="card"><h3>Total Drill Metres</h3><div class="stat">${fmtNum(dp.reduce((s,d)=>s+(d.actual_meters||0),0))}</div></div>
      ${ep.length?'<div class="card"><h3>Exploration Programs</h3><div class="stat">'+ep.length+'</div></div>':''}
      <div class="card" onclick="showAllDrillResults()" style="cursor:pointer"><h3>Drill Results</h3><div class="stat">${dr.length}</div></div>
      <div class="card"><h3>Resource Estimates</h3><div class="stat">${reCount}</div></div>
      ${p.current_interest?'<div class="card"><h3>Interest</h3><div class="stat" style="font-size:16px">'+p.current_interest+'</div></div>':''}
      ${p.size_ha?'<div class="card"><h3>Size</h3><div class="stat">'+p.size_ha+' Ha</div></div>':''}
    </div>`;

    // Property Notes
    if(p.resource_notes){
      html+='<div class="section"><div class="section-header"><h2>Property Notes</h2></div>';
      html+='<div class="section-body" style="padding:16px;color:#ccc;line-height:1.6;font-size:14px;background:rgba(255,255,255,0.03);border-radius:8px;border:1px solid rgba(255,255,255,0.08)">';
      html+=p.resource_notes.replace(/\\n/g,'<br>');
      html+='</div></div>';
    }
  // Exploration Programs (unified: drill_programs + exploration_programs)
  const allProgs = [
    ...dp.map(d=>({src:'dp', id:d.id, year:d.year, program_name:d.program_name, zone_name:d.zone_name,
                   operator:d.operator, type:d.drill_type||'Drilling',
                   planned_m:d.planned_meters, planned_h:d.planned_holes,
                   actual_m:d.actual_meters, actual_h:d.actual_holes,
                   objectives:d.objectives, result_count:d.result_count||0})),
    ...ep.map(e=>({src:'ep', id:e.id, year:e.year, program_name:e.program_name,
                   operator:e.operator, type:e.program_type||'Exploration',
                   description:e.description, results_summary:e.results_summary}))
  ].sort((a,b)=>(Number(b.year)||0)-(Number(a.year)||0));
  if(allProgs.length){
    html+=`<div class="section"><div class="section-header" onclick="toggleSection(this)">
      <h2>Exploration Programs</h2><span class="badge">${allProgs.length}</span></div>
      <div class="section-body"><div class="scroll-table"><table>
      <thead><tr><th>Year</th><th>Program</th><th>Operator</th><th>Type</th><th>Details</th></tr></thead>
      <tbody>${allProgs.map(p=>{
        const hasDrillResults = p.src==='dp' && p.result_count>0;
        const hasExpDetail = p.src==='ep' && (p.description||p.results_summary);
        const clickable = hasDrillResults || hasExpDetail;
        const onclickAttr = hasDrillResults ? `onclick="showDM(${p.id})"` :
                            hasExpDetail ? `onclick="showEP(${p.id})"` : '';
        const details = p.src==='dp'
          ? (`${fmtNum(p.actual_m)||fmtNum(p.planned_m)||'-'} m / ${fmtNum(p.actual_h)||fmtNum(p.planned_h)||'-'} holes`
             + (hasDrillResults?` <span class="badge" style="background:var(--gold);color:#000">${p.result_count} results</span>`:''))
          : ((p.description||'').substring(0,140) + ((p.description||'').length>140?'…':''));
        return `<tr style="${clickable?'cursor:pointer':'opacity:0.6'}" ${onclickAttr}>
          <td style="color:var(--gold)">${p.year||'-'}</td>
          <td>${p.zone_name?'<span style="color:var(--gold);font-size:11px">['+p.zone_name+']</span> ':''}${p.program_name||'-'}</td>
          <td>${p.operator||'-'}</td>
          <td><span class="badge" style="font-size:10px">${p.type}</span></td>
          <td style="font-size:12px;color:var(--text2);max-width:360px">${details}</td>
        </tr>`;
      }).join('')}</tbody></table></div></div></div>`;
  }

      // Economic Studies
    const econStudies = data.economic_studies||[];
    if(econStudies.length){
        html+='<div class="card"><div class="section-header"><h2>Economic Studies</h2><span class="badge">'+econStudies.length+'</span></div>';
        html+='<table class="data-table"><thead><tr><th>Study Type</th><th>Date</th><th>NPV (Base)</th><th>IRR</th><th>Payback</th><th>Commodity Price</th><th></th></tr></thead><tbody>';
        econStudies.forEach(s=>{
            const npvM = s.base_case_npv ? '$'+(s.base_case_npv/1e6).toFixed(0)+'M' : '-';
            const irr = s.base_case_irr ? s.base_case_irr+'%' : '-';
            const pb = s.base_case_payback ? s.base_case_payback+' yrs' : '-';
            const price = s.commodity_price ? '$'+s.commodity_price+' '+s.commodity_price_unit : '-';
            html+='<tr>';
            html+='<td><span class="badge">'+s.study_type+'</span></td>';
            html+='<td>'+s.study_date+'</td>';
            html+='<td style="color:#4ecdc4;font-weight:bold">'+npvM+'</td>';
            html+='<td style="color:#4ecdc4">'+irr+'</td>';
            html+='<td>'+pb+'</td>';
            html+='<td>'+price+'</td>';
            html+='<td><a href="/sensitivity/'+s.id+'" style="color:#d4a017;font-weight:bold;text-decoration:none">Sensitivity Tool \u2192</a></td>';
            html+='</tr>';
        });
        html+='</tbody></table></div>';
    }

    // Ownership History
      const own=data.ownership_history||[];
      if(own.length){
          html+='<div class="card"><div class="section-header"><h2>Ownership History</h2></div>';
          html+='<div class="ownership-timeline">';
          own.forEach((o,i)=>{
            
            html+=`<div class="ownership-entry">`;
            html+=`<div class="own-period">${o.date_or_period}</div>`;
            html+=`<div class="own-details">`;
            html+=`<div class="own-owner">${o.counterparties}</div>`;
            if(o.interest_details) html+=`<div class="own-nature">${o.interest_details}</div>`;
            if(o.terms) html+=`<div class="own-terms">${o.terms}</div>`;
            if(o.source_url) html+=`<div class="own-source">Source: ${o.source_url}</div>`;
            html+=`</div></div>`;
          });
          html+='</div></div>';
      }

      // Resource Estimates
    if(re.length){
      // Group RE rows by estimate (same date+type = one estimate)
      const reEsts=[];let _lk=null;
      re.forEach((r,_ri)=>{
        const k=r.estimate_date+(r.estimate_type||"");
        if(k!==_lk){reEsts.push({key:k,type:r.estimate_type||'-',date:r.estimate_date||'-',compliance:r.compliance_code||'',cats:[],ids:[]});_lk=k;}
        const est=reEsts[reEsts.length-1];
        est.cats.push(r.category||'Unknown');
        est.ids.push(_ri);
      });
      // Compute summary per estimate: detect metals and compute totals
      let hasAu=false,hasCu=false,hasZn=false,hasAg=false;
      re.forEach((r,_ri)=>{if(r.grade_au_gpt||r.contained_au_moz)hasAu=true;if(r.grade_cueq_pct||r.grade_cu_pct||r.contained_cu_mlbs||r.contained_cueq_mlbs)hasCu=true;if(r.grade_zn_pct||r.contained_zn_mlbs)hasZn=true;if(r.grade_ag_gpt||r.contained_ag_moz)hasAg=true;});
      reEsts.forEach(est=>{
        let tT=0,tCu=0,tCuEq=0,wCuEq=0,tAuMoz=0,wAu=0,tZnMlbs=0,tAgMoz=0,wCu=0,wZn=0,wAg=0;
        est.ids.forEach(id=>{
          const r=re[id];
          if(r){
            if(r.tonnes_mt) tT+=r.tonnes_mt;
            if(r.contained_au_moz) tAuMoz+=r.contained_au_moz;
            if(r.tonnes_mt&&r.grade_au_gpt) wAu+=r.tonnes_mt*r.grade_au_gpt;
            if(r.contained_cueq_mlbs) tCuEq+=r.contained_cueq_mlbs;if(r.contained_cu_mlbs) tCu+=r.contained_cu_mlbs;
            if(r.contained_zn_mlbs) tZnMlbs+=r.contained_zn_mlbs;
            if(r.contained_ag_moz) tAgMoz+=r.contained_ag_moz;
            if(r.tonnes_mt&&r.grade_cu_pct) wCu+=r.tonnes_mt*r.grade_cu_pct;
            if(r.tonnes_mt&&r.grade_zn_pct) wZn+=r.tonnes_mt*r.grade_zn_pct;
            if(r.tonnes_mt&&r.grade_ag_gpt) wAg+=r.tonnes_mt*r.grade_ag_gpt;
            if(r.tonnes_mt&&r.grade_cueq_pct) wCuEq+=r.tonnes_mt*r.grade_cueq_pct;
          }
        });
        est.totalTonnes=tT;est.totalAuMoz=tAuMoz;est.avgAu=tT>0?(wAu/tT):0;est.avgCuEq=tT>0?(wCuEq/tT):0;est.totalCuEqMlbs=tCuEq;est.totalCuMlbs=tCu;est.totalZnMlbs=tZnMlbs;est.totalAgMoz=tAgMoz;est.avgCu=tT>0?(wCu/tT):0;est.avgZn=tT>0?(wZn/tT):0;est.avgAg=tT>0?(wAg/tT):0;
      });
      const gradeHead='Grade';
      const containedHead='Contained';
        function fmtCont(o,isE){let p=[];if(isE){if(o.totalAuMoz)p.push(o.totalAuMoz.toFixed(2)+' Moz Au');if(o.totalCuEqMlbs)p.push(Math.round(o.totalCuEqMlbs)+' Mlbs CuEq');else if(o.totalCuMlbs)p.push(Math.round(o.totalCuMlbs)+' Mlbs Cu');if(o.totalZnMlbs)p.push(Math.round(o.totalZnMlbs)+' Mlbs Zn');if(o.totalAgMoz)p.push(o.totalAgMoz.toFixed(1)+' Moz Ag');}else{if(o.contained_au_moz)p.push(o.contained_au_moz.toFixed(2)+' Moz Au');if(o.contained_cueq_mlbs)p.push(Math.round(o.contained_cueq_mlbs)+' Mlbs CuEq');else if(o.contained_cu_mlbs)p.push(Math.round(o.contained_cu_mlbs)+' Mlbs Cu');if(o.contained_zn_mlbs)p.push(Math.round(o.contained_zn_mlbs)+' Mlbs Zn');if(o.contained_ag_moz)p.push(o.contained_ag_moz.toFixed(1)+' Moz Ag');}if(!p.length&&o.contained&&o.contained_unit){p.push(parseFloat(o.contained).toFixed(2)+' '+o.contained_unit)}return p.length?p.join(', '):'-';}
    function fmtGrd(o,isE){let p=[];if(isE){if(o.avgCuEq)p.push(o.avgCuEq.toFixed(2)+'% CuEq');else if(o.avgAu)p.push(o.avgAu.toFixed(2)+' g/t Au');if(o.avgCu)p.push(o.avgCu.toFixed(2)+'% Cu');if(o.avgZn)p.push(o.avgZn.toFixed(2)+'% Zn');if(o.avgAg)p.push(o.avgAg.toFixed(1)+' g/t Ag');}else{if(o.grade_cueq_pct)p.push(o.grade_cueq_pct.toFixed(2)+'% CuEq');else if(o.grade_au_gpt)p.push(o.grade_au_gpt.toFixed(2)+' g/t Au');if(o.grade_cu_pct)p.push(o.grade_cu_pct.toFixed(2)+'% Cu');if(o.grade_zn_pct)p.push(o.grade_zn_pct.toFixed(2)+'% Zn');if(o.grade_ag_gpt)p.push(o.grade_ag_gpt.toFixed(1)+' g/t Ag');}if(!p.length&&o.grade&&o.grade_unit){p.push(parseFloat(o.grade).toFixed(2)+' '+o.grade_unit)}return p.length?p.join(', '):'-';}
    const reCount=reEsts.length;
      html+=`<div class="section"><div class="section-header" onclick="toggleSection(this)">
        <h2>Resource Estimates</h2><span class="badge">${reCount}</span></div>
        <div class="section-body"><div class="scroll-table"><table>
    <thead><tr><th>Estimate</th><th>Date</th><th>Category</th><th class="num">Total Tonnes</th><th class="num">${gradeHead}</th><th class="num">${containedHead}</th></tr></thead>
    <tbody>${(()=>{let html='';reEsts.forEach((est,gIdx)=>{const rows=est.ids.map(id=>re[id]).filter(Boolean);if(rows.length===1){const r=rows[0];const c=r.category||'Unknown';const bg=c.includes('Indicated')?'rgba(76,175,80,0.2);color:#81c784':c.includes('Measured')?'rgba(33,150,243,0.2);color:#64b5f6':c==='Proven'||c==='Probable'?'rgba(171,71,188,0.2);color:#ce93d8':'rgba(255,183,77,0.2);color:#ffb74d';html+=`<tr style="background:${gIdx%2===0?'rgba(255,255,255,0.03)':'rgba(100,140,180,0.08)'};cursor:pointer" onclick="showREModal('${est.key}')"><td style="font-weight:600">${r.estimate_type||'-'}</td><td>${r.estimate_date||'-'}</td><td><span style="display:inline-block;padding:2px 8px;border-radius:3px;font-size:11px;background:${bg}">${c}</span></td><td class="num" style="font-weight:600">${r.tonnes_mt?r.tonnes_mt.toFixed(2)+' Mt':'-'}</td><td class="num" style="font-weight:600;color:var(--accent)">${fmtGrd(r,false)}</td><td class="num">${fmtCont(r,false)}</td></tr>`;}else{html+=`<tr style="background:rgba(100,140,180,0.12);cursor:pointer" onclick="showREModal('${est.key}')"><td colspan="6" style="font-weight:700;padding:8px 12px;border-left:3px solid var(--accent);font-size:14px">${est.type} <span style="opacity:0.6;font-weight:400;margin-left:8px">${est.date}</span></td></tr>`;rows.forEach((r,i)=>{const c=r.category||'Unknown';const bg=c.includes('Indicated')?'rgba(76,175,80,0.2);color:#81c784':c.includes('Measured')?'rgba(33,150,243,0.2);color:#64b5f6':c==='Proven'||c==='Probable'?'rgba(171,71,188,0.2);color:#ce93d8':'rgba(255,183,77,0.2);color:#ffb74d';html+=`<tr style="background:${i%2===0?'rgba(255,255,255,0.02)':'rgba(100,140,180,0.05)'};cursor:pointer" onclick="showREModal('${est.key}')"><td></td><td></td><td><span style="display:inline-block;padding:2px 8px;border-radius:3px;font-size:11px;background:${bg}">${c}</span></td><td class="num" style="font-weight:600">${r.tonnes_mt?r.tonnes_mt.toFixed(2)+' Mt':'-'}</td><td class="num" style="font-weight:600;color:var(--accent)">${fmtGrd(r,false)}</td><td class="num">${fmtCont(r,false)}</td></tr>`;});}});return html;})()}</tbody></table></div></div></div>`;
    }

// Nearby Mines
  if(nm.length){
    html+=`<div class="section"><div class="section-header" onclick="toggleSection(this)">
      <h2>Nearby Mines & Discoveries</h2><span class="badge">${nm.length}</span></div>
      <div class="section-body"><div class="scroll-table"><table>
      <thead><tr><th>Mine/Deposit</th><th>Owner</th><th>Distance</th><th>Commodity</th><th>Resource</th><th>Relevance</th></tr></thead>
      <tbody>${nm.map(n=>`<tr>
        <td style="font-weight:600">${n.nearby_name||'-'}</td><td>${n.owner_operator||'-'}</td>
        <td>${n.distance||'-'}</td><td>${n.commodity||'-'}</td>
        <td style="font-size:12px">${n.resource_info||'-'}</td>
        <td style="font-size:12px;max-width:250px">${n.relevance||'-'}</td>
      </tr>`).join('')}</tbody></table></div></div></div>`;
  }


  html+=`</div>`;
  co.innerHTML=html;
  setTimeout(mergeResourceEstimateRows,100);

  if(p.latitude&&p.longitude){
    setTimeout(()=>{
      const pm=L.map('propMap',{zoomControl:false,attributionControl:false}).setView([p.latitude,p.longitude],8);
      L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',{maxZoom:19}).addTo(pm);
      L.circleMarker([p.latitude,p.longitude],{radius:8,fillColor:'#d4af37',color:'#fff',weight:2,fillOpacity:0.8}).addTo(pm);
    },50);
  }
}

function detectMetalColumns(results){
  const cols=[];
  const metals=[
    {key:'au_gpt',label:'Au (g/t)'},{key:'ag_gpt',label:'Ag (g/t)'},
    {key:'cu_pct',label:'Cu (%)'},{key:'zn_pct',label:'Zn (%)'},
    {key:'ni_pct',label:'Ni (%)'},{key:'co_pct',label:'Co (%)'},
    {key:'pb_pct',label:'Pb (%)'},{key:'pt_gpt',label:'Pt (g/t)'},
    {key:'cueq_pct',label:'CuEq (%)'},
    {key:'fe2o3_pct',label:'Fe2O3 (%)'},{key:'tio2_pct',label:'TiO2 (%)'},
  ];
  for(const m of metals){
    if(results.some(r=>r[m.key]!=null))cols.push(m);
  }
  return cols;
}

function isHighGrade(row,metalCols){
  for(const mc of metalCols){
    if(isHighVal(row[mc.key],mc.key))return true;
  }
  return false;
}
function isHighVal(val,key){
  if(val==null)return false;
  if(key==='au_gpt')return val>=2.0;
  if(key==='cu_pct')return val>=1.0;
  if(key==='cueq_pct')return val>=2.0;
  if(key==='ag_gpt')return val>=100;
  if(key==='ni_pct')return val>=0.5;
  if(key==='zn_pct')return val>=2.0;
  return false;
}

async function showDrillResults(dpId){
            const resp = await fetch(`/api/drill_programs/${dpId}`);
            const data = await resp.json();
            const prog = data.program;
            const results = data.results || [];
            const siblings = data.siblings_with_data || [];
            const modal = document.getElementById('drillModal');
            const body = document.getElementById('modalBody');
            document.getElementById('modalTitle').textContent = prog.program_name + (prog.year ? ' ('+prog.year+')' : '');

            // If no results at all
            if(results.length === 0){
                let html = '<div style="padding:20px;text-align:center;color:#aaa;">';
                html += '<p style="font-size:16px;margin-bottom:10px;">No assay results imported for this program yet.</p>';
                if(prog.actual_holes){
                    html += '<p style="font-size:13px;color:#666;">This program lists ' + prog.actual_holes + ' holes drilled, but detailed results have not been digitized.</p>';
                }
                if(siblings.length > 0){
                    html += '<p style="font-size:13px;color:#888;margin-top:15px;">Available assay data for this property:</p>';
                    siblings.forEach(s => {
                        html += '<p style="margin:5px 0;"><a href="#" onclick="showDrillResults('+s.id+');return false;" style="color:#f0a500;">' + s.program_name + (s.year ? ' ('+s.year+')' : '') + '</a> — ' + s.result_count + ' results</p>';
                    });
                }
                html += '</div>';
                body.innerHTML = html;
                modal.classList.add('active');
                modal.style.display = '';
                return;
            }

            // Helper: does a row have any real grade data?
            function hasRealGrade(r){
                const keys = ['au_gpt','ag_gpt','cu_pct','co_pct','fe2o3_pct','cueq_pct','li2o_pct'];
                return keys.some(k => r[k] !== null && r[k] !== undefined && r[k] !== 0 && r[k] !== 0.0);
            }
function fmtGrade(v, key, row){
                if(v === null || v === undefined) return '-';
                if(v === 0 || v === 0.0){
                }
                if(key && key.endsWith('_pct')) return v.toFixed(2) + '%';
                return v.toFixed(2);
            }
            // Determine which metal columns have real data
            function getMetalCols(rows){
                const all = [
                    {key:'au_gpt',label:'Au g/t'},
                    {key:'ag_gpt',label:'Ag g/t'},
                    {key:'cu_pct',label:'Cu %'},
                    {key:'co_pct',label:'Co %'},
                    {key:'fe2o3_pct',label:'Fe2O3 %'},
                    {key:'cueq_pct',label:'CuEq %'},
                    {key:'li2o_pct',label:'Li2O %'}
                ];
                return all.filter(col => rows.some(r => r[col.key] !== null && r[col.key] !== undefined));
            }

            // Split by type
            const intervals = results.filter(r => r.result_type === 'interval' || r.result_type === 'including');
            const samples = results.filter(r => r.result_type === 'sample');
            const depths = results.filter(r => r.result_type === 'total_depth');
            const unknown = results.filter(r => !r.result_type || (r.result_type !== 'interval' && r.result_type !== 'including' && r.result_type !== 'sample' && r.result_type !== 'total_depth'));

            let html = '';

            // Intervals section
            if(intervals.length > 0){
                const mcols = getMetalCols(intervals);
                html += '<h4 style="color:#f0a500;margin:10px 0 5px;">Drill Intercepts</h4>';
                html += '<table style="width:100%;border-collapse:collapse;font-size:13px;">';
                html += '<tr style="border-bottom:1px solid #444;color:#aaa;"><th style="text-align:left;padding:4px;">Hole ID</th><th>From (m)</th><th>To (m)</th><th>Interval (m)</th>';
                mcols.forEach(c => { html += '<th>'+c.label+'</th>'; });
                html += '</tr>';
                intervals.forEach(r => {
                    const isIncl = r.result_type === 'including';
                    const style = isIncl ? 'font-style:italic;padding-left:20px;color:#ccc;' : '';
                    html += '<tr style="border-bottom:1px solid #333;">';
                    html += '<td style="padding:4px;'+style+'">'+(isIncl?'<span style="color:#888;">incl.</span> ':'')+r.hole_id+'</td>';
                    html += '<td style="text-align:center;">'+(r.from_m !== null ? r.from_m : '-')+'</td>';
                    html += '<td style="text-align:center;">'+(r.to_m !== null ? r.to_m : '-')+'</td>';
                    html += '<td style="text-align:center;">'+(r.interval_m !== null ? r.interval_m : '-')+'</td>';
                    mcols.forEach(c => {
                        html += '<td style="text-align:center;">'+fmtGrade(r[c.key], c.key, r)+'</td>';
                    });
                    html += '</tr>';
                });
                html += '</table>';
            }

            // Samples section
            if(samples.length > 0){
                const mcols = getMetalCols(samples);
                html += '<h4 style="color:#f0a500;margin:15px 0 5px;">Samples</h4>';
                html += '<table style="width:100%;border-collapse:collapse;font-size:13px;">';
                html += '<tr style="border-bottom:1px solid #444;color:#aaa;"><th style="text-align:left;padding:4px;">Hole / Sample ID</th>';
                if(mcols.length > 0){
                    mcols.forEach(c => { html += '<th>'+c.label+'</th>'; });
                } else {
                    html += '<th style="color:#666;">Assays not available</th>';
                }
                html += '</tr>';
                samples.forEach(r => {
                    html += '<tr style="border-bottom:1px solid #333;">';
                    html += '<td style="padding:4px;">'+r.hole_id+'</td>';
                    if(mcols.length > 0){
                        mcols.forEach(c => {
                            html += '<td style="text-align:center;">'+fmtGrade(r[c.key], c.key, r)+'</td>';
                        });
                    } else {
                        html += '<td style="text-align:center;color:#666;">-</td>';
                    }
                    html += '</tr>';
                });
                html += '</table>';
            }

            // Depths section
            if(depths.length > 0){
                html += '<h4 style="color:#f0a500;margin:15px 0 5px;">Holes Drilled</h4>';
                html += '<table style="width:100%;border-collapse:collapse;font-size:13px;">';
                html += '<tr style="border-bottom:1px solid #444;color:#aaa;"><th style="text-align:left;padding:4px;">Hole ID</th><th>Total Depth (m)</th></tr>';
                depths.forEach(r => {
                    html += '<tr style="border-bottom:1px solid #333;">';
                    html += '<td style="padding:4px;">'+r.hole_id+'</td>';
                    html += '<td style="text-align:center;">'+(r.depth_m !== null ? r.depth_m : '-')+'</td>';
                    html += '</tr>';
                });
                html += '</table>';
            }

        // Other Results (non-standard result_types)
        if(unknown.length > 0){
            const umcols = getMetalCols(unknown);
            html += '<h4 style="color:#f0a500;margin:10px 0 5px;">Results</h4>';
            html += '<table style="width:100%;border-collapse:collapse;font-size:13px;">';
            html += '<tr style="border-bottom:1px solid #444;color:#aaa;"><th style="text-align:left;padding:4px;">Hole ID</th><th>From (m)</th><th>To (m)</th><th>Interval (m)</th>';
            umcols.forEach(c => { html += '<th>'+c.label+'</th>'; });
            html += '<th style="text-align:left;padding:4px;">Type</th></tr>';
            unknown.forEach(r => {
                const isHigh = isHighGrade(r, umcols);
                const style = isHigh ? 'font-weight:bold;color:#f0a500;' : '';
                html += '<tr style="border-bottom:1px solid #333;">';
                html += '<td style="padding:4px;'+style+'">'+r.hole_id+'</td>';
                html += '<td style="text-align:center;">'+(r.from_m !== null ? r.from_m : '-')+'</td>';
                html += '<td style="text-align:center;">'+(r.to_m !== null ? r.to_m : '-')+'</td>';
                html += '<td style="text-align:center;">'+(r.interval_m !== null ? r.interval_m : '-')+'</td>';
                umcols.forEach(c => {
                    html += '<td style="text-align:center;">'+fmtGrade(r[c.key], c.key, r)+'</td>';
                });
                html += '<td style="padding:4px;font-size:11px;color:#888;">'+(r.result_type||'-')+'</td>';
                html += '</tr>';
            });
            html += '</table>';
        }

            // Summary
            let parts = [];
            if(intervals.length) parts.push(intervals.length + ' intercept(s)');
            if(samples.length) parts.push(samples.length + ' sample(s)');
            if(depths.length) parts.push(depths.length + ' hole(s)');
            if(parts.length) html += '<p style="color:#888;margin-top:10px;font-size:12px;">Total: '+parts.join(', ')+'</p>';

            body.innerHTML = html;
            modal.classList.add('active');
            modal.style.display = '';
        }
function showAllDrillResults(){
  const results=window._allDrillResults;
  if(!results||!results.length){return;}
  const modal=document.getElementById('drillModal');
  const body=document.getElementById('modalBody');
  const title=document.getElementById('modalTitle');
  title.textContent='All Drill Results ('+results.length+')';
  const mc=[];
  const metals=['au_gpt','ag_gpt','cu_pct','zn_pct','ni_pct','co_pct','pt_gpt','cueq_pct'];
  const labels=['Au (g/t)','Ag (g/t)','Cu (%)','Zn (%)','Ni (%)','Co (%)','Pt (g/t)','CuEq (%)'];
  metals.forEach((m,i)=>{if(results.some(r=>r[m]!=null))mc.push({key:m,label:labels[i]});});
  let h='<div class="scroll-table"><table><thead><tr><th>Hole ID</th><th>Zone</th><th class="num">From</th><th class="num">To</th><th class="num">Interval</th>';
  mc.forEach(m=>{h+='<th class="num">'+m.label+'</th>';});
  h+='<th>Notes</th></tr></thead><tbody>';
  results.forEach(r=>{
    const isHigh=r.highlight==1;
    h+='<tr class="'+(isHigh?'highlight-row':'')+'">';
    h+='<td style="font-weight:600">'+(r.hole_id||'-')+'</td>';
    h+='<td>'+(r.zone_target||'-')+'</td>';
    h+='<td class="num">'+(r.from_m!=null?Number(r.from_m).toFixed(1):'-')+'</td>';
    h+='<td class="num">'+(r.to_m!=null?Number(r.to_m).toFixed(1):'-')+'</td>';
    h+='<td class="num" style="font-weight:600">'+(r.interval_m!=null?Number(r.interval_m).toFixed(1):'-')+'</td>';
    mc.forEach(m=>{
      const v=r[m.key];
      h+='<td class="num">'+(v!=null?Number(v).toFixed(m.key.includes('pct')?2:2):'-')+'</td>';
    });
    h+='<td style="font-size:12px">'+(r.notes||'')+'</td>';
    h+='</tr>';
  });
  h+='</tbody></table></div>';
  h+='<p style="margin-top:12px;color:var(--text2);font-size:13px">'+results.length+' result'+(results.length!=1?'s':'')+' total</p>';
  body.innerHTML=h;
  modal.classList.add('active');
}
function closeDrillModal(){document.getElementById('drillModal').classList.remove('active');}

function fmtNum(v){return v!=null?Number(v).toLocaleString():'-';}
function fmtDec(v){return v!=null?Number(v).toFixed(1):'-';}
function fmtGrade(v){return v!=null?Number(v).toFixed(2):'-';}

function toggleSection(header){
  const body=header.nextElementSibling;
  body.style.display=body.style.display==='none'?'':'none';
}

// Search
let searchTimeout;
document.getElementById('searchInput').addEventListener('input',function(){
  clearTimeout(searchTimeout);
  const q=this.value.trim();
  if(!q){document.getElementById('searchResults').classList.remove('active');return;}
  searchTimeout=setTimeout(async()=>{
    const results=await fetchJSON(`/api/search?q=${encodeURIComponent(q)}`);
    const sr=document.getElementById('searchResults');
    if(!results.length){sr.classList.remove('active');return;}
    sr.innerHTML=results.map(r=>`<div class="sr-item" onclick="showProperty(${r.id});document.getElementById('searchResults').classList.remove('active');document.getElementById('searchInput').value='';">
      <span><span class="ticker">${r.ticker}</span>${r.name}</span>
      <span class="metals">${r.primary_metals||'-'}</span>
    </div>`).join('');
    sr.classList.add('active');
  },200);
});
document.addEventListener('click',e=>{
  if(!e.target.closest('.search-box'))document.getElementById('searchResults').classList.remove('active');
});

init();

    

    // Resource Estimate Modal v2
    window._reData = {};
    window._reGroups = {};
    function cacheREData(data) {
      if(data && data.resource_estimates) {
        data.resource_estimates.forEach(r => { window._reData[r.id] = r; });
        // Group by estimate key
        window._reGroups = {};
        let lk="";
        data.resource_estimates.forEach(r => {
          const k = r.estimate_date+(r.estimate_type||"");
          if(!window._reGroups[k]) window._reGroups[k]={type:r.estimate_type||'Resource Estimate',date:r.estimate_date||'',compliance:r.compliance_code||'',rows:[],prepared_by:r.prepared_by||'',qualified_person:r.qualified_person||'',cutoff:r.cutoff_assumptions||'',source:r.source_url||'',notes:r.notes||''};
          window._reGroups[k].rows.push(r);
          if(r.notes && r.notes.length > (window._reGroups[k].notes||'').length) window._reGroups[k].notes = r.notes;
          if(r.source_url) window._reGroups[k].source = r.source_url;
        });
      }
    }
  function showREModal(key) {
    const g = window._reGroups[key];
    if(!g) return;
    const m = document.getElementById('reModalContent');
    let h = '<button class="re-modal-close" onclick="closeREModal()">&times;</button>';
    h += '<h3>'+g.type+'</h3>';
    h += '<div class="re-modal-sub">';
    if(g.date) h += g.date;
    if(g.compliance) h += ' &middot; '+g.compliance;
    h += '</div>';
    const gF=[
      {k:'grade_cueq_pct',l:'CuEq (%)',f:v=>v.toFixed(2)},
      {k:'grade_cu_pct',l:'Cu (%)',f:v=>v.toFixed(2)},
      {k:'grade_au_gpt',l:'Au (g/t)',f:v=>v.toFixed(2)},
      {k:'grade_ag_gpt',l:'Ag (g/t)',f:v=>v.toFixed(1)},
      {k:'grade_zn_pct',l:'Zn (%)',f:v=>v.toFixed(2)},
      {k:'grade_mo_pct',l:'Mo (%)',f:v=>v.toFixed(3)},
      {k:'grade_treo_pct',l:'TREO (%)',f:v=>v.toFixed(2)},
      {k:'grade_u3o8_lbs_per_ton',l:'U3O8 (lbs/t)',f:v=>v.toFixed(2)},
      {k:'grade_tree_lbs_per_ton',l:'TREE (lbs/t)',f:v=>v.toFixed(2)},
      {k:'grade_li_ppm',l:'Li (ppm)',f:v=>v.toFixed(0)},
    ];
    const cF=[
      {k:'contained_au_moz',l:'Au (Moz)',f:v=>v.toFixed(3)},
      {k:'contained_ag_moz',l:'Ag (Moz)',f:v=>v.toFixed(3)},
      {k:'contained_cueq_mlbs',l:'CuEq (Mlbs)',f:v=>v.toFixed(1)},{k:'contained_cu_mlbs',l:'Cu (Mlbs)',f:v=>v.toFixed(1)},
      {k:'contained_zn_mlbs',l:'Zn (Mlbs)',f:v=>v.toFixed(1)},
      {k:'contained_mo_mlbs',l:'Mo (Mlbs)',f:v=>v.toFixed(1)},
      {k:'contained_u3o8_mlbs',l:'U3O8 (Mlbs)',f:v=>v.toFixed(1)},
      {k:'contained_tree_mlbs',l:'TREE (Mlbs)',f:v=>v.toFixed(1)}
    ];
    const aG=gF.filter(x=>g.rows.some(r=>r[x.k]&&r[x.k]>0));
    const aC=cF.filter(x=>g.rows.some(r=>r[x.k]&&r[x.k]>0));
    h+='<table class="re-cat-table"><thead><tr><th>Category</th><th class="num">Tonnes (Mt)</th>';
    aG.forEach(x=>{h+='<th class="num">'+x.l+'</th>';});
    aC.forEach(x=>{h+='<th class="num">'+x.l+'</th>';});
    h+='</tr></thead><tbody>';
    let totT=0;
    g.rows.forEach(r=>{
      const cat=r.category||'Unknown';
      const cc=cat.includes('Indicated')?'rgba(76,175,80,0.2)':cat.includes('Measured')?'rgba(33,150,243,0.2)':cat==='Proven'?'rgba(33,150,243,0.2)':cat==='Probable'?'rgba(171,71,188,0.2)':'rgba(255,183,77,0.2)';
      h+='<tr><td><span style="display:inline-block;padding:2px 8px;border-radius:3px;font-size:11px;background:'+cc+'">'+cat+'</span></td>';
      h+='<td class="num">'+(r.tonnes_mt?r.tonnes_mt.toFixed(2):'-')+'</td>';
      aG.forEach(x=>{
        const v=r[x.k];
        h+='<td class="num"'+(x.k==='grade_cueq_pct'?' style="color:var(--accent)"':'')+'>'+(v?x.f(v):'-')+'</td>';
      });
      aC.forEach(x=>{
        const v=r[x.k];
        h+='<td class="num">'+(v?x.f(v):'-')+'</td>';
      });
      h+='</tr>';
      if(r.tonnes_mt) totT+=r.tonnes_mt;
    });
    if(g.rows.length>1){
      let tots={};cF.forEach(x=>{tots[x.k]=0;});
      g.rows.forEach(r=>{cF.forEach(x=>{if(r[x.k])tots[x.k]+=r[x.k];});});
      h+='<tr style="border-top:2px solid var(--border);font-weight:700"><td>Total</td><td class="num">'+totT.toFixed(2)+'</td>';
      aG.forEach(()=>{h+='<td class="num">-</td>';});
      aC.forEach(x=>{h+='<td class="num">'+(tots[x.k]?x.f(tots[x.k]):'-')+'</td>';});
      h+='</tr>';
    }
    h+='</tbody></table>';
    const oG=g.rows.find(r=>r.other_grades);
    const oC=g.rows.find(r=>r.other_contained);
    if(oG||oC){
      h+='<div class="re-divider"></div>';
      if(oG) h+='<div class="re-notes"><strong>Other Grades:</strong> '+oG.other_grades+'</div>';
      if(oC) h+='<div class="re-notes"><strong>Other Contained:</strong> '+oC.other_contained+'</div>';
    }
    h+='<div class="re-divider"></div><div class="re-grid">';
    if(g.prepared_by) h+='<div class="re-grid-item"><div class="re-label">Prepared By</div><div class="re-value">'+g.prepared_by+'</div></div>';
    if(g.qualified_person) h+='<div class="re-grid-item"><div class="re-label">Qualified Person</div><div class="re-value">'+g.qualified_person+'</div></div>';
    if(g.compliance) h+='<div class="re-grid-item"><div class="re-label">Compliance Standard</div><div class="re-value accent">'+g.compliance+'</div></div>';
    h+='</div>';
    if(g.cutoff){
      h+='<div class="re-divider"></div>';
      h+='<div style="margin-bottom:8px"><div class="re-label" style="margin-bottom:4px">Cut-off Grade & Assumptions</div><div class="re-notes">'+g.cutoff+'</div></div>';
    }
    if(g.notes){
      h+='<div class="re-divider"></div>';
      h+='<div class="re-notes">'+g.notes+'</div>';
    }
    if(g.source){
      h+='<div class="re-divider"></div>';
      h+='<div class="re-source"><a href="'+g.source+'" target="_blank" style="display:inline-flex;align-items:center;gap:6px;padding:8px 0;color:#d4a843;font-weight:600;text-decoration:none;font-size:14px">View Source Document &rarr;</a></div>';
    }
    m.innerHTML=h;
  setTimeout(mergeREModalRows,50);
    document.querySelector('.re-modal-overlay').classList.add('active');
  }
    function closeREModal() {
      document.getElementById('reModalOverlay').classList.remove('active');
    }
    document.addEventListener('keydown', e => { if(e.key === 'Escape') closeREModal(); });


// Resource Estimates table merge - merges multi-commodity rows into single rows per category
function mergeResourceEstimateRows(){
  const tables=document.querySelectorAll('table');
  let reTable=null;
  tables.forEach(t=>{t.querySelectorAll('th').forEach(th=>{if(th.textContent.trim()==='Estimate')reTable=t;});});
  if(!reTable)return;
  const thead=reTable.querySelector('thead'),tbody=reTable.querySelector('tbody');
  if(!thead||!tbody)return;
  const rows=Array.from(tbody.querySelectorAll('tr'));
  let estimates=[],currentEst=null;
  rows.forEach(row=>{
    const cells=row.querySelectorAll('td');
    if(cells.length<=2){currentEst={headerRow:row,categories:{}};estimates.push(currentEst);}
    else if(currentEst){
      let category='',tonnes='',grade='',contained='';
      Array.from(cells).forEach(c=>{
        const span=c.querySelector('span');
        if(span&&/Measured|Indicated|Inferred/.test(span.textContent))category=span.textContent.trim();
        const txt=c.textContent.trim();
        if(txt.includes('Mt'))tonnes=txt;
        if((txt.includes('%')||txt.includes('g/t'))&&!txt.includes('Mlbs')&&!txt.includes('Moz'))grade=txt;
        if(txt.includes('Mlbs')||txt.includes('Moz'))contained=txt;
      });
      if(category){
        if(!currentEst.categories[category])currentEst.categories[category]={tonnes:tonnes,grades:[],containeds:[]};
        if(grade)currentEst.categories[category].grades.push(grade);
        if(contained)currentEst.categories[category].containeds.push(contained);
      }
    }
  });
  let needsMerge=false;
  estimates.forEach(est=>{Object.values(est.categories).forEach(cat=>{if(cat.grades.length>1)needsMerge=true;});});
  if(!needsMerge)return;
  const allGradeLabels=[];
  estimates.forEach(est=>{Object.values(est.categories).forEach(cat=>{cat.grades.forEach(g=>{const label=g.replace(/[\d.]+\s*/,'').trim();if(!allGradeLabels.includes(label))allGradeLabels.push(label);});});});
const allContainedLabels=[];
estimates.forEach(est=>{Object.values(est.categories).forEach(cat=>{cat.containeds.forEach(g=>{const label=g.replace(/[\d.]+\s*/,'').trim();if(!allContainedLabels.includes(label))allContainedLabels.push(label);});});});
  const headerRow=thead.querySelector('tr');
  headerRow.innerHTML='';
  ['Estimate','Date','Category','Tonnes'].forEach(h=>{const th=document.createElement('th');th.textContent=h;headerRow.appendChild(th);});
  allGradeLabels.forEach(label=>{const th=document.createElement('th');th.className='num';th.textContent=label;headerRow.appendChild(th);});
allContainedLabels.forEach(label=>{const th=document.createElement('th');th.className='num';th.textContent=label;headerRow.appendChild(th);});
  tbody.innerHTML='';
  const badgeColors={'Measured':'#2d6a4f','Indicated':'#1a5276','Inferred':'#7d3c98'};
  estimates.forEach(est=>{
    tbody.appendChild(est.headerRow);
    Object.entries(est.categories).forEach(([cat,data])=>{
      const tr=document.createElement('tr');
      tr.innerHTML+='<td></td><td></td>';
      const catTd=document.createElement('td');
      const span=document.createElement('span');
      span.textContent=cat;
      span.style.cssText='padding:2px 8px;border-radius:4px;font-size:0.85em;color:white;background:'+(badgeColors[cat]||'#555')+';';
      catTd.appendChild(span);tr.appendChild(catTd);
      const tonTd=document.createElement('td');tonTd.className='num';tonTd.textContent=data.tonnes;tr.appendChild(tonTd);
      allGradeLabels.forEach(label=>{
        const td=document.createElement('td');td.className='num';
        const match=data.grades.find(g=>{const gLabel=g.replace(/[\d.]+\s*/,'').trim();return gLabel===label;});
        if(match){const num=match.match(/[\d.]+/);td.textContent=num?num[0]:match;}else{td.textContent='-';}
        tr.appendChild(td);
      });
    allContainedLabels.forEach(label=>{
      const td=document.createElement('td');td.className='num';
      const match=data.containeds.find(g=>{const cLabel=g.replace(/[\d.]+\s*/,'').trim();return cLabel===label;});
      if(match){const num=match.match(/[\d.]+/);td.textContent=num?num[0]:match;}else{td.textContent='-';}
      tr.appendChild(td);
    });
      tbody.appendChild(tr);
    });
  });
}

// Modal RE table merge - merges multi-commodity rows into single rows per category
function mergeREModalRows(){
  const modal=document.querySelector('.re-modal-overlay.active')||document.querySelector('.re-modal-overlay');
  if(!modal)return;
  const table=modal.querySelector('table');
  if(!table)return;
  const tbody=table.querySelector('tbody');
  if(!tbody)return;
  const rows=Array.from(tbody.querySelectorAll('tr'));
  if(rows.length<3)return;
  // Parse rows: group by category, merge values
  const categories={};
  const catOrder=[];
  let totalRow=null;
  rows.forEach(row=>{
    const cells=Array.from(row.querySelectorAll('td'));
    if(cells.length===0)return;
    // Check if total row
    if(cells[0]&&cells[0].textContent.trim()==='Total'){totalRow=row;return;}
    // Find category from span badge
    const span=cells[0]?cells[0].querySelector('span'):null;
    if(!span)return;
    const cat=span.textContent.trim();
    if(!cat)return;
    if(!categories[cat]){categories[cat]={values:[],span:span.outerHTML};catOrder.push(cat);}
    // Collect cell values (skip first cell which is category)
    const vals=[];
    for(let i=1;i<cells.length;i++){
      const txt=cells[i].textContent.trim();
      vals.push(txt);
    }
    categories[cat].values.push(vals);
  });
  // Check if merge needed
  let needsMerge=false;
  Object.values(categories).forEach(c=>{if(c.values.length>1)needsMerge=true;});
  if(!needsMerge)return;
  // Merge: for each category, combine values (take non-dash value)
  const numCols=categories[catOrder[0]].values[0].length;
  tbody.innerHTML='';
  let realTotalTonnes=0;
  const colTotals=new Array(numCols).fill(0);
  catOrder.forEach(cat=>{
    const data=categories[cat];
    const tr=document.createElement('tr');
    // Category cell
    const catTd=document.createElement('td');
    catTd.innerHTML=data.span;
    tr.appendChild(catTd);
    // Merge values across commodity rows
    for(let i=0;i<numCols;i++){
      const td=document.createElement('td');
      td.className='num';
      let merged='-';
      data.values.forEach(vals=>{
        if(vals[i]&&vals[i]!=='-'){
          if(merged==='-')merged=vals[i];
          else if(i===0){/* tonnes - don't duplicate */}
          else{merged=vals[i];} // take latest non-dash
        }
      });
      td.textContent=merged;
      // Track totals for first col (tonnes)
      if(i===0&&merged!=='-'){
        const n=parseFloat(merged);
        if(!isNaN(n))realTotalTonnes+=n;
      }
      // Track numeric totals for other cols
      if(i>0&&merged!=='-'){
        const n=parseFloat(merged);
        if(!isNaN(n))colTotals[i]+=n;
      }
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  });
  // Add corrected total row if there were multiple categories
  if(catOrder.length>1){
    const tr=document.createElement('tr');
    tr.style.cssText='border-top:2px solid var(--border);font-weight:700';
    const totalTd=document.createElement('td');
    totalTd.textContent='Total';
    tr.appendChild(totalTd);
    for(let i=0;i<numCols;i++){
      const td=document.createElement('td');
      td.className='num';
      if(i===0){td.textContent=realTotalTonnes.toFixed(2);}
      else{td.textContent='-';}
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
}
</script>
<div id="drillModal" class="modal-overlay" onclick="if(event.target===this)closeDrillModal()">
  <div class="modal-content">
    <div class="modal-header">
      <h2 id="modalTitle">Drill Results</h2>
      <button class="modal-close" onclick="closeDrillModal()">&times;</button>
    </div>
    <div class="modal-body" id="modalBody">
      <div class="modal-loading">Loading...</div>
    </div>
  </div>
</div>
<div id="drM" class="dr-mo" onclick="if(event.target===this)hideDM()"><div class="dr-mb" onclick="event.stopPropagation()"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px"><h3 id="drMT" style="margin:0"></h3><button onclick="hideDM()" style="background:none;border:none;color:var(--gold);font-size:22px;cursor:pointer;padding:4px 8px;line-height:1">&times;</button></div><div id="drMB"></div></div></div>
</body>
</html>"""

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
