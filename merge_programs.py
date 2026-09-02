import sqlite3
db = sqlite3.connect('/opt/mineportal/mining_portal.db')
c = db.cursor()

# 1. Horwood 1963: merge program 5 into 4
print("=== Horwood 1963 ===")
c.execute("UPDATE drill_results SET drill_program_id=4 WHERE drill_program_id=5")
print(f"  Moved {c.rowcount} results from program 5 to 4")
c.execute("UPDATE drill_programs SET program_name='Diamond drilling + mapping' WHERE id=4")
c.execute("DELETE FROM drill_programs WHERE id=5")
print("  Merged program 5 into 4, deleted 5")

# 2. Sting Copper 2024: merge 33,34,35 into 33
print("\n=== Sting Copper 2024 ===")
c.execute("UPDATE drill_results SET drill_program_id=33 WHERE drill_program_id IN (34,35)")
print(f"  Moved {c.rowcount} results to program 33")
c.execute("""UPDATE drill_programs SET 
    year='2024',
    program_name='Maiden drill program (Phase 1 Summer + Fall)',
    operator='Vital Battery Metals / Dahrouge Geological Consulting',
    actual_meters=912.0,
    actual_holes=5
    WHERE id=33""")
c.execute("DELETE FROM drill_programs WHERE id IN (34,35)")
print("  Merged 34,35 into 33, deleted 34,35")

# 3. McGee Lithium 2020: merge 52 into 50
print("\n=== McGee Lithium 2020 ===")
c.execute("UPDATE drill_results SET drill_program_id=50 WHERE drill_program_id=52")
print(f"  Moved {c.rowcount} results from program 52 to 50")
c.execute("DELETE FROM drill_programs WHERE id=52")
print("  Merged program 52 into 50, deleted 52")

db.commit()
db.close()
print("\nAll merges complete!")
