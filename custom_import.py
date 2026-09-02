#!/usr/bin/env python3
"""
Custom XML importer for MineTerminal portal.
Handles non-MTP-namespace XML files with ad-hoc structures:
  - Arctic Fox: <mine_terminal> root
  - Appia: <MineTerminalData> root
  - Blue Lagoon: <mine_terminal_data> root

Wipes existing company data before re-importing.
"""
import sqlite3, sys, os
from lxml import etree

DB_PATH = "/opt/mineportal/mining_portal.db"

def txt(el, tag, default=""):
    """Get text of first child element matching tag."""
    if el is None:
        return default
    ch = el.find(tag)
    if ch is not None and ch.text:
        return ch.text.strip()
    return default

def num(el, tag, default=None):
    """Get float from child element text."""
    v = txt(el, tag, "")
    if v:
        try:
            return float(v.replace(",","").replace(">",""))
        except:
            pass
    return default

def wipe_company(db, ticker):
    """Delete all data for a company by ticker."""
    cur = db.cursor()
    cur.execute("SELECT id FROM companies WHERE ticker=?", (ticker,))
    row = cur.fetchone()
    if not row:
        print(f"  Company {ticker} not found in DB, nothing to wipe.")
        return None
    cid = row[0]
    cur.execute("SELECT id FROM properties WHERE company_id=?", (cid,))
    pids = [r[0] for r in cur.fetchall()]
    for pid in pids:
        for tbl in ["drill_results","resource_estimates","ownership_history",
                     "drill_programs","nearby_mines"]:
            cur.execute(f"DELETE FROM {tbl} WHERE property_id=?", (pid,))
    cur.execute("DELETE FROM properties WHERE company_id=?", (cid,))
    cur.execute("DELETE FROM sources WHERE company_id=?", (cid,))
    cur.execute("DELETE FROM companies WHERE id=?", (cid,))
    db.commit()
    print(f"  Wiped company {ticker} (id={cid}), {len(pids)} properties removed.")
    return cid

def ensure_columns(db):
    """Add any missing columns to existing tables."""
    cur = db.cursor()
    # Check drill_results columns
    cur.execute("PRAGMA table_info(drill_results)")
    existing = {r[1] for r in cur.fetchall()}
    extras = {
        "mo_pct": "REAL", "li_pct": "REAL", "treo_pct": "REAL",
        "u3o8_lbs_per_ton": "REAL", "tree_lbs_per_ton": "REAL",
        "nb2o5_pct": "REAL", "tho2_pct": "REAL", "zro2_pct": "REAL",
        "p2o5_pct": "REAL"
    }
    for col, typ in extras.items():
        if col not in existing:
            cur.execute(f"ALTER TABLE drill_results ADD COLUMN {col} {typ}")
            print(f"  Added drill_results.{col}")

    # Check resource_estimates columns
    cur.execute("PRAGMA table_info(resource_estimates)")
    existing = {r[1] for r in cur.fetchall()}
    re_extras = {
        "grade_mo_pct": "REAL", "grade_treo_pct": "REAL",
        "grade_u3o8_lbs_per_ton": "REAL", "grade_tree_lbs_per_ton": "REAL",
        "contained_mo_mlbs": "REAL", "contained_u3o8_mlbs": "REAL",
        "contained_tree_mlbs": "REAL", "other_grades": "TEXT",
        "other_contained": "TEXT"
    }
    for col, typ in re_extras.items():
        if col not in existing:
            cur.execute(f"ALTER TABLE resource_estimates ADD COLUMN {col} {typ}")
            print(f"  Added resource_estimates.{col}")
    db.commit()

# ──────────────────────────────────────────
# ARCTIC FOX IMPORTER
# ──────────────────────────────────────────
def import_arctic_fox(db, xml_path):
    print("\n=== Importing Arctic Fox ===")
    tree = etree.parse(xml_path)
    root = tree.getroot()

    co = root.find("company")
    name = txt(co, "name")
    ticker_el = co.find(".//tickers/ticker[@exchange='CSE']")
    ticker = ticker_el.text.strip() if ticker_el is not None else "AFX"
    website = ""
    desc = txt(co, "business_description")

    wipe_company(db, ticker)

    cur = db.cursor()
    cur.execute("INSERT INTO companies(ticker,name,exchange,description,website) VALUES(?,?,?,?,?)",
                (ticker, name, "CSE", desc, website))
    cid = cur.lastrowid
    print(f"  Created company: {name} ({ticker}), id={cid}")

    for prop in root.findall(".//properties/property"):
        prop_name = txt(prop, "name")
        jur_el = prop.find("jurisdiction")
        jurisdiction = txt(jur_el, "province_state") if jur_el is not None else ""
        country = txt(jur_el, "country") if jur_el is not None else "Canada"
        location = txt(prop, "location_description") or txt(prop, "region")

        size_ha = num(prop, ".//tenure/area_hectares")
        lat = num(prop, ".//coordinates/latitude")
        lon = num(prop, ".//coordinates/longitude")

        commodities = []
        for c in prop.findall(".//commodities/commodity"):
            if c.text:
                commodities.append(c.text.strip())
        primary_metals = ", ".join(commodities)

        status = txt(prop, "stage") or txt(prop, "status_note", "")
        deposit = txt(prop, "deposit_type")

        own = prop.find("ownership")
        interest_type = txt(own, "interest_type") if own is not None else ""
        ownership_pct = txt(own, "ownership_pct") if own is not None else ""
        current_interest = f"{ownership_pct}%" if ownership_pct else ""

        cur.execute("""INSERT INTO properties(company_id,name,jurisdiction,country,general_location,
                       size_ha,current_interest,nature_of_interest,mineralization_type,primary_metals,
                       status,latitude,longitude,coord_quality)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (cid, prop_name, jurisdiction, country, location,
                     size_ha, current_interest, interest_type, deposit, primary_metals,
                     status, lat, lon, "Approximate"))
        pid = cur.lastrowid
        print(f"    Property: {prop_name} (id={pid})")

        # Drill results
        for dr in prop.findall(".//drill_results/drill_result"):
            hole_id = txt(dr, "hole_id")
            from_m = num(dr, "from_m")
            to_m = num(dr, "to_m")
            interval_m = num(dr, "interval_m")
            result_type = txt(dr, "result_type")
            notes = txt(dr, "notes")
            year = txt(dr, "date_reported", "")[:4] if txt(dr, "date_reported") else ""

            assays = dr.find("assays")
            cu_pct = num(assays, "cu_pct") if assays is not None else None
            mo_pct = num(assays, "mo_pct") if assays is not None else None

            cur.execute("""INSERT INTO drill_results(property_id,hole_id,year,from_m,to_m,interval_m,
                           cu_pct,mo_pct,result_type,notes) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        (pid, hole_id, year, from_m, to_m, interval_m,
                         cu_pct, mo_pct, result_type, notes))

        # Historical sampling (Shipshaw)
        for sr in prop.findall(".//historical_sampling/sample_result"):
            interval_m = num(sr, "interval_m")
            other = txt(sr, "other_assays")
            notes = txt(sr, "notes")
            cur.execute("""INSERT INTO drill_results(property_id,hole_id,year,interval_m,
                           other_assays,result_type,notes) VALUES(?,?,?,?,?,?,?)""",
                        (pid, "Historical", "", interval_m, other, "historical", notes))

    db.commit()
    print(f"  Arctic Fox import complete.")

# ──────────────────────────────────────────
# BLUE LAGOON IMPORTER
# ──────────────────────────────────────────
def import_blue_lagoon(db, xml_path):
    print("\n=== Importing Blue Lagoon ===")
    tree = etree.parse(xml_path)
    root = tree.getroot()

    co = root.find("company")
    name = txt(co, "name")
    ticker_el = co.find(".//tickers/ticker[@exchange='CSE']")
    ticker = ticker_el.text.strip() if ticker_el is not None else "BLLG"
    website = txt(co, "website")
    desc = txt(co, "primary_focus")

    wipe_company(db, ticker)

    cur = db.cursor()
    cur.execute("INSERT INTO companies(ticker,name,exchange,description,website) VALUES(?,?,?,?,?)",
                (ticker, name, "CSE", desc, website))
    cid = cur.lastrowid
    print(f"  Created company: {name} ({ticker}), id={cid}")

    for prop in co.findall(".//properties/property"):
        prop_name = txt(prop, "property_name")
        jur = prop.find("jurisdiction")
        jurisdiction = txt(jur, "province_state") if jur is not None else ""
        country = txt(jur, "country") if jur is not None else "Canada"

        loc = prop.find("location")
        location = txt(loc, "description") if loc is not None else ""
        lat = num(loc, "latitude") if loc is not None else None
        lon = num(loc, "longitude") if loc is not None else None

        lp = prop.find("land_package")
        size_ha = num(lp, "area_hectares") if lp is not None else None

        commodities = []
        comm = prop.find("commodities")
        if comm is not None:
            p = txt(comm, "primary")
            if p: commodities.append(p)
            for s in comm.findall("secondary"):
                if s.text: commodities.append(s.text.strip())
        primary_metals = ", ".join(commodities)

        status = txt(prop, "status")
        dep = prop.find("deposit_type")
        deposit = txt(dep, "primary") if dep is not None else ""

        own = prop.find("ownership")
        ownership_pct = txt(own, "ownership_percent") if own is not None else ""
        interest_type = txt(own, "interest_type") if own is not None else ""
        current_interest = f"{ownership_pct}%" if ownership_pct else ""

        infra = prop.find("infrastructure")
        infra_notes = ""
        if infra is not None:
            parts = []
            for ch in infra:
                if ch.text:
                    parts.append(f"{ch.tag}: {ch.text.strip()}")
            infra_notes = "; ".join(parts)

        cur.execute("""INSERT INTO properties(company_id,name,jurisdiction,country,general_location,
                       size_ha,current_interest,nature_of_interest,mineralization_type,primary_metals,
                       status,latitude,longitude,coord_quality,infrastructure_notes)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (cid, prop_name, jurisdiction, country, location,
                     size_ha, current_interest, interest_type, deposit, primary_metals,
                     status, lat, lon, "Approximate", infra_notes))
        pid = cur.lastrowid
        print(f"    Property: {prop_name} (id={pid})")

        # Drill programs
        for prog in prop.findall(".//exploration_programs/program"):
            year = txt(prog, "year")
            prog_name = txt(prog, "program_name")
            operator = txt(prog, "operator")
            drill_type = txt(prog, "program_type")
            planned_m = num(prog, "planned_metres")
            actual_m = num(prog, "actual_metres")
            actual_h = num(prog, "actual_holes")

            cur.execute("""INSERT INTO drill_programs(property_id,year,program_name,operator,
                           drill_type,planned_meters,actual_meters,actual_holes)
                           VALUES(?,?,?,?,?,?,?,?)""",
                        (pid, year, prog_name, operator, drill_type,
                         planned_m, actual_m, int(actual_h) if actual_h else None))

        # Drill results
        for dr in prop.findall(".//drill_results/drill_result"):
            hole_id = txt(dr, "hole_id")
            year = txt(dr, "drill_year")
            zone = txt(dr, "target_zone")
            from_m = num(dr, "from_m")
            to_m = num(dr, "to_m")
            interval_m = num(dr, "interval_m")
            result_type = txt(dr, "result_type")
            notes = txt(dr, "notes")

            assays = dr.find("assays")
            au_gpt = num(assays, "au_gpt") if assays is not None else None
            ag_gpt = num(assays, "ag_gpt") if assays is not None else None
            cu_pct = num(assays, "cu_pct") if assays is not None else None

            cur.execute("""INSERT INTO drill_results(property_id,hole_id,year,zone_target,
                           from_m,to_m,interval_m,au_gpt,ag_gpt,cu_pct,result_type,notes)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (pid, hole_id, year, zone, from_m, to_m, interval_m,
                         au_gpt, ag_gpt, cu_pct, result_type, notes))

        # Resource estimates
        for re in prop.findall(".//resources/resource_estimate"):
            est_date = txt(re, "effective_date")
            compliance = txt(re, "reporting_standard")
            cutoff = txt(re, "cutoff_grade")
            constraint = txt(re, "constraint")
            re_notes = txt(re, "notes")
            cutoff_full = f"{cutoff}; {constraint}" if constraint else cutoff

            for cat in re.findall(".//categories/category"):
                classification = txt(cat, "classification")
                tonnes_mt = num(cat, "tonnage_mt")
                subtype = txt(cat, "subtype")

                category_str = classification
                if subtype:
                    category_str = f"{classification} ({subtype})"

                # Parse grades
                grade_au = None; grade_ag = None; grade_cu = None; grade_cueq = None
                grade_mo = None
                other_grades_parts = []
                for g in cat.findall(".//grades/grade"):
                    commodity = g.get("commodity", "")
                    unit = g.get("unit", "")
                    val = None
                    try:
                        val = float(g.text.strip())
                    except:
                        pass
                    if commodity == "Gold" and "g/t" in unit:
                        grade_au = val
                    elif commodity == "Silver" and "g/t" in unit:
                        grade_ag = val
                    elif commodity == "Copper" and "CuEq" in unit:
                        grade_cueq = val
                    elif commodity == "Copper" and "%" in unit:
                        grade_cu = val
                    elif commodity == "Molybdenum" and "%" in unit:
                        grade_mo = val
                    else:
                        other_grades_parts.append(f"{commodity}: {val} {unit}")

                # Parse contained metals
                cont_au = None; cont_ag = None; cont_cu = None; cont_mo = None
                other_contained_parts = []
                for m in cat.findall(".//contained_metals/metal"):
                    commodity = m.get("commodity", "")
                    unit = m.get("unit", "")
                    val = None
                    try:
                        val = float(m.text.strip())
                    except:
                        pass
                    if commodity == "Gold" and "Moz" in unit:
                        cont_au = val
                    elif commodity == "Silver" and "Moz" in unit:
                        cont_ag = val
                    elif commodity == "Copper" and "Mlbs" in unit:
                        cont_cu = val
                    elif commodity == "Molybdenum" and "Mlbs" in unit:
                        cont_mo = val
                    else:
                        other_contained_parts.append(f"{commodity}: {val} {unit}")

                other_grades = "; ".join(other_grades_parts) if other_grades_parts else None
                other_contained = "; ".join(other_contained_parts) if other_contained_parts else None

                cur.execute("""INSERT INTO resource_estimates(property_id,estimate_date,category,
                               tonnes_mt,grade_au_gpt,grade_ag_gpt,grade_cu_pct,grade_cueq_pct,
                               grade_mo_pct,contained_au_moz,contained_ag_moz,contained_cu_mlbs,
                               contained_mo_mlbs,other_grades,other_contained,
                               cutoff_assumptions,compliance_code,notes)
                               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (pid, est_date, category_str, tonnes_mt,
                             grade_au, grade_ag, grade_cu, grade_cueq, grade_mo,
                             cont_au, cont_ag, cont_cu, cont_mo,
                             other_grades, other_contained,
                             cutoff_full, compliance, re_notes))

    db.commit()
    print(f"  Blue Lagoon import complete.")

# ──────────────────────────────────────────
# APPIA IMPORTER
# ──────────────────────────────────────────
def import_appia(db, xml_path):
    print("\n=== Importing Appia ===")
    tree = etree.parse(xml_path)
    root = tree.getroot()

    co = root.find("company")
    name = txt(co, "name")
    ticker = txt(co, "primary_ticker", "API")
    exchange = txt(co, "primary_exchange", "CSE")
    website = txt(co, "website")
    desc = txt(co, "industry")

    wipe_company(db, ticker)

    cur = db.cursor()
    cur.execute("INSERT INTO companies(ticker,name,exchange,description,website) VALUES(?,?,?,?,?)",
                (ticker, name, exchange, desc, website))
    cid = cur.lastrowid
    print(f"  Created company: {name} ({ticker}), id={cid}")

    for prop in root.findall(".//properties/property"):
        ident = prop.find("identification")
        prop_name = prop.get("name", "") or (txt(ident, "property_name") if ident else "")
        if not prop_name and ident is not None:
            prop_name = txt(ident, "property_name")

        jurisdiction = txt(ident, "jurisdiction") if ident is not None else ""
        country = txt(ident, "country") if ident is not None else "Canada"
        location = txt(ident, "general_location") if ident is not None else ""
        commodities_str = txt(ident, "commodities") if ident is not None else ""

        size_ha_text = ""
        if ident is not None:
            area_el = ident.find("area_ha")
            if area_el is not None and area_el.text:
                try:
                    size_ha = float(area_el.text.strip().replace(",",""))
                except:
                    size_ha = None
            else:
                size_ha = None
        else:
            size_ha = None

        coords = prop.find("coordinates")
        lat = None; lon = None
        if coords is not None:
            lat_el = coords.find("latitude")
            if lat_el is not None and lat_el.text:
                try: lat = float(lat_el.text.strip())
                except: pass
            lon_el = coords.find("longitude")
            if lon_el is not None and lon_el.text:
                try: lon = float(lon_el.text.strip())
                except: pass
            # Try geolocation sub
            if lat is None:
                geo = coords.find("geolocation")
                if geo is not None:
                    lat_el2 = geo.find("latitude")
                    if lat_el2 is not None and lat_el2.text:
                        try: lat = float(lat_el2.text.strip())
                        except: pass
                    lon_el2 = geo.find("longitude")
                    if lon_el2 is not None and lon_el2.text:
                        try: lon = float(lon_el2.text.strip())
                        except: pass

        status = txt(ident, "current_status") if ident is not None else ""
        mineralization = txt(prop, "mineralization_notes")

        own = prop.find("ownership")
        ownership_type = txt(own, "current_ownership_type") if own is not None else ""

        cur.execute("""INSERT INTO properties(company_id,name,jurisdiction,country,general_location,
                       size_ha,current_interest,nature_of_interest,mineralization_type,primary_metals,
                       status,latitude,longitude,coord_quality,resource_notes)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (cid, prop_name, jurisdiction, country, location,
                     size_ha, ownership_type, "", mineralization, commodities_str,
                     status, lat, lon, "Approximate", ""))
        pid = cur.lastrowid
        print(f"    Property: {prop_name} (id={pid})")

        # Drill programs
        for prog in prop.findall(".//drill_programs/drill_program"):
            year = txt(prog, "program_year")
            target = txt(prog, "target_zone")
            operator = txt(prog, "operator")
            drill_type = txt(prog, "drill_type")
            completed_h_text = txt(prog, "completed_holes")
            completed_h = None
            if completed_h_text:
                try: completed_h = int(completed_h_text)
                except: pass

            completed_m_el = prog.find("completed_m")
            completed_m = None
            if completed_m_el is not None and completed_m_el.text:
                try: completed_m = float(completed_m_el.text.strip().replace(",",""))
                except: pass

            summary = txt(prog, "program_summary")

            cur.execute("""INSERT INTO drill_programs(property_id,year,program_name,operator,
                           drill_type,actual_meters,actual_holes,objectives)
                           VALUES(?,?,?,?,?,?,?,?)""",
                        (pid, year, target, operator, drill_type,
                         completed_m, completed_h, summary))

        # Drill results
        dr_count = 0
        for dr in prop.findall(".//drill_results/drill_result"):
            hole_id = txt(dr, "hole_id")
            year = txt(dr, "year")
            zone = txt(dr, "zone")

            from_m_el = dr.find("from_m")
            from_m = None
            if from_m_el is not None and from_m_el.text:
                try: from_m = float(from_m_el.text.strip())
                except: pass

            to_m_el = dr.find("to_m")
            to_m = None
            if to_m_el is not None and to_m_el.text:
                try: to_m = float(to_m_el.text.strip())
                except: pass

            interval_m_el = dr.find("interval_m")
            interval_m = None
            if interval_m_el is not None and interval_m_el.text:
                try: interval_m = float(interval_m_el.text.strip())
                except: pass

            result_type = txt(dr, "interval_type")
            notes = txt(dr, "notes")

            # Parse assays - Appia uses <assay commodity="TREO" unit="%">
            treo_pct = None
            other_assays_parts = []
            for a in dr.findall(".//assays/assay"):
                commodity = a.get("commodity", "")
                unit = a.get("unit", "")
                val = None
                if a.text:
                    try: val = float(a.text.strip())
                    except: pass
                if commodity.upper() == "TREO" and "%" in unit:
                    treo_pct = val
                else:
                    other_assays_parts.append(f"{commodity}: {val}{unit}")

            # Also check for direct element assays (Arctic Fox style within Appia)
            assays_el = dr.find("assays")
            cu_pct = None
            if assays_el is not None:
                cu_el = assays_el.find("cu_pct")
                if cu_el is not None and cu_el.text:
                    try: cu_pct = float(cu_el.text.strip())
                    except: pass

            other_assays = "; ".join(other_assays_parts) if other_assays_parts else None

            cur.execute("""INSERT INTO drill_results(property_id,hole_id,year,zone_target,
                           from_m,to_m,interval_m,treo_pct,cu_pct,other_assays,result_type,notes)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (pid, hole_id, year, zone, from_m, to_m, interval_m,
                         treo_pct, cu_pct, other_assays, result_type, notes))
            dr_count += 1

        if dr_count > 0:
            print(f"      {dr_count} drill results")

        # Resource estimates
        for re_el in prop.findall(".//resource_estimates/resource_estimate"):
            zone = txt(re_el, "zone")
            est_date = txt(re_el, "estimate_date")
            res_status = txt(re_el, "resource_status")
            category = txt(re_el, "category")
            grade_text = txt(re_el, "grade")
            contained_text = txt(re_el, "contained_metal")
            re_notes = txt(re_el, "notes")

            # Skip empty/placeholder resource estimates
            if not category and not grade_text and "No" in res_status:
                continue

            # Try to parse tonnes from notes
            tonnes_mt = None
            if re_notes:
                import re
                mt_match = re.search(r'([\d.]+)\s*Mt', re_notes)
                if mt_match:
                    try: tonnes_mt = float(mt_match.group(1))
                    except: pass

            cat_str = category
            if zone and zone != "Project-wide / WRCB + multiple zones":
                cat_str = f"{category} ({zone})" if category else zone

            cur.execute("""INSERT INTO resource_estimates(property_id,estimate_date,category,
                           tonnes_mt,other_grades,other_contained,
                           compliance_code,notes)
                           VALUES(?,?,?,?,?,?,?,?)""",
                        (pid, est_date, cat_str, tonnes_mt,
                         grade_text, contained_text,
                         res_status, re_notes))

        # Nearby operations
        for nb in prop.findall(".//nearby_operations/nearby_operation"):
            nb_name = txt(nb, "nearby_name")
            owner = txt(nb, "owner_operator")
            distance_el = nb.find("distance_km")
            distance = ""
            if distance_el is not None and distance_el.text:
                distance = f"{distance_el.text.strip()} km {txt(nb, 'direction')}"
            ntype = txt(nb, "type")

            cur.execute("""INSERT INTO nearby_mines(property_id,nearby_name,owner_operator,
                           distance,commodity,relevance) VALUES(?,?,?,?,?,?)""",
                        (pid, nb_name, owner, distance, ntype, txt(nb, "notes")))

    db.commit()
    print(f"  Appia import complete.")

# ──────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────
def main():
    if len(sys.argv) < 2:
        print("Usage: python3 custom_import.py <xml_file> [<xml_file2> ...]")
        print("  Supported: arctic_fox, appia, blue_lagoon XML files")
        sys.exit(1)

    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA foreign_keys=ON")
    ensure_columns(db)

    for xml_path in sys.argv[1:]:
        if not os.path.exists(xml_path):
            print(f"ERROR: File not found: {xml_path}")
            continue

        tree = etree.parse(xml_path)
        root = tree.getroot()
        tag = root.tag.lower()

        if tag == "mine_terminal":
            import_arctic_fox(db, xml_path)
        elif tag == "mineterminaldata":
            import_appia(db, xml_path)
        elif tag == "mine_terminal_data":
            import_blue_lagoon(db, xml_path)
        else:
            print(f"ERROR: Unrecognized root element <{root.tag}> in {xml_path}")
            print(f"  Expected: mine_terminal, MineTerminalData, or mine_terminal_data")

    db.close()
    print("\nAll imports complete.")

if __name__ == "__main__":
    main()
