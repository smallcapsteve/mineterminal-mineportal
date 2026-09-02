with open('/opt/mineportal/app.py', 'r') as f:
    content = f.read()

old_css = '.tag-status{background:rgba(34,197,94,0.15);color:var(--green);border:1px solid rgba(34,197,94,0.3);}'
new_css = old_css + '\n' + '.tag-status-optioned{background:rgba(59,130,246,0.15);color:#3b82f6;border:1px solid rgba(59,130,246,0.3);}' + '\n' + '.tag-status-terminated{background:rgba(239,68,68,0.15);color:#ef4444;border:1px solid rgba(239,68,68,0.3);}' + '\n' + '.tag-status-lapsed{background:rgba(245,158,11,0.15);color:#f59e0b;border:1px solid rgba(245,158,11,0.3);}' + '\n' + '.tag-status-writtenoff{background:rgba(107,114,128,0.15);color:#6b7280;border:1px solid rgba(107,114,128,0.3);}' + '\n' + '.tag-status-former{background:rgba(107,114,128,0.15);color:#6b7280;border:1px solid rgba(107,114,128,0.3);}' + '\n' + '.tag-status-closed{background:rgba(107,114,128,0.15);color:#6b7280;border:1px solid rgba(107,114,128,0.3);}'

content = content.replace(old_css, new_css, 1)

old_badge = '${p.status?\'<span class="tag tag-status">${p.status}</span>\':\'\'}' 
new_badge = '${p.status?\'<span class="tag tag-status \'+statusCls(p.status)+\'">${p.status}</span>\':\'\'}' 
content = content.replace(old_badge, new_badge)

insert_marker = 'function fmtGrade'
status_fn = 'function statusCls(s){if(!s)return \'\';s=s.toLowerCase();if(s.includes(\'optioned\'))return \'tag-status-optioned\';if(s.includes(\'terminated\'))return \'tag-status-terminated\';if(s.includes(\'lapsed\'))return \'tag-status-lapsed\';if(s.includes(\'written\'))return \'tag-status-writtenoff\';if(s===\'former\')return \'tag-status-former\';if(s===\'closed\')return \'tag-status-closed\';return \'\';}\n' + insert_marker

content = content.replace(insert_marker, status_fn, 1)

with open('/opt/mineportal/app.py', 'w') as f:
    f.write(content)

print("Patch applied!")
with open('/opt/mineportal/app.py', 'r') as f:
    text = f.read()
checks = ['statusCls' in text, 'tag-status-optioned' in text, 'statusCls(p.status)' in text]
print("  statusCls found:", checks[0])
print("  CSS classes found:", checks[1])
print("  badge updated:", checks[2])
