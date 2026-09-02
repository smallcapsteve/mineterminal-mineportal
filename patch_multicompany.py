import re

with open('/opt/mineportal/app.py', 'r') as f:
    text = f.read()

original = text

# --- 1. /api/companies: use junction table for property counts ---
old_companies = """    FROM companies c
    LEFT JOIN properties p ON p.company_id = c.id
    LEFT JOIN drill_programs dp ON dp.property_id = p.id
    LEFT JOIN drill_results dr ON dr.property_id = p.id"""

new_companies = """    FROM companies c
    LEFT JOIN property_companies pc ON pc.company_id = c.id
    LEFT JOIN properties p ON p.id = pc.property_id
    LEFT JOIN drill_programs dp ON dp.property_id = p.id
    LEFT JOIN drill_results dr ON dr.property_id = p.id"""

if old_companies in text:
    text = text.replace(old_companies, new_companies, 1)
    print("1. Patched /api/companies to use junction table")
else:
    print("1. SKIP - /api/companies already patched or not found")

# --- 2. /api/companies/<cid>: use junction table for property list ---
old_company_props = '    props = db.execute("SELECT * FROM properties WHERE company_id=? ORDER BY name", (cid,)).fetchall()'
new_company_props = '    props = db.execute("SELECT p.* FROM properties p JOIN property_companies pc ON pc.property_id = p.id WHERE pc.company_id=? ORDER BY p.name", (cid,)).fetchall()'

if old_company_props in text:
    text = text.replace(old_company_props, new_company_props, 1)
    print("2. Patched /api/companies/<cid> to use junction table")
else:
    print("2. SKIP - /api/companies/<cid> already patched or not found")

# --- 3. /api/properties/<pid>: add linked_companies to response ---
old_return = """    return jsonify({
        "property": dict(prop),
        "drill_programs": [dict(r) for r in programs],
        "drill_results": [dict(r) for r in results],
        "resource_estimates": [dict(r) for r in resources],
        "nearby_mines": [dict(r) for r in nearby],
        "ownership_history": [dict(r) for r in ownership],
        "exploration_programs": [dict(r) for r in exploration],
    })"""

new_return = """    linked_companies = db.execute("SELECT c.id, c.ticker, c.name FROM companies c JOIN property_companies pc ON pc.company_id = c.id WHERE pc.property_id=? ORDER BY c.ticker", (pid,)).fetchall()
    return jsonify({
        "property": dict(prop),
        "drill_programs": [dict(r) for r in programs],
        "drill_results": [dict(r) for r in results],
        "resource_estimates": [dict(r) for r in resources],
        "nearby_mines": [dict(r) for r in nearby],
        "ownership_history": [dict(r) for r in ownership],
        "exploration_programs": [dict(r) for r in exploration],
        "linked_companies": [dict(r) for r in linked_companies],
    })"""

if old_return in text:
    text = text.replace(old_return, new_return, 1)
    print("3. Patched /api/properties/<pid> to return linked_companies")
else:
    print("3. SKIP - return block not found (checking whitespace...)")
    # Try to find it with flexible whitespace
    idx = text.find('"exploration_programs": [dict(r) for r in exploration],')
    if idx > 0:
        # Find the closing })
        close_idx = text.find('    })', idx)
        if close_idx > 0:
            insert_point = idx + len('"exploration_programs": [dict(r) for r in exploration],')
            # Insert linked_companies query before the return and add to dict
            lc_query = '\n    linked_companies = db.execute("SELECT c.id, c.ticker, c.name FROM companies c JOIN property_companies pc ON pc.company_id = c.id WHERE pc.property_id=? ORDER BY c.ticker", (pid,)).fetchall()'
            # Add to the return dict
            old_exploration_line = '        "exploration_programs": [dict(r) for r in exploration],\n    })'
            new_exploration_line = '        "exploration_programs": [dict(r) for r in exploration],\n        "linked_companies": [dict(r) for r in linked_companies],\n    })'
            text = text.replace(old_exploration_line, new_exploration_line, 1)
            # Insert the query before "return jsonify"
            text = text.replace('    return jsonify({\n        "property": dict(prop),', lc_query + '\n    return jsonify({\n        "property": dict(prop),', 1)
            print("3. Patched via fallback method")

# --- 4. Property detail JS: show multiple company breadcrumbs ---
old_breadcrumb = """<a href="#" onclick="event.preventDefault();showCompany(${p.company_id})" style="color:var(--text2);font-size:13px">${p.ticker}</a>"""

new_breadcrumb = """${(data.linked_companies||[{id:p.company_id,ticker:p.ticker}]).map(lc=>'<a href="#" onclick="event.preventDefault();showCompany('+lc.id+')" style="color:var(--text2);font-size:13px">'+lc.ticker+'</a>').join(' <span style="color:var(--text2)">/</span> ')}"""

if old_breadcrumb in text:
    text = text.replace(old_breadcrumb, new_breadcrumb, 1)
    print("4. Patched property detail breadcrumb for multi-company")
else:
    print("4. SKIP - breadcrumb not found")

if text != original:
    with open('/opt/mineportal/app.py', 'w') as f:
        f.write(text)
    print("\nAll patches written to app.py")
else:
    print("\nNo changes made")
