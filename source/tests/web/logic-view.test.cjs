const {test} = require('node:test');
const assert = require('node:assert/strict');
const graph = require('../../web/ladder-graph.js');
const {tokenizeST, labelTarget} = require('../../web/logic-view.js');
const instruction = require('../../web/instruction-view.js');
const op = (name, ...args) => ({name, args});
const rung = nodes => ({number: '0', comment: 'Seal in', text: 'source retained', nodes});
const seal = () => graph.compile(rung([op('XIO', 'Stop'), {branch: [[op('XIC', 'Start')], [op('XIC', 'Latch')]]}, op('OTE', 'Latch')]), 'Main/Main');
test('ALMA faceplate binds rate settings, live rate and condition shelf flags', () => {
  const face = instruction.describe({opcode: 'ALMA', operands: ['Alarm', 'Input', 'Ack', 'Disable', 'Enable']});
  assert.deepEqual(face.rows.slice(-4).map(row => [row.label, row.ref, row.member]), [
    ['ROCPeriod', 'Alarm.ROCPeriod', true], ['ROCPosLimit', 'Alarm.ROCPosLimit', true],
    ['ROCNegLimit', 'Alarm.ROCNegLimit', true], ['ROC', 'Alarm.ROC', true],
  ]);
  assert.deepEqual(face.flags.filter(flag => flag.label.startsWith('R')), [
    {label: 'R+', ref: 'Alarm.ROCPosInAlarm'}, {label: 'R-', ref: 'Alarm.ROCNegInAlarm'},
  ]);
  assert.deepEqual(face.rows.slice(-6, -4).map(row => row.ref),
    ['Alarm.ShelveDuration', 'Alarm.MaxShelveDuration']);
  assert.equal(face.rows.find(row => row.label === 'MinDurationPRE')?.ref, 'Alarm.MinDurationPRE');
  assert.deepEqual(face.flags.slice(-6).map(flag => flag.ref), [
    'Alarm.HHShelved', 'Alarm.HShelved', 'Alarm.LShelved', 'Alarm.LLShelved',
    'Alarm.ROCPosShelved', 'Alarm.ROCNegShelved',
  ]);
  const timestamps = face.fields.filter(field => field.type === 'LINT');
  assert.equal(timestamps.length, 11);
  assert(timestamps.some(field => field.ref === 'Alarm.HHInAlarmTime' && field.visible === false));
  assert(timestamps.some(field => field.ref === 'Alarm.UnshelveTime' && field.visible === false));
  assert(face.rows.every(row => row.type !== 'LINT'));
});
test('call operand samples require the same rung, opcode and authored operands', () => {
  const g = graph.compile(rung([op('SBR', 'Slots[Index]')]), 'Main/Worker');
  const sample = [{address: 'Slots[1]', value: 7, type: 'DINT'}];
  const event = {instruction: 'SBR', args: ['Slots[Index]'], in: true, out: true, operand_samples: sample};
  const trace = {rung_index: 1, operand_source: g.source, events: [event]};
  const read = (model, visit, index) => graph.power(model, visit, index).nodes[g.order[0]].operandSamples;
  assert.equal(read(g, trace, 1), sample);
  assert.equal(read(g, trace, 0), null);
  assert.equal(read({...g, source: 'Edited source'}, trace, 1), null);
  assert.equal(read(g, {...trace, events: [{...event, args: ['Slots[Other]']}]}, 1), null);
  assert.equal(read(g, {...trace, events: [{...event, instruction: 'RET'}]}, 1), null);
  assert.equal(read(g, {...trace, events: [{instruction:'SBR', args: event.args, in: false, out: false}]}, 1), null);
});

test('loop details belong to the matching FOR visit and keep the source operand order', () => {
  const args = ['Worker', 'IndexSlots[Slot]', '0', 'Bounds[Slot]', '1'];
  const g = graph.compile(rung([op('FOR', ...args)]), 'Main/Main');
  const loop = {visits: 2, exit: 'bounds'};
  const event = {instruction: 'FOR', args, in: true, out: true, operand_samples: [null], loop_trace: loop};
  const trace = {rung_index: 0, operand_source: g.source, events: [event]};
  assert.equal(graph.power(g, trace, 0).nodes[g.order[0]].loopTrace, loop);
  assert.equal(graph.power({...g, source: 'edited'}, trace, 0).nodes[g.order[0]].loopTrace, null);
  assert.equal(graph.power(g, {...trace, events: [{...event, operand_samples: null}]}, 0).nodes[g.order[0]].loopTrace, null);
  const face = instruction.describe({opcode: 'FOR', operands: args});
  assert.deepEqual(face.rows.map(row => row.argument), [0, 1, 2, 3, 4]);
});

function validate(g) {
  const nodes = new Map(g.nodes.map(node => [node.id, node]));
  assert.equal(nodes.size, g.nodes.length);
  const degrees = new Map(g.nodes.map(node => [node.id, 0]));
  for (const edge of g.edges) {
    assert.equal(nodes.get(edge.from.node).ports.find(p => p.id === edge.from.port)?.direction, 'out');
    assert.equal(nodes.get(edge.to.node).ports.find(p => p.id === edge.to.port)?.direction, 'in');
    degrees.set(edge.to.node, degrees.get(edge.to.node) + 1);
  }
  const ready = [...degrees].filter(([, n]) => !n).map(([id]) => id);let visited = 0;
  while (ready.length) {
    const id = ready.shift();visited++;
    for (const edge of g.edges.filter(e => e.from.node === id)) {
      const degree = degrees.get(edge.to.node) - 1;degrees.set(edge.to.node, degree);if (!degree) ready.push(edge.to.node);
    }
  }
  assert.equal(visited, g.nodes.length, 'Power topology must be acyclic');
}
test('seal-in source becomes an explicit power graph with split/join ports', () => {
  const g = seal();validate(g);
  assert.equal(g.schemaVersion, 1);assert.equal(g.nodes.length, 8);assert.equal(g.edges.length, 8);
  assert.deepEqual(g.order.map(id => g.nodes.find(n => n.id === id).opcode), ['XIO', 'XIC', 'XIC', 'OTE']);
  const split = g.nodes.find(n => n.side === 'split'), join = g.nodes.find(n => n.side === 'join');
  assert.deepEqual(split.ports.map(p => p.id), ['in', 'path0', 'path1']);
  assert.deepEqual(join.ports.map(p => p.id), ['path0', 'path1', 'out']);
  assert.equal(g.source, 'source retained');
});
test('nested branches and empty bypass paths keep their independent connections', () => {
  const g = graph.compile(rung([{branch: [[op('XIC', 'A'), {branch: [[], [op('XIC', 'B')]]}], [op('XIC', 'C')]]}, op('OTE', 'Q')]));
  validate(g);assert.equal(g.nodes.filter(n => n.kind === 'junction').length, 4);
  assert(g.edges.some(e => e.from.node.endsWith(':split') && e.to.node.endsWith(':join')), 'Empty bypass is an edge, not an invented instruction');
  assert.equal(new Set(g.edges.map(e => e.id)).size, g.edges.length);
});
test('source conversion never mutates source arrays or instruction arguments', () => {
  const source = rung([op('MOV', 'Source', 'Dest')]), original = structuredClone(source);
  const g = graph.compile(source);g.nodes.find(n => n.kind === 'instruction').operands[0] = 'Changed';
  assert.deepEqual(source, original);
});
test('exact time literal metadata follows the node without changing source operands', () => {
  const literal = 'LDT#2026-01-01-00:00:00.000_000_001';
  const move = {...op('MOV', literal, 'Stamp'),
    literal_values: {[literal]: {type: 'LDT literal', value: '1767225600000000001'}}};
  const g = graph.compile(rung([{branch: [[move], [op('NOP')]]}]));
  const node = g.nodes.find(n => n.opcode === 'MOV');
  assert.equal(node.operands[0], literal);
  assert.deepEqual(node.literalValues, move.literal_values);
  node.literalValues[literal].value = '0';
  assert.equal(move.literal_values[literal].value, '1767225600000000001');
});
test('node identities stay stable across scans and operand-value changes', () => {
  const a = seal(), b = seal();assert.deepEqual(a, b);
  graph.power(a, {power: true, events: []});graph.layout(a, 1400);assert.deepEqual(a, b);
  const modified = rung([op('MOV', 'Different', 'Dest')]);
  assert.deepEqual(graph.compile(modified).order, graph.compile(rung([op('MOV', 'Source', 'Dest')])).order);
});
test('layout gives every edge two valid port coordinates and retains series order', () => {
  const g = seal(), drawing = graph.layout(g, 1200);assert(drawing.width >= 1200);
  for (const edge of g.edges) {
    const a = drawing.ports[edge.from.node + '/' + edge.from.port], b = drawing.ports[edge.to.node + '/' + edge.to.port];
    assert(a && b);assert(a.x <= b.x);assert.equal(a.y, b.y);
  }
  const a = drawing.nodes[g.order[0]], q = drawing.nodes[g.order.at(-1)];
  assert(a.x + a.width < q.x);assert(q.x + q.width < drawing.width);
});
test('parallel instruction extents cannot overlap, including nested timer boxes', () => {
  const g = graph.compile(rung([{branch: [[op('TON', 'T', '?', '?')], [{branch: [[op('XIC', 'A')], [op('MOV', 'X', 'Y')]]}]]}, op('OTE', 'Q')]));
  validate(g);const drawing = graph.layout(g);
  const boxes = g.order.map(id => ({id, ...drawing.nodes[id]}));
  for (let a = 0; a < boxes.length; a++) for (let b = a + 1; b < boxes.length; b++) {
    const x = boxes[a], y = boxes[b];
    const overlap = x.x < y.x + y.width && x.x + x.width > y.x && x.y - x.above < y.y + y.below && x.y + x.below > y.y - y.above;
    assert(!overlap, `${x.id} overlaps ${y.id}`);
  }
});
test('terminal coils align to a shared right rail across different rungs', () => {
  const a = graph.compile(rung([op('XIC', 'A'), op('OTE', 'Q')]));
  const b = graph.compile(rung([op('XIC', 'A'), op('XIC', 'B'), op('OTE', 'Q')]));
  const aa = graph.layout(a, 1200), bb = graph.layout(b, 1200);
  assert.equal(aa.nodes[a.order.at(-1)].x, bb.nodes[b.order.at(-1)].x);
});
test('last-scan branch traces energize the join through either path', () => {
  const g = seal(), values = graph.power(g, {power: true, events: [
    {instruction: 'XIO', in: true, out: true}, {instruction: 'XIC', in: true, out: false},
    {instruction: 'XIC', in: true, out: true}, {instruction: 'OTE', in: true, out: true}]});
  assert.equal(values.nodes[g.order[1]].out, false);assert.equal(values.nodes[g.order[2]].out, true);
  assert.equal(values.nodes[g.nodes.find(n => n.side === 'join').id].out, true);
  assert.equal(values.nodes[g.order.at(-1)].out, true);
});
test('absent traces stay unknown instead of displaying false or fabricated power', () => {
  const g = seal(), values = graph.power(g);
  assert(Object.values(values.edges).every(value => value === undefined));
  assert(Object.values(values.nodes).every(value => value.out === undefined));
});
test('a partial jump trace cannot energize unvisited instructions', () => {
  const g = graph.compile(rung([op('JMP', 'End'), op('XIC', 'Skipped'), op('OTE', 'Q')]));
  const values = graph.power(g, {power: true, events: [{instruction: 'JMP', in: true, out: true}]});
  assert.equal(values.nodes[g.order[1]].event, null);assert.equal(values.nodes[g.order[1]].out, undefined);
  const intoSkipped = g.edges.find(e => e.to.node === g.order[1]);assert.equal(values.edges[intoSkipped.id], undefined);
});
test('recovery marks the exact trace node while the outgoing wire stays powered', () => {
  const g = graph.compile(rung([{branch: [[op('MOV', 'A', 'X')], [op('MOV', 'A', 'X')]]}, op('MOV', 'B', 'Y')]));
  const fault = {type: 4, code: 20}, move = {instruction: 'MOV', args: ['A', 'X'], in: true, out: true};
  const trace = {rung_index: 1, recovery_source: g.source, events: [
    move, {...move, recovered_fault: fault}, {...move, args: ['B', 'Y']}]};
  const values = graph.power(g, trace, 1);
  assert.deepEqual(g.order.map(id => values.nodes[id].recoveredFault), [null, fault, null]);
  for (const edge of g.edges) assert.equal(values.edges[edge.id], true);
  assert.deepEqual(graph.power(g, trace, 0).nodes[g.order[1]].recoveredFault, null);
  assert.deepEqual(graph.power({...g, source: 'edited rung'}, trace, 1).nodes[g.order[1]].recoveredFault, null);
  const mismatch = {...trace, events: [move, {...move, args: ['A', 'Z'], recovered_fault: fault}, move]};
  assert.deepEqual(graph.power(g, mismatch, 1).nodes[g.order[1]].recoveredFault, null);
  assert.deepEqual(graph.power(g, {...trace, events: [move, move, move]}, 1).nodes[g.order[1]].recoveredFault, null);
});
test('an empty rung remains a direct rail-to-rail connection', () => {
  const g = graph.compile(rung([]));validate(g);assert.equal(g.edges.length, 1);assert.equal(g.order.length, 0);
  assert.equal(graph.power(g, {power: true, events: []}).edges[g.edges[0].id], true);
});
test('ST tokens preserve exact source including strings, radix literals and operators', () => {
  const source = "IF Input THEN Value := 16#FFFF + 9007199254740993UL; Text := 'it$'s <tag>'; END_IF; // note";
  const tokens = tokenizeST(source);assert.equal(tokens.map(t => t.text).join(''), source);
  assert(tokens.some(t => t.kind === 'keyword' && t.text === 'IF'));
  assert(tokens.some(t => t.kind === 'number' && t.text === '16#FFFF'));
  assert(tokens.some(t => t.kind === 'string' && t.text.includes('<tag>')));
});
test('ST block comments remain comments across lines and support nesting', () => {
  const state = {depth: 0}, lines = ['(* outer (* nested', '*) still outer', '*) Value := 1;'];
  const tokens = lines.map(line => tokenizeST(line, state));assert.equal(state.depth, 0);
  assert(tokens[1].every(token => token.kind === 'comment'));
  assert(tokens[2].some(token => token.kind === 'number'));
  assert.deepEqual(tokens.map(row => row.map(t => t.text).join('')), lines);
});

test('timer and control faceplates monitor saved members instead of neutral placeholders', () => {
  const face = (opcode, ...operands) => instruction.describe({opcode, operands});
  assert.deepEqual(face('TON', 'Delay', '?', '?').rows.map(row => row.ref), ['Delay', 'Delay.PRE', 'Delay.ACC']);
  assert.deepEqual(face('FFL', 'Item', 'Queue[0]', 'QueueState', '?', '?').rows.slice(-2).map(row => row.ref), ['QueueState.LEN', 'QueueState.POS']);
  assert.equal(face('BSL', 'Bits', 'Shift', 'Input', '?').rows.at(-1).ref, 'Shift.LEN');
  assert.deepEqual(face('DDT', 'A', 'B', 'Results', 'Compare', '?', '?', 'Found', '?', '?').rows.map(row => row.ref),
    ['A', 'B', 'Results', 'Compare', 'Compare.LEN', 'Compare.POS', 'Found', 'Found.LEN', 'Found.POS']);
  assert.equal(face('MOV', '?', 'Dest').rows[0].ref, '?', 'Only defined pseudo-operands may be expanded');
});

test('routine faceplates distinguish input and return arguments from the neutral count', () => {
  const face = instruction.describe({opcode: 'JSR', operands: ['Worker', '2', 'A', 'B', 'Result']});
  assert.deepEqual(face.rows.map(row => row.argument), [0, 2, 3, 4]);
  assert.deepEqual(face.rows.map(row => [row.label, row.ref]), [['Routine Name', 'Worker'], ['Input Par 1', 'A'], ['Input Par 2', 'B'], ['Return Par 1', 'Result']]);
  assert(face.rows[0].sourceOnly);assert(!face.rows[1].sourceOnly);
});

function aoiDefinition() {
  return {QUEUE: {name: 'Queue', description: 'Public test definition', parameters: [
    {name: 'EnableIn', type: 'BOOL', usage: 'Input', required: false, visible: false},
    {name: 'HiddenArg', type: 'DINT', usage: 'Input', required: true, visible: false},
    {name: 'Buffer', type: 'DINT', usage: 'InOut', dimensions: '6', required: true, visible: true},
    {name: 'Ready', type: 'BOOL', usage: 'Output', required: false, visible: true},
    ...Array.from({length: 8}, (_, i) => ({name: 'Setting' + i, type: 'DINT', usage: 'Input', required: false, visible: true})),
    {name: 'Private', type: 'DINT', usage: 'Output', required: false, visible: false},
    {name: 'EnableOut', type: 'BOOL', usage: 'Output', required: false, visible: false}]}};
}

test('AOI rows retain declaration order, binding roles and independent visibility', () => {
  const definitions = aoiDefinition(), original = structuredClone(definitions);
  const face = instruction.describe({opcode: 'qUeUe', operands: ['Driver', '17', 'External[2]']}, definitions);
  assert.equal(face.kind, 'aoi');assert.equal(face.title, 'Queue');
  assert.deepEqual(face.rows.slice(0, 3).map(row => [row.label, row.ref]), [['Instance', 'Driver'], ['Buffer', 'External[2]'], ['Ready', 'Driver.Ready']]);
  assert.equal(face.fields.find(row => row.label === 'HiddenArg').ref, '17');
  assert.equal(face.fields.find(row => row.label === 'Private').ref, 'Driver.Private');
  assert.equal(face.rows[1].usage, 'InOut');assert.equal(face.rows[1].dimensions, '6');
  assert.equal(face.rows.length, 11);assert(!face.rows.some(row => row.label === 'EnableOut'));
  assert.deepEqual(definitions, original);
});

test('AOI geometry uses every visible row and keeps nested branches apart', () => {
  const g = graph.compile(rung([{branch: [[op('QUEUE', 'Driver', '17', 'External')], [op('TON', 'T', '?', '?')]]}, op('OTE', 'Q')]));
  const original = structuredClone(g), drawing = graph.layout(g, 0, node => instruction.dimensions(node, instruction.describe(node, aoiDefinition())));
  const a = drawing.nodes[g.order[0]], b = drawing.nodes[g.order[1]];
  assert.equal(a.rows, 11);assert(a.below > 370);assert(a.y + a.below < b.y - b.above);
  for (const id of g.order) {const box = drawing.nodes[id];assert(box.y + box.below < drawing.height);}
  assert.deepEqual(g, original);
});

test('unknown instructions retain all source operands without inventing a supported definition', () => {
  const node = {opcode: 'VENDOR_CUSTOM', operands: Array.from({length: 9}, (_, i) => 'Argument' + i)};
  const face = instruction.describe(node);assert.equal(face.known, false);assert.equal(face.rows.length, 9);
  assert.deepEqual(face.rows.map(row => row.ref), node.operands);assert.equal(instruction.dimensions(node, face).rows, 9);
});

test('label navigation finds a unique target across rungs, including branch labels', () => {
  const a = graph.compile(rung([op('JMP', 'Finish')]), 'Main/Logic');
  const b = graph.compile({...rung([{branch: [[op('LBL', 'FINISH')], [op('NOP')]]}]), number: '9'}, 'Main/Logic');
  const original = structuredClone([a, b]), target = labelTarget([a, b], 'finish');
  assert.deepEqual(target, {nodeId: b.order[0], graphId: b.id});assert.deepEqual([a, b], original);
});
test('missing and ambiguous labels do not invent a navigation destination', () => {
  const a = graph.compile(rung([op('LBL', 'Again'), op('LBL', 'AGAIN')]));
  assert.equal(labelTarget([a], 'Missing'), null);assert.equal(labelTarget([a], 'Again'), null);
});

test('UID and UIE are named operand-free inline instructions in the power graph', () => {
  const g = graph.compile(rung([op('UID'), op('UID'), op('UIE'), op('UIE')]));validate(g);
  for (const id of g.order) {
    const node = g.nodes.find(n => n.id === id), face = instruction.describe(node);
    assert.equal(face.known, true);assert.deepEqual(face.rows, []);
    assert.equal(face.title, node.opcode === 'UID' ? 'User Interrupt Disable' : 'User Interrupt Enable');
    assert.equal(face.kind, 'inline');assert.equal(instruction.dimensions(node, face).symbol, true);
  }
});
