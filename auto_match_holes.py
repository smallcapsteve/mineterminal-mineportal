import sqlite3, re

db = sqlite3.connect('/opt/mineportal/mining_portal.db')
db.row_factory = sqlite3.Row

def extract_year(hole_id):
    """Extract 2-digit year from hole ID like AC23-001, VB24-003, H95-1, OPAP-90-1, TL-79-5"""
    m = re.match(r'^[A-Za-z]+-?(\d{2})-', hole_id)
    if m:
        yy = int(m.group(1))
        return 1900 + yy if yy > 50 else 2000 + yy
    return None

# Find all results in "Various" or catch-all programs
various = db.execute("""
    SELECT dr.id, dr.hole_id, dr.drill_program_id, dp.year, dp.program_name, dp.property_id, p.name
    FROM drill_results dr
    JOIN drill_programs dp ON dr.drill_program_id = dp.id
    JOIN properties p ON dp.property_id = p.id
    WHERE dp.year = 'Various' OR dp.program_name LIKE '%Results Results%'
""").fetchall()

print(f"Found {len(various)} results in catch-all programs\n")

# Group by property
from collections import defaultdict
by_prop = defaultdict(list)
for r in various:
    by_prop[r['property_id']].append(r)

for pid, results in by_prop.items():
    prop_name = results[0]['name']
    print(f"\n=== {prop_name} (property {pid}) ===")
    
    # Get all programs for this property
    programs = db.execute("SELECT id, year, program_name FROM drill_programs WHERE property_id=?", (pid,)).fetchall()
    
    for r in results:
        yr = extract_year(r['hole_id'])
        if yr:
            # Find matching programs by year
            matches = [p for p in programs if str(yr) in str(p['year']) and p['id'] != r['drill_program_id']]
            if len(matches) == 1:
                print(f"  {r['hole_id']} -> year {yr} -> MATCH: program {matches[0]['id']} ({matches[0]['program_name']})")
            elif len(matches) > 1:
                print(f"  {r['hole_id']} -> year {yr} -> AMBIGUOUS: {[(m['id'], m['program_name']) for m in matches]}")
            else:
                print(f"  {r['hole_id']} -> year {yr} -> NO MATCH found")
        else:
            print(f"  {r['hole_id']} -> cannot extract year")

db.close()
