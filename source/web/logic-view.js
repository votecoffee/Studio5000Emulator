/* Read-only logic documents. Graph topology, layout and monitoring stay separate. */
(function (root, factory) {
  const api = factory(root);
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.LogixLogicView = api;
})(typeof globalThis === 'object' ? globalThis : this, function (root) {
  'use strict';
  const KEYWORDS = new Set(('IF THEN ELSIF ELSE END_IF CASE OF END_CASE FOR TO BY DO END_FOR WHILE END_WHILE REPEAT UNTIL END_REPEAT EXIT RETURN AND OR XOR NOT MOD TRUE FALSE').split(' '));
  const faceplates = root.LogixInstructionView || (typeof require === 'function' ? require('./instruction-view.js') : null);
  const values = root.LogixLogicValues || (typeof require === 'function' ? require('./logic-values.js') : null);
  function labelTarget(graphs, label) {
    const matches = graphs.flatMap(graph => graph.nodes.filter(node => node.kind === 'instruction' && node.opcode === 'LBL' && node.operands[0]?.toLowerCase() === String(label).toLowerCase()).map(node => ({nodeId: node.id, graphId: graph.id})));
    return matches.length === 1 ? matches[0] : null;
  }
  const short = (text, limit = 28) => String(text).length > limit ? String(text).slice(0, limit - 1) + '…' : String(text);
  const valueText = row => !row || row.value == null ? '?' : typeof row.value === 'boolean' ? (row.value ? '1' : '0') : String(row.value);
  const sampleText = sample => sample.aggregate ? 'Aggregate' : valueText(sample);
  const sampleLabel = (argument, loop) => loop ? (argument === 1 ? 'Index at exit' : 'Last loop read') : 'Last transfer';
  const loopExitLabels = {terminal: 'Terminal condition', brk: 'BRK', bounds: 'Cleared bounds fault'};
  const faultCode = fault => fault ? `${fault.type}/${fault.code}` : '';
  const faultMessage = code => `Instruction skipped after fault ${code} was cleared.`;
  function html(tag, className, text) {
    const el = document.createElement(tag);if (className) el.className = className;
    if (text !== undefined) el.textContent = text;return el;
  }
  function svg(tag, attrs = {}, text) {
    const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
    if (text !== undefined) el.textContent = text;return el;
  }

  function tokenizeST(text, state = {depth: 0}) {
    const tokens = [];let at = 0;
    const add = (kind, end) => {tokens.push({kind, text: text.slice(at, end)});at = end;};
    while (at < text.length) {
      if (state.depth || text.startsWith('(*', at)) {
        let end = at;
        do {
          if (text.startsWith('(*', end)) {state.depth++;end += 2;}
          else if (text.startsWith('*)', end)) {state.depth--;end += 2;}
          else end++;
        } while (end < text.length && state.depth);
        add('comment', end);continue;
      }
      if (text.startsWith('//', at)) {add('comment', text.length);continue;}
      if (text[at] === "'") {
        let end = at + 1;
        while (end < text.length) {
          if (text[end] === '$' || text.slice(end, end + 2) === "''") end += 2;
          else if (text[end++] === "'") break;
        }
        add('string', Math.min(end, text.length));continue;
      }
      const rest = text.slice(at);
      const number = rest.match(/^(?:2|8|16)#[\da-fA-F](?:[\da-fA-F_ ]*[\da-fA-F])?(?:[Uu][Ll]?|[Ll])(?![\w.])/)
        || rest.match(/^(?:(?:2|8|16)#[\da-fA-F_]+|(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?[uUlL]*)/);
      if (number) {add('number', at + number[0].length);continue;}
      const word = text.slice(at).match(/^[A-Za-z_][\w:]*/);
      if (word) {add(KEYWORDS.has(word[0].toUpperCase()) ? 'keyword' : /^\s*\(/.test(text.slice(at + word[0].length)) ? 'function' : 'plain', at + word[0].length);continue;}
      add('plain', at + 1);
    }
    return tokens;
  }

  function lrealMathRadix(node, ref, read) {
    const args = node?.operands || [];
    if (!String(ref).includes('#') || !args.slice(0, -1).includes(ref) || !['ADD','SUB','MUL','DIV','MOD','NEG','ABS','XPY','SQR','LN','LOG','DEG','RAD','SIN','COS','TAN','ASN','ACS','ATN'].includes(node?.opcode)) return false;
    return args.some(arg => {const type = read?.(arg)?.type;return type === 'LREAL' || type === 'LREAL literal';});
  }
  function realMathRadix(node, ref, read) {
    const args = node?.operands || [], sources = args.slice(0, -1);
    if (!String(ref).includes('#') || !sources.includes(ref) || !['ADD','SUB','MUL','DIV','MOD','NEG','ABS','XPY','SQR','LN','LOG','DEG','RAD','SIN','COS','TAN','ASN','ACS','ATN'].includes(node?.opcode)) return false;
    const destination = read?.(args.at(-1))?.type;
    return destination === 'REAL' || ['SINT','INT','DINT','LINT','USINT','UINT','UDINT','ULINT'].includes(destination) && sources.some(arg => read?.(arg)?.type === 'REAL' || /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?$/.test(arg) && /[.Ee]/.test(arg));
  }
  function parameterRadix(node, ref, definitions = {}) {
    if (!String(ref).includes('#')) return false;
    const args = node?.operands || [], index = args.indexOf(ref);
    if (node?.opcode === 'RET') return index >= 0;
    if (node?.opcode === 'JSR') return index >= 2 && index < 2 + Number(args[1]);
    const face = node && faceplates?.describe(node, definitions);
    return !!(face?.kind === 'aoi' && face.fields.some(field => field.ref === ref && field.required && field.usage === 'Input'));
  }
  const dintWordOperands = new Map([
    ['MVM', [0, 1]], ['BTD', [0, 1, 3, 4]], ['DTR', [0, 1]],
    ['SQI', [1, 2]], ['SQO', [1]], ['SQL', [1]],
    ['FLL', [0, 2]], ['COP', [2]], ['CPS', [2]], ['FFL', [0]], ['LFL', [0]],
    ['FIND', [2]], ['INSERT', [2]], ['MID', [1, 2]], ['DELETE', [1, 2]], ['FOR', [2, 3, 4]]
  ]);
  function ladderWordRadix(node, ref, version, processor) {
    if (version !== '35' || !/^1756-L8[1-5]E$/i.test(processor)) return false;
    if (['JSR', 'RET'].includes(node?.opcode)) return parameterRadix(node, ref);
    return dintWordOperands.get(node?.opcode)?.some(index => node.operands?.[index] === ref) ?? false;
  }
  function create(options) {
    const canvas = options.canvas, inspector = options.inspector, status = options.status;
    let current, key = '', sourceIdentity = '', zoom = 1, showValues = true, showComments = true, selected = '', documents = [], valueMap = new Map(), snapshot, lastTraces = new Map();
    let inspection = '', monitorSelection = '', draftSelection = '', draftRungs;
    let movePick, drag, hovered, suppressedClick, resizeGuide = null, resizeDots = [];
    const wireTargets = new WeakMap(), dragSources = new WeakMap();

    function acceptsWire(source, target) {
      if (!target) return false;
      if (source.resize) return source.rung === target.rung &&
        current.draft.canResize(source.rung, source.id, target.gap);
      return current.draft.canMove(source.rung, source.id, target.rung, target.gap);
    }
    function validWires(doc, source) {
      return [...doc.row.querySelectorAll('.lv-draft-gap')].filter(dot => acceptsWire(source, wireTargets.get(dot)));
    }
    function indicateResize(source) {
      if (resizeGuide === source) return;
      for (const dot of resizeDots) dot.classList.remove('resize-target');
      resizeGuide = source;
      resizeDots = source ? validWires(documents[source.rung], source) : [];
      for (const dot of resizeDots) dot.classList.add('resize-target');
    }
    function moveStatus() {
      if (!current?.draft) return;
      const source = movePick || (drag?.active ? drag : null);
      indicateResize(source?.resize ? source : null);
      canvas.classList.toggle('lv-pick-wire', !!source && !source.resize);
      const text = source?.resize ? 'Choose a highlighted wire to resize the branch · Esc cancels' :
        movePick ? 'Choose a destination wire · Esc cancels' :
        drag?.active ? 'Drop on a wire dot' : 'Draft · Simulator uses the loaded routine';
      if (status.textContent !== text) status.textContent = text;
    }
    function pickWire(doc, source) {
      movePick = source;
      moveStatus();
      const first = validWires(doc, source)[0];
      (first || canvas.querySelector('.lv-draft-gap'))?.focus();
    }
    function highlight(dot) {
      if (dot === hovered) return;
      hovered?.classList.remove('drop-target');
      hovered = dot;
      hovered?.classList.add('drop-target');
    }
    function endDrag() {
      if (!drag) return;
      const {element, pointer} = drag;
      drag = null;
      if (element.hasPointerCapture(pointer)) element.releasePointerCapture(pointer);
      highlight(null);
      moveStatus();
    }
    function dropTarget(event) {
      const dot = document.elementFromPoint(event.clientX, event.clientY)?.closest('.lv-draft-gap');
      return acceptsWire(drag, wireTargets.get(dot)) ? dot : null;
    }
    function applyWire(source, target) {
      if (!acceptsWire(source, target)) return;
      const id = source.resize ? options.onDraftResize(source.rung, source.id, target.gap) :
        options.onDraftMove(source.rung, source.id, target.rung, target.gap);
      if (!id) return;
      movePick = null;
      select(target.graphId + ':draft:' + id + (source.resize ? ':join' : ''), true);
      moveStatus();
    }
    canvas.addEventListener('pointerdown', event => {
      const element = event.target.closest('.lv-instruction, .lv-draft-branch'), source = dragSources.get(element);
      if (!source || !event.isPrimary || event.button !== 0 || drag) return;
      suppressedClick = null;
      drag = {...source, element, pointer: event.pointerId, x: event.clientX, y: event.clientY, active: false};
      element.setPointerCapture(event.pointerId);
    });
    canvas.addEventListener('pointermove', event => {
      if (!drag || event.pointerId !== drag.pointer) return;
      if (!drag.active) {
        if (Math.hypot(event.clientX - drag.x, event.clientY - drag.y) < 5) return;
        drag.active = true;
        movePick = null;
      }
      event.preventDefault();
      highlight(dropTarget(event));
      moveStatus();
    });
    canvas.addEventListener('pointerup', event => {
      if (!drag || event.pointerId !== drag.pointer) return;
      const source = drag, dot = drag.active ? dropTarget(event) : null;
      endDrag();
      if (!source.active) return;
      suppressedClick = source.element;
      setTimeout(() => {if (suppressedClick === source.element) suppressedClick = null;}, 0);
      if (dot) applyWire(source, wireTargets.get(dot));
    });
    for (const type of ['pointercancel', 'lostpointercapture']) canvas.addEventListener(type, event => {
      if (drag?.pointer === event.pointerId) endDrag();
    });
    canvas.addEventListener('click', event => {
      if (suppressedClick && suppressedClick.contains(event.target)) event.stopImmediatePropagation();
    }, true);
    for (const area of [canvas, inspector]) area.addEventListener('keydown', event => {
      if (event.key !== 'Escape' || (!movePick && !drag)) return;
      event.preventDefault();
      movePick = null;
      endDrag();
      moveStatus();
    });
    function read(ref, node) {
      if (node?.literalValues && Object.hasOwn(node.literalValues, ref)) return node.literalValues[ref];
      const bitwiseRadix = node?.opcode === 'MEQ' || ['AND','OR','XOR','NOT'].includes(node?.opcode) && node.operands?.slice(0,-1).includes(ref);
      const wordRadix = ladderWordRadix(node, ref, current.state.version, current.state.processor);
      const integerRadix = lrealMathRadix(node, ref, arg => snapshot?.read(arg)) || realMathRadix(node, ref, arg => snapshot?.read(arg)) || ['EQU','NEQ','LES','LEQ','GRT','GEQ','LIM'].includes(node?.opcode) || ['ADD','SUB','MUL','DIV','MOD','NEG','ABS'].includes(node?.opcode) && node.operands?.slice(0,-1).includes(ref);
      const bcdRadix = ['FRD','TOD'].includes(node?.opcode) && node.operands?.[0] === ref;
      return snapshot?.read(ref, {movRadix: node?.opcode === 'MOV' && node.operands?.[0] === ref, bitwiseRadix, integerRadix, dintRadix: integerRadix || wordRadix, bcdRadix, callRadix: parameterRadix(node, ref, current.state.aoi_definitions)}) || null;
    }
    function operandDisplay(field, node, power) {
      if (current.draft) return {};
      const sample = power?.operandSamples?.[field.argument];
      const unsampled = !!power?.loopTrace && field.argument > 0 && !sample;
      return {sample, unsampled, row: sample || (unsampled ? null : read(field.ref, node))};
    }
    function trace(rung) {return lastTraces.get(rung);}
    function presentation(node) {return faceplates.describe(node, current.state.aoi_definitions);}
    function parameters(node) {return presentation(node).fields;}
    function openAOI(node) {
      const face = presentation(node);if (face.kind !== 'aoi') return null;
      const target = current.state.routines.find(r => r.key.toLowerCase() === ('AOI:' + face.title + '/Logic').toLowerCase());
      const address = snapshot.resolve(node.operands[0]);
      const context = Object.keys(current.state.aoi_instances || {}).find(key => key.toLowerCase() === address?.toLowerCase());
      return target && context ? {key: target.key, context} : null;
    }
    function updateSelection(focus = false) {
      function updateItem(id, element) {
        const active = id === selected;
        element.classList.toggle('selected', active);
        if (element.getAttribute('aria-pressed') !== String(active)) element.setAttribute('aria-pressed', String(active));
        if (focus && id === selected) {
          element.focus({preventScroll: true});
          element.scrollIntoView({block: 'nearest', inline: 'nearest'});
        }
      }
      for (const doc of documents) {
        for (const [id, item] of doc.instructions) updateItem(id, item.group);
        for (const [id, item] of doc.branches || []) updateItem(id, item.element);
      }
    }
    function select(id, focus = false) {
      if (movePick && selected !== id) {
        movePick = null;
        moveStatus();
      }
      selected = id;
      if (current.draft) draftSelection = id;
      else monitorSelection = id;
      updateSelection(focus);
      updateInspector();
      canvas.dispatchEvent(new CustomEvent('logic-node-selected', {bubbles: true, detail: {nodeId: id,
        graphId: documents.find(doc => doc.graph?.nodes.some(n => n.id === id))?.graph.id || current?.routine.key}}));
    }
    function bind(group, id, description, navigate) {
      group.setAttribute('tabindex', '0');group.setAttribute('role', 'button');group.setAttribute('aria-label', description);
      group.addEventListener('click', () => select(id));
      if (navigate) group.addEventListener('dblclick', navigate);
      group.addEventListener('keydown', event => {
        if (navigate && event.ctrlKey && event.key === 'Enter') {event.preventDefault();navigate();return;}
        if (event.key === 'Enter' || event.key === ' ') {event.preventDefault();select(id);}
        if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
          const ids = documents.flatMap(doc => [...doc.instructions.keys()]), at = ids.indexOf(id);
          event.preventDefault();select(ids[Math.max(0, Math.min(ids.length - 1, at + (event.key === 'ArrowRight' ? 1 : -1)))], true);
        }
      });
    }
    function updateInspector() {
      const doc = documents.find(doc => doc.instructions.has(selected) || doc.branches?.has(selected));
      inspector.hidden = !doc;if (!doc) {inspection = '';return;}
      const item = doc.instructions.get(selected);
      if (current.draft) {
        if (item) editInspector(doc, item);
        else editBranch(doc, doc.branches.get(selected).node);
        return;
      }
      const fields = item.fields || parameters(item.node), event = doc.graph ? doc.power?.nodes[selected] : null;
      const loop = event?.loopTrace;
      const rows = fields.map(field => ({...field, ...operandDisplay(field, item.node, event)}));
      const face = item.graph ? presentation(item.node) : null;
      const recovery = faultCode(event?.recoveredFault);
      const fingerprint = JSON.stringify([selected, rows, event?.in, event?.out, loop, recovery, face?.description]);if (fingerprint === inspection) return;
      inspection = fingerprint;inspector.replaceChildren();
      const head = html('div', 'lv-inspector-head');head.append(html('strong', '', face ? (face.kind === 'aoi' ? face.title : item.node.opcode + ' · ' + face.title) : item.node.type || item.node.kind));
      const context = doc.graph ? `Rung ${doc.graph.number} · Last scan ${event?.in === undefined ? '?' : Number(event.in)} → ${event?.out === undefined ? '?' : Number(event.out)}` : current.routine.key;
      head.append(html('span', '', context));
      const close = html('button', '', 'Close');close.setAttribute('aria-label', 'Close instruction details');close.onclick = () => {selected = '';select('');};head.append(close);
      const target = ['JSR', 'FOR'].includes(item.node.opcode) && current.state.routines.find(r => r.key.toLowerCase() === (current.routine.key.split('/')[0] + '/' + item.node.operands[0]).toLowerCase());
      if (target) {const open = html('button', '', 'Open routine ↗');open.onclick = () => options.onOpenRoutine(target.key);head.insertBefore(open, close);}
      const jump = item.node.opcode === 'JMP' && labelTarget(documents.filter(d => d.graph).map(d => d.graph), item.node.operands[0]);
      if (jump) {const open = html('button', '', 'Go to label ↗');open.onclick = () => select(jump.nodeId, true);head.insertBefore(open, close);}
      const aoi = item.graph && openAOI(item.node);
      if (aoi) {const open = html('button', '', 'Open AOI logic ↗');open.onclick = () => options.onOpenRoutine(aoi.key, aoi.context);head.insertBefore(open, close);}
      inspector.append(head);
      if (recovery) inspector.append(html('p', 'lv-inspector-fault', faultMessage(recovery)));
      if (loop) inspector.append(html('p', 'lv-loop-summary',
        loopExitLabels[loop.exit] + ' · ' + loop.visits + (loop.visits === 1 ? ' routine visit' : ' routine visits')));
      if (face?.description) inspector.append(html('p', 'lv-instruction-description', face.description));
      const table = html('div', 'lv-operand-list');
      for (const field of rows) {
        const row = html('div', 'lv-operand'), reference = html('div');
        reference.append(html('code', '', field.ref));
        if (field.sample) {
          const label = sampleLabel(field.argument, loop);
          reference.append(html('span', 'lv-sample-address',
            field.sample.address ? label + ' · ' + field.sample.address : label));
        } else if (field.unsampled) reference.append(html('span', 'lv-sample-address', 'Not sampled'));
        const display = field.sourceOnly || field.unsampled ? '—' : field.sample ? sampleText(field.sample) : valueText(field.row);
        const valueClass = field.sample ? ' captured' :
          !field.sourceOnly && !field.unsampled && field.row?.value == null ? ' unknown' : '';
        row.append(html('span', 'lv-field-label', field.label + (field.visible === false ? ' (hidden)' : '')),
          reference, html('span', 'lv-current-value' + valueClass, display),
          html('span', 'lv-field-type', [field.usage, field.sourceOnly ? 'Source text' : field.type || field.row?.type || 'Not available'].filter(Boolean).join(' · ')));
        table.append(row);
      }
      inspector.append(table);
    }
    function editInspector(doc, item) {
      const {node} = item;
      const fingerprint = JSON.stringify([node.id, node.operands, 'draft']);
      if (inspection === fingerprint) return;
      inspection = fingerprint;
      const head = html('div', 'lv-inspector-head');
      head.append(html('strong', '', node.opcode + ' · ' + presentation(node).title),
        html('span', '', 'Rung ' + doc.graph.number + ' · Draft'));
      const move = html('button', '', 'Move instruction');
      move.onclick = () => pickWire(doc, {rung: doc.rungIndex, id: node.draftId});
      const remove = html('button', '', 'Delete instruction');
      remove.onclick = () => options.onDraftRemove(doc.rungIndex, node.draftId);
      const close = html('button', '', 'Close');
      close.onclick = () => select('');
      head.append(move, remove, close);
      inspector.replaceChildren(head);
      const shape = current.draft.operandShape(node.opcode);
      const variable = shape && shape.max_args > shape.min_args;
      if (!node.operands.length && !variable) return;
      const form = html('form', 'lv-draft-operands'), fields = html('div', 'lv-draft-operand-fields');
      const labels = [], inputs = [];
      function addField(value = '?') {
        const label = html('label'), caption = html('span'), input = html('input');
        input.value = value;input.spellcheck = false;
        labels.push(caption);inputs.push(input);
        label.append(caption, input);fields.append(label);
      }
      const operandValues = () => inputs.map(input => input.value);
      function labelFields() {
        const captions = faceplates.operandLabels({...node, operands: operandValues()}, current.state.aoi_definitions);
        captions.forEach((caption, i) => {labels[i].textContent = caption;});
      }
      node.operands.forEach(addField);
      labelFields();
      if (node.opcode === 'JSR' && !shape?.add_on) inputs[1]?.addEventListener('input', labelFields);
      form.append(fields);
      if (variable) {
        const grouping = shape.step > 1 ? ' operand pair' : ' operand';
        const add = html('button', 'lv-draft-add-operand', 'Add' + grouping);
        const remove = html('button', 'lv-draft-remove-operand', 'Remove last' + grouping);
        add.type = remove.type = 'button';
        function updateLimits() {
          add.disabled = inputs.length + shape.step > shape.max_args;
          remove.disabled = inputs.length - shape.step < shape.min_args;
        }
        add.onclick = () => {
          for (let i = 0; i < shape.step; i++) addField();
          labelFields();updateLimits();
          inputs.at(-shape.step).focus();
        };
        remove.onclick = () => {
          for (let i = 0; i < shape.step; i++) {
            inputs.pop().parentElement.remove();
            labels.pop();
          }
          updateLimits();
          if (remove.disabled) add.focus();
        };
        updateLimits();
        form.append(add, remove);
      }
      const submit = html('button', '', 'Update operands');
      const feedback = html('span');feedback.setAttribute('role', 'alert');
      form.append(submit, feedback);
      form.onsubmit = event => {
        event.preventDefault();
        try {
          options.onDraftOperands(doc.rungIndex, node.draftId, operandValues());
          feedback.textContent = '';
        } catch (error) {feedback.textContent = error.message;}
      };
      inspector.append(form);
    }
    function editBranch(doc, node) {
      const fingerprint = JSON.stringify([node.id, node.legCount]);
      if (fingerprint === inspection) return;
      inspection = fingerprint;
      const head = html('div', 'lv-inspector-head');
      const source = {rung: doc.rungIndex, id: node.draftId, resize: true};
      const resize = html('button', '', 'Resize branch');
      resize.disabled = !validWires(doc, source).length;
      resize.onclick = () => pickWire(doc, source);
      const add = html('button', '', 'Add leg');
      add.onclick = () => options.onDraftAddLeg(doc.rungIndex, node.draftId);
      const close = html('button', '', 'Close');
      close.onclick = () => select('');
      head.append(html('strong', '', 'Branch'), html('span', '', 'Rung ' + doc.graph.number + ' · Draft'), resize, add, close);
      const legs = html('div', 'lv-draft-legs');
      for (let leg = 0; leg < node.legCount; leg++) {
        const remove = html('button', '', 'Delete leg ' + (leg + 1));
        remove.disabled = node.legCount < 2;
        remove.onclick = () => options.onDraftRemoveLeg(doc.rungIndex, node.draftId, leg);
        legs.append(remove);
      }
      inspector.replaceChildren(head, legs);
    }
    function branchHandle(node, position, graph, rungIndex) {
      const control = svg('rect', {class: 'lv-draft-branch', x: position.x - 5,
        y: (position.y + position.endY) / 2 - 5, width: 10, height: 10,
        tabindex: 0, role: 'button', 'aria-label': 'Edit branch in rung ' + graph.number});
      control.append(svg('title', {}, 'Click for branch controls or drag to resize'));
      dragSources.set(control, {rung: rungIndex, id: node.draftId, resize: true});
      control.addEventListener('click', () => select(node.id));
      control.addEventListener('keydown', event => {
        if (event.key === 'Enter' || event.key === ' ') {event.preventDefault();select(node.id);}
      });
      return control;
    }
    function insertPoint(graph, rungIndex, edge, a, b) {
      const dot = svg('circle', {class: 'lv-draft-gap', cx: (a.x + b.x) / 2, cy: (a.y + b.y) / 2,
        r: 6, tabindex: 0, role: 'button', 'aria-label': 'Wire insertion point in rung ' + graph.number});
      const target = {graphId: graph.id, rung: rungIndex, gap: edge.gap};
      wireTargets.set(dot, target);
      const insert = () => {
        if (movePick) {applyWire(movePick, target);return;}
        const id = graph.id + ':draft:' + options.onDraftInsert(rungIndex, edge.gap);
        if (documents.some(doc => doc.instructions.has(id))) select(id, true);
      };
      dot.addEventListener('click', insert);
      dot.addEventListener('keydown', event => {
        if (event.key === 'Enter' || event.key === ' ') {event.preventDefault();insert();}
      });
      return dot;
    }
    function drawInstruction(node, position, graph) {
      const {x, y, width, above, below, symbol} = position, group = svg('g', {class: 'lv-instruction', transform: `translate(${x},${y})`, 'data-node-id': node.id});
      group.append(svg('rect', {class: 'lv-selection', x: -5, y: -above + 5, width: width + 10, height: above + below - 10, rx: 2}));
      const cx = width / 2, title = svg('title', {}, node.opcode + '(' + node.operands.join(', ') + ')');group.append(title);
      const fields = [], op = node.opcode, face = presentation(node);
      group.dataset.instructionKind = face.kind;
      if (face.description) title.textContent += '\n' + face.description;
      if (symbol) {
        group.append(svg('path', {class: 'lv-inner-wire input', d: `M0 0 H${cx - 16}`}), svg('path', {class: 'lv-inner-wire output', d: `M${cx + 16} 0 H${width}`}));
        group.append(svg('rect', {class: 'lv-energized-fill', x: cx - 16, y: -14, width: 32, height: 28}));
        if (face.kind === 'contact') {
          group.append(svg('path', {class: 'lv-symbol', d: `M${cx - 9} -13 V13 M${cx + 9} -13 V13${op === 'XIO' ? ` M${cx - 12} 12 L${cx + 12} -12` : ''}`}));
        } else if (face.kind === 'coil') {
          group.append(svg('path', {class: 'lv-symbol', d: `M${cx - 5} -14 C${cx - 23} -8 ${cx - 23} 8 ${cx - 5} 14 M${cx + 5} -14 C${cx + 23} -8 ${cx + 23} 8 ${cx + 5} 14`}));
          if (op !== 'OTE') group.append(svg('text', {x: cx, y: 4, class: 'lv-coil-letter'}, op === 'OTL' ? 'L' : 'U'));
        } else group.append(svg('text', {x: cx, y: 5, class: 'lv-inline-op'}, op === 'JMP' ? '>>' : op === 'LBL' ? '<<' : '[' + op + ']'));
        const operand = svg('text', {x: cx, y: -27, class: 'lv-reference'}, short(node.operands[0] || '', Math.floor(width / 7)));group.append(operand);
        if (node.operands[0] && !face.fields[0]?.sourceOnly) {const value = svg('text', {x: cx, y: 29, class: 'lv-value'});group.append(value);fields.push({el: value, ref: node.operands[0]});}

      } else {
        const boxWidth = position.boxWidth, height = face.rows.length * 34 + 39;
        group.append(svg('rect', {class: 'lv-block' + (face.kind === 'aoi' ? ' lv-aoi-block' : ''), x: 0, y: -24, width: boxWidth, height}),
          svg('path', {class: 'lv-block-rule', d: `M0 5 H${boxWidth}`}),
          svg('text', {x: 9, y: -7, class: face.kind === 'aoi' ? 'lv-aoi-name' : 'lv-block-title'}, face.title));
        if (face.kind !== 'aoi' && face.known) group.append(svg('text', {x: boxWidth - 8, y: -7, class: 'lv-block-opcode'}, op));
        face.flags.forEach((flag, i) => {
          const x = boxWidth + 24, y = i * 22;
          group.append(svg('path', {class: 'lv-status-coil', d: `M${boxWidth} ${y} H${x - 12} M${x - 6} ${y - 7} C${x - 15} ${y - 4} ${x - 15} ${y + 4} ${x - 6} ${y + 7} M${x + 6} ${y - 7} C${x + 15} ${y - 4} ${x + 15} ${y + 4} ${x + 6} ${y + 7}`}));
          const el = svg('text', {x, y: y + 3, class: 'lv-state-bit'}, flag.label);group.append(el);fields.push({el, ...flag, flag: flag.label});
        });
        if (face.flags.length) group.append(svg('path', {class: 'lv-inner-wire output', d: `M${boxWidth + 36} 0 H${width}`}));
        face.rows.forEach((param, i) => {
          const y = 24 + i * 34;
          const row = svg('g', {'data-parameter': param.label, 'data-usage': param.usage || '', class: 'lv-parameter-row'});
          const label = svg('text', {x: 9, y, class: 'lv-param-name'}, param.label);
          const reference = svg('text', {x: position.labelWidth + 18, y, class: 'lv-param-reference' + (param.instance ? ' lv-instance-name' : '')}, param.member ? '' : short(param.ref, 40));
          reference.append(svg('title', {}, param.ref));row.append(label, reference);
          if (param.usage) {
            const left = param.usage !== 'Output', right = param.usage !== 'Input';
            row.append(svg('path', {class: 'lv-parameter-direction', d: `${left ? `M-6 ${y - 4} H0 M-4 ${y - 7} L0 ${y - 4} L-4 ${y - 1}` : ''} ${right ? `M${boxWidth} ${y - 4} H${boxWidth + 6} M${boxWidth + 2} ${y - 7} L${boxWidth + 6} ${y - 4} L${boxWidth + 2} ${y - 1}` : ''}`}));
            label.append(svg('title', {}, [param.usage, param.type, param.dimensions ? '[' + param.dimensions + ']' : '', param.required ? 'Required argument' : 'Instance parameter', param.description].filter(Boolean).join(' · ')));
          }
          if (!param.sourceOnly) {
            const value = svg('text', {x: boxWidth - 9, y: param.member ? y : y + 13, class: 'lv-param-value' + (param.member ? ' lv-member-value' : '')});
            row.append(value);fields.push({el: value, ref: param.ref, argument: param.argument, valueLimit: Math.floor((boxWidth - 18) / 6)});
          }
          group.append(row);
        });
      }
      for (const name of ['in', 'out']) group.append(svg('circle', {class: 'lv-port', cx: name === 'in' ? 0 : width, cy: 0, r: 3,
        'data-port-id': name, 'data-port-direction': name === 'in' ? 'in' : 'out'}));
      const navigate = !current.draft && op === 'JMP' ? () => {const target = labelTarget(documents.map(d => d.graph), node.operands[0]);if (target) select(target.nodeId, true);} : null;
      const label = `${op} ${node.operands.join(', ')}. Select instruction details.${navigate ? ' Ctrl+Enter to follow label.' : ''}`;
      const marker = svg('text', {x: symbol ? width - 5 : position.boxWidth - 8, y: symbol ? -38 : -31,
        class: 'lv-fault-marker', 'aria-hidden': 'true'}, '');
      group.append(marker);bind(group, node.id, label, navigate);
      return {group, monitors: fields, node, graph, title, titleText: title.textContent, label, marker};
    }
    function focusDraftRung(index, target) {
      documents[index]?.row?.querySelector(target)?.focus();
    }
    function rungActions(index, graph) {
      const actions = html('div', 'lv-draft-rung-actions');
      actions.setAttribute('role', 'group');
      actions.setAttribute('aria-label', 'Actions for rung ' + graph.number);
      function button(label, action, run) {
        const control = html('button', '', label);
        control.type = 'button';
        control.dataset.rungAction = action;
        control.onclick = run;
        actions.append(control);
        return control;
      }
      button('Insert rung above', 'insert', () => {
        if (options.onDraftInsertRung(index)) focusDraftRung(index, '.lv-draft-gap');
      });
      button('Duplicate rung', 'duplicate', () => {
        if (options.onDraftDuplicateRung(index)) focusDraftRung(index + 1, '.lv-draft-gap');
      });
      button('Copy rung', 'copy', () => options.onDraftCopyRung(index));
      button('Edit comment', 'comment', () => options.onDraftComment(index));
      button('Move rung', 'move', () => options.onDraftMoveRung(index)).disabled = current.draft.rungs.length === 1;
      button('Delete rung', 'delete', () => {
        if (options.onDraftRemoveRung(index)) {
          focusDraftRung(Math.min(index, documents.length - 1), '[data-rung-action="insert"]');
        }
      }).disabled = current.draft.rungs.length === 1;
      return actions;
    }
    function renderLadder() {
      const graphs = (current.draft?.rungs || current.routine.rungs)
        .map(rung => root.LadderGraph.compile(rung, current.routine.key, !!current.draft));
      const minimum = Math.max(760, ...graphs.map(graph => root.LadderGraph.layout(graph, 0, node => faceplates.dimensions(node, presentation(node))).width));
      for (const [rungIndex, graph] of graphs.entries()) {
        const geometry = root.LadderGraph.layout(graph, minimum, node => faceplates.dimensions(node, presentation(node))), row = html('section', 'lv-rung');row.dataset.rung = graph.number;
        const comment = html('div', 'lv-rung-comment', graph.comment);comment.hidden = !showComments || !graph.comment;row.append(comment);
        if (current.draft) row.append(rungActions(rungIndex, graph));
        const picture = svg('svg', {class: 'lv-ladder', viewBox: `0 0 ${geometry.width} ${geometry.height}`, width: geometry.width * zoom,
          height: geometry.height * zoom, 'aria-label': `Rung ${graph.number}: ${graph.source || 'ladder logic'}`});
        picture.append(svg('text', {x: 9, y: geometry.nodes[graph.nodes[0].id].y + 4, class: 'lv-rung-number'}, graph.number));
        const instructions = new Map(), paths = new Map(), junctions = new Map(), gaps = [], branches = new Map();
        for (const edge of graph.edges) {
          const a = geometry.ports[edge.from.node + '/' + edge.from.port], b = geometry.ports[edge.to.node + '/' + edge.to.port];
          const path = svg('path', {class: 'lv-wire', d: `M${a.x} ${a.y} H${(a.x + b.x) / 2} V${b.y} H${b.x}`, 'data-edge-id': edge.id});
          picture.append(path);paths.set(edge.id, path);
          if (edge.gap) gaps.push(insertPoint(graph, rungIndex, edge, a, b));
        }
        for (const node of graph.nodes) {
          const p = geometry.nodes[node.id];
          if (node.kind === 'instruction') {
            const item = drawInstruction(node, p, graph);
            if (current.draft) {
              dragSources.set(item.group, {rung: rungIndex, id: node.draftId});
              item.group.classList.add('lv-draft-instruction');
            }
            instructions.set(node.id, item);
            picture.append(item.group);
          } else {
            const path = svg('path', {class: node.kind === 'rail' ? 'lv-rail' : 'lv-junction',
              d: node.kind === 'rail' ? `M${p.x} ${p.top} V${p.bottom}` : `M${p.x} ${p.y} V${p.endY}`});
            picture.append(path);junctions.set(node.id, path);
            if (current.draft && node.side === 'join') branches.set(node.id, {node, element: branchHandle(node, p, graph, rungIndex)});
          }
        }
        picture.append(...gaps, ...[...branches.values()].map(item => item.element));
        row.append(picture);canvas.append(row);
        documents.push({graph, rungIndex, row, geometry, svg: picture, instructions, paths, junctions, branches});
      }
    }
    function renderST() {
      const syntax = {depth: 0}, doc = {instructions: new Map(), rows: new Map()};documents.push(doc);
      const sheet = html('div', 'lv-st-document');sheet.style.fontSize = (13 * zoom) + 'px';
      for (const line of current.routine.lines || []) {
        const row = html('div', 'lv-st-line'), number = /^\d+$/.test(line.number) ? Number(line.number) + 1 : line.number;
        const code = html('code', 'lv-st-source');for (const token of tokenizeST(line.text, syntax)) code.append(html('span', 'lv-st-' + (token.kind === 'number' ? 'numeric' : token.kind), token.text));
        row.append(html('span', 'lv-st-number', number), code, html('span', 'lv-st-result'));
        const call = current.routine.rungs.find(rung => rung.number === line.number)?.nodes.find(node => node.name === 'JSR');
        const target = call && current.state.routines.find(r => r.key.toLowerCase() === (current.routine.key.split('/')[0] + '/' + call.args[0]).toLowerCase());
        if (target) {const button = html('button', 'lv-st-call', '↗');button.setAttribute('aria-label', 'Open routine ' + call.args[0]);button.title = 'Open ' + target.key;button.onclick = () => options.onOpenRoutine(target.key);row.append(button);}
        sheet.append(row);doc.rows.set(String(line.number), row);
      }
      canvas.append(sheet);
    }
    function renderFBD() {
      const graph = current.routine.diagram;if (!graph?.nodes?.length) return;
      const placed = new Map(), boxes = [];
      for (const node of [...graph.nodes].sort((a, b) => a.y - b.y || a.x - b.x)) {
        const incoming = [...new Set(graph.wires.filter(w => w.target === node.id).map(w => w.target_pin))];
        const outgoing = [...new Set(graph.wires.filter(w => w.source === node.id).map(w => w.source_pin))];
        const box = {x: Math.max(24, node.x * 1.2 + 24), y: Math.max(24, node.y * 1.3 + 24), width: 224,
          height: 63 + Math.max(1, incoming.length, outgoing.length) * 23, incoming, outgoing};
        for (let pass = 0; pass < graph.nodes.length; pass++) {
          const hit = boxes.find(b => box.x < b.x + b.width + 16 && box.x + box.width + 16 > b.x && box.y < b.y + b.height + 16 && box.y + box.height + 16 > b.y);
          if (!hit) break;box.y = hit.y + hit.height + 24;
        }
        boxes.push(box);placed.set(node.id, box);
      }
      const width = Math.max(760, ...boxes.map(b => b.x + b.width + 40)), height = Math.max(200, ...boxes.map(b => b.y + b.height + 24));
      const picture = svg('svg', {class: 'lv-fbd', viewBox: `0 0 ${width} ${height}`, width: width * zoom, height: height * zoom, 'aria-label': 'Function block diagram'});
      const doc = {instructions: new Map(), svg: picture, width, height, paths: new Map()};documents.push(doc);
      for (const wire of graph.wires) {
        const a = placed.get(wire.source), b = placed.get(wire.target);if (!a || !b) continue;
        const x = a.x + a.width, y = a.y + 60 + a.outgoing.indexOf(wire.source_pin) * 23, tx = b.x, ty = b.y + 60 + b.incoming.indexOf(wire.target_pin) * 23;
        const path = svg('path', {class: 'lv-fbd-wire', d: `M${x} ${y} H${(x + tx) / 2} V${ty} H${tx}`});
        path.append(svg('title', {}, `${wire.source}.${wire.source_pin} → ${wire.target}.${wire.target_pin}`));picture.append(path);doc.paths.set(path, wire.source);
      }
      for (const node of graph.nodes) {
        const p = placed.get(node.id), id = current.routine.key + ':fbd:' + node.id;
        const group = svg('g', {class: 'lv-fbd-node', transform: `translate(${p.x},${p.y})`});
        group.append(svg('rect', {class: 'lv-fbd-box', width: p.width, height: p.height}), svg('text', {x: 10, y: 20, class: 'lv-block-opcode'}, node.type || node.kind),
          svg('text', {x: 10, y: 40, class: 'lv-param-reference'}, short(node.operand, 28)));
        for (const [direction, pins] of [['in', p.incoming], ['out', p.outgoing]]) pins.forEach((pin, i) => {
          const x = direction === 'in' ? 0 : p.width, y = 60 + i * 23;
          group.append(svg('circle', {class: 'lv-fbd-pin', cx: x, cy: y, r: 3}), svg('text', {class: 'lv-fbd-pin-name', x: x + (direction === 'in' ? 9 : -9), y: y - 5, 'text-anchor': direction === 'in' ? 'start' : 'end'}, short(pin, 18)));
        });
        const value = svg('text', {x: p.width - 9, y: 20, class: 'lv-param-value'});group.append(value);
        bind(group, id, `${node.type || node.kind} ${node.operand}. Select details.`);
        const members = current.state.tags.filter(row => row.name.toLowerCase().startsWith((node.operand + '.').toLowerCase())).slice(0, 40);
        doc.instructions.set(id, {group, node: {...node, opcode: node.type || node.kind}, fields: members.length ? members.map(row => ({label: row.name.slice(node.operand.length + 1), ref: row.name})) : [{label: 'Operand', ref: node.operand}], monitors: [{el: value, ref: node.operand}]});
        picture.append(group);
      }
      canvas.append(picture);
    }
    function rebuild() {
      endDrag();
      indicateResize(null);
      const scroll = {left: canvas.scrollLeft, top: canvas.scrollTop};documents = [];canvas.replaceChildren();inspection = '';
      canvas.className = 'lv-canvas language-' + current.routine.kind.toLowerCase();canvas.classList.toggle('lv-hide-values', !showValues);
      if (current.routine.problems?.length) canvas.append(html('p', 'lv-source-note', current.routine.problems.join('\n')));
      if (current.routine.kind === 'RLL') renderLadder();
      else if (current.routine.kind === 'ST') renderST();
      else if (current.routine.kind === 'FBD') renderFBD();
      if (!canvas.children.length) canvas.append(html('p', 'lv-empty', current.routine.problems.join('\n') || 'This routine has no displayable logic.'));
      canvas.scrollLeft = scroll.left;canvas.scrollTop = scroll.top;update();
    }
    function update() {
      lastTraces = new Map();
      for (const item of current.state.trace || []) if (!current.draft && item.routine === current.routine.key && (!current.context || item.context === current.context)) {
        lastTraces.set(item.rung_index ?? String(item.number), item);
      }
      for (const doc of documents) {
        if (doc.graph) {
          const indexed = trace(doc.rungIndex);
          const visit = String(indexed?.number) === doc.graph.number ? indexed : trace(doc.graph.number);
          doc.power = root.LadderGraph.power(doc.graph, visit, doc.rungIndex);
          for (const [id, path] of doc.paths) path.classList.toggle('live', doc.power.edges[id] === true);
          for (const [id, path] of doc.junctions) path.classList.toggle('live', doc.power.nodes[id]?.out === true);
          for (const [id, item] of doc.instructions) {
            const power = doc.power.nodes[id];item.group.classList.toggle('live', power?.out === true);
            item.group.classList.toggle('power-in', power?.in === true);item.group.classList.toggle('untraced', !power?.event);
            item.group.classList.toggle('unsupported', !current.recognized(item.node.opcode));
            const recovery = faultCode(power?.recoveredFault), marker = recovery ? `SKIPPED ${recovery}` : '';
            if (item.marker.textContent !== marker) {
              item.marker.textContent = marker;
              item.group.classList.toggle('recovered-fault', !!recovery);
              item.group.setAttribute('aria-label', recovery ? `${item.label} ${faultMessage(recovery)}` : item.label);
              item.title.textContent = recovery ? `${item.titleText}\n${faultMessage(recovery)}` : item.titleText;
            }
            for (const field of item.monitors) {
              const {sample, unsampled, row} = operandDisplay(field, item.node, power);
              if (sample) {
                const value = sampleText(sample);
                field.el.textContent = sample.address ?
                  short(sample.address, Math.max(6, field.valueLimit - value.length - 3)) + ' = ' + value : value;
                field.el.setAttribute('aria-label', sampleLabel(field.argument, power.loopTrace) + ' · ' +
                  (sample.address ? sample.address + ' = ' : '') + value);
              } else {
                field.el.textContent = unsampled ? '—' : field.flag || (row?.aggregate ? '' : valueText(row));
                field.el.removeAttribute('aria-label');
              }
              field.el.classList.toggle('captured', !!sample);
              field.el.classList.toggle('unknown', !sample && !unsampled && (!row || row.value == null));
              field.el.classList.toggle('on', !!field.flag && row?.value === true);
            }
          }
        } else if (doc.rows) {
          for (const [number, row] of doc.rows) {
            const last = trace(number);row.classList.toggle('executed', !!last);row.classList.toggle('condition-false', last?.power === false);
            row.querySelector('.lv-st-result').textContent = last?.detail || '';row.title = last ? `${last.statement}: ${last.detail}` : 'Not visited in the last scan';
          }
        } else {
          for (const item of doc.instructions.values()) {
            const last = trace(String(item.node.id));item.group.classList.toggle('live', last?.power === true);
            for (const field of item.monitors) {const row = read(field.ref, item.node);field.el.textContent = row && !row.aggregate ? valueText(row) : '';}
          }
          for (const [path, source] of doc.paths) path.classList.toggle('live', trace(String(source))?.power === true);
        }
      }
      canvas.classList.toggle('lv-hide-values', !!current.draft || !showValues);
      for (const doc of documents) {if (doc.row) doc.row.firstChild.hidden = !showComments || !doc.graph.comment;}
      const count = [...lastTraces.values()].length;
      if (!current.draft) status.textContent = count ? `Last scan ${current.state.scan} · ${count} ${current.routine.kind === 'ST' ? 'line' : 'rung/block'} visits` : 'No execution trace';
      moveStatus();
      updateSelection();
      updateInspector();
    }
    return {
      render(value) {
        const wasEditing = !!current?.draft;
        current = value;valueMap = new Map(value.state.tags.map(row => [row.name.toLowerCase(), row]));
        snapshot = values.create(value.state.tags, {routine: value.routine.key, context: value.context, bindings: value.state.aoi_bindings?.[value.context] || {}});
        const source = JSON.stringify([value.state.connectivity?.source_l5x_sha256 || value.state.name, value.routine.key, value.routine.rungs, value.routine.lines, value.routine.diagram, value.state.aoi_definitions]);
        if (source !== sourceIdentity) {
          monitorSelection = draftSelection = '';sourceIdentity = source;
          zoom = 1;canvas.scrollTo(0, 0);options.onZoom?.(zoom);
        }
        selected = value.draft ? draftSelection : monitorSelection;
        const next = JSON.stringify([source, value.context]);
        const nextDraft = value.draft?.rungs;
        if (next !== key || nextDraft !== draftRungs || wasEditing !== !!value.draft) {
          movePick = null;
          key = next;draftRungs = nextDraft;
          canvas.dataset.routine = current.routine.key;rebuild();
        } else update();
      },
      zoom(value) {zoom = Math.max(0.1, Math.min(2, value));if (current) rebuild();return zoom;},
      fit() {if (!current) return zoom;const width = Math.max(760, ...documents.filter(d => d.svg).map(d => d.geometry?.width || d.width));return this.zoom(Math.min(1, Math.max(0.1, (canvas.clientWidth - 12) / width)));},
      values(value) {showValues = value;if (current) update();},
      comments(value) {showComments = value;if (current) update();},
      focusDraftRung,
      graphs() {return documents.filter(d => d.graph).map(d => structuredClone(d.graph));},
      dispose() {endDrag();indicateResize(null);movePick = null;documents = [];current = null;}
    };
  }
  return {create, tokenizeST, labelTarget, parameterRadix, lrealMathRadix, realMathRadix, ladderWordRadix};
});
