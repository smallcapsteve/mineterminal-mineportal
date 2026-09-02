with open('/opt/mineportal/app.py', 'r') as f:
    lines = f.readlines()

# Line 393 (0-indexed: 392) - replace status in All Properties table
line = lines[392]
old_part = "<td>${p.status||'-'}</td>"
new_part = '<td>${p.status?\'<span class="tag tag-status \'+statusCls(p.status)+\'">\'+p.status+\'</span>\':\'- \'}</td>'
if old_part in line:
    lines[392] = line.replace(old_part, new_part)
    print("Line 393 updated")
else:
    print("WARNING: old_part not found on line 393")
    print("Line 393 is:", repr(line))

with open('/opt/mineportal/app.py', 'w') as f:
    f.writelines(lines)

print("Saved. Verifying line 393:")
with open('/opt/mineportal/app.py', 'r') as f:
    all_lines = f.readlines()
print(all_lines[392].strip())
