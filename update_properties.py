import sqlite3

db = sqlite3.connect('/opt/mineportal/mining_portal.db')
db.row_factory = sqlite3.Row
c = db.cursor()

updates = [
    # ACDX - Chuchi South: Optioned Out to Pacific Ridge, ACDX retains 49%
    ("UPDATE properties SET status='Optioned Out', current_interest='49%%' WHERE id=4", "Chuchi South -> Optioned Out, 49%%"),
    # ACDX - Chuchi West: Optioned Out to Pacific Ridge
    ("UPDATE properties SET status='Optioned Out' WHERE id=5", "Chuchi West -> Optioned Out"),
    # Aventis - Vent Copper: Terminated
    ("UPDATE properties SET status='Terminated' WHERE id=10", "Vent Copper -> Terminated"),
    # Aventis - Schofield Lithium: Claims Lapsed
    ("UPDATE properties SET status='Claims Lapsed' WHERE id=8", "Schofield Lithium -> Claims Lapsed"),
    # Aventis - Dickson Lake Lithium: Claims Lapsed
    ("UPDATE properties SET status='Claims Lapsed' WHERE id=9", "Dickson Lake Lithium -> Claims Lapsed"),
    # Adelayde - George Lake South: fix acres to hectares (4722 * 0.404686 = 1911.3)
    ("UPDATE properties SET size_ha=1911.3 WHERE id=22", "George Lake South size_ha 4722 -> 1911.3 (was acres)"),
    # Adelayde - Chibougamau Vanadium: Written Off
    ("UPDATE properties SET status='Written Off' WHERE id=19", "Chibougamau Vanadium -> Written Off"),
    # Adelayde - Green Clay Lithium: Written Off
    ("UPDATE properties SET status='Written Off' WHERE id=15", "Green Clay Lithium -> Written Off"),
    # Adelayde - Perron-East Gold: Written Off
    ("UPDATE properties SET status='Written Off' WHERE id=18", "Perron-East Gold -> Written Off"),
]

for sql, desc in updates:
    c.execute(sql)
    print(f"  {desc} ({c.rowcount} row)")

db.commit()
print("\nAll updates applied successfully!")

# Verify
print("\n=== Verification ===")
c.execute("SELECT id, name, status, current_interest, size_ha FROM properties WHERE id IN (4,5,8,9,10,15,18,19,22)")
for row in c.fetchall():
    print(f"  id={row['id']} | {row['name']} | status={row['status']} | interest={row['current_interest']} | size={row['size_ha']}")

db.close()
