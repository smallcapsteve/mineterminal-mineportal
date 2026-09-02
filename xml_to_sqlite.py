#!/usr/bin/env python3
"""
MineTerminalPro: XML → SQLite Importer
Reads validated MTP XML files and populates the mining_portal SQLite database.

Usage:
    python xml_to_sqlite.py <xml_file> [<xml_file2> ...] --db <path_to_db>
    python xml_to_sqlite.py xml_output/*.xml --db mining_portal.db
"""

import sqlite3, os, sys, argparse
from lxml import etree

MTP_NS = "https://mineterminalpro.com/schema/v1"


def ns(tag):
    return f"{{{MTP_NS}}}{tag}"


def text(el, tag):
    """Get text content of a child element."""
    child = el.find(ns(tag))
    if child is not None and child.text:
        return child.text.strip()
    return None


def text_path(el, path):
    """Get text via a dot-separated path like 'jurisdiction.country'."""
    parts = path.split(".")
    current = el
    for p in parts:
        current = current.find(ns(p))
        if current is None:
            return None
    return current.text.strip() if current is not None and current.text else None


def safe_float(val):
    if val is None:
        return None
    try:
        s = val.replace(",", "").replace("~", "").strip()
        return float(s)
    except:
        return None


def safe_int(val):
    f = safe_float(val)
    return int(f) if f is not None else None


def ensure_columns(db):
    """Add multi-metal resource estimate columns to existing databases."""
    new_cols = [
        ("resource_estimates", "grade_cueq_pct", "REAL"),
        ("resource_estimates", "grade_cu_pct", "REAL"),
        ("resource_estimates", "grade_zn_pct", "REAL"),
        ("resource_estimates", "grade_ag_gpt", "REAL"),
        ("resource_estimates", "contained_cu_mlbs", "REAL"),
        ("resource_estimates", "contained_zn_mlbs", "REAL"),
        ("resource_estimates", "contained_ag_moz", "REAL"),
    ]
    for table, col, col_type in new_cols:
        try:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
            print(f"  Added column: {table}.{col}")
        except sqlite3.OperationalError:
            pass  # Column already exists
    db.commit()


def create_schema(db):
    """Create the portal database schema (matches load_data.py / app.py)."""
    db.executescript("""
    CREATE TABLE IF NOT EXISTS companies (
        id INTEGER PRIMARY KEY,
        ticker TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        exchange TEXT DEFAULT 'CSE',
        description TEXT,
        website TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS properties (
        id INTEGER PRIMARY KEY,
        company_id INTEGER NOT NULL REFERENCES companies(id),
        name TEXT NOT NULL,
        jurisdiction TEXT,
        country TEXT,
        general_location TEXT,
        size_ha REAL,
        current_interest TEXT,
        nature_of_interest TEXT,
        mineralization_type TEXT,
        primary_metals TEXT,
        status TEXT,
        resource_notes TEXT,
        latitude REAL,
        longitude REAL,
        coord_quality TEXT,
        infrastructure_notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(company_id, name)
    );
    CREATE TABLE IF NOT EXISTS ownership_history (
        id INTEGER PRIMARY KEY,
        property_id INTEGER NOT NULL REFERENCES properties(id),
        date_or_period TEXT,
        event_type TEXT,
        counterparties TEXT,
        interest_details TEXT,
        terms TEXT,
        notes TEXT,
        source_url TEXT
    );
    CREATE TABLE IF NOT EXISTS drill_programs (
        id INTEGER PRIMARY KEY,
        property_id INTEGER NOT NULL REFERENCES properties(id),
        year TEXT,
        program_name TEXT,
        operator TEXT,
        drill_type TEXT,
        planned_meters REAL,
        planned_holes INTEGER,
        actual_meters REAL,
        actual_holes INTEGER,
        objectives TEXT,
        source_url TEXT
    );
    CREATE TABLE IF NOT EXISTS drill_results (
        id INTEGER PRIMARY KEY,
        drill_program_id INTEGER REFERENCES drill_programs(id),
        property_id INTEGER NOT NULL REFERENCES properties(id),
        hole_id TEXT,
        year TEXT,
        zone_target TEXT,
        from_m REAL,
        to_m REAL,
        interval_m REAL,
        au_gpt REAL,
        ag_gpt REAL,
        cu_pct REAL,
        zn_pct REAL,
        ni_pct REAL,
        co_pct REAL,
        pb_pct REAL,
        pt_gpt REAL,
        cueq_pct REAL,
        fe2o3_pct REAL,
        tio2_pct REAL,
        other_assays TEXT,
        depth_m REAL,
        result_type TEXT,
        highlight INTEGER DEFAULT 0,
        notes TEXT,
        source_url TEXT
    );
    CREATE TABLE IF NOT EXISTS resource_estimates (
        id INTEGER PRIMARY KEY,
        property_id INTEGER NOT NULL REFERENCES properties(id),
        estimate_date TEXT,
        prepared_by TEXT,
        estimate_type TEXT,
        category TEXT,
        tonnes_mt REAL,
        grade_au_gpt REAL,
        grade_cueq_pct REAL,
        grade_cu_pct REAL,
        grade_zn_pct REAL,
        grade_ag_gpt REAL,
        contained_au_moz REAL,
        contained_cu_mlbs REAL,
        contained_zn_mlbs REAL,
        contained_ag_moz REAL,
        cutoff_assumptions TEXT,
        compliance_code TEXT,
        notes TEXT,
        source_url TEXT
    );
    CREATE TABLE IF NOT EXISTS nearby_mines (
        id INTEGER PRIMARY KEY,
        property_id INTEGER NOT NULL REFERENCES properties(id),
        nearby_name TEXT,
        owner_operator TEXT,
        distance TEXT,
        commodity TEXT,
        resource_info TEXT,
        relevance TEXT,
        source_url TEXT
    );
    CREATE TABLE IF NOT EXISTS sources (
        id INTEGER PRIMARY KEY,
        company_id INTEGER NOT NULL REFERENCES companies(id),
        ref_id TEXT,
        title TEXT,
        date TEXT,
        doc_type TEXT,
        url TEXT,
        notes TEXT
    );
    """)
    db.commit()


def import_xml(db, xml_path):
    """Import a single XML file into the database."""
    doc = etree.parse(xml_path)
    root = doc.getroot()

    stats = {"companies": 0, "properties": 0, "drill_programs": 0,
             "drill_results": 0, "resource_estimates": 0}

    for company_el in root.findall(ns("company")):
        ticker = text(company_el, "ticker")
        name = text(company_el, "name")
        exchange = text(company_el, "exchange") or "CSE"
        website = text(company_el, "website")
        description = text(company_el, "description")

        if not ticker or not name:
            continue

        # Insert or get company
        db.execute("INSERT OR IGNORE INTO companies (ticker, name, exchange, description, website) VALUES (?,?,?,?,?)",
                   (ticker, name, exchange, description, website))
        company_id = db.execute("SELECT id FROM companies WHERE ticker=?", (ticker,)).fetchone()[0]
        stats["companies"] += 1

        # Properties
        props_el = company_el.find(ns("properties"))
        if props_el is None:
            continue

        for prop_el in props_el.findall(ns("property")):
            prop_name = text(prop_el, "name")
            if not prop_name:
                continue

            country = text_path(prop_el, "jurisdiction.country")
            province = text_path(prop_el, "jurisdiction.province")
            jurisdiction = province or country
            lat = safe_float(text_path(prop_el, "location.latitude"))
            lon = safe_float(text_path(prop_el, "location.longitude"))
            area = safe_float(text(prop_el, "areaHectares"))
            stage = text(prop_el, "stage")
            primary_commodity = text(prop_el, "primaryCommodity")
            description_prop = text(prop_el, "description")

            # Collect secondary commodities
            sec_el = prop_el.find(ns("secondaryCommodities"))
            all_metals = [primary_commodity] if primary_commodity else []
            if sec_el is not None:
                for c in sec_el.findall(ns("commodity")):
                    if c.text and c.text.strip() not in all_metals:
                        all_metals.append(c.text.strip())
            metals_str = ", ".join(all_metals) if all_metals else None

            # Ownership info for current_interest
            current_interest = None
            nature_of_interest = None
            own_el = prop_el.find(ns("ownership"))
            if own_el is not None:
                for interest in own_el.findall(ns("interest")):
                    if interest.get("isCurrent") == "true":
                        pct = text(interest, "interestPercent")
                        itype = text(interest, "interestType")
                        holder = text(interest, "holder")
                        if pct:
                            current_interest = f"{pct}%"
                        nature_of_interest = itype

            db.execute("""INSERT OR IGNORE INTO properties
                (company_id, name, jurisdiction, country, general_location, size_ha,
                 current_interest, nature_of_interest, mineralization_type, primary_metals,
                 status, latitude, longitude)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (company_id, prop_name, jurisdiction, country, description_prop, area,
                 current_interest, nature_of_interest, primary_commodity, metals_str,
                 stage, lat, lon))

            prop_id = db.execute("SELECT id FROM properties WHERE company_id=? AND name=?",
                                (company_id, prop_name)).fetchone()
            if not prop_id:
                continue
            prop_id = prop_id[0]
            stats["properties"] += 1

            # Ownership history
            if own_el is not None:
                for interest in own_el.findall(ns("interest")):
                    holder = text(interest, "holder")
                    itype = text(interest, "interestType")
                    pct = text(interest, "interestPercent")
                    notes = text(interest, "notes")
                    db.execute("""INSERT INTO ownership_history
                        (property_id, event_type, counterparties, interest_details, notes)
                        VALUES (?,?,?,?,?)""",
                        (prop_id, itype, holder, f"{pct}%" if pct else None, notes))

            # Resource Estimates
            re_wrapper = prop_el.find(ns("resourceEstimates"))
            if re_wrapper is not None:
                for re_el in re_wrapper.findall(ns("resourceEstimate")):
                    est_name = text(re_el, "name")
                    report_date = text(re_el, "reportDate")
                    prepared_by = text(re_el, "preparedBy")
                    standard = text(re_el, "reportStandard")
                    notes = text(re_el, "notes")
                    source_url = text(re_el, "sourceUrl")

                    cutoff_desc = None
                    cutoff_el = re_el.find(ns("cutoff"))
                    if cutoff_el is not None:
                        cutoff_desc = text(cutoff_el, "description") or text(cutoff_el, "unit")

                    # Each category row becomes a separate DB row
                    cats_el = re_el.find(ns("categories"))
                    if cats_el is not None:
                        for cat in cats_el.findall(ns("category")):
                            classification = text(cat, "classification")
                            subtype = text(cat, "subtype")
                            constraint = text(cat, "constraint")
                            tonnes = safe_float(text(cat, "tonnes"))

                            # Parse ALL grade entries into metal-specific columns
                            grade_au, grade_cueq, grade_cu, grade_zn, grade_ag = (None,)*5
                            grades_el = cat.find(ns("grades"))
                            if grades_el is not None:
                                for g in grades_el.findall(ns("grade")):
                                    commodity = g.get("commodity", "")
                                    val = safe_float(g.get("value"))
                                    unit = g.get("unit", "")
                                    if commodity == "Gold":
                                        grade_au = val
                                    elif commodity == "Silver":
                                        grade_ag = val
                                    elif commodity == "Copper":
                                        # CuEq typically has unit containing "eq" or
                                        # is a second Copper entry after Cu is already set
                                        if "eq" in unit.lower() or (grade_cu is not None):
                                            grade_cueq = val
                                        else:
                                            grade_cu = val
                                    elif commodity == "Zinc":
                                        grade_zn = val

                            # Parse ALL contained metal entries
                            cont_au, cont_cu, cont_zn, cont_ag = (None,)*4
                            cm_el = cat.find(ns("containedMetal"))
                            if cm_el is not None:
                                for m in cm_el.findall(ns("metal")):
                                    commodity = m.get("commodity", "")
                                    val = safe_float(m.get("value"))
                                    unit = m.get("unit", "")
                                    if commodity == "Gold":
                                        cont_au = val
                                    elif commodity == "Silver":
                                        cont_ag = val
                                    elif commodity == "Copper":
                                        cont_cu = val
                                    elif commodity == "Zinc":
                                        cont_zn = val

                            # Build category string with subtype or constraint
                            category_str = classification
                            if subtype:
                                category_str = f"{classification} ({subtype})"
                            elif constraint and constraint != "Unconstrained":
                                category_str = f"{classification} ({constraint})"

                            db.execute("""INSERT INTO resource_estimates
                                (property_id, estimate_date, prepared_by, estimate_type, category,
                                 tonnes_mt, grade_au_gpt, grade_cueq_pct, grade_cu_pct,
                                 grade_zn_pct, grade_ag_gpt,
                                 contained_au_moz, contained_cu_mlbs, contained_zn_mlbs,
                                 contained_ag_moz,
                                 cutoff_assumptions, compliance_code, notes, source_url)
                                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                (prop_id, report_date, prepared_by, est_name, category_str,
                                 tonnes, grade_au, grade_cueq, grade_cu,
                                 grade_zn, grade_ag,
                                 cont_au, cont_cu, cont_zn,
                                 cont_ag,
                                 cutoff_desc, standard, notes, source_url))
                            stats["resource_estimates"] += 1

            # Drill Programs & Results
            dp_wrapper = prop_el.find(ns("drillPrograms"))
            if dp_wrapper is not None:
                for dp_el in dp_wrapper.findall(ns("drillProgram")):
                    prog_name = text(dp_el, "name")
                    year = text(dp_el, "year")
                    operator = text(dp_el, "operator")
                    drill_type = text(dp_el, "drillType")
                    planned_m = safe_float(text(dp_el, "plannedMetres"))
                    actual_m = safe_float(text(dp_el, "actualMetres"))
                    planned_h = safe_int(text(dp_el, "plannedHoles"))
                    actual_h = safe_int(text(dp_el, "actualHoles"))
                    prog_notes = text(dp_el, "notes")

                    db.execute("""INSERT INTO drill_programs
                        (property_id, year, program_name, operator, drill_type,
                         planned_meters, planned_holes, actual_meters, actual_holes, objectives)
                        VALUES (?,?,?,?,?,?,?,?,?,?)""",
                        (prop_id, year, prog_name, operator, drill_type,
                         planned_m, planned_h, actual_m, actual_h, prog_notes))

                    prog_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
                    stats["drill_programs"] += 1

                    # Drill results within this program
                    results_el = dp_el.find(ns("results"))
                    if results_el is None:
                        continue

                    for result_el in results_el.findall(ns("result")):
                        hole_id = text(result_el, "holeId")
                        from_m = safe_float(text(result_el, "fromMetres"))
                        to_m = safe_float(text(result_el, "toMetres"))
                        length_m = safe_float(text(result_el, "lengthMetres"))
                        true_width = safe_float(text(result_el, "trueWidthMetres"))
                        result_notes = text(result_el, "notes")

                        is_significant = result_el.get("isSignificant") == "true"
                        is_including = result_el.get("including") == "true"

                        # Parse assays into metal-specific columns
                        au, ag, cu, zn, ni, co, pb, pt, cueq = (None,)*9
                        other_assays = []

                        assays_el = result_el.find(ns("assays"))
                        if assays_el is not None:
                            for assay in assays_el.findall(ns("assay")):
                                commodity = assay.get("commodity", "")
                                value = safe_float(assay.get("value"))
                                unit = assay.get("unit", "")

                                if commodity == "Gold":
                                    au = value
                                elif commodity == "Silver":
                                    ag = value
                                elif commodity == "Copper":
                                    if "eq" in unit.lower() or cueq is not None:
                                        # Second copper entry is likely CuEq
                                        if cu is not None:
                                            cueq = value
                                        else:
                                            cu = value
                                    else:
                                        cu = value
                                elif commodity == "Zinc":
                                    zn = value
                                elif commodity == "Nickel":
                                    ni = value
                                elif commodity == "Cobalt":
                                    co = value
                                elif commodity == "Lead":
                                    pb = value
                                elif commodity == "PGMs":
                                    pt = value
                                elif commodity == "Uranium":
                                    other_assays.append(f"U3O8: {value}{unit}")
                                else:
                                    other_assays.append(f"{commodity}: {value}{unit}")

                        result_type = "including" if is_including else None
                        other_str = "; ".join(other_assays) if other_assays else None

                        db.execute("""INSERT INTO drill_results
                            (drill_program_id, property_id, hole_id, year, zone_target,
                             from_m, to_m, interval_m, au_gpt, ag_gpt, cu_pct, zn_pct,
                             ni_pct, co_pct, pb_pct, pt_gpt, cueq_pct, other_assays,
                             depth_m, result_type, highlight, notes)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (prog_id, prop_id, hole_id, year, None,
                             from_m, to_m, length_m, au, ag, cu, zn,
                             ni, co, pb, pt, cueq, other_str,
                             true_width, result_type, 1 if is_significant else 0, result_notes))
                        stats["drill_results"] += 1

    db.commit()
    return stats


def main():
    parser = argparse.ArgumentParser(description="Import MTP XML into SQLite portal database")
    parser.add_argument("files", nargs="+", help="XML file(s) to import")
    parser.add_argument("--db", required=True, help="Path to SQLite database")
    parser.add_argument("--reset", action="store_true", help="Delete and recreate database")
    args = parser.parse_args()

    if args.reset and os.path.exists(args.db):
        os.remove(args.db)
        print(f"Removed existing database: {args.db}")

    db = sqlite3.connect(args.db)
    create_schema(db)
    ensure_columns(db)  # Add multi-metal columns to existing DBs

    total_stats = {"companies": 0, "properties": 0, "drill_programs": 0,
                   "drill_results": 0, "resource_estimates": 0}

    for filepath in args.files:
        fname = os.path.basename(filepath)
        print(f"Importing: {fname}")
        stats = import_xml(db, filepath)
        for k in total_stats:
            total_stats[k] += stats[k]
        print(f"  → {stats['companies']} companies, {stats['properties']} properties, "
              f"{stats['drill_programs']} programs, {stats['drill_results']} results, "
              f"{stats['resource_estimates']} estimates")

    # Summary
    print(f"\n{'='*60}")
    print("DATABASE SUMMARY")
    print(f"{'='*60}")
    for table in ["companies", "properties", "drill_programs", "drill_results",
                   "resource_estimates", "ownership_history", "nearby_mines", "sources"]:
        count = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {count}")

    # Properties with coordinates
    with_coords = db.execute("SELECT COUNT(*) FROM properties WHERE latitude IS NOT NULL").fetchone()[0]
    total_props = db.execute("SELECT COUNT(*) FROM properties").fetchone()[0]
    print(f"\n  Properties with coordinates: {with_coords}/{total_props}")

    db.close()
    print(f"\nDatabase saved: {args.db}")


if __name__ == "__main__":
    main()
