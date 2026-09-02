#!/usr/bin/env python3
import os, re
SRC='/opt/mineportal/app.py'
text=open(SRC).read()

# Find first "// Exploration Programs" line (start of block 1)
m1 = re.search(r'\n  // Exploration Programs\n', text)
if not m1:
    raise SystemExit('no first marker')
start = m1.start() + 1   # position right after the leading \n

# Find the 2nd marker
rest = text[m1.end():]
m2 = re.search(r'\n  // Exploration Programs\n', rest)
if not m2:
    raise SystemExit('no second marker')

# After the second marker, find the closing `  }\n` that follows the
# last `html+=` line. The ep block ends exactly with:
#   html+=`</tbody></table></div></div>`;\n  }\n
block2_abs_end = m1.end() + m2.end()
tail = text[block2_abs_end:]
m3 = re.search(r'html\+=`</tbody></table></div></div>`;\n  \}\n', tail)
if not m3:
    raise SystemExit('no end-of-ep-block anchor')
end = block2_abs_end + m3.end()   # just past the closing }\n

UNIFIED = """  // Exploration Programs (unified: drill_programs + exploration_programs)
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

new_text = text[:start] + UNIFIED + text[end:]

# Insert showEP after showDM
if 'function showEP(' not in new_text:
    m = re.search(r'\nfunction showDM\(pid\)\{', new_text)
    if not m: raise SystemExit('no showDM')
    j = m.end()-1; depth=0
    while j < len(new_text):
        c=new_text[j]
        if c=='{': depth+=1
        elif c=='}':
            depth-=1
            if depth==0: break
        j+=1
    SHOW_EP = """
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
    new_text = new_text[:j+1] + SHOW_EP + new_text[j+1:]

# Expose ep to window alongside dp
if 'window._ep=ep' not in new_text:
    new_text = new_text.replace('window._dp=dp;', 'window._dp=dp;\nwindow._ep=ep;', 1)

# Sanity
assert '@app.route' in new_text, 'flask routes missing'
assert new_text.count('// Exploration Programs') == 1, 'duplicate marker still present'

tmp=SRC+'.tmp_patch'
open(tmp,'w').write(new_text)
print('orig:',os.path.getsize(SRC),'new:',os.path.getsize(tmp))
os.replace(tmp, SRC)
print('PATCH APPLIED OK')
