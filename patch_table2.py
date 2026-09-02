with open('/opt/mineportal/app.py', 'r') as f:
    lines = f.readlines()

# Fix line 392 (0-indexed: 391)
line391 = lines[391]
print("Line 392:", repr(line391[:80]))
old = "${p.status||'-'}"
new = "${p.status?'<span class=\"tag tag-status '+statusCls(p.status)+'\">'+ p.status+'</span>':'-'}"
if old in line391:
    lines[391] = line391.replace(old, new, 1)
    print("  -> Updated line 392")

# Fix line 458 (0-indexed: 457)
line457 = lines[457]
print("Line 458:", repr(line457[:80]))
if old in line457:
    lines[457] = line457.replace(old, new, 1)
    print("  -> Updated line 458")

with open('/opt/mineportal/app.py', 'w') as f:
    f.writelines(lines)
print("Done!")
