'use strict';
const $ = id => document.getElementById(id);
let state = null, selected = '', selectedContext = '', running = false, stepping = false, modePending = false, observing = false, currentTab = 'ladder', report = null, editTag = null;
let connectivityPoll = null;
let locatorTimer = null, locatorRequest = null, locatorDeadline = 0;
const recognized = name => report?.supported_instructions.includes(name) || report?.known_add_on_instructions?.includes(name);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(action, data = {}) {
  const response = await fetch('/api/' + action, {method:'POST', headers:{'Content-Type':'application/json','X-Logix-Token':window.LOGIX_TOKEN}, body:JSON.stringify(data)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Request failed');
  return result;
}
function error(e) { $('alert').hidden = false; $('alert').textContent = e.message; }
async function accept(value, refreshReport = false) {
  state = value;
  running = !!value.controller?.running;
  if (refreshReport && value.loaded) report = await api('report');
  render();
}
function render() {
  if(state?.app_version){$('app-version').textContent=state.app_version;document.title=`LogixLab ${state.app_version} · Offline PLC lab`;}
  const appliance=state?.execution_environment==='vmware-host-only';
  $('desktop-status').lastChild.textContent=appliance?' VMware appliance':' Local session';
  $('desktop-status').title=appliance?'Host-only VM. Use the Windows tray to open, import projects or quit.':state?.desktop?.tray_available ? 'Tray icon active: Open app or Quit LogixLab.' : (state?.desktop?.tray_error || 'Use End session to shut down the app.');
  $('settings').hidden=appliance;
  $('open').textContent=appliance?'＋ Open L5X':'＋ Open ACD / L5X';
  $('file').accept=appliance?'.l5x':'.acd,.l5x';
  $('footer-text').textContent=appliance?'VMware host-only execution · ACD import uses the Windows tray':'ACD import uses your installed Rockwell SDK · engine runs independently';
  const loaded = !!state?.loaded;
  ['reset','step','run','apply','snapshot','report','mode'].forEach(id => $(id).disabled = !loaded);
  $('save-logic').disabled=!loaded||running||!state?.routine_edits?.l5x_export_available||!!state?.connectivity?.native_programming_lease?.owned;
  $('harness').disabled = !loaded || $('mode').value !== 'routine';
  renderConnectivity();
  const device=state?.device_io||{};
  $('device-badge').textContent=device.writes_enabled?'EXTERNAL WRITES ENABLED':'READ ONLY';
  $('device-writes').checked=!!device.writes_enabled;
  $('device-api').textContent=location.origin+'/api/device-io/snapshot';
  $('device-summary').textContent=`Snapshot ${device.snapshot_sequence||0} · ${device.pending_writes||0}/${device.queue_capacity||64} queued input batches · apply between scans`;
  if (!loaded) return;
  $('project-name').textContent = state.name;
  $('project-detail').textContent = `Studio 5000 v${state.version} · ${state.processor} · ${state.routines.length} routines · ${state.mode === 'routine' ? 'isolated routine harness' : 'whole project'}`;
  $('scan').textContent = state.scan.toLocaleString(); $('time').textContent = state.ms.toLocaleString();
  $('routine-count').textContent = state.routines.length;
  const blocked = state.blockers.length > 0;
  const inhibited=!!state.connectivity?.native_programming_lease?.scan_inhibited;
  $('status').textContent = state.fault ? 'FAULT · ROLLED BACK' : blocked ? 'EXECUTION BLOCKED' : inhibited ? 'SCANS INHIBITED' : running ? 'REMOTE RUN' : 'REMOTE PROGRAM';
  $('status').className = 'badge ' + (blocked || inhibited || state.fault ? 'blocked' : 'ready');
  $('step').disabled = blocked||inhibited||running||modePending;
  $('run').disabled = modePending||(!running&&(blocked||inhibited||!!state.fault));
  $('run').textContent = running ? '■ Program' : '▶ Run';
  $('dt').disabled = running||modePending;
  if(running)$('dt').value=state.controller.scan_interval_ms;
  $('scope-note').textContent = state.mode === 'routine' ? 'Harness: selected routine and called routines only.' : `${state.tasks.length} modeled task(s) · deterministic periodic releases · serial execution.`;
  $('alert').hidden = !(blocked || inhibited || state.fault);
  $('alert').textContent = state.fault || (blocked ? `${state.blockers.length} execution blocker(s). Open Coverage for details.\n${state.blockers.slice(0,3).join('\n')}` : inhibited?'Native programming preparation inhibits scans. Release or disconnect the owning client to resume.':'');
  const provenance = state.provenance;
  $('provenance').textContent = `${provenance.method || 'L5X'}\nSHA-256: ${(provenance.original_acd_sha256 || report?.source_l5x_sha256 || '').slice(0,20)}…`;
  $('converter').value = state.converter;
  renderExplorer(); renderTags(); renderLadder(); renderCoverage(); renderChanges();
}
function renderExplorer() {
  const groups = new Map();
  state.routines.forEach(r => { const program = r.key.split('/')[0]; if (!groups.has(program)) groups.set(program, []); groups.get(program).push(r); });
  if (!state.routines.some(r => r.key === selected)) selected = state.routines.find(r => state.entry_routines?.includes(r.key.toLowerCase()))?.key || state.routines.find(r=>r.active)?.key || state.routines[0]?.key || '';
  $('explorer').replaceChildren();
  for (const [name,routines] of groups) {
    const heading = document.createElement('div'); heading.className = 'program'; heading.textContent = '▾ ' + name; $('explorer').append(heading);
    routines.forEach(r => {
      const button = document.createElement('button'); button.className = 'routine' + (selected === r.key ? ' selected' : '');
      button.innerHTML = `<span>${escapeHtml(r.key.split('/')[1])}</span><small>${r.problems.length ? '⚠' : r.kind}</small>`;
      button.onclick = () => { selected = r.key; renderExplorer(); renderLadder(); }; $('explorer').append(button);
    });
  }
  if ($('harness').dataset.project !== report?.source_l5x_sha256) {
    $('harness').replaceChildren();
    state.routines.filter(r=>r.harness!==false).forEach(r => { const option=document.createElement('option');option.value=r.key;option.textContent=r.key;$('harness').append(option); });
    const entry=state.routines.find(r=>state.entry_routines?.includes(r.key.toLowerCase()));
    if(entry)$('harness').value=entry.key;
    $('harness').dataset.project = report?.source_l5x_sha256 || '';
  }
}
function renderTags() {
  const filter = $('filter').value.toLowerCase();
  const strings=new Set(state.tags.filter(t=>t.kind==='string').map(t=>t.name));
  const tags = state.tags.filter(t => {
    if(!t.name.toLowerCase().includes(filter))return false;
    const bytes=t.name.match(/^(.*)\.DATA\[\d+\]$/i);
    return !bytes || !strings.has(bytes[1]) || filter.includes('.data');
  });
  $('tag-count').textContent = state.tags.length; $('tags').replaceChildren();
  tags.slice(0,3000).forEach(tag => {
    const row = document.createElement('div'); row.className='tag-row';
    const name = document.createElement('div'); name.className='tag-name';
    name.innerHTML = `${escapeHtml(tag.name)}<small>${escapeHtml(tag.type)}${tag.aoi_local ? ' · AOI LOCAL' : ''}${tag.unknown ? ' · UNKNOWN' : tag.constant ? ' · CONSTANT' : ''}${tag.alias ? ' · ALIAS' : ''}</small>`;
    row.append(name);
    if (tag.problem) { const problem=document.createElement('span');problem.className='tag-problem';problem.textContent=tag.problem;row.append(problem); }
    else {
      const button=document.createElement('button');button.className='tag-value' + (tag.value === true ? ' on' : '');
      button.textContent = typeof tag.value === 'boolean' ? (tag.value ? '1' : '0') : (tag.kind==='string' && !tag.value ? '∅' : tag.value);
      button.disabled = tag.constant;
      button.onclick = async () => {
        try {
          if (typeof tag.value === 'boolean') await accept(await api('write', {tag:tag.name, value:!tag.value}));
          else { editTag = tag; $('edit-name').textContent=tag.name + ' · ' + tag.type; $('edit-value').value=tag.value; $('edit-dialog').showModal(); $('edit-value').focus(); }
        } catch(e) { error(e); }
      }; row.append(button);
    }
    $('tags').append(row);
  });
  if (tags.length > 3000) {const note=document.createElement('p');note.textContent='Showing first 3,000 results. Narrow the filter.';$('tags').append(note);}
}
function sequence(nodes, events, cursor) {
  const div=document.createElement('div'); div.className='seq';
  for (const node of nodes) {
    const wire=document.createElement('div');wire.className='wire';div.append(wire);
    if (node.branch) {
      const branch=document.createElement('div');branch.className='branch';
      node.branch.forEach(path=>branch.append(sequence(path,events,cursor)));div.append(branch);
    } else {
      const event=events[cursor.value++];
      const op=document.createElement('div');op.className='op' + (event?.out ? ' live' : '') + (report && !recognized(node.name) ? ' bad' : '');
      op.innerHTML=`<div class="op-name">${escapeHtml(node.name)}</div><div class="op-args">${node.args.map(escapeHtml).join('<br>')}</div>`;
      op.title=event ? `Condition in: ${event.in}\nCondition out: ${event.out}` : 'No execution trace for this instruction';div.append(op);
      if(node.name==='JSR'){
        const target=state.routines.find(r=>r.key.toLowerCase()===(selected.split('/')[0]+'/'+node.args[0]).toLowerCase());
        if(target){op.classList.add('call-link');op.setAttribute('role','button');op.setAttribute('tabindex','0');op.setAttribute('aria-label','Open routine '+node.args[0]);op.title+='\nOpen '+target.key;
          op.onclick=()=>{selected=target.key;renderExplorer();renderLadder();};op.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();op.click();}};}
      }
    }
  }
  const wire=document.createElement('div');wire.className='wire';div.append(wire);return div;
}
function renderLadder() {
  const routine=state.routines.find(r=>r.key===selected);if(!routine)return;
  const aoi=routine.key.startsWith('AOI:') ? routine.key.split('/')[0].slice(4) : '';
  const contexts=Object.entries(state.aoi_instances || {}).filter(([name,v])=>v.definition===aoi).map(([name])=>name);
  $('aoi-context').hidden=!aoi;
  if(!contexts.includes(selectedContext))selectedContext=contexts[0] || '';
  $('aoi-context').replaceChildren();
  for(const name of contexts){const option=document.createElement('option');option.value=name;option.textContent=name;$('aoi-context').append(option);}
  $('aoi-context').value=selectedContext;
  $('routine-name').textContent=routine.key; $('routine-type').textContent=routine.kind + (routine.active ? ' · IN EXECUTION SCOPE' : ' · OUTSIDE EXECUTION SCOPE');
  $('rungs').replaceChildren();
  if(routine.kind==='ST'){
    const note=document.createElement('div');note.className='st-note';note.textContent='Structured Text · Green lines executed this scan. Details show the last visit.';$('rungs').append(note);
    for(const line of routine.lines || []){
      const trace=state.trace.findLast(t=>t.routine===routine.key && t.number===line.number && (!aoi || t.context===selectedContext));
      const row=document.createElement('div');row.className='st-row'+(trace ? trace.power ? ' executed' : ' condition-false' : '');
      row.innerHTML=`<span class="st-number">${escapeHtml(line.number.padStart(3,'0'))}</span><code class="st-source">${escapeHtml(line.text) || ' '}</code><span class="st-result">${escapeHtml(trace?.detail || '')}</span>`;
      row.title=trace ? `${trace.statement}: ${trace.detail}` : 'No executed statement starts on this line in the current scan';
      const call=routine.rungs.find(r=>r.number===line.number)?.nodes.find(n=>n.name==='JSR');
      if(call){const target=state.routines.find(r=>r.key.toLowerCase()===(routine.key.split('/')[0]+'/'+call.args[0]).toLowerCase());
        if(target){const button=document.createElement('button');button.className='st-call';button.textContent='↗';button.setAttribute('aria-label','Open routine '+call.args[0]);button.onclick=()=>{selected=target.key;renderExplorer();renderLadder();};row.append(button);}}
      $('rungs').append(row);
    }
    return;
  }
  if (!routine.rungs.length) {const el=document.createElement('p');el.className='limits';el.style.padding='24px';el.textContent=routine.problems.join('\n') || 'No ladder rungs.';$('rungs').append(el);}
  routine.rungs.forEach(rung=>{
    const trace=state.trace.findLast(t=>t.routine===routine.key && t.number===rung.number && (!aoi || t.context===selectedContext));
    const row=document.createElement('div');row.className='rung';
    row.innerHTML=`<div class="rung-meta"><b>${escapeHtml(rung.number.padStart(3,'0'))}</b><span class="rung-comment">${escapeHtml(rung.comment)}</span></div>`;
    const rail=document.createElement('div');rail.className='rail'+(trace?.power ? ' live' : '');rail.append(sequence(rung.nodes,trace?.events || [],{value:0}));row.append(rail);$('rungs').append(row);
  });
}
function renderCoverage() {
  if (!report) return;
  const blocked=state.blockers.length>0;
  $('coverage-body').innerHTML=`<div class="coverage-result ${blocked?'blocked':''}">${blocked ? `${state.blockers.length} blockers prevent execution in this scope.` : 'This scope can execute in the current software model.'}</div>
  ${state.blockers.map(b=>`<div class="issue">${escapeHtml(b)}</div>`).join('')}
  <h3>TASK SCHEDULING</h3><p class="limits">${escapeHtml(report.task_schedule?.policy || '')}</p><div class="chips">${(report.task_schedule?.tasks || []).map(t=>`<span class="chip">${escapeHtml(t.name)} · ${t.inhibited?'inhibited':t.kind==='Continuous'?'background':`${t.rate_ms} ms · priority ${t.priority}`} · ${t.executions} executions · next ${t.next_release_ms??'—'}</span>`).join('') || '<span class="limits">No executable task schedule in this scope.</span>'}</div>
  <h3>STRUCTURED TEXT</h3><p class="limits">${escapeHtml(report.structured_text?.policy || '')}</p><div class="chips">${Object.entries(report.structured_text?.constructs || {}).map(([n,c])=>`<span class="chip">${escapeHtml(n)} × ${c}</span>`).join('') || '<span class="limits">No ST statements in program routines.</span>'}</div>
  <h3>SUBROUTINE PARAMETERS</h3><p class="limits">${escapeHtml(report.routine_parameters?.contract || '')}</p><div class="chips">${Object.entries(report.routine_parameters?.calls || {}).map(([name,v])=>`<span class="chip">${escapeHtml(name)} · ${v.inputs} in / ${v.returns} out</span>`).join('') || '<span class="limits">No JSR calls in this scope.</span>'}</div>
  <h3>ADD-ON INSTRUCTIONS</h3><p class="limits">${report.add_on_instructions?.definitions || 0} definitions · ${(report.add_on_instructions?.active_definitions || []).map(escapeHtml).join(', ') || 'none in execution scope'}<br>${escapeHtml(report.add_on_instructions?.local_state_policy || '')}</p>
  <h3>INSTRUCTION INVENTORY · PROGRAM ROUTINES</h3><div class="chips">${Object.entries(report.instructions).map(([n,c])=>`<span class="chip ${recognized(n)?'':'bad'}">${escapeHtml(n)} × ${c}</span>`).join('')}</div>
  <h3>MODEL LIMITS</h3><ul class="limits">${report.limits.map(x=>`<li>${escapeHtml(x)}</li>`).join('')}</ul>
  <h3>OTHER ROUTINE FINDINGS</h3>${Object.entries(report.project_routine_issues).map(([k,v])=>`<div class="issue"><b>${escapeHtml(k)}</b><br>${v.map(escapeHtml).join('<br>')}</div>`).join('') || '<p class="limits">No parser or instruction findings.</p>'}
  <h3>SOURCE HASH</h3><div class="issue">${escapeHtml(report.source_l5x_sha256)}</div>`;
}
function renderChanges() {
  $('changes-body').innerHTML=state.changes.slice(0,500).map(c=>`<tr><td>${c.scan} / ${c.ms}</td><td>${escapeHtml(c.tag)}</td><td>${escapeHtml(c.before)} → ${escapeHtml(c.after)}</td></tr>`).join('');
}
function selectTab(name) {currentTab=name;document.querySelectorAll('[data-tab]').forEach(b=>b.classList.toggle('active',b.dataset.tab===name));document.querySelectorAll('.tab-content').forEach(panel=>panel.hidden=panel.id!==name);}
async function loadDemo(sample='ConveyorDemo') {$('busy-text').textContent='Opening demo…';$('busy').hidden=false;try{selected='';await accept(await api('demo',{sample}),true);$('mode').value='project';render();}catch(e){error(e);}finally{$('busy').hidden=true;}}
async function scan() {
  if(stepping)return;stepping=true;
  try{await accept(await api('step',{dt:Number($('dt').value),count:1}));}catch(e){error(e);try{const res=await fetch('/api/state',{headers:{'X-Logix-Token':window.LOGIX_TOKEN}});await accept(await res.json());}catch(_){} }finally{stepping=false;}
}
function download(data,name) {const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function downloadL5X(result) {const blob=new Blob([result.content],{type:'application/xml;charset=utf-8'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=result.filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
$('open').onclick=()=>{$('file').value='';$('file').click();};
$('file').onchange=async()=>{
  const file=$('file').files[0];if(!file)return;if(file.size>100000000)return error(new Error('100 MB file limit'));
  $('busy-text').textContent='Importing ' + file.name + '…';$('busy').hidden=false;
  try{const content=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=reject;reader.readAsDataURL(file);});selected='';await accept(await api('load',{name:file.name,content}),true);$('mode').value='project';const task=state.tasks[0];if(state.tasks.length===1&&task?.type==='Periodic'&&!task.inhibited)$('dt').value=Number(task.rate);render();if(state.blockers.length)selectTab('coverage');}catch(e){error(e);}finally{$('busy').hidden=true;}
};
$('demo').onclick=()=>loadDemo();$('welcome-demo').onclick=()=>loadDemo();$('data-demo').onclick=()=>loadDemo('DataLab');$('task-demo').onclick=()=>loadDemo('TaskLab');$('system-demo').onclick=()=>loadDemo('SystemLab');$('aoi-demo').onclick=()=>loadDemo('AOILab');
$('call-demo').onclick=()=>loadDemo('CallLab');
$('text-demo').onclick=()=>loadDemo('TextLab');
$('string-demo').onclick=()=>loadDemo('StringLab');
$('control-demo').onclick=()=>loadDemo('ControlLab');
$('sequence-demo').onclick=()=>loadDemo('SequenceLab');
$('conversion-demo').onclick=()=>loadDemo('ConversionLab');
$('math-demo').onclick=()=>loadDemo('MathLab');
$('stats-demo').onclick=()=>loadDemo('StatsLab');
$('network-demo').onclick=()=>loadDemo('NetworkLab');
$('structure-demo').onclick=()=>loadDemo('StructureLab');
$('layout-demo').onclick=()=>loadDemo('LayoutLab');
$('flag-demo').onclick=()=>loadDemo('FlagLab');
$('integer-demo').onclick=()=>loadDemo('IntegerLab');
$('bit-demo').onclick=()=>loadDemo('BitLab');
$('aoi-context').onchange=()=>{selectedContext=$('aoi-context').value;renderLadder();};
$('step').onclick=scan;
  $('device-apply').onclick=async()=>{try{await accept(await api('device-io-configure',{allow_writes:$('device-writes').checked}));}catch(e){error(e);}};
$('run').onclick=async()=>{if(modePending)return;modePending=true;let failure=null;render();try{
  await accept(await api('controller-mode',{mode:running?'Program':'Run',dt:Number($('dt').value)}));
}catch(e){failure=e;}finally{modePending=false;render();if(failure)error(failure);}};
$('reset').onclick=async()=>{try{await accept(await api('reset'),true);}catch(e){error(e);}};
$('mode').onchange=()=>{$('harness').disabled=$('mode').value!=='routine';};
$('apply').onclick=async()=>{try{await accept(await api('configure',{mode:$('mode').value,routine:$('harness').value}),true);}catch(e){error(e);}};
$('filter').oninput=()=>{if(state?.loaded)renderTags();};
document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>selectTab(b.dataset.tab));
$('settings').onclick=()=>{$('converter').value=state?.converter || '';$('settings-dialog').showModal();};
$('cancel-settings').onclick=()=>$('settings-dialog').close();
$('save-settings').onclick=async()=>{try{await accept(await api('settings',{converter:$('converter').value}));$('settings-dialog').close();}catch(e){error(e);}};
$('cancel-edit').onclick=()=>$('edit-dialog').close();
$('save-edit').onclick=async()=>{try{let value=$('edit-value').value;if(editTag.kind==='integer_text'){if(!/^[+-]?\d+$/.test(value))throw new Error('Enter an integer in decimal notation');}else if(editTag.kind!=='string'){value=Number(value);if(!Number.isFinite(value))throw new Error('Enter a finite numeric value');}await accept(await api('write',{tag:editTag.name,value}));$('edit-dialog').close();}catch(e){error(e);}};
$('edit-value').onkeydown=e=>{if(e.key==='Enter')$('save-edit').click();};
$('report').onclick=async()=>{try{download(await api('report'),'LogixLab-coverage.json');}catch(e){error(e);}};
$('quit').onclick=async()=>{clearInterval(connectivityPoll);clearLocator();try{
  await api('quit');$('plc-address').dataset.active='false';$('plc-address').textContent='PLC endpoint stopped';
  $('alert').hidden=false;$('alert').textContent=state?.execution_environment==='vmware-host-only'
    ?'Session ended. You can close this tab. Run START-VM.cmd to start the appliance again.'
    :'Session ended. You can close this tab. Launch LogixLab.exe to start again.';
  document.querySelectorAll('button').forEach(b=>b.disabled=true);
}catch(e){error(e);}};
$('snapshot').onclick=async()=>{try{download(await api('snapshot'),'LogixLab-snapshot.json');}catch(e){error(e);}};
$('save-logic').onclick=async()=>{try{downloadL5X(await api('export-edited-l5x'));}catch(e){error(e);}};
window.addEventListener('beforeunload',()=>{clearInterval(connectivityPoll);clearLocator();});
fetch('/api/state',{headers:{'X-Logix-Token':window.LOGIX_TOKEN}}).then(r=>r.json()).then(async value=>{if(value.loaded){$('mode').value=value.mode;await accept(value,true);}else{state=value;render();}}).catch(error);

function clearLocator() {
  clearInterval(locatorTimer);locatorTimer=null;locatorRequest=null;
  $('device-locator').hidden=true;$('locator-time').textContent='';
}
function updateLocator() {
  const seconds=Math.max(0,Math.ceil((locatorDeadline-performance.now())/1000));
  if(!seconds){clearLocator();return;}
  $('locator-time').textContent=`${seconds} s remaining`;
}
function renderLocator(c) {
  const locator=c.locator;
  if(!c.enabled||!locator?.active||!Number.isFinite(locator.remaining_ms)||locator.remaining_ms<=0){clearLocator();return;}
  locatorDeadline=performance.now()+locator.remaining_ms;
  if(locator.request_id!==locatorRequest||locatorTimer===null){
    locatorRequest=locator.request_id;
    const elapsed=Number.isFinite(locator.elapsed_ms)?Math.max(0,locator.elapsed_ms):0;
    $('device-locator').style.animationDelay=`-${elapsed%1500}ms`;
    if(locatorTimer===null)locatorTimer=setInterval(updateLocator,250);
  }
  $('device-locator').hidden=false;updateLocator();
}
function renderConnectivity() {
  const c=state?.connectivity || {};const active=!!c.enabled;
  $('plc-address').textContent=c.bind_address?`PLC IP ${c.bind_address}${active?'':' · stopped'}`:'PLC endpoint off';
  $('plc-address').dataset.active=String(active);
  $('plc-address').title=c.address?`${c.address} · TCP + UDP · slot 0`:'Start an endpoint in Connectivity.';
  renderLocator(c);
  $('eip-badge').textContent=active?'LISTENING':'STOPPED';$('eip-badge').className='badge'+(active?' ready':'');
  $('eip-start').disabled=!state?.loaded||active;$('eip-stop').disabled=!active;
  $('eip-bind').disabled=active;$('eip-port').disabled=active;$('eip-profile').disabled=active;$('eip-native').disabled=active;$('eip-writes').disabled=active||$('eip-native').checked;$('eip-trace').disabled=!c.trace_events;
  if(active){$('eip-profile').value=c.profile;$('eip-bind').value=c.bind_address;$('eip-port').value=c.address.split(':').at(-1);$('eip-writes').checked=c.allow_writes;$('eip-native').checked=!!c.native_session?.enabled;}
  $('eip-refresh').disabled=!state?.loaded;
  $('studio-tag-writes').checked=!!state?.native_tag_writes?.enabled;
  $('studio-tag-writes').disabled=!state?.loaded||!c.native_session?.enabled||!!state?.controller?.running||!!c.active_tcp_clients;
  $('studio-edits').checked=!!state?.routine_edits?.enabled;
  $('studio-edits').disabled=!state?.loaded||!!state?.controller?.running||!!c.active_tcp_clients;
  $('studio-edit-state').textContent=(state?.routine_edits?.modified?`Edited logic revision ${state.routine_edits.revision}. Use Save edited L5X to keep a working copy. `:'')+'Enable before connecting Studio. Program mode, standard ladder routines; changes stay in memory until saved as L5X.';
  $('eip-address').textContent=(c.address||'127.0.0.1:44818')+' · TCP + UDP · slot 0';
  $('eip-summary').textContent=(active?'Accepting clients':'Endpoint stopped')+' · '+(c.allow_writes?'tag writes enabled':c.native_session?.tag_writes?'Studio scalar writes enabled':'tag reads only')+(c.native_session?.enabled?' · native mode '+c.native_session.controller_mode+' · anonymous compatibility; authentication unverified':'')+(c.native_symbols?.bound?' · '+c.native_symbols.symbols+' ACD symbol IDs · '+c.native_symbols.programs+' program IDs':'')+(c.native_programming_lease?' · native transfer lock '+(!c.native_programming_lease.available?'unavailable':c.native_programming_lease.owned?'held':'free')+(c.native_programming_lease.scan_inhibited?' · scans inhibited':'')+'; project transfer unsupported':'')+' · '+(c.active_tcp_clients||0)+' TCP clients · '+(c.trace_events||0)+' trace events';
  if(c.native_programming_lease?.preparation_state==='ready') $('eip-summary').textContent+=' · native preparation ready';
  const staged=c.native_programming_lease?.library_staging?.instances||0;
  if(staged) $('eip-summary').textContent+=` · ${staged} staged library descriptors; library data unsupported`;
  const stagedMetadata=c.native_programming_lease?.metadata_staging?.instances||0;
  if(stagedMetadata) $('eip-summary').textContent+=` · ${stagedMetadata} staged metadata definitions · ${c.native_programming_lease.metadata_staging.value_count||0} staged definition values; project commit unsupported`;
  const discovery=c.discovery||{};
  $('eip-discovery').textContent=!active?'Start the endpoint to check broadcast discovery.':discovery.broadcast_enabled?
    `Broadcast discovery: ${discovery.broadcast_addresses.join(', ')} · ${discovery.interface}`:
    `Unicast discovery only · ${discovery.reason||'Broadcast discovery unavailable'}`;
  const identity=c.identity;
  $('eip-identity').textContent=identity ? `${identity.product_name} · revision ${identity.revision.major}.${identity.revision.minor} · virtual hardware ${identity.hardware_revision?.major ?? '?'}.${identity.hardware_revision?.minor ?? '?'} · virtual firmware build ${identity.firmware_build ?? '?'} · experimental profile · research serial ${identity.serial}. Studio Go Online remains unverified.` : 'The research identity is the default. The experimental L85E profile requires a matching v35 source project. Studio Go Online remains unverified.';
  $('eip-counts').innerHTML=Object.entries(c.counts||{}).map(([k,v])=>`<span class="chip">${escapeHtml(k)} × ${v}</span>`).join('')||'<span class="limits">No requests recorded.</span>';
  $('eip-unsupported').innerHTML=(c.unsupported||[]).map(x=>`<div class="issue">${escapeHtml(x.request)} × ${x.count}</div>`).join('')||'No unsupported requests recorded.';
  const rejected=c.native_rejections||[];
  const rejectionReasons={unbound_context:'Compatibility context is not bound',unsupported_probe:'Probe is not implemented',read_only_policy:'Service is outside the native read-only policy',source_correlation_unavailable:'Source correlation is unavailable',invalid_request:'Unsupported or malformed path or request',compatibility_context:'Compatibility context or source metadata is unavailable',programming_lease_conflict:'Another native client holds the transfer lock',programming_lease_owner_required:'This operation requires the client that owns the transfer lock'};
  Object.assign(rejectionReasons,{run_mode_inhibit_required:'The owning client must inhibit scans before preparation',programming_preparation_required:'The owning client must complete preparation first',configuration_change_not_permitted:'This acknowledgement cannot change configuration',source_configuration_unavailable:'The source does not establish the supported configuration'});
  Object.assign(rejectionReasons,{library_type_not_permitted:'This library type is unsupported',library_stage_conflict:'A staged descriptor conflicts with this request',library_stage_full:'The library descriptor limit has been reached',library_stage_missing:'The staged descriptor does not exist'});
  Object.assign(rejectionReasons,{metadata_stage_conflict:'A staged metadata definition conflicts with this request',metadata_stage_full:'The metadata definition limit has been reached',metadata_stage_missing:'The staged metadata definition does not exist',metadata_values_not_permitted:'The metadata target is outside staged definitions',metadata_value_selector_not_permitted:'The metadata selector is unsupported',metadata_value_type_not_permitted:'The metadata value type is unsupported',metadata_value_conflict:'A staged metadata value conflicts with this request',metadata_values_full:'The metadata value limit has been reached'});
  $('eip-native-rejections').innerHTML=rejected.slice(0,8).map(x=>{
    const target=x.class_id==null?(x.symbolic?'Symbolic path':'Unparsed path'):`Class 0x${x.class_id.toString(16).toUpperCase()}, instance ${x.instance}`;
    const service=`0x${x.service.toString(16).toUpperCase()}`, status=`0x${x.status.toString(16).toUpperCase()}`;
    const scope=x.aoi_instance!=null?` · AOI instance ${x.aoi_instance}`:x.controller_instance!=null?` · Controller instance ${x.controller_instance}`:x.io_map_instance!=null?` · I/O Map instance ${x.io_map_instance}`:x.program_instance==null?'':` · Program instance ${x.program_instance}`;
    return `<div class="issue">${escapeHtml(target+scope)} · service ${escapeHtml(service)} · status ${escapeHtml(status)}<br>${escapeHtml(rejectionReasons[x.reason]||x.reason)} × ${x.count}</div>`;
  }).join('')||'No native policy rejections recorded.';
  if(rejected.length>8)$('eip-native-rejections').innerHTML+=`<p>${rejected.length-8} more groups in the protocol trace.</p>`;
  const gaps=c.attribute_gaps||[];
  $('eip-attribute-gaps').innerHTML=gaps.slice(0,8).map(x=>{
    const target=`${x.class_name} (0x${x.class_id.toString(16).toUpperCase()}), instance ${x.instance}`;
    const scope=x.scope||(x.aoi_instance!=null?`AOI instance ${x.aoi_instance}`:x.controller_instance!=null?`Controller instance ${x.controller_instance}`:x.io_map_instance!=null?`I/O Map instance ${x.io_map_instance}`:x.program_instance!=null?`Program instance ${x.program_instance}`:'Controller scope');
    const fields=x.attributes.map(a=>`${a.name} (${a.id}, status 0x14)`).join(', ');
    return `<div class="issue">${escapeHtml(target)} · ${escapeHtml(scope)}<br>${escapeHtml(fields)} × ${x.count}</div>`;
  }).join('')||'No unsupported attribute reads recorded.';
  if(gaps.length>8)$('eip-attribute-gaps').innerHTML+=`<p>${gaps.length-8} more groups in the protocol trace.</p>`;
}
$('eip-native').onchange=()=>{if($('eip-native').checked){$('eip-writes').checked=false;$('eip-profile').value='logix-v35-l85e';}$('eip-writes').disabled=$('eip-native').checked;};
$('eip-start').onclick=async()=>{try{await accept(await api('connectivity-start',{port:Number($('eip-port').value),bind_address:$('eip-bind').value.trim(),profile:$('eip-profile').value,allow_writes:$('eip-writes').checked,native_read_only:$('eip-native').checked}));}catch(e){error(e);}};
$('studio-tag-writes').onchange=async()=>{try{await accept(await api('native-tag-writes-configure',{allow_writes:$('studio-tag-writes').checked}));}catch(e){error(e);}};
$('studio-edits').onchange=async()=>{try{await accept(await api('routine-edits-configure',{allow_writes:$('studio-edits').checked}));}catch(e){error(e);}};
$('eip-stop').onclick=async()=>{try{await accept(await api('connectivity-stop'));}catch(e){error(e);}};
$('eip-refresh').onclick=async()=>{try{await accept(await api('observe'));}catch(e){error(e);}};
$('eip-trace').onclick=async()=>{try{download(await api('connectivity-trace'),'LogixLab-protocol-trace.json');}catch(e){error(e);}};
connectivityPoll=setInterval(async()=>{if(state?.loaded&&!stepping&&!modePending&&!observing){observing=true;try{await accept(await api('observe'));}catch(_){}finally{observing=false;}}},500);
