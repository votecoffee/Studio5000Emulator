'use strict';
const $ = id => document.getElementById(id);
let state = null, selected = '', selectedContext = '', running = false, stepping = false, modePending = false, observing = false, currentTab = 'ladder', report = null, editTag = null;
let connectivityPoll = null;
let moduleFormGeneration, modulePending = false;
const moduleStatusLabels = {4096:'Faulted',16384:'Running',24576:'Inhibited',28672:'Waiting'};
const moduleInputLabels = {clear:'Cleared',running:'Running',faulted:'Faulted'};
let locatorTimer = null, locatorRequest = null, locatorDeadline = 0;
const ladderDrafts = new Map();
let editingDraft = null, draftFileRequest = 0, draftCheckRequest = 0, draftApplyPending = false;
let displayedDraftCatalog;
const draftReviewDialog = $('ladder-draft-review-dialog');
let displayedReviewRungs;
const recognized = name => report?.supported_instructions.includes(name) || report?.known_add_on_instructions?.includes(name) || report?.function_blocks?.instructions?.includes(name);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const logicView = LogixLogicView.create({canvas: $('rungs'), inspector: $('instruction-inspector'), status: $('logic-status'),
  onOpenRoutine(key, context) {selected=key;if(context!==undefined)selectedContext=context;renderExplorer();renderLadder();},
  onZoom(value) {updateZoom(value);},
  onDraftInsert(rung, gap) {return changeDraft(draft => draft.insert(rung, gap, $('ladder-draft-palette').value));},
  onDraftOperands(rung, id, operands) {return changeDraft(draft => draft.setOperands(rung, id, operands));},
  onDraftRemove(rung, id) {return changeDraft(draft => draft.remove(rung, id));},
  onDraftMove(from, id, to, gap) {return changeDraft(draft => draft.move(from, id, to, gap));},
  onDraftResize(rung, id, gap) {return changeDraft(draft => draft.resize(rung, id, gap));},
  onDraftAddLeg(rung, id) {return changeDraft(draft => draft.addLeg(rung, id));},
  onDraftRemoveLeg(rung, id, leg) {return changeDraft(draft => draft.removeLeg(rung, id, leg));},
  onDraftInsertRung(index) {return changeDraft(draft => draft.insertRung(index));},
  onDraftDuplicateRung(index) {return changeDraft(draft => draft.duplicateRung(index));},
  onDraftRemoveRung(index) {return changeDraft(draft => draft.removeRung(index));},
  onDraftMoveRung(index) {openDraftRungMove(index);},
  onDraftComment(index) {openDraftComment(index);}});
let logicZoom = 1;
function updateZoom(value) {
  logicZoom=value;const percent=Math.round(value*100), select=$('logic-zoom');
  if(![...select.options].some(option=>option.value===String(percent)))select.add(new Option(percent+'%',String(percent)));
  select.value=String(percent);
}
$('logic-zoom').onchange=()=>updateZoom(logicView.zoom(Number($('logic-zoom').value)/100));
$('logic-zoom-in').onclick=()=>updateZoom(logicView.zoom(logicZoom*1.25));
$('logic-zoom-out').onclick=()=>updateZoom(logicView.zoom(logicZoom/1.25));
$('logic-fit').onclick=()=>updateZoom(logicView.fit());
$('logic-values').onchange=()=>logicView.values($('logic-values').checked);
$('logic-comments').onchange=()=>logicView.comments($('logic-comments').checked);
$('ladder-draft-mode').onclick = () => {
  const routine = state?.routines?.find(row => row.key === selected);
  const catalog = currentDraftCatalog();
  if (!catalog || !LogixLadderDraft.canEdit(routine)) return;
  const key = draftIdentity(routine);
  setDraftFileStatus('');
  ++draftFileRequest;
  clearDraftCheck();
  if (editingDraft === key) editingDraft = null;
  else {
    if (!ladderDrafts.has(key)) ladderDrafts.set(key, LogixLadderDraft.create(routine, catalog));
    editingDraft = key;
  }
  renderLadder();
};
$('ladder-draft-undo').onclick = () => changeDraft(draft => draft.undo());
$('ladder-draft-redo').onclick = () => changeDraft(draft => draft.redo());
$('ladder-draft-append').onclick = () => {
  const index = ladderDrafts.get(editingDraft)?.rungs.length;
  if (changeDraft(draft => draft.insertRung(index))) logicView.focusDraftRung(index, '.lv-draft-gap');
};
$('ladder-draft-save').onclick = () => {
  const draft = ladderDrafts.get(editingDraft);
  if (!draft?.changed) return;
  download(draftDocument(draft), selected.replace(/[^a-z0-9_-]+/gi, '-') + '.ladder-draft.json');
};
$('ladder-draft-review').onclick = () => {
  const draft = ladderDrafts.get(editingDraft);
  if (!draft?.changed || draftApplyPending) return;
  renderDraftReview(draft);
  draftReviewDialog.showModal();
};
draftReviewDialog.onclose = () => {
  if (draftReviewDialog.open) return;
  displayedReviewRungs = null;
  $('ladder-draft-review-rows').replaceChildren();
};
$('ladder-draft-validate').onclick = async () => {
  const key = editingDraft, draft = ladderDrafts.get(key);
  if (!draft) return;
  const request = ++draftCheckRequest;
  const isCurrent = () => request === draftCheckRequest && draftIsActive(key, draft);
  showDraftCheck('Checking draft…', [], true);
  try {
    const result = await api('ladder-draft-validate', {project_generation: state.project_generation, draft: draftDocument(draft)});
    if (!isCurrent()) return;
    showDraftCheck(result.valid ? 'Draft passed execution preflight' : 'Draft has execution blockers', result.diagnostics);
  } catch (error) {
    if (isCurrent()) showDraftCheck('Draft validation failed', [error.message]);
  }
};
$('ladder-draft-apply').onclick = async () => {
  const key = editingDraft, draft = ladderDrafts.get(key);
  if (!draft?.changed || draftApplyPending || !draftApplyAllowed()) return;
  const proposed = draftDocument(draft);
  draftApplyPending = true;
  ++draftFileRequest;
  ++draftCheckRequest;
  setDraftFileStatus('');
  showDraftCheck('Applying draft…', [], true);
  render();
  try {
    const next = await api('ladder-draft-apply', {project_generation: state.project_generation, draft: proposed});
    ladderDrafts.delete(key);
    if (editingDraft === key) editingDraft = null;
    await accept(next, true);
    showDraftCheck('Draft applied · Save edited L5X to keep a working copy');
  } catch (error) {
    if (draftIsActive(key, draft)) showDraftCheck('Draft could not be applied', [error.message]);
  } finally {
    draftApplyPending = false;
    $('ladder-draft-validate').disabled = false;
    render();
  }
};
$('ladder-draft-open').onclick = () => $('ladder-draft-file').click();
$('ladder-draft-file').onchange = async event => {
  const file = event.target.files[0], key = editingDraft, draft = ladderDrafts.get(key);
  event.target.value = '';
  if (!file || !draft || draftApplyPending) return;
  const request = ++draftFileRequest;
  const projectGeneration = state.project_generation;
  const routine = selected;
  const isCurrent = () => request === draftFileRequest && draftIsActive(key, draft);
  setDraftFileStatus('Opening draft…');
  try {
    const source = await file.text();
    if (!isCurrent()) return;
    let saved;
    try {saved = JSON.parse(source.replace(/^\uFEFF/, ''));}
    catch {throw new Error('The selected draft file is not valid JSON');}
    if (saved?.format === 'logixlab-rll-draft' && saved.routine !== routine) {
      throw new Error('Open this draft from its original ladder routine');
    }
    const restored = await api('ladder-draft-open', {project_generation: projectGeneration, draft: saved});
    if (!isCurrent()) return;
    const changed = changeDraft(active => active.restore(restored.rungs));
    setDraftFileStatus(changed ? 'Draft opened · Undo restores the previous draft' : 'Draft already matches this file');
  } catch (error) {
    if (isCurrent()) setDraftFileStatus(error.message, true);
  }
};
$('ladder-draft-discard').onclick = () => {
  if (!ladderDrafts.get(editingDraft) || !window.confirm('Discard this routine draft?')) return;
  ladderDrafts.delete(editingDraft);editingDraft = null;
  ++draftFileRequest;
  setDraftFileStatus('');
  clearDraftCheck();
  renderLadder();
};
$('ladder').addEventListener('keydown', event => {
  if (editingDraft === null || !(event.ctrlKey || event.metaKey) || event.altKey ||
      event.target.closest('input, select, textarea, [contenteditable]')) return;
  const key = event.key.toLowerCase();
  if (key !== 'z' && key !== 'y') return;
  event.preventDefault();
  changeDraft(draft => key === 'y' || event.shiftKey ? draft.redo() : draft.undo());
});
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
function selectedModule() {
  return state?.module_simulation?.find(module=>module.name===$('module-name').value);
}
function loadModuleInput() {
  const input = selectedModule()?.input;
  $('module-input').value = input?.state ?? 'clear';
  $('module-fault-code').value = input?.state === 'faulted' ? input.fault_code : 516;
  $('module-fault-info').value = input?.fault_info ?? 0;
  $('module-connection-feedback').textContent = '';
}
function renderModuleSimulation() {
  const modules = state?.module_simulation ?? [];
  if (moduleFormGeneration !== state?.project_generation) {
    moduleFormGeneration = state?.project_generation;
    $('module-name').replaceChildren(...modules.map(module=>new Option(module.label,module.name)));
    loadModuleInput();
  }
  const module = selectedModule();
  $('module-connection-form').hidden = !module;
  $('module-simulation-empty').hidden = !!module;
  if (!module) return;
  const inhibited = !!state.connectivity?.native_programming_lease?.scan_inhibited;
  const faulted = $('module-input').value === 'faulted';
  $('module-fault-fields').hidden = !faulted;
  $('module-name').disabled = $('module-input').disabled = modulePending;
  $('module-fault-code').disabled = $('module-fault-info').disabled = !faulted || modulePending;
  $('module-apply').disabled = modulePending || inhibited;
  const input = module.input;
  const diagnostics = input.state === 'faulted'
    ? ' (0x' + input.fault_code.toString(16).toUpperCase().padStart(4,'0') + ', info ' + input.fault_info + ')' : '';
  $('module-connection-summary').textContent = 'Input ' + moduleInputLabels[input.state] + diagnostics
    + ' · Effective ' + (moduleStatusLabels[module.entry_status] ?? 'Unknown')
    + (module.major_fault_on_loss ? ' · Required in Run' : '');
}
function renderOutputSamples(panel, field, rows, label) {
  $(panel).hidden = !rows.length;
  $(field).textContent = rows.map(row => [
    row.module, row.tag, row.task, 'Scan ' + row.scan, row.simulation_ms + ' ms', label + ' ' + row.sequence,
  ].filter(Boolean).join(' · ') + '\n' + JSON.stringify(row.value)).join('\n\n');
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
  ['reset','step','run','apply','snapshot','report','mode','logic-fit','logic-zoom','logic-zoom-in','logic-zoom-out','logic-values','logic-comments'].forEach(id => $(id).disabled = !loaded);
  $('save-logic').disabled=!loaded||running||!state?.routine_edits?.l5x_export_available||!!state?.connectivity?.native_programming_lease?.owned;
  $('harness').disabled = !loaded || $('mode').value !== 'routine';
  renderConnectivity();
  renderModuleSimulation();
  renderOutputSamples('immediate-outputs', 'immediate-output-values', state?.immediate_outputs || [], 'Send');
  renderOutputSamples('task-outputs', 'task-output-values', state?.task_outputs || [], 'Sample');
  const device=state?.device_io||{};
  $('device-badge').textContent=device.writes_enabled?'EXTERNAL TAG WRITES ENABLED':'EXTERNAL TAGS READ ONLY';
  $('device-writes').checked=!!device.writes_enabled;
  $('device-api').textContent=location.origin+'/api/device-io/snapshot';
  $('device-summary').textContent=`Snapshot ${device.snapshot_sequence||0} · ${device.pending_writes||0}/${device.queue_capacity||64} queued input batches · apply between scans`;
  const moduleFault = state?.controller?.module_major_fault;
  $('clear-module-fault').hidden = !moduleFault;
  if (!loaded) {
    if (draftReviewDialog.open) draftReviewDialog.close();
    return;
  }
  $('project-name').textContent = state.name;
  $('project-detail').textContent = `Studio 5000 v${state.version} · ${state.processor} · ${state.routines.length} routines · ${state.mode === 'routine' ? 'isolated routine harness' : 'whole project'}`;
  $('scan').textContent = state.scan.toLocaleString(); $('time').textContent = state.ms.toLocaleString();
  $('routine-count').textContent = state.routines.length;
  const blocked = state.blockers.length > 0;
  const inhibited=!!state.connectivity?.native_programming_lease?.scan_inhibited;
  $('clear-module-fault').disabled = modePending || inhibited || !moduleFault?.clear_ready;
  $('status').textContent = moduleFault ? `I/O MAJOR FAULT · ${moduleFault.type}/${moduleFault.code}` : state.fault ? 'FAULT · ROLLED BACK' : blocked ? 'EXECUTION BLOCKED' : inhibited ? 'SCANS INHIBITED' : running ? 'REMOTE RUN' : 'REMOTE PROGRAM';
  $('status').className = 'badge ' + (blocked || inhibited || state.fault ? 'blocked' : 'ready');
  $('step').disabled = blocked||inhibited||running||modePending||draftApplyPending||!!moduleFault;
  $('run').disabled = modePending||draftApplyPending||(!running&&(blocked||inhibited||!!state.fault));
  $('run').textContent = running ? '■ Program' : '▶ Run';
  const schedule=state.task_schedule?.tasks;
  const fixedPeriod=schedule?.length===1&&!schedule[0].source_inhibited?schedule[0].rate_ms:null;
  $('dt').disabled = running||modePending||!!fixedPeriod;
  if(running||fixedPeriod)$('dt').value=fixedPeriod||state.controller.scan_interval_ms;
  $('scope-note').textContent = state.mode === 'routine' ? 'Harness: selected routine and called routines only.' : `${state.tasks.length} modeled task(s) · deterministic periodic releases · serial execution.`;
  const clearedFault = state.controller.last_cleared_module_fault;
  const clearedProgramFault = state.controller.last_cleared_program_fault;
  if (clearedProgramFault && (!clearedFault || clearedProgramFault.timestamp_us >= clearedFault.timestamp_us)) {
    $('scope-note').textContent = `Last handler clear · Program fault ${clearedProgramFault.type}/${clearedProgramFault.code} · ${clearedProgramFault.handler.routine} · skipped ${clearedProgramFault.instruction}`;
  } else if (running && clearedFault) {
    $('scope-note').textContent = `Last handler clear · I/O fault ${clearedFault.type}/${clearedFault.code} · ${clearedFault.handler.routine}`;
  }
  $('alert').hidden = !(blocked || inhibited || state.fault);
  $('alert').textContent = state.fault || (blocked ? `${state.blockers.length} execution blocker(s). Open Coverage for details.\n${state.blockers.slice(0,3).join('\n')}` : inhibited?'Native programming preparation inhibits scans. Release or disconnect the owning client to resume.':'');
  if (moduleFault) {
    const handler = moduleFault.handler;
    if (handler) {
      $('alert').textContent += handler.status === 'completed'
        ? ` Controller fault handler ${handler.routine} completed.`
        : ` Controller fault handler ${handler.routine} rolled back. ${handler.error}`;
    }
    const recovery = moduleFault.upstream_module ? 'the upstream and required modules' : 'the module';
    $('alert').textContent += moduleFault.clear_ready
      ? ' Clear the fault to return to Program with current tag values.'
      : ` Restore ${recovery} to effective Running in Device I/O, then clear the fault.`;
  }
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
function setDraftFileStatus(message, failed = false) {
  const status = $('ladder-draft-file-status');
  status.textContent = message;
  status.classList.toggle('failed', failed);
}
function draftDocument(draft) {
  return {format: 'logixlab-rll-draft', version: 3, routine: selected,
    source_sha256: state.source_sha256, base_revision: state.routine_edits?.revision ?? 0,
    base_logic_sha256: state.routine_edits?.logic_sha256 ?? null,
    rungs: draft.rungs.map(({base_index, comment, text}) => ({base_index, comment, text}))};
}
function openDraftComment(index) {
  const key = editingDraft, draft = ladderDrafts.get(key), row = draft?.rungs[index];
  if (!row || draftApplyPending) return;
  const dialog = $('ladder-comment-dialog'), input = $('ladder-comment-text');
  $('ladder-comment-heading').textContent = 'Edit comment for rung ' + row.number;
  input.value = row.comment;
  $('ladder-comment-form').onsubmit = event => {
    event.preventDefault();
    dialog.close();
    if (event.submitter?.value === 'cancel' || !draftIsActive(key, draft)) return;
    const current = draft.rungs.findIndex(item => item.draftRungId === row.draftRungId);
    if (changeDraft(active => active.setComment(current, input.value))) {
      logicView.focusDraftRung(current, '[data-rung-action="comment"]');
    }
  };
  dialog.showModal();
}
function openDraftRungMove(index) {
  const key = editingDraft, draft = ladderDrafts.get(key), rungs = draft?.rungs;
  if (!rungs?.[index] || rungs.length < 2 || draftApplyPending) return;
  const dialog = $('ladder-rung-move-dialog'), destination = $('ladder-rung-destination');
  $('ladder-rung-move-heading').textContent = 'Move rung ' + rungs[index].number;
  const placeholder = new Option('Choose a destination', '');
  placeholder.disabled = true;
  destination.replaceChildren(placeholder);
  const remaining = rungs.filter((_, position) => position !== index);
  for (let to = 0; to <= remaining.length; to++) {
    if (to === index) continue;
    const label = remaining[to] ? 'Before rung ' + remaining[to].number : 'End of routine';
    destination.add(new Option(label, String(to)));
  }
  destination.value = '';
  $('ladder-rung-move-form').onsubmit = event => {
    event.preventDefault();
    dialog.close();
    if (event.submitter?.value === 'cancel' || !destination.value || !draftIsActive(key, draft) || draft.rungs !== rungs) return;
    const to = Number(destination.value);
    if (changeDraft(active => active.moveRung(index, to))) {
      logicView.focusDraftRung(to, '[data-rung-action="move"]');
    }
  };
  dialog.showModal();
}
function draftReviewColumn(side, rung, showComment) {
  const column = document.createElement('div'), heading = document.createElement('h4');
  heading.textContent = side + ' rung ' + rung.number;
  const logic = document.createElement('pre');
  logic.textContent = rung.text;
  column.append(heading, logic);
  if (showComment) {
    const comment = document.createElement('p');
    comment.className = 'lv-draft-review-comment';
    comment.textContent = rung.comment || 'No comment';
    column.append(comment);
  }
  return column;
}
function renderDraftReview(draft) {
  displayedReviewRungs = draft.rungs;
  $('ladder-draft-review-routine').textContent = selected;
  const counts = {added: 0, removed: 0, edited: 0, reordered: 0, renumbered: 0};
  const numberChanges = [], content = document.createDocumentFragment();
  for (const item of draft.review()) {
    counts[item.kind]++;
    if (item.kind === 'renumbered') {
      numberChanges.push(item);
      continue;
    }
    const row = document.createElement('article'), header = document.createElement('div');
    row.dataset.reviewKind = item.kind;
    header.className = 'lv-draft-review-row-head';
    const heading = document.createElement('h3');
    let label = item.kind[0].toUpperCase() + item.kind.slice(1);
    if (item.kind === 'edited') {
      label = item.logic && item.comment ? 'Logic and comment changed' : item.logic ? 'Logic changed' : 'Comment changed';
      if (item.reordered) label += ' · Reordered';
    }
    heading.textContent = label;
    header.append(heading);
    if (item.after) {
      const jump = document.createElement('button');
      jump.type = 'button';
      jump.textContent = 'Go to rung ' + item.after.number;
      jump.onclick = () => {
        draftReviewDialog.close();
        logicView.focusDraftRung(item.index, '.lv-draft-gap');
      };
      header.append(jump);
    }
    const columns = document.createElement('div');
    columns.className = 'lv-draft-review-columns';
    const showComment = item.before?.comment || item.after?.comment;
    if (item.before) columns.append(draftReviewColumn('Loaded', item.before, showComment));
    if (item.after) columns.append(draftReviewColumn('Draft', item.after, showComment));
    row.append(header, columns);
    content.append(row);
  }
  if (numberChanges.length) {
    const numbering = document.createElement('details'), label = document.createElement('summary');
    numbering.className = 'lv-draft-review-numbering';
    label.textContent = 'Renumbering only';
    numbering.append(label);
    numbering.addEventListener('toggle', () => {
      if (!numbering.open || numbering.children.length !== 1) return;
      const list = document.createElement('ul');
      for (const {from, to} of numberChanges) {
        const li = document.createElement('li');
        li.textContent = `Loaded rung ${from} → Draft rung ${to}`;
        list.append(li);
      }
      numbering.append(list);
    });
    content.append(numbering);
  }
  $('ladder-draft-review-summary').textContent = Object.entries(counts).filter(([, count]) => count)
    .map(([kind, count]) => `${count} ${kind}`).join(' · ') || 'No changes in this draft.';
  $('ladder-draft-review-rows').replaceChildren(content);
}
function showDraftCheck(message, diagnostics = [], pending = false) {
  const section = $('ladder-draft-validation'), details = $('ladder-draft-diagnostics');
  section.hidden = !message;
  section.classList.toggle('failed', diagnostics.length > 0);
  $('ladder-draft-validation-status').textContent = message;
  const items = document.createDocumentFragment();
  for (const diagnostic of diagnostics) {
    const row = document.createElement('li');
    row.textContent = diagnostic;
    items.append(row);
  }
  details.replaceChildren(items);
  details.hidden = diagnostics.length === 0;
  $('ladder-draft-validate').disabled = pending || draftApplyPending;
}
function clearDraftCheck() {
  ++draftCheckRequest;
  showDraftCheck('');
}
function draftIsActive(key, draft) {
  return key === editingDraft && draftIdentity({key: selected}) === key && draft === ladderDrafts.get(key);
}
function draftIdentity(routine) {
  return JSON.stringify([state.instance_id, state.project_generation, state.source_sha256,
    state.routine_edits?.revision ?? 0, state.routine_edits?.logic_sha256 ?? null, routine.key]);
}
function draftApplyAllowed() {
  const connectivity = state?.connectivity;
  const nativeBusy = connectivity?.native_session?.enabled &&
    (connectivity.active_tcp_clients || connectivity.native_programming_lease?.owned);
  return state?.routine_edits?.draft_apply_available && state.controller?.mode === 'Program' && !nativeBusy;
}
function currentDraftCatalog() {
  return report?.source_l5x_sha256 === state?.source_sha256 ? report?.ladder_instruction_catalog : null;
}
function renderDraftPalette(catalog) {
  if (displayedDraftCatalog === catalog) return;
  displayedDraftCatalog = catalog;
  const select = $('ladder-draft-palette'), previous = select.value;
  const builtIns = document.createElement('optgroup'), addOns = document.createElement('optgroup');
  builtIns.label = 'Ladder instructions';
  addOns.label = 'Add-On Instructions';
  for (const name of Object.keys(catalog).sort()) {
    const addOn = catalog[name].add_on, title = LogixInstructionView.catalog[name]?.title;
    const label = addOn || (title && title !== name ? name + ' · ' + title : name);
    (addOn ? addOns : builtIns).append(new Option(label, name));
  }
  select.replaceChildren(builtIns, new Option('Branch', 'Branch'));
  if (addOns.children.length) select.append(addOns);
  select.value = previous === 'Branch' || Object.hasOwn(catalog, previous) ? previous : 'XIC';
}
function changeDraft(action) {
  const draft = ladderDrafts.get(editingDraft);
  if (!draft || draftApplyPending) return null;
  const result = action(draft);
  if (result) {
    clearDraftCheck();
    renderLadder();
  }
  return result;
}
function draftControls(routine) {
  const catalog = currentDraftCatalog(), editable = !!catalog && LogixLadderDraft.canEdit(routine);
  const key = editable ? draftIdentity(routine) : null;
  if (editingDraft !== null && editingDraft !== key) {
    editingDraft = null;
    ++draftFileRequest;
    setDraftFileStatus('');
    clearDraftCheck();
  }
  const draft = ladderDrafts.get(editingDraft), mode = $('ladder-draft-mode');
  if (draft) renderDraftPalette(catalog);
  mode.hidden = !editable;
  mode.disabled = draftApplyPending;
  mode.textContent = draft ? 'Monitor' : ladderDrafts.get(key)?.changed ? 'Resume draft' : 'Edit draft';
  $('ladder-draft-toolbar').hidden = !draft;
  $('ladder-draft-append').disabled = draftApplyPending;
  $('ladder-draft-undo').disabled = draftApplyPending || !draft?.canUndo;
  $('ladder-draft-redo').disabled = draftApplyPending || !draft?.canRedo;
  $('ladder-draft-save').disabled = draftApplyPending || !draft?.changed;
  $('ladder-draft-review').disabled = draftApplyPending || !draft?.changed;
  $('ladder-draft-open').disabled = draftApplyPending;
  $('ladder-draft-discard').disabled = draftApplyPending;
  const apply = $('ladder-draft-apply');
  apply.disabled = draftApplyPending || !draft?.changed || !draftApplyAllowed();
  apply.title = !state.routine_edits?.draft_apply_available ? 'Apply requires a complete ordinary project in whole-project mode' :
    state.controller?.mode !== 'Program' ? 'Switch to Program before applying a draft' :
    !draftApplyAllowed() ? 'Disconnect Studio clients and release native programming before applying a draft' :
    'Replace the loaded routine in memory';
  $('logic-view-mode').textContent = draft ? 'Offline draft' : 'Read-only monitor';
  $('logic-values').closest('label').hidden = !!draft;
  if (draftReviewDialog.open) {
    if (!draft || draftApplyPending) draftReviewDialog.close();
    else if (displayedReviewRungs !== draft.rungs) renderDraftReview(draft);
  }
  return draft;
}
function renderLadder() {
  const routine = state.routines.find(r => r.key === selected);
  const draft = draftControls(routine);
  if (!routine) return;
  const aoi=routine.key.startsWith('AOI:') ? routine.key.split('/')[0].slice(4) : '';
  const contexts=Object.entries(state.aoi_instances || {}).filter(([name,v])=>v.definition===aoi).map(([name])=>name);
  $('aoi-context').hidden=!aoi;
  if(!contexts.includes(selectedContext))selectedContext=contexts[0] || '';
  $('aoi-context').replaceChildren();
  for(const name of contexts){const option=document.createElement('option');option.value=name;option.textContent=name;$('aoi-context').append(option);}
  $('aoi-context').value=selectedContext;
  $('routine-name').textContent=routine.key; $('routine-type').textContent=routine.kind + (routine.active ? ' · IN EXECUTION SCOPE' : ' · OUTSIDE EXECUTION SCOPE');
  $('logic-comments-label').hidden=routine.kind!=='RLL';
  logicView.render({routine, state, context: aoi ? selectedContext : '', recognized, draft});
}
function renderCoverage() {
  if (!report) return;
  const priority=t=>t.priority===t.source_priority?String(t.priority):t.priority+' (source '+t.source_priority+')';
  const blocked=state.blockers.length>0;
  $('coverage-body').innerHTML=`<div class="coverage-result ${blocked?'blocked':''}">${blocked ? `${state.blockers.length} blockers prevent execution in this scope.` : 'This scope can execute in the current software model.'}</div>
  ${state.blockers.map(b=>`<div class="issue">${escapeHtml(b)}</div>`).join('')}
  <h3>TASK SCHEDULING</h3><p class="limits">${escapeHtml(state.task_schedule?.policy || '')}</p><div class="chips">${(state.task_schedule?.tasks || []).map(t=>`<span class="chip">${escapeHtml(t.name)} · ${t.inhibited?'inhibited':t.kind==='Continuous'?'background':t.kind==='Event'?`EVENT · priority ${priority(t)} · ${t.event_instruction_overlaps} modeled overlaps · ${t.event_pending_requests_coalesced} pending duplicates merged`:`${t.rate_ms} ms${t.rate_ms===t.source_rate_ms?'':` (source ${t.source_rate_ms} ms)`} · priority ${priority(t)}`} · ${t.executions} executions · next ${t.next_release_ms??'—'}</span>`).join('') || '<span class="limits">No executable task schedule in this scope.</span>'}</div>
  <h3>FUNCTION BLOCKS</h3><p class="limits">${escapeHtml(report.function_blocks?.graph || '')}<br>${escapeHtml(report.function_blocks?.ordering || '')}</p>
  <h3>STRUCTURED TEXT</h3><p class="limits">${escapeHtml(report.structured_text?.policy || '')}</p><div class="chips">${Object.entries(report.structured_text?.constructs || {}).map(([n,c])=>`<span class="chip">${escapeHtml(n)} × ${c}</span>`).join('') || '<span class="limits">No ST statements in program routines.</span>'}</div>
  <h3>SUBROUTINE PARAMETERS</h3><p class="limits">${escapeHtml(report.routine_parameters?.contract || '')}</p><div class="chips">${Object.entries(report.routine_parameters?.calls || {}).map(([name,v])=>`<span class="chip">${escapeHtml(name)} · ${v.inputs} in / ${v.returns} out</span>`).join('') || '<span class="limits">No routine calls in this scope.</span>'}</div>
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
async function loadDemo(sample='ConveyorDemo') {$('sample-menu').open=false;$('busy-text').textContent='Opening demo…';$('busy').hidden=false;try{selected='';await accept(await api('demo',{sample}),true);$('mode').value='project';render();}catch(e){error(e);}finally{$('busy').hidden=true;}}
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
  try{const content=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=reject;reader.readAsDataURL(file);});selected='';await accept(await api('load',{name:file.name,content}),true);$('mode').value='project';render();if(state.blockers.length)selectTab('coverage');}catch(e){error(e);}finally{$('busy').hidden=true;}
};
$('demo').onclick=()=>loadDemo();$('welcome-demo').onclick=()=>loadDemo();$('data-demo').onclick=()=>loadDemo('DataLab');$('task-demo').onclick=()=>loadDemo('TaskLab');$('system-demo').onclick=()=>loadDemo('SystemLab');$('module-status-demo').onclick=()=>loadDemo('ModuleStatusLab');$('message-demo').onclick=()=>loadDemo('MessageLab');$('timer-demo').onclick=()=>loadDemo('TimerLab');$('counter-demo').onclick=()=>loadDemo('CounterLab');$('pulse-demo').onclick=()=>loadDemo('PulseLab');$('scale-demo').onclick=()=>loadDemo('ScaleLab');$('signal-demo').onclick=()=>loadDemo('SignalLab');$('rate-demo').onclick=()=>loadDemo('RateLab');$('event-demo').onclick=()=>loadDemo('EventLab');$('aoi-demo').onclick=()=>loadDemo('AOILab');
$('aoi-constants-demo').onclick=()=>loadDemo('AOIConstantsLab');
$('call-demo').onclick=()=>loadDemo('CallLab');
$('loop-demo').onclick=()=>loadDemo('LoopLab');
$('moving-demo').onclick=()=>loadDemo('MovingLab');
$('capture-demo').onclick=()=>loadDemo('CaptureLab');
$('filter-demo').onclick=()=>loadDemo('FilterLab');
$('digital-demo').onclick=()=>loadDemo('DigitalLab');
$('accumulator-demo').onclick=()=>loadDemo('AccumulatorLab');
$('process-demo').onclick=()=>loadDemo('ProcessLab');
$('curve-demo').onclick=()=>loadDemo('CurveDelayLab');
$('regulator-demo').onclick=()=>loadDemo('RegulatorLab');
$('copy-demo').onclick=()=>loadDemo('CopyLab');
$('selector-demo').onclick=()=>loadDemo('SelectorLab');
$('fbd-signal-demo').onclick=()=>loadDemo('FBDSignalLab');
$('fbd-state-demo').onclick=()=>loadDemo('FBDStateLab');
$('fbd-logic-demo').onclick=()=>loadDemo('FBDLogicLab');
$('fbd-trend-demo').onclick=()=>loadDemo('FBDTrendLab');
$('fbd-total-demo').onclick=()=>loadDemo('FBDTotalLab');
$('fbd-process-demo').onclick=()=>loadDemo('FBDProcessLab');
$('fbd-advanced-demo').onclick=()=>loadDemo('FBDAdvancedMathLab');
$('target-move-demo').onclick=()=>loadDemo('TargetMoveLab');
$('wide-expression-demo').onclick=()=>loadDemo('WideExpressionLab');
$('queue-reference-demo').onclick=()=>loadDemo('QueueReferenceLab');
$('aoi-queue-demo').onclick=()=>loadDemo('AOIQueueLab');
$('aoi-file-demo').onclick=()=>loadDemo('AOIFileLab');
$('pid-demo').onclick=()=>loadDemo('PIDLab');
$('alarm-demo').onclick=()=>loadDemo('AlarmLab');
$('aoi-alarm-demo').onclick=()=>loadDemo('AOIAlarmLab');
$('aoi-pid-demo').onclick=()=>loadDemo('AOIPIDLab');
$('aoi-sequencer-demo').onclick=()=>loadDemo('AOISequencerLab');
$('aoi-stats-demo').onclick=()=>loadDemo('AOIStatsLab');
$('aoi-sort-demo').onclick=()=>loadDemo('AOISortLab');
$('aoi-bit-demo').onclick=()=>loadDemo('AOIBitLab');
$('fbd-convert-demo').onclick=()=>loadDemo('FBDConversionLab');
$('fbd-math-demo').onclick=()=>loadDemo('FBDMathLab');
$('fbd-bitwise-demo').onclick=()=>loadDemo('FBDBitwiseLab');
$('fbd-compare-demo').onclick=()=>loadDemo('FBDCompareLab');
$('text-demo').onclick=()=>loadDemo('TextLab');
$('string-demo').onclick=()=>loadDemo('StringLab');
$('control-demo').onclick=()=>loadDemo('ControlLab');
$('record-demo').onclick=()=>loadDemo('RecordLab');
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
$('clear-module-fault').onclick = async () => {
  const fault = state?.controller?.module_major_fault;
  if (!fault || $('clear-module-fault').disabled) return;
  const generation = state.project_generation;
  modePending = true;
  let failure;
  render();
  try {
    const result = await api('module-major-fault-clear', {project_generation:generation, fault_id:fault.fault_id});
    if (state.project_generation === generation) await accept(result);
  } catch (e) {
    failure = e;
  } finally {
    modePending = false;
    render();
    if (failure && state.project_generation === generation) error(failure);
  }
};
$('reset').onclick=async()=>{try{await accept(await api('reset'),true);}catch(e){error(e);}};
$('mode').onchange=()=>{$('harness').disabled=$('mode').value!=='routine';};
$('apply').onclick=async()=>{try{await accept(await api('configure',{mode:$('mode').value,routine:$('harness').value}),true);}catch(e){error(e);}};
$('filter').oninput=()=>{if(state?.loaded)renderTags();};
$('module-name').onchange=()=>{loadModuleInput();renderModuleSimulation();};
$('module-input').onchange=renderModuleSimulation;
$('module-connection-form').onsubmit=async event=>{
  event.preventDefault();
  const module = selectedModule();
  if (!module || $('module-apply').disabled) return;
  const generation = state.project_generation;
  const data = {module:module.name, project_generation:generation, state:$('module-input').value};
  if (data.state === 'faulted') {
    data.fault_code = $('module-fault-code').valueAsNumber;
    data.fault_info = $('module-fault-info').valueAsNumber;
  }
  modulePending = true;
  renderModuleSimulation();
  try {
    await api('module-connection',data);
    if (state?.project_generation === generation)
      $('module-connection-feedback').textContent = module.label + ' input applied.';
  } catch (failure) {
    if (state?.project_generation === generation)
      $('module-connection-feedback').textContent = failure.message;
  } finally {
    modulePending = false;
    renderModuleSimulation();
  }
};
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
connectivityPoll = setInterval(async () => {
  if (!state?.loaded || stepping || modePending || draftApplyPending || observing) return;
  const before = state;
  observing = true;
  try {
    const next = await api('observe');
    if (!draftApplyPending && state === before) await accept(next);
  } catch (_) {} finally {observing = false;}
}, 500);
