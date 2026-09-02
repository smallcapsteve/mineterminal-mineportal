"""MineTerminal Admin Module - CRUD + Standardized API v1"""
from flask import Blueprint, jsonify, request, g, make_response
import sqlite3, os, json, hashlib, functools

admin_bp = Blueprint('admin', __name__)
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'm1234')

# ============ AUTH ============
def _make_token():
    return hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest()[:32]

def require_admin(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('X-Admin-Token') or request.cookies.get('admin_token')
        if not token or token != _make_token():
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated

@admin_bp.route('/admin/api/login', methods=['POST'])
def admin_login():
    data = request.get_json(force=True)
    if data.get('password') == ADMIN_PASSWORD:
        token = _make_token()
        resp = make_response(jsonify({'ok': True, 'token': token}))
        resp.set_cookie('admin_token', token, httponly=True, samesite='Lax')
        return resp
    return jsonify({'error': 'Invalid password'}), 401

@admin_bp.route('/admin/api/logout', methods=['POST'])
def admin_logout():
    resp = make_response(jsonify({'ok': True}))
    resp.delete_cookie('admin_token')
    return resp

# ============ DB HELPERS ============
def get_db():
    if 'db' not in g:
        db_path = os.environ.get("DB_PATH", "/opt/mineportal/mining_portal.db")
        g.db = sqlite3.connect(db_path)
        g.db.row_factory = sqlite3.Row
    return g.db

def row_to_dict(row):
    return dict(row) if row else None

def rows_to_list(rows):
    return [dict(r) for r in rows]

# ============ TABLE DEFINITIONS ============
TABLES = {
    'companies': {
        'pk': 'id',
        'label': 'Companies',
        'columns': ['id','ticker','name','exchange','description','website'],
        'required': ['ticker','name'],
        'fk': {},
        'display_col': 'name',
        'order': 'ticker'
    },
    'properties': {
        'pk': 'id',
        'label': 'Properties',
        'columns': ['id','company_id','name','jurisdiction','country','general_location',
                     'size_ha','current_interest','nature_of_interest','mineralization_type',
                     'primary_metals','status','resource_notes','latitude','longitude',
                     'coord_quality','infrastructure_notes','parent_property_id','current_owner','royalty_notes'],
        'required': ['company_id','name'],
        'fk': {'company_id': 'companies'},
        'display_col': 'name',
        'order': 'name'
    },
    'resource_estimates': {
        'pk': 'id',
        'label': 'Resource Estimates',
        'columns': ['id','property_id','commodity','grade_unit','contained_unit',
                    'measured_tonnes','measured_grade','measured_contained',
                    'indicated_tonnes','indicated_grade','indicated_contained',
                    'inferred_tonnes','inferred_grade','inferred_contained',
                    'proven_tonnes','proven_grade','proven_contained',
                    'probable_tonnes','probable_grade','probable_contained',
                    'cutoff_assumptions','estimate_date','prepared_by',
                    'compliance_code','notes','source_url'],
        'required': ['property_id'],
        'fk': {'property_id': 'properties'},
        'display_col': 'commodity',
        'order': 'property_id'
    },
    'estimate_commodities': {
        'pk': 'id',
        'label': 'Estimate Commodities',
        'columns': ['id','estimate_id','commodity','grade_unit','contained_unit',
                     'measured_grade','measured_contained',
                     'indicated_grade','indicated_contained',
                     'inferred_grade','inferred_contained',
                     'proven_grade','proven_contained',
                     'probable_grade','probable_contained'],
        'required': ['estimate_id'],
        'fk': {'estimate_id': 'resource_estimates'},
        'display_col': 'commodity',
        'order': 'estimate_id'
    },
    'drill_programs': {
        'pk': 'id',
        'label': 'Drill Programs',
        'columns': ['id','property_id','year','program_name','operator','drill_type',
                     'planned_meters','planned_holes','actual_meters','actual_holes',
                     'objectives','source_url'],
        'required': ['property_id'],
        'fk': {'property_id': 'properties'},
        'display_col': 'program_name',
        'order': 'year DESC'
    },
    'drill_results': {
        'pk': 'id',
        'label': 'Drill Results',
        'columns': ['id','drill_program_id','property_id','hole_id','year','zone_target',
                     'from_m','to_m','interval_m','au_gpt','ag_gpt','cu_pct','zn_pct',
                     'ni_pct','co_pct','pb_pct','pt_gpt','cueq_pct','fe2o3_pct',
                     'tio2_pct','other_assays','depth_m','result_type','highlight',
                     'notes','source_url','mo_pct','li_pct','treo_pct',
                     'u3o8_lbs_per_ton','tree_lbs_per_ton','nb2o5_pct','tho2_pct',
                     'zro2_pct','p2o5_pct'],
        'required': ['property_id'],
        'fk': {'property_id': 'properties', 'drill_program_id': 'drill_programs'},
        'display_col': 'hole_id',
        'order': 'id DESC'
    },
    'ownership_history': {
        'pk': 'id',
        'label': 'Ownership History',
        'columns': ['id','property_id','date_or_period','event_type','counterparties',
                     'interest_details','terms','notes','source_url','sort_order'],
        'required': ['property_id'],
        'fk': {'property_id': 'properties'},
        'display_col': 'event_type',
        'order': 'sort_order'
    },
    'nearby_mines': {
        'pk': 'id',
        'label': 'Nearby Mines',
        'columns': ['id','property_id','nearby_name','owner_operator','distance',
                     'commodity','resource_info','relevance','source_url'],
        'required': ['property_id'],
        'fk': {'property_id': 'properties'},
        'display_col': 'nearby_name',
        'order': 'property_id'
    },
    'sources': {
        'pk': 'id',
        'label': 'Sources',
        'columns': ['id','company_id','ref_id','title','date','doc_type','url','notes'],
        'required': ['company_id'],
        'fk': {'company_id': 'companies'},
        'display_col': 'title',
        'order': 'date DESC'
    },
    'exploration_programs': {
        'pk': 'id',
        'label': 'Exploration Programs',
        'columns': ['id','property_id','year','program_type','description',
                     'expenditure','results','source'],
        'required': ['property_id'],
        'fk': {'property_id': 'properties'},
        'display_col': 'program_type',
        'order': 'year DESC'
    }
}

# ============ ADMIN CRUD ROUTES ============

@admin_bp.route('/admin/api/tables')
@require_admin
def admin_tables():
    return jsonify({t: {'label': v['label'], 'columns': v['columns'],
                        'required': v['required'], 'fk': v['fk']}
                    for t, v in TABLES.items()})

@admin_bp.route('/admin/api/stats')
@require_admin
def admin_stats():
    db = get_db()
    stats = {}
    for table in list(TABLES.keys()) + ['property_companies']:
        stats[table] = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    return jsonify(stats)

@admin_bp.route('/admin/api/lookup/<table>')
@require_admin
def admin_lookup(table):
    """Return id + display label for FK dropdowns"""
    if table not in TABLES:
        return jsonify({'error': 'Unknown table'}), 404
    db = get_db()
    tdef = TABLES[table]
    dcol = tdef['display_col']
    if table == 'companies':
        rows = db.execute(f"SELECT id, ticker || ' - ' || name as label FROM {table} ORDER BY ticker").fetchall()
    elif table == 'properties':
        rows = db.execute("""SELECT p.id, c.ticker || ' / ' || p.name as label
            FROM properties p JOIN property_companies pc ON pc.property_id=p.id
            JOIN companies c ON c.id=pc.company_id ORDER BY c.ticker, p.name""").fetchall()
    elif table == 'drill_programs':
        rows = db.execute("""SELECT dp.id, dp.year || ' - ' || dp.program_name as label
            FROM drill_programs dp ORDER BY dp.year DESC""").fetchall()
    else:
        rows = db.execute(f"SELECT id, {dcol} as label FROM {table} ORDER BY {tdef['order']}").fetchall()
    return jsonify(rows_to_list(rows))

@admin_bp.route('/admin/api/<table>', methods=['GET'])
@require_admin
def admin_list(table):
    if table not in TABLES:
        return jsonify({'error': f'Unknown table: {table}'}), 404
    db = get_db()
    tdef = TABLES[table]
    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)
    search = request.args.get('q', '')
    fk_col = request.args.get('fk_col', '')
    fk_val = request.args.get('fk_val', '')

    where = []
    params = []
    if search:
        text_cols = [c for c in tdef['columns'] if c != 'id'][:6]
        clauses = [f"CAST({c} AS TEXT) LIKE ?" for c in text_cols]
        where.append(f"({' OR '.join(clauses)})")
        params.extend([f'%{search}%'] * len(clauses))
    if fk_col and fk_val and fk_col in tdef.get('fk', {}):
        where.append(f"{fk_col} = ?")
        params.append(fk_val)

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    count = db.execute(f"SELECT COUNT(*) FROM {table} {where_sql}", params).fetchone()[0]
    rows = db.execute(f"SELECT * FROM {table} {where_sql} ORDER BY {tdef['order']} LIMIT ? OFFSET ?",
                      params + [limit, offset]).fetchall()
    return jsonify({'table': table, 'total': count, 'limit': limit,
                    'offset': offset, 'data': rows_to_list(rows)})

@admin_bp.route('/admin/api/<table>/<int:rid>', methods=['GET'])
@require_admin
def admin_get(table, rid):
    if table not in TABLES:
        return jsonify({'error': f'Unknown table: {table}'}), 404
    db = get_db()
    row = db.execute(f"SELECT * FROM {table} WHERE id = ?", [rid]).fetchone()
    if not row:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(row_to_dict(row))

@admin_bp.route('/admin/api/<table>', methods=['POST'])
@require_admin
def admin_create(table):
    if table not in TABLES:
        return jsonify({'error': f'Unknown table: {table}'}), 404
    data = request.get_json(force=True)
    tdef = TABLES[table]
    for req in tdef['required']:
        if req not in data or data[req] is None or data[req] == '':
            return jsonify({'error': f'Missing required field: {req}'}), 400
    cols = [c for c in tdef['columns'] if c != 'id' and c in data]
    vals = [data[c] for c in cols]
    placeholders = ','.join(['?'] * len(cols))
    col_names = ','.join(cols)
    db = get_db()
    try:
        cur = db.execute(f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})", vals)
        db.commit()
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    row = db.execute(f"SELECT * FROM {table} WHERE id = ?", [cur.lastrowid]).fetchone()
    return jsonify(row_to_dict(row)), 201

@admin_bp.route('/admin/api/<table>/<int:rid>', methods=['PUT'])
@require_admin
def admin_update(table, rid):
    if table not in TABLES:
        return jsonify({'error': f'Unknown table: {table}'}), 404
    data = request.get_json(force=True)
    tdef = TABLES[table]
    cols = [c for c in tdef['columns'] if c != 'id' and c in data]
    if not cols:
        return jsonify({'error': 'No fields to update'}), 400
    vals = [data[c] for c in cols]
    set_clause = ','.join([f"{c}=?" for c in cols])
    db = get_db()
    try:
        db.execute(f"UPDATE {table} SET {set_clause} WHERE id = ?", vals + [rid])
        db.commit()
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    row = db.execute(f"SELECT * FROM {table} WHERE id = ?", [rid]).fetchone()
    if not row:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(row_to_dict(row))

@admin_bp.route('/admin/api/<table>/<int:rid>', methods=['DELETE'])
@require_admin
def admin_delete(table, rid):
    if table not in TABLES:
        return jsonify({'error': f'Unknown table: {table}'}), 404
    db = get_db()
    row = db.execute(f"SELECT * FROM {table} WHERE id = ?", [rid]).fetchone()
    if not row:
        return jsonify({'error': 'Not found'}), 404
    # Cascade delete estimate_commodities
    if table == 'resource_estimates':
        db.execute('DELETE FROM estimate_commodities WHERE estimate_id=?', [rid])
    db.execute(f"DELETE FROM {table} WHERE id = ?", [rid])
    db.commit()
    return jsonify({'ok': True, 'deleted': row_to_dict(row)})

@admin_bp.route('/admin/api/<table>/bulk', methods=['POST'])
@require_admin
def admin_bulk_create(table):
    if table not in TABLES:
        return jsonify({'error': f'Unknown table: {table}'}), 404
    data = request.get_json(force=True)
    if not isinstance(data, list):
        return jsonify({'error': 'Expected JSON array'}), 400
    db = get_db()
    tdef = TABLES[table]
    created = []
    errors = []
    for i, item in enumerate(data):
        try:
            for req in tdef['required']:
                if req not in item or item[req] is None:
                    raise ValueError(f'Missing required field: {req}')
            cols = [c for c in tdef['columns'] if c != 'id' and c in item]
            vals = [item[c] for c in cols]
            placeholders = ','.join(['?'] * len(cols))
            col_names = ','.join(cols)
            cur = db.execute(f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})", vals)
            created.append(cur.lastrowid)
        except Exception as e:
            errors.append({'index': i, 'error': str(e)})
    db.commit()
    return jsonify({'created': len(created), 'ids': created, 'errors': errors}), 201

# ============ PROPERTY-COMPANIES JUNCTION ============

@admin_bp.route('/admin/api/property_companies', methods=['GET'])
@require_admin
def admin_list_pc():
    db = get_db()
    pid = request.args.get('property_id', type=int)
    cid = request.args.get('company_id', type=int)
    where, params = [], []
    if pid: where.append("pc.property_id = ?"); params.append(pid)
    if cid: where.append("pc.company_id = ?"); params.append(cid)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    rows = db.execute(f"""SELECT pc.*, p.name as property_name, c.ticker as company_ticker
        FROM property_companies pc
        JOIN properties p ON p.id=pc.property_id
        JOIN companies c ON c.id=pc.company_id {where_sql}""", params).fetchall()
    return jsonify({'data': rows_to_list(rows)})

@admin_bp.route('/admin/api/property_companies', methods=['POST'])
@require_admin
def admin_create_pc():
    data = request.get_json(force=True)
    db = get_db()
    try:
        db.execute("INSERT INTO property_companies (property_id,company_id) VALUES (?,?)",
                   [data['property_id'], data['company_id']])
        db.commit()
        return jsonify({'ok': True}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@admin_bp.route('/admin/api/property_companies', methods=['DELETE'])
@require_admin
def admin_delete_pc():
    data = request.get_json(force=True)
    db = get_db()
    db.execute("DELETE FROM property_companies WHERE property_id=? AND company_id=?",
               [data['property_id'], data['company_id']])
    db.commit()
    return jsonify({'ok': True})

# ============ STANDARDIZED PUBLIC API v1 ============

@admin_bp.route('/api/v1/companies')
def v1_companies():
    db = get_db()
    rows = db.execute("""
        SELECT c.*, COUNT(DISTINCT pc.property_id) as property_count
        FROM companies c LEFT JOIN property_companies pc ON pc.company_id=c.id
        GROUP BY c.id ORDER BY c.ticker""").fetchall()
    return jsonify({'data': rows_to_list(rows), 'total': len(rows)})

@admin_bp.route('/api/v1/companies/<int:cid>')
def v1_company(cid):
    db = get_db()
    co = db.execute("SELECT * FROM companies WHERE id=?", [cid]).fetchone()
    if not co: return jsonify({'error': 'Not found'}), 404
    result = row_to_dict(co)
    result['properties'] = rows_to_list(db.execute("""
        SELECT p.* FROM properties p JOIN property_companies pc ON pc.property_id=p.id
        WHERE pc.company_id=? ORDER BY p.name""", [cid]).fetchall())
    result['sources'] = rows_to_list(db.execute(
        "SELECT * FROM sources WHERE company_id=?", [cid]).fetchall())
    return jsonify(result)

@admin_bp.route('/api/v1/properties')
def v1_properties():
    db = get_db()
    limit = request.args.get('limit', 500, type=int)
    offset = request.args.get('offset', 0, type=int)
    company_id = request.args.get('company_id', type=int)
    where, params = [], []
    if company_id:
        where.append("pc.company_id=?"); params.append(company_id)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    rows = db.execute(f"""
        SELECT DISTINCT p.*, c.ticker as company_ticker, c.name as company_name
        FROM properties p JOIN property_companies pc ON pc.property_id=p.id
        JOIN companies c ON c.id=pc.company_id {where_sql}
        ORDER BY c.ticker, p.name LIMIT ? OFFSET ?""",
        params + [limit, offset]).fetchall()
    total = db.execute(f"""SELECT COUNT(DISTINCT p.id) FROM properties p
        JOIN property_companies pc ON pc.property_id=p.id {where_sql}""", params).fetchone()[0]
    return jsonify({'data': rows_to_list(rows), 'total': total,
                    'limit': limit, 'offset': offset})

@admin_bp.route('/api/v1/properties/<int:pid>')
def v1_property(pid):
    db = get_db()
    prop = db.execute("SELECT * FROM properties WHERE id=?", [pid]).fetchone()
    if not prop: return jsonify({'error': 'Not found'}), 404
    r = row_to_dict(prop)
    r['companies'] = rows_to_list(db.execute("""
        SELECT c.* FROM companies c JOIN property_companies pc ON pc.company_id=c.id
        WHERE pc.property_id=?""", [pid]).fetchall())
    r['resource_estimates'] = rows_to_list(db.execute(
        "SELECT * FROM resource_estimates WHERE property_id=? ORDER BY estimate_date DESC", [pid]).fetchall())
    r['drill_programs'] = rows_to_list(db.execute(
        "SELECT * FROM drill_programs WHERE property_id=? ORDER BY year DESC", [pid]).fetchall())
    r['drill_results'] = rows_to_list(db.execute(
        "SELECT * FROM drill_results WHERE property_id=? ORDER BY id DESC LIMIT 200", [pid]).fetchall())
    r['ownership_history'] = rows_to_list(db.execute(
        "SELECT * FROM ownership_history WHERE property_id=? ORDER BY sort_order", [pid]).fetchall())
    r['nearby_mines'] = rows_to_list(db.execute(
        "SELECT * FROM nearby_mines WHERE property_id=?", [pid]).fetchall())
    r['exploration_programs'] = rows_to_list(db.execute(
        "SELECT * FROM exploration_programs WHERE property_id=? ORDER BY year DESC", [pid]).fetchall())
    return jsonify(r)

@admin_bp.route('/api/v1/resource-estimates')
def v1_resource_estimates():
    db = get_db()
    property_id = request.args.get('property_id', type=int)
    company_id = request.args.get('company_id', type=int)
    where, params = [], []
    if property_id: where.append("re.property_id=?"); params.append(property_id)
    if company_id: where.append("pc.company_id=?"); params.append(company_id)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    rows = db.execute(f"""
        SELECT re.*, p.name as property_name, c.ticker as company_ticker, c.name as company_name
        FROM resource_estimates re
        JOIN properties p ON p.id=re.property_id
        JOIN property_companies pc ON pc.property_id=p.id
        JOIN companies c ON c.id=pc.company_id {where_sql}
        ORDER BY c.ticker, p.name, re.estimate_date DESC""", params).fetchall()
    return jsonify({'data': rows_to_list(rows), 'total': len(rows)})

@admin_bp.route('/api/v1/drill-programs')
def v1_drill_programs():
    db = get_db()
    property_id = request.args.get('property_id', type=int)
    where, params = [], []
    if property_id: where.append("dp.property_id=?"); params.append(property_id)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    rows = db.execute(f"""
        SELECT dp.*, p.name as property_name, COUNT(dr.id) as result_count
        FROM drill_programs dp JOIN properties p ON p.id=dp.property_id
        LEFT JOIN drill_results dr ON dr.drill_program_id=dp.id {where_sql}
        GROUP BY dp.id ORDER BY dp.year DESC""", params).fetchall()
    return jsonify({'data': rows_to_list(rows), 'total': len(rows)})

@admin_bp.route('/api/v1/drill-results')
def v1_drill_results():
    db = get_db()
    program_id = request.args.get('program_id', type=int)
    property_id = request.args.get('property_id', type=int)
    limit = request.args.get('limit', 500, type=int)
    offset = request.args.get('offset', 0, type=int)
    where, params = [], []
    if program_id: where.append("dr.drill_program_id=?"); params.append(program_id)
    if property_id: where.append("dr.property_id=?"); params.append(property_id)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    rows = db.execute(f"""
        SELECT dr.*, p.name as property_name
        FROM drill_results dr JOIN properties p ON p.id=dr.property_id {where_sql}
        ORDER BY dr.id DESC LIMIT ? OFFSET ?""", params + [limit, offset]).fetchall()
    total = db.execute(f"SELECT COUNT(*) FROM drill_results dr {where_sql}", params).fetchone()[0]
    return jsonify({'data': rows_to_list(rows), 'total': total,
                    'limit': limit, 'offset': offset})

@admin_bp.route('/api/v1/ownership-history')
def v1_ownership():
    db = get_db()
    property_id = request.args.get('property_id', type=int)
    if not property_id:
        return jsonify({'error': 'property_id required'}), 400
    rows = db.execute("SELECT * FROM ownership_history WHERE property_id=? ORDER BY sort_order",
                      [property_id]).fetchall()
    return jsonify({'data': rows_to_list(rows), 'total': len(rows)})

@admin_bp.route('/api/v1/nearby-mines')
def v1_nearby_mines():
    db = get_db()
    property_id = request.args.get('property_id', type=int)
    if not property_id:
        return jsonify({'error': 'property_id required'}), 400
    rows = db.execute("SELECT * FROM nearby_mines WHERE property_id=?",
                      [property_id]).fetchall()
    return jsonify({'data': rows_to_list(rows), 'total': len(rows)})

# ============ ADMIN UI ============
@admin_bp.route('/admin/')
@admin_bp.route('/admin')
def admin_ui():
    html_path = os.path.join(os.path.dirname(__file__), 'admin_ui.html')
    if os.path.exists(html_path):
        with open(html_path) as f:
            return f.read()
    return '<h1>Admin UI file not found at ' + html_path + '</h1>', 404

# --- Company Detail Endpoint ---
@admin_bp.route('/admin/api/company/<int:cid>/detail')
def company_detail(cid):
    token = request.headers.get('X-Admin-Token') or request.cookies.get('admin_token')
    if not token or token != _make_token():
        return jsonify({'error': 'unauthorized'}), 401
    db = get_db()
    co = db.execute('SELECT * FROM companies WHERE id=?', [cid]).fetchone()
    if not co:
        return jsonify({'error': 'not found'}), 404
    company = dict(co)
    props = [dict(r) for r in db.execute(
        'SELECT DISTINCT p.* FROM properties p LEFT JOIN property_companies pc ON p.id=pc.property_id WHERE p.company_id=? OR pc.company_id=?',
        [cid, cid]).fetchall()]
    prop_ids = [p['id'] for p in props]
    result = {'company': company, 'properties': props}
    if prop_ids:
        ph = ','.join('?' * len(prop_ids))
        for t in ['resource_estimates','drill_programs','drill_results','ownership_history','nearby_mines','exploration_programs']:
            result[t] = [dict(r) for r in db.execute(f'SELECT * FROM {t} WHERE property_id IN ({ph})', prop_ids).fetchall()]
    else:
        for t in ['resource_estimates','drill_programs','drill_results','ownership_history','nearby_mines','exploration_programs']:
            result[t] = []
    # Fetch estimate_commodities for these estimates
    re_ids = [r['id'] for r in result.get('resource_estimates', [])]
    if re_ids:
        eph = ','.join('?' * len(re_ids))
        result['estimate_commodities'] = [dict(r) for r in db.execute(f'SELECT * FROM estimate_commodities WHERE estimate_id IN ({eph})', re_ids).fetchall()]
    else:
        result['estimate_commodities'] = []
    return jsonify(result)

@admin_bp.route('/api/v1/companies/<int:cid>')
def api_v1_company_detail(cid):
    db = get_db()
    co = db.execute('SELECT * FROM companies WHERE id=?', [cid]).fetchone()
    if not co:
        return jsonify({'error': 'not found'}), 404
    company = dict(co)
    props = [dict(r) for r in db.execute(
        'SELECT DISTINCT p.* FROM properties p LEFT JOIN property_companies pc ON p.id=pc.property_id WHERE p.company_id=? OR pc.company_id=?',
        [cid, cid]).fetchall()]
    prop_ids = [p['id'] for p in props]
    result = {'company': company, 'properties': props}
    if prop_ids:
        ph = ','.join('?' * len(prop_ids))
        for t in ['resource_estimates','drill_programs','drill_results','ownership_history','nearby_mines','exploration_programs']:
            result[t] = [dict(r) for r in db.execute(f'SELECT * FROM {t} WHERE property_id IN ({ph})', prop_ids).fetchall()]
    else:
        for t in ['resource_estimates','drill_programs','drill_results','ownership_history','nearby_mines','exploration_programs']:
            result[t] = []

    # Fetch estimate_commodities for these estimates
    re_ids = [r['id'] for r in result.get('resource_estimates', [])]
    if re_ids:
        eph = ','.join('?' * len(re_ids))
        result['estimate_commodities'] = [dict(r) for r in db.execute(f'SELECT * FROM estimate_commodities WHERE estimate_id IN ({eph})', re_ids).fetchall()]
    else:
        result['estimate_commodities'] = []

    resp = jsonify(result)
    resp.headers['Access-Control-Allow-Origin'] = '*'
    return resp

# ============= XML IMPORT =============
import xml.etree.ElementTree as ET
import re

@admin_bp.route('/admin/api/import-xml', methods=['POST'])
@require_admin
def admin_import_xml():
    """Import data from XML. Supports full company hierarchy.
    Matches existing records by name/ticker and updates them; creates new ones otherwise."""
    if 'file' not in request.files:
        # Try raw XML in body
        xml_data = request.get_data(as_text=True)
        if not xml_data or not xml_data.strip():
            return jsonify({'error': 'No XML file or data provided'}), 400
    else:
        xml_data = request.files['file'].read().decode('utf-8')

    # Sanitize unescaped ampersands in XML (e.g. "MD&A" -> "MD&amp;A")
    xml_data = re.sub(r'&(?!amp;|lt;|gt;|quot;|apos;|#)', '&amp;', xml_data)

    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError as e:
        return jsonify({'error': f'Invalid XML: {str(e)}'}), 400

    db = get_db()
    stats = {'companies': {'created': 0, 'updated': 0},
             'properties': {'created': 0, 'updated': 0},
             'drill_programs': {'created': 0, 'updated': 0},
             'drill_results': {'created': 0, 'updated': 0},
    'resource_estimates': {
        'pk': 'id',
        'label': 'Resource Estimates',
        'columns': ['id','property_id','commodity','grade_unit','contained_unit',
                    'measured_tonnes','measured_grade','measured_contained',
                    'indicated_tonnes','indicated_grade','indicated_contained',
                    'inferred_tonnes','inferred_grade','inferred_contained',
                    'proven_tonnes','proven_grade','proven_contained',
                    'probable_tonnes','probable_grade','probable_contained',
                    'cutoff_assumptions','estimate_date','prepared_by',
                    'compliance_code','notes','source_url'],
        'required': ['property_id'],
        'fk': {'property_id': 'properties'},
        'display_col': 'commodity',
        'order': 'property_id'
    },
             'exploration_programs': {'created': 0, 'updated': 0},
             'nearby_mines': {'created': 0, 'updated': 0}}
    errors = []

    def get_text(el, tag, default=None):
        child = el.find(tag)
        if child is not None and child.text and child.text.strip():
            return child.text.strip()
        return default

    def get_float(el, tag):
        v = get_text(el, tag)
        if v is None:
            return None
        try:
            return float(v)
        except ValueError:
            return None

    def get_int(el, tag):
        v = get_text(el, tag)
        if v is None:
            return None
        try:
            return int(float(v))
        except ValueError:
            return None

    def upsert_company(el):
        name = get_text(el, 'name')
        ticker = get_text(el, 'ticker')
        if not name:
            return None, 'Company missing name'
        # Match by name OR ticker
        existing = None
        if ticker:
            existing = db.execute('SELECT * FROM companies WHERE ticker=? COLLATE NOCASE', [ticker]).fetchone()
        if not existing:
            existing = db.execute('SELECT * FROM companies WHERE name=? COLLATE NOCASE', [name]).fetchone()

        data = {
            'name': name,
            'ticker': ticker,
            'exchange': get_text(el, 'exchange'),
            'website': get_text(el, 'website'),
            'description': get_text(el, 'description')
        }

        if existing:
            cid = existing['id']
            updates = {k: v for k, v in data.items() if v is not None}
            if updates:
                set_clause = ','.join([f"{k}=?" for k in updates])
                db.execute(f"UPDATE companies SET {set_clause} WHERE id=?", list(updates.values()) + [cid])
            stats['companies']['updated'] += 1
        else:
            cols = [k for k, v in data.items() if v is not None]
            vals = [data[k] for k in cols]
            placeholders = ','.join(['?'] * len(cols))
            cur = db.execute(f"INSERT INTO companies ({','.join(cols)}) VALUES ({placeholders})", vals)
            cid = cur.lastrowid
            stats['companies']['created'] += 1
        return cid, None

    def upsert_property(el, company_id):
        name = get_text(el, 'name')
        if not name:
            return None, 'Property missing name'
        existing = db.execute('SELECT * FROM properties WHERE name=? COLLATE NOCASE AND company_id=?', [name, company_id]).fetchone()

        data = {
            'name': name,
            'company_id': company_id,
            'jurisdiction': get_text(el, 'jurisdiction'),
            'country': get_text(el, 'country'),
            'general_location': get_text(el, 'general_location'),
            'primary_metals': get_text(el, 'primary_metals'),
            'status': get_text(el, 'status'),
            'current_interest': get_text(el, 'current_interest'),
            'size_ha': get_float(el, 'size_ha'),
            'mineralization_type': get_text(el, 'mineralization_type'),
            'latitude': get_float(el, 'latitude'),
            'longitude': get_float(el, 'longitude'),
            'nature_of_interest': get_text(el, 'nature_of_interest'),
            'resource_notes': get_text(el, 'resource_notes'),
            'infrastructure_notes': get_text(el, 'infrastructure_notes'),
            'coord_quality': get_text(el, 'coord_quality'),
            'current_owner': get_text(el, 'current_owner'),
            'royalty_notes': get_text(el, 'royalty_notes')
        }

        if existing:
            pid = existing['id']
            updates = {k: v for k, v in data.items() if v is not None and k != 'company_id'}
            if updates:
                set_clause = ','.join([f"{k}=?" for k in updates])
                db.execute(f"UPDATE properties SET {set_clause} WHERE id=?", list(updates.values()) + [pid])
            stats['properties']['updated'] += 1
        else:
            cols = [k for k, v in data.items() if v is not None]
            vals = [data[k] for k in cols]
            placeholders = ','.join(['?'] * len(cols))
            cur = db.execute(f"INSERT INTO properties ({','.join(cols)}) VALUES ({placeholders})", vals)
            pid = cur.lastrowid
            # Also link in property_companies
            db.execute("INSERT OR IGNORE INTO property_companies (property_id, company_id) VALUES (?,?)",
                       [pid, company_id])
            stats['properties']['created'] += 1
        return pid, None

    def upsert_drill_program(el, property_id):
        program_name = get_text(el, 'program_name')
        year = get_text(el, 'year')
        if not program_name:
            return None, 'Drill program missing program_name'
        existing = db.execute('SELECT * FROM drill_programs WHERE program_name=? COLLATE NOCASE AND property_id=?',
                              [program_name, property_id]).fetchone()
        data = {
            'property_id': property_id,
            'program_name': program_name,
            'year': year,
            'drill_type': get_text(el, 'drill_type'),
            'planned_holes': get_int(el, 'planned_holes'),
            'planned_meters': get_float(el, 'planned_meters'),
            'actual_holes': get_int(el, 'actual_holes'),
            'actual_meters': get_float(el, 'actual_meters'),
            'operator': get_text(el, 'operator'),
            'objectives': get_text(el, 'objectives'),
            'source_url': get_text(el, 'source_url')
        }

        if existing:
            dpid = existing['id']
            updates = {k: v for k, v in data.items() if v is not None and k != 'property_id'}
            if updates:
                set_clause = ','.join([f"{k}=?" for k in updates])
                db.execute(f"UPDATE drill_programs SET {set_clause} WHERE id=?", list(updates.values()) + [dpid])
            stats['drill_programs']['updated'] += 1
        else:
            cols = [k for k, v in data.items() if v is not None]
            vals = [data[k] for k in cols]
            placeholders = ','.join(['?'] * len(cols))
            cur = db.execute(f"INSERT INTO drill_programs ({','.join(cols)}) VALUES ({placeholders})", vals)
            dpid = cur.lastrowid
            stats['drill_programs']['created'] += 1
        return dpid, None

    def insert_drill_result(el, property_id, drill_program_id):
        data = {
            'property_id': property_id,
            'drill_program_id': drill_program_id,
            'hole_id': get_text(el, 'hole_id'),
            'year': get_text(el, 'year'),
            'zone_target': get_text(el, 'zone_target'),
            'from_m': get_float(el, 'from_m'),
            'to_m': get_float(el, 'to_m'),
            'interval_m': get_float(el, 'interval_m'),
            'au_gpt': get_float(el, 'au_gpt'),
            'ag_gpt': get_float(el, 'ag_gpt'),
            'cu_pct': get_float(el, 'cu_pct'),
            'ni_pct': get_float(el, 'ni_pct'),
            'zn_pct': get_float(el, 'zn_pct'),
            'pb_pct': get_float(el, 'pb_pct'),
            'result_type': get_text(el, 'result_type'),
            'highlight': get_text(el, 'highlight'),
            'notes': get_text(el, 'notes'),
            'source_url': get_text(el, 'source_url')
        }
        # Match by hole_id + from_m + to_m + drill_program_id
        hole = get_text(el, 'hole_id')
        from_m = get_float(el, 'from_m')
        to_m = get_float(el, 'to_m')
        existing = None
        if hole and from_m is not None and to_m is not None:
            existing = db.execute(
                'SELECT id FROM drill_results WHERE drill_program_id=? AND hole_id=? AND from_m=? AND to_m=?',
                [drill_program_id, hole, from_m, to_m]).fetchone()

        if existing:
            rid = existing['id']
            updates = {k: v for k, v in data.items() if v is not None and k not in ('property_id', 'drill_program_id')}
            if updates:
                set_clause = ','.join([f"{k}=?" for k in updates])
                db.execute(f"UPDATE drill_results SET {set_clause} WHERE id=?", list(updates.values()) + [rid])
            stats['drill_results']['updated'] += 1
        else:
            cols = [k for k, v in data.items() if v is not None]
            vals = [data[k] for k in cols]
            placeholders = ','.join(['?'] * len(cols))
            db.execute(f"INSERT INTO drill_results ({','.join(cols)}) VALUES ({placeholders})", vals)
            stats['drill_results']['created'] += 1

    def insert_resource_estimate(el, property_id):
        shared = {
            'property_id': property_id,
            'measured_tonnes': get_float(el, 'measured_tonnes'),
            'indicated_tonnes': get_float(el, 'indicated_tonnes'),
            'inferred_tonnes': get_float(el, 'inferred_tonnes'),
            'proven_tonnes': get_float(el, 'proven_tonnes'),
            'probable_tonnes': get_float(el, 'probable_tonnes'),
            'cutoff_assumptions': get_text(el, 'cutoff_assumptions'),
            'estimate_date': get_text(el, 'estimate_date'),
            'prepared_by': get_text(el, 'prepared_by'),
            'compliance_code': get_text(el, 'compliance_code'),
            'notes': get_text(el, 'notes'),
            'source_url': get_text(el, 'source_url'),
        }
        commodities = el.findall('.//commodity')
        if commodities:
            for comm_el in commodities:
                data = dict(shared)
                data['commodity'] = get_text(comm_el, 'name')
                data['grade_unit'] = get_text(comm_el, 'grade_unit')
                data['contained_unit'] = get_text(comm_el, 'contained_unit')
                for fld in ['measured','indicated','inferred','proven','probable']:
                    data[fld+'_grade'] = get_float(comm_el, fld+'_grade')
                    data[fld+'_contained'] = get_float(comm_el, fld+'_contained')
                cols = [k for k, v in data.items() if v is not None]
                vals = [data[k] for k in cols]
                if cols:
                    placeholders = ','.join(['?'] * len(cols))
                    db.execute(f"INSERT INTO resource_estimates ({','.join(cols)}) VALUES ({placeholders})", vals)
                    stats['resource_estimates']['created'] += 1
        else:
            data = dict(shared)
            data['commodity'] = get_text(el, 'commodity') or get_text(el, 'name')
            data['grade_unit'] = get_text(el, 'grade_unit')
            data['contained_unit'] = get_text(el, 'contained_unit')
            for fld in ['measured','indicated','inferred','proven','probable']:
                data[fld+'_grade'] = get_float(el, fld+'_grade')
                data[fld+'_contained'] = get_float(el, fld+'_contained')
            cols = [k for k, v in data.items() if v is not None]
            vals = [data[k] for k in cols]
            if cols:
                placeholders = ','.join(['?'] * len(cols))
                db.execute(f"INSERT INTO resource_estimates ({','.join(cols)}) VALUES ({placeholders})", vals)
                stats['resource_estimates']['created'] += 1

    def insert_ownership(el, property_id):
        data = {
            'property_id': property_id,
            'event_type': get_text(el, 'event_type'),
            'date_or_period': get_text(el, 'date_or_period'),
            'counterparties': get_text(el, 'counterparties'),
            'terms': get_text(el, 'terms'),
            'interest_details': get_text(el, 'interest_details'),
            'notes': get_text(el, 'notes'),
            'source_url': get_text(el, 'source_url')
        }
        cols = [k for k, v in data.items() if v is not None]
        vals = [data[k] for k in cols]
        if cols:
            placeholders = ','.join(['?'] * len(cols))
            db.execute(f"INSERT INTO ownership_history ({','.join(cols)}) VALUES ({placeholders})", vals)
            stats['ownership_history']['created'] += 1

    def insert_exploration(el, property_id):
        data = {
            'property_id': property_id,
            'program_type': get_text(el, 'program_type'),
            'year': get_text(el, 'year'),
            'description': get_text(el, 'description'),
            'results_summary': get_text(el, 'results_summary'),
            'source_url': get_text(el, 'source_url')
        }
        cols = [k for k, v in data.items() if v is not None]
        vals = [data[k] for k in cols]
        if cols:
            placeholders = ','.join(['?'] * len(cols))
            db.execute(f"INSERT INTO exploration_programs ({','.join(cols)}) VALUES ({placeholders})", vals)
            stats['exploration_programs']['created'] += 1

    def insert_nearby_mine(el, property_id):
        data = {
            'property_id': property_id,
            'mine_name': get_text(el, 'mine_name'),
            'operator': get_text(el, 'operator'),
            'distance_km': get_float(el, 'distance_km'),
            'status': get_text(el, 'status'),
            'commodity': get_text(el, 'commodity'),
            'notes': get_text(el, 'notes')
        }
        cols = [k for k, v in data.items() if v is not None]
        vals = [data[k] for k in cols]
        if cols:
            placeholders = ','.join(['?'] * len(cols))
            db.execute(f"INSERT INTO nearby_mines ({','.join(cols)}) VALUES ({placeholders})", vals)
            stats['nearby_mines']['created'] += 1

    try:
        for company_el in root.findall('.//company'):
            cid, err = upsert_company(company_el)
            if err:
                errors.append(err)
                continue

            for prop_el in company_el.findall('.//property'):
                pid, err = upsert_property(prop_el, cid)
                if err:
                    errors.append(err)
                    continue

                for dp_el in prop_el.findall('.//drill_program'):
                    dpid, err = upsert_drill_program(dp_el, pid)
                    if err:
                        errors.append(err)
                        continue
                    for dr_el in dp_el.findall('.//drill_result'):
                        try:
                            insert_drill_result(dr_el, pid, dpid)
                        except Exception as e:
                            errors.append(f'Drill result error: {str(e)}')

                for re_el in prop_el.findall('.//resource_estimate'):
                    try:
                        insert_resource_estimate(re_el, pid)
                    except Exception as e:
                        errors.append(f'Resource estimate error: {str(e)}')

                for oh_el in prop_el.findall('.//ownership_record') + prop_el.findall('.//ownership_event'):
                    try:
                        insert_ownership(oh_el, pid)
                    except Exception as e:
                        errors.append(f'Ownership error: {str(e)}')

                for ep_el in prop_el.findall('.//exploration_program'):
                    try:
                        insert_exploration(ep_el, pid)
                    except Exception as e:
                        errors.append(f'Exploration error: {str(e)}')

                for nm_el in prop_el.findall('.//nearby_mine'):
                    try:
                        insert_nearby_mine(nm_el, pid)
                    except Exception as e:
                        errors.append(f'Nearby mine error: {str(e)}')

        db.commit()
    except Exception as e:
        db.rollback()
        return jsonify({'error': f'Import failed: {str(e)}'}), 500

    return jsonify({'ok': True, 'stats': stats, 'errors': errors})


@admin_bp.route('/admin/api/xml-template')
def xml_template():
    xml = '''<?xml version="1.0" encoding="UTF-8"?>
<mineportal>
  <company>
    <name>Company Name</name>
    <ticker>TICK</ticker>
    <exchange>TSX</exchange>
    <website>https://example.com</website>
    <description>Company description</description>
    <property>
      <name>Property Name</name>
      <jurisdiction>Ontario, Canada</jurisdiction>
      <country>Canada</country>
      <primary_metals>Gold</primary_metals>
      <status>Exploration</status>
      <current_interest>100%</current_interest>
      <size_ha>1500</size_ha>
      <latitude>48.5</latitude>
      <longitude>-80.1</longitude>
      <drill_program>
        <program_name>2024 Diamond Drilling</program_name>
        <year>2024</year>
        <drill_type>Diamond</drill_type>
        <planned_holes>10</planned_holes>
        <planned_meters>2000</planned_meters>
        <actual_holes>8</actual_holes>
        <actual_meters>1800</actual_meters>
        <operator>Drill Co</operator>
        <drill_result>
          <hole_id>DDH-001</hole_id>
          <from_m>45.0</from_m>
          <to_m>52.5</to_m>
          <interval_m>7.5</interval_m>
          <zone_target>Main Zone</zone_target>
          <au_gpt>3.45</au_gpt>
          <ag_gpt>12.1</ag_gpt>
          <result_type>Assay</result_type>
        </drill_result>
      </drill_program>
      <resource_estimate>
        <category>Indicated</category>
        <tonnes_mt>2.5</tonnes_mt>
        <grade_au_gpt>2.1</grade_au_gpt>
        <contained_au_moz>0.169</contained_au_moz>
        <cutoff_assumptions>0.5 g/t Au</cutoff_assumptions>
      </resource_estimate>
      <ownership_record>
        <event_type>Staking</event_type>
        <date_or_period>2020</date_or_period>
        <counterparties>Company Name</counterparties>
        <terms>Original staking</terms>
      </ownership_record>
      <exploration_program>
        <program_type>Soil sampling</program_type>
        <year>2023</year>
        <description>Soil sampling program</description>
        <results_summary>Results summary</results_summary>
      </exploration_program>
      <nearby_mine>
        <mine_name>Nearby Mine</mine_name>
        <operator>Operator</operator>
        <distance_km>15</distance_km>
        <status>Production</status>
        <commodity>Gold</commodity>
      </nearby_mine>
    </property>
  </company>
</mineportal>'''
    resp = make_response(xml)
    resp.headers['Content-Type'] = 'application/xml'
    resp.headers['Content-Disposition'] = 'attachment; filename=mineportal_template.xml'
    return resp

# ============ MTP_INVALIDATE_HOOK_BEGIN ============
try:
    from mtp_notify import notify as _mtp_notify
except Exception as _e:
    _mtp_notify = lambda *a, **kw: None  # noqa: E731

@admin_bp.after_request
def _mtp_invalidate_after(response):
    """Fire cache-invalidation webhook after every successful admin write."""
    try:
        from flask import request as _req
        if _req.method in ("POST", "PUT", "DELETE", "PATCH"):
            if 200 <= response.status_code < 300:
                ep = _req.endpoint or ""
                # Limit to admin.* endpoints (the blueprint's routes).
                if ep.startswith("admin."):
                    # Skip auth endpoints (login/logout) which don't change data.
                    if ep in ("admin.admin_login", "admin.admin_logout"):
                        return response
                    table = (_req.view_args or {}).get("table")
                    rid = (_req.view_args or {}).get("rid")
                    _mtp_notify(ep, table=table, rid=rid)
    except Exception:
        pass
    return response
# ============ MTP_INVALIDATE_HOOK_END ============
