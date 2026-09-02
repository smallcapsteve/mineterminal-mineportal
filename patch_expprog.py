#!/usr/bin/env python3
"""Unify the two 'Exploration Programs' render blocks in app.py and add showEP()."""
import sys, re, shutil, time

SRC = '/opt/mineportal/app.py'

with open(SRC, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# --- Part 1: find and replace the two Exploration Programs blocks ---
# Block 1 starts with the first `    // Exploration Programs` line
# Block 2 ends with the `    }` that closes `if(ep.length){`
start_idx = None
end_idx = None
seen_comments = 0
i = 0
while i < len(lines):
    L = lines[i]
    if L.rstrip() == '    // Exploration Programs':
        seen_comments += 1
        if seen_comments == 1:
            start_idx = i
    if seen_comments == 2 and L.rstrip() == '    }':
        # this is end of the second if(ep.length){ block
        end_idx = i
        break
    i += 1

if start_idx is None or end_idx is None:
    print('ERROR: could not locate both Exploration Programs blocks')
    sys.exit(1)

print(f'Block range: lines {start_idx+1}..{end_idx+1} (0-indexed {start_idx}..{end_idx})')

UNIFIED = r"""    // Exploration Programs (unified: drill_programs + exploration_programs)
    const allProgs = [
      ...dp.map(d=>({src:'dp', id:d.id, year:d.year, program_name:d.program_name, zone_name:d.zone_name,
                     operator:d.operator, type:d.drill_type||'Drilling',
                     planned_m:d.planned_meters, planned_h:d.planned_holes,
                     actual_m:d.actual_meters, actual_h:d.actual_holes,
                     objectives:d.objectives, result_count:d.result_count||0})),
      ...ep.map(e=>({src:'ep', id:e.id, year:e.year, program_name:e.program_name,
                     operator:e.operator, type:e.program_type||'Exploration',
                     description:e.description, results_summary:e.results_summary}))
    ].sort((a,b)=>(Number(b.year)||0)-(Number(a.year)||0));
    if(allProgs.length){
      html+=`<div class="section"><div class="section-header" onclick="toggleSection(this)">
        <h2>Exploration Programs</h2><span class="badge">${allProgs.length}</span></div>
        <div class="section-body"><div class="scroll-table"><table>
        <thead><tr><th>Year</th><th>Program</th><th>Operator</th><th>Type</th><th>Details</th></tr></thead>
        <tbody>${allProgs.map(p=>{
          const hasDrillResults = p.src==='dp' && p.result_count>0;
          const hasExpDetail = p.src==='ep' && (p.description||p.results_summary);
          const clickable = hasDrillResults || hasExpDetail;
          const onclickAttr = hasDrillResults ? `onclick="showDM(${p.id})"` :
                              hasExpDetail ? `onclick="showEP(${p.id})"` : '';
          const details = p.src==='dp'
            ? (`${fmtNum(p.actual_m)||fmtNum(p.planned_m)||'-'} m / ${fmtNum(p.actual_h)||fmtNum(p.planned_h)||'-'} holes`
               + (hasDrillResults?` <span class="badge" style="background:var(--gold);color:#000">${p.result_count} results</span>`:''))
            : ((p.description||'').substring(0,140) + ((p.description||'').length>140?'…':''));
          return `<tr style="${clickable?'cursor:pointer':'opacity:0.6'}" ${onclickAttr}>
            <td style="color:var(--gold)">${p.year||'-'}</td>
            <td>${p.zone_name?'<span style="color:var(--gold);font-size:11px">['+p.zone_name+']</span> ':''}${p.program_name||'-'}</td>
            <td>${p.operator||'-'}</td>
            <td><span class="badge" style="font-size:10px">${p.type}</span></td>
            <td style="font-size:12px;color:var(--text2);max-width:360px">${details}</td>
          </tr>`;
        }).join('')}</tbody></table></div></div></div>`;
    }
"""

new_lines = lines[:start_idx] + [UNIFIED] + lines[end_idx+1:]

# --- Part 2: insert showEP function after showDM function ---
# showDM ends with `document.getElementById('drM').classList.add('active');\n}\n`
# We'll find the line `function showDM(pid){` and count braces to find end.
text = ''.join(new_lines)
if 'function showEP(' in text:
    print('showEP already exists, skipping insert')
else:
    m = re.search(r'\nfunction showDM\(pid\)\{', text)
    if not m:
        print('ERROR: could not locate showDM function')
        sys.exit(1)
    # Find matching closing brace
    start = m.end() - 1  # position of the opening brace
    depth = 0
    j = start
    while j < len(text):
        c = text[j]
        if c == '{': depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                break
        j += 1
    if depth != 0:
        print('ERROR: could not find end of showDM')
        sys.exit(1)
    insert_pos = j + 1  # right after showDM closing }
    SHOW_EP = r"""
function showEP(pid){
  clearDT();
  var ep=(window._ep||[]).filter(function(e){return e.id===pid;});
  if(!ep.length) return;
  var e=ep[0];
  document.getElementById('drMT').textContent='EXPLORATION PROGRAM '+(e.year?('('+e.year+')'):'')+' \u2014 '+(e.program_name||'Program');
  var rows='';
  if(e.program_type) rows+='<tr><th style="text-align:left;color:var(--gold);width:140px">Type</th><td>'+e.program_type+'</td></tr>';
  if(e.operator) rows+='<tr><th style="text-align:left;color:var(--gold)">Operator</th><td>'+e.operator+'</td></tr>';
  if(e.description) rows+='<tr><th style="text-align:left;color:var(--gold);vertical-align:top">Description</th><td style="white-space:pre-wrap">'+e.description+'</td></tr>';
  if(e.results_summary) rows+='<tr><th style="text-align:left;color:var(--gold);vertical-align:top">Results</th><td style="white-space:pre-wrap">'+e.results_summary+'</td></tr>';
  if(e.expenditure) rows+='<tr><th style="text-align:left;color:var(--gold)">Expenditure</th><td>'+e.expenditure+'</td></tr>';
  if(e.source) rows+='<tr><th style="text-align:left;color:var(--gold)">Source</th><td>'+e.source+'</td></tr>';
  if(!rows) rows='<tr><td style="color:var(--text2)">No additional details recorded.</td></tr>';
  document.getElementById('drMB').innerHTML='<table style="width:100%">'+rows+'</table>';
  document.getElementById('drM').classList.add('active');
}
"""
    text = text[:insert_pos] + SHOW_EP + text[insert_pos:]

# --- Part 3: expose ep to window (so showEP can read it) ---
# Find `window._dp=dp;` and ensure a `window._ep=ep;` exists nearby
if 'window._ep=ep' not in text:
    text = text.replace('window._dp=dp;', 'window._dp=dp;\nwindow._ep=ep;', 1)

# Write atomically
tmp = SRC + '.tmp_patch'
with open(tmp, 'w', encoding='utf-8') as f:
    f.write(text)

# Syntax check: just confirm file opens and has grown
import os
orig_size = os.path.getsize(SRC)
new_size = os.path.getsize(tmp)
print(f'orig_size={orig_size} new_size={new_size} delta={new_size-orig_size}')
# Quick sanity: still has Flask route and exploration count
assert 'def index' in text or '@app.route' in text, 'lost flask routes!'
os.replace(tmp, SRC)
print('PATCH APPLIED OK')
