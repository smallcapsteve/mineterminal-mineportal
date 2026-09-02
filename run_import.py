#!/usr/bin/env python3
import sqlite3,json,gzip,base64,sys,os
DB="/opt/mineportal/mining_portal.db"
def main():
    b64=sys.stdin.read().strip()
    data=json.loads(gzip.decompress(base64.b64decode(b64)))
    db=sqlite3.connect(DB)
    db.execute("PRAGMA foreign_keys=OFF")
    # Ensure extra columns
    cur=db.cursor()
    cur.execute("PRAGMA table_info(drill_results)")
    ex={r[1] for r in cur.fetchall()}
    for c,t in [("mo_pct","REAL"),("li_pct","REAL"),("treo_pct","REAL"),("u3o8_lbs_per_ton","REAL"),("tree_lbs_per_ton","REAL"),("nb2o5_pct","REAL"),("tho2_pct","REAL"),("zro2_pct","REAL"),("p2o5_pct","REAL")]:
        if c not in ex:
            try:cur.execute(f"ALTER TABLE drill_results ADD COLUMN {c} {t}")
            except:pass
    cur.execute("PRAGMA table_info(resource_estimates)")
    ex={r[1] for r in cur.fetchall()}
    for c,t in [("grade_mo_pct","REAL"),("grade_treo_pct","REAL"),("grade_u3o8_lbs_per_ton","REAL"),("grade_tree_lbs_per_ton","REAL"),("contained_mo_mlbs","REAL"),("contained_u3o8_mlbs","REAL"),("contained_tree_mlbs","REAL"),("other_grades","TEXT"),("other_contained","TEXT")]:
        if c not in ex:
            try:cur.execute(f"ALTER TABLE resource_estimates ADD COLUMN {c} {t}")
            except:pass
    db.commit()
    # Map old IDs to new IDs
    cid_map={}; pid_map={}
    # Wipe existing companies
    tickers=[r[1] for r in data["companies"]["rows"]]
    for tk in tickers:
        cur.execute("SELECT id FROM companies WHERE ticker=?",(tk,))
        row=cur.fetchone()
        if row:
            cid=row[0]
            cur.execute("SELECT id FROM properties WHERE company_id=?",(cid,))
            pids=[r[0] for r in cur.fetchall()]
            for pid in pids:
                for tbl in ["drill_results","resource_estimates","ownership_history","drill_programs","nearby_mines"]:
                    cur.execute(f"DELETE FROM {tbl} WHERE property_id=?", (pid,))
            cur.execute("DELETE FROM properties WHERE company_id=?",(cid,))
            cur.execute("DELETE FROM sources WHERE company_id=?",(cid,))
            cur.execute("DELETE FROM companies WHERE id=?",(cid,))
            print(f"Wiped {tk} ({len(pids)} properties)")
    db.commit()
    # Insert companies
    cc=data["companies"]["cols"]
    for r in data["companies"]["rows"]:
        old_id=r[0]; vals=r[1:]
        cur.execute(f"INSERT INTO companies({','.join(cc[1:])}) VALUES({','.join(['?']*len(vals))})",vals)
        cid_map[old_id]=cur.lastrowid
        print(f"Company: {r[2]} ({r[1]}) -> id={cur.lastrowid}")
    # Insert properties
    pc=data["properties"]["cols"]
    for r in data["properties"]["rows"]:
        old_id=r[0]; vals=list(r[1:])
        vals[0]=cid_map[vals[0]]  # company_id
        cur.execute(f"INSERT INTO properties({','.join(pc[1:])}) VALUES({','.join(['?']*len(vals))})",vals)
        pid_map[old_id]=cur.lastrowid
    print(f"Properties: {len(data['properties']['rows'])} inserted")
    # Insert drill_programs
    dc=data["drill_programs"]["cols"]
    for r in data["drill_programs"]["rows"]:
        vals=list(r[1:]); vals[0]=pid_map[vals[0]]
        cur.execute(f"INSERT INTO drill_programs({','.join(dc[1:])}) VALUES({','.join(['?']*len(vals))})",vals)
    print(f"Drill programs: {len(data['drill_programs']['rows'])} inserted")
    # Insert drill_results
    drc=data["drill_results"]["cols"]
    for r in data["drill_results"]["rows"]:
        vals=list(r[1:]); vals[1]=pid_map[vals[1]]  # property_id is col index 1 (after removing id)
        cur.execute(f"INSERT INTO drill_results({','.join(drc[1:])}) VALUES({','.join(['?']*len(vals))})",vals)
    print(f"Drill results: {len(data['drill_results']['rows'])} inserted")
    # Insert resource_estimates
    rc=data["resource_estimates"]["cols"]
    for r in data["resource_estimates"]["rows"]:
        vals=list(r[1:]); vals[0]=pid_map[vals[0]]
        cur.execute(f"INSERT INTO resource_estimates({','.join(rc[1:])}) VALUES({','.join(['?']*len(vals))})",vals)
    print(f"Resource estimates: {len(data['resource_estimates']['rows'])} inserted")
    # Insert nearby_mines
    nc=data["nearby_mines"]["cols"]
    for r in data["nearby_mines"]["rows"]:
        vals=list(r[1:]); vals[0]=pid_map[vals[0]]
        cur.execute(f"INSERT INTO nearby_mines({','.join(nc[1:])}) VALUES({','.join(['?']*len(vals))})",vals)
    print(f"Nearby mines: {len(data['nearby_mines']['rows'])} inserted")
    db.commit()
    db.close()
    print("DONE")
if __name__=="__main__":
    main()
