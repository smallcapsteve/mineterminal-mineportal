import sqlite3

db = sqlite3.connect('/opt/mineportal/mining_portal.db')
c = db.cursor()

program_id = 29
property_id = 4
year = '2024'
zone = 'BP Zone'
source = 'https://www.juniorminingnetwork.com/junior-miner-news/press-releases/320-tsx-venture/pex/171048-pacific-ridge-s-inaugural-drill-program-returns-some-of-the-best-drill-results-ever-recorded-at-the-chuchi-copper-gold-project.html'

# (hole_id, from_m, to_m, interval_m, cu_pct, au_gpt, ag_gpt, cueq_pct, result_type, highlight, notes)
results = [
    # CH-24-070 main
    ('CH-24-070', 66.0, 479.9, 413.9, 0.15, 0.15, 0.43, 0.26, 'interval', 1, 'Deepest mineralization to date at 420m vertical depth'),
    # CH-24-070 includes
    ('CH-24-070', 66.0, 169.0, 103.0, 0.19, 0.20, 0.61, 0.32, 'sub-interval', 0, 'Higher-grade sub-interval'),
    ('CH-24-070', 358.0, 459.0, 101.0, 0.19, 0.16, 0.39, 0.30, 'sub-interval', 0, 'Higher-grade sub-interval'),

    # CH-24-071 main
    ('CH-24-071', 54.0, 172.0, 118.0, 0.17, 0.17, 0.57, 0.28, 'interval', 0, ''),
    # CH-24-071 includes
    ('CH-24-071', 107.0, 129.0, 22.0, 0.26, 0.22, 0.91, 0.41, 'sub-interval', 0, 'Higher-grade sub-interval'),

    # CH-24-072 main
    ('CH-24-072', 7.0, 481.0, 474.0, 0.12, 0.12, 0.56, 0.21, 'interval', 0, ''),
    # CH-24-072 includes
    ('CH-24-072', 7.0, 77.0, 70.0, 0.15, 0.14, 0.73, 0.25, 'sub-interval', 0, 'Higher-grade sub-interval'),
    ('CH-24-072', 198.0, 234.0, 36.0, 0.26, 0.32, 1.26, 0.48, 'sub-interval', 1, 'Best sub-interval in CH-24-072'),
    ('CH-24-072', 411.0, 481.0, 70.0, 0.16, 0.14, 0.64, 0.26, 'sub-interval', 0, 'Higher-grade sub-interval'),

    # CH-24-073 main
    ('CH-24-073', 143.0, 525.0, 382.0, 0.19, 0.12, 0.47, 0.27, 'interval', 1, '65m of 0.42% CuEq or 0.63 g/t AuEq'),
    # CH-24-073 includes
    ('CH-24-073', 143.0, 243.0, 100.0, 0.26, 0.14, 0.58, 0.36, 'sub-interval', 0, 'Higher-grade sub-interval'),
    ('CH-24-073', 143.0, 208.0, 65.0, 0.31, 0.16, 0.69, 0.42, 'sub-interval', 1, 'Best sub-interval: 0.63 g/t AuEq'),
    ('CH-24-073', 425.0, 525.0, 100.0, 0.25, 0.16, 0.66, 0.37, 'sub-interval', 0, 'Higher-grade sub-interval'),

    # CH-24-074 main
    ('CH-24-074', 49.8, 348.0, 298.2, 0.21, 0.11, 0.51, 0.29, 'interval', 1, 'Last hole of program, drilled at interpreted centre of system'),
    # CH-24-074 includes
    ('CH-24-074', 49.8, 171.0, 121.2, 0.23, 0.08, 0.55, 0.29, 'sub-interval', 0, 'Higher-grade sub-interval'),
    ('CH-24-074', 189.0, 348.0, 159.0, 0.21, 0.14, 0.49, 0.31, 'sub-interval', 0, 'Higher-grade sub-interval'),
    ('CH-24-074', 297.0, 348.0, 51.0, 0.22, 0.15, 0.49, 0.33, 'sub-interval', 0, 'Last 51m returned 0.33% CuEq, increasing grade with depth'),
]

sql = """INSERT INTO drill_results 
    (drill_program_id, property_id, hole_id, year, zone_target, from_m, to_m, interval_m, 
     cu_pct, au_gpt, ag_gpt, cueq_pct, result_type, highlight, notes, source_url)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""

count = 0
for r in results:
    hole_id, from_m, to_m, interval_m, cu_pct, au_gpt, ag_gpt, cueq_pct, result_type, highlight, notes = r
    c.execute(sql, (program_id, property_id, hole_id, year, zone, from_m, to_m, interval_m,
                    cu_pct, au_gpt, ag_gpt, cueq_pct, result_type, highlight, notes, source))
    count += 1

db.commit()
print(f"Inserted {count} drill results for Chuchi South 2024 program (id={program_id})")

# Also update the program with actual hole/metre counts
c.execute("UPDATE drill_programs SET actual_holes=5, actual_metres=2716.0 WHERE id=?", (program_id,))
db.commit()
print("Updated program 29 with actual_holes=5, actual_metres=2716")

# Verify
c.execute("SELECT COUNT(*) FROM drill_results WHERE drill_program_id=?", (program_id,))
print(f"Total results for program {program_id}: {c.fetchone()[0]}")

db.close()
