'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const draftModel = require('../../web/ladder-draft.js');
const graph = require('../../web/ladder-graph.js');

const op = (name, ...args) => ({name, args});
function fixture() {
  return {kind: 'RLL', key: 'MainProgram/Main', problems: [], rungs: [
    {number: '0', text: '  XIC(Start) OTE(Run);', comment: 'Seal in', nodes: [op('XIC', 'Start'), op('OTE', 'Run')]},
    {number: '1', text: 'MOV(0, Count);', comment: 'Reset', nodes: [op('MOV', '0', 'Count')]}
  ]};
}

test('draft uses wire gaps and preserves source and stable node identity through history', () => {
  const routine = fixture(), original = structuredClone(routine);
  const draft = draftModel.create(routine);
  const first = graph.compile(draft.rungs[0], routine.key, true);
  const oldIds = first.order.slice();
  const branchId = draft.insert(0, first.edges[1].gap, 'Branch');
  const branched = graph.compile(draft.rungs[0], routine.key, true);
  const branch = branched.nodes.find(node => node.id.endsWith(':draft:' + branchId + ':split'));
  assert.deepEqual(branched.order, oldIds);
  const path = branched.edges.find(edge => edge.from.node === branch.id && edge.from.port === 'path1');
  assert.deepEqual(path.gap, {legs: [[1, 1]], index: 0});
  assert.equal(draft.rungs[0].text, 'XIC(Start)[,]OTE(Run);');
  const id = draft.insert(0, path.gap, 'XIO');
  assert.equal(draft.setOperands(0, id, ['Stop']), id);
  assert.equal(draft.rungs[0].text, 'XIC(Start)[,XIO(Stop)]OTE(Run);');
  assert.equal(draft.rungs[1].text, original.rungs[1].text);
  assert.deepEqual(routine, original);
  assert.equal(draft.undo(), true);
  assert.equal(draft.rungs[0].text, 'XIC(Start)[,XIO(?)]OTE(Run);');
  draft.undo();
  draft.undo();
  assert.equal(draft.changed, false);
  assert.equal(draft.rungs[0].text, original.rungs[0].text);
  draft.redo();
  draft.redo();
  draft.redo();
  assert.equal(graph.compile(draft.rungs[0], routine.key, true).nodes.some(node => node.draftId === id), true);
  assert.equal(draft.rungs[0].text, 'XIC(Start)[,XIO(Stop)]OTE(Run);');
});

test('nested gaps compile to drawable wires and never appear on the monitor graph', () => {
  const routine = fixture(), draft = draftModel.create(routine);
  assert(draft.insert(0, {legs: [], index: 0}, 'Branch'));
  assert(draft.insert(0, {legs: [[0, 0]], index: 0}, 'Branch'));
  const ladder = graph.compile(draft.rungs[0], routine.key, true);
  const point = ladder.edges.find(edge => edge.gap.legs.length === 2 &&
    edge.gap.legs.at(-1)[1] === 0);
  assert(draft.insert(0, point.gap, 'MOV'));
  const layout = graph.layout(ladder);
  for (const edge of ladder.edges) {
    assert(layout.ports[edge.from.node + '/' + edge.from.port]);
    assert(layout.ports[edge.to.node + '/' + edge.to.port]);
  }
  assert.equal(draft.rungs[0].text, '[[MOV(?,?),],]XIC(Start)OTE(Run);');
  assert(graph.compile(routine.rungs[0], routine.key).edges.every(edge => !('gap' in edge)));
});

test('operand boundary checks are transactional and preserve literal punctuation', () => {
  const draft = draftModel.create(fixture()), id = draft.rungs[1].nodes[0].draftId;
  for (const label of ['A,B', 'A);OTE(B', "'unfinished", 'Index[(1])', " 'dangling$' "]) {
    assert.throws(() => draft.setOperands(1, id, [label, 'Count']), /operand/i);
    assert.equal(draft.canUndo, false);
  }
  assert(draft.setOperands(1, id, ["'a$,b$'c'", 'Target[Index(1,2),3]']));
  assert.equal(draft.rungs[1].text, "MOV('a$,b$'c',Target[Index(1,2),3]);");
  draft.remove(1, id);
  assert.equal(draft.rungs[1].text, ';');
  draft.undo();
  assert.equal(draft.rungs[1].nodes[0].draftId, id);
  draft.setOperands(1, id, ['0', 'Count']);
  assert.equal(draft.canRedo, false);
  assert.equal(draft.changed, false);
  assert.equal(draft.rungs[1].text, 'MOV(0, Count);');
});

test('non-RLL, AOI and diagnosed routines stay in Monitor', () => {
  const routine = fixture();
  for (const override of [{kind: 'ST'}, {kind: 'FBD'}, {key: 'AOI:Sample/Logic'},
    {problems: ['Rung 1: pending/test edit rung type']}, {rungs: []}]) {
    assert.equal(draftModel.canEdit({...routine, ...override}), false);
  }
  assert.equal(draftModel.canEdit(routine), true);
  assert.throws(() => draftModel.create({...routine, kind: 'FBD'}), /read-only/);
});

test('moves between rungs preserve the instruction ID and undo both rungs together', () => {
  const routine = fixture(), draft = draftModel.create(routine);
  const id = draft.rungs[0].nodes[0].draftId;
  const same = {legs: [], index: 1};
  assert.equal(draft.canMove(0, id, 0, same), false);
  assert.equal(draft.move(0, id, 0, same), null);
  assert.equal(draft.move(0, id, 99, same), null);
  assert.equal(draft.canUndo, false);
  assert(draft.move(0, id, 1, same));
  assert.equal(draft.rungs[0].text, 'OTE(Run);');
  assert.equal(draft.rungs[1].text, 'MOV(0,Count)XIC(Start);');
  assert.equal(draft.rungs[1].nodes[1].draftId, id);
  assert.equal(draft.undo(), true);
  assert.deepEqual(draft.rungs.map(rung => rung.text), routine.rungs.map(rung => rung.text));
  assert.equal(draft.redo(), true);
  assert.equal(draft.rungs[1].nodes[1].draftId, id);
});

test('moves into a later nested branch resolve the destination before removing the source', () => {
  const routine = fixture(), draft = draftModel.create(routine);
  const moved = draft.rungs[0].nodes[0].draftId;
  const outer = draft.insert(0, {legs: [], index: 1}, 'Branch');
  const inner = draft.insert(0, {legs: [[1, 1]], index: 0}, 'Branch');
  const ladder = graph.compile(draft.rungs[0], routine.key, true);
  const split = ladder.nodes.find(node => node.id.endsWith(':draft:' + inner + ':split'));
  const wire = ladder.edges.find(edge => edge.from.node === split.id && edge.from.port === 'path0');
  assert.equal(draft.move(0, outer, 0, wire.gap), null);
  assert.equal(draft.move(0, moved, 0, wire.gap), moved);
  assert.equal(draft.rungs[0].text, '[,[XIC(Start),]]OTE(Run);');
  assert.equal(draft.rungs[0].nodes[0].branch[1][0].branch[0][0].draftId, moved);
});

test('branch leg commands preserve remaining nodes and restore nested topology on undo', () => {
  const routine = fixture(), draft = draftModel.create(routine);
  const branch = draft.insert(0, {legs: [], index: 1}, 'Branch');
  const first = draft.insert(0, {legs: [[1, 0]], index: 0}, 'TON');
  const last = draft.insert(0, {legs: [[1, 1]], index: 0}, 'ADD');
  assert.equal(draft.addLeg(0, branch), branch);
  const visual = graph.compile(draft.rungs[0], routine.key, true);
  assert(visual.nodes.some(node => node.side === 'join' && node.draftId === branch && node.legCount === 3));
  assert.equal(draft.removeLeg(0, branch, 3), null);
  assert.equal(draft.removeLeg(0, branch, 0), branch);
  assert.equal(draft.rungs[0].text, 'XIC(Start)[ADD(?,?,?),]OTE(Run);');
  assert(draft.removeLeg(0, branch, 1));
  assert.equal(draft.rungs[0].text, 'XIC(Start)ADD(?,?,?)OTE(Run);');
  assert.equal(draft.rungs[0].nodes[1].draftId, last);
  draft.undo();
  draft.undo();
  assert.equal(draft.rungs[0].nodes[1].draftId, branch);
  assert.equal(draft.rungs[0].nodes[1].branch[0][0].draftId, first);
  assert.equal(draft.rungs[0].nodes[1].branch.length, 3);
});

test('resizing wraps following nodes into the top leg and releases a contiguous suffix', () => {
  const routine = fixture();
  const branch = {branch: [[op('XIC', 'A')], [op('XIO', 'B')]]};
  const parallel = {branch: [[op('XIC', 'C')], [op('XIC', 'D')]]};
  routine.rungs[0].nodes = [branch, parallel, op('ADD', '1', '2', 'Count'), op('OTE', 'Run')];
  routine.rungs[0].text = ' [XIC(A),XIO(B)] [XIC(C),XIC(D)] ADD(1, 2, Count) OTE(Run);';
  const draft = draftModel.create(routine);
  const [first, adjacent, add, last] = draft.rungs[0].nodes;
  const wrap = {legs: [], index: 3};
  assert(draft.canResize(0, first.draftId, wrap));
  assert(draft.resize(0, first.draftId, wrap));
  assert.equal(draft.rungs[0].text, '[XIC(A)[XIC(C),XIC(D)]ADD(1,2,Count),XIO(B)]OTE(Run);');
  assert.deepEqual(draft.rungs[0].nodes[0].branch[0].slice(1).map(item => item.draftId), [adjacent.draftId, add.draftId]);
  assert.equal(draft.rungs[0].nodes[1].draftId, last.draftId);
  assert.equal(draft.rungs[1].text, routine.rungs[1].text);
  const extended = draft.rungs[0].text;
  const unwrap = {legs: [[0, 0]], index: 1};
  assert(draft.resize(0, first.draftId, unwrap));
  assert.equal(draft.rungs[0].text, routine.rungs[0].text);
  assert.equal(draft.changed, false);
  assert(draft.undo());
  assert.equal(draft.rungs[0].text, extended);
  assert(draft.redo());
  assert.equal(draft.rungs[0].text, routine.rungs[0].text);
});

test('resizing stays in the selected branch parent and rejects unrelated and boundary wires', () => {
  const routine = fixture();
  const inner = {branch: [[op('XIC', 'A')], [op('XIO', 'B')]]};
  routine.rungs[0].nodes = [op('XIC', 'Start'),
    {branch: [[inner, op('XIC', 'C')], [op('XIC', 'D')]]}, op('OTE', 'Run')];
  const draft = draftModel.create(routine), nested = draft.rungs[0].nodes[1].branch[0][0].draftId;
  const original = draft.rungs[0].text;
  for (const gap of [{legs: [], index: 3}, {legs: [[1, 1]], index: 1},
    {legs: [[1, 0], [0, 1]], index: 0}, {legs: [[1, 0], [0, 0]], index: 1},
    {legs: [[1, 0]], index: 1}, {legs: [[1, 0]], index: 3}]) {
    assert.equal(draft.canResize(0, nested, gap), false);
    assert.equal(draft.resize(0, nested, gap), null);
  }
  assert.equal(draft.rungs[0].text, original);
  assert.equal(draft.canUndo, false);

  const diagram = graph.compile(draft.rungs[0], routine.key, true);
  const wire = diagram.edges.find(edge => edge.gap.legs.length === 1
    && edge.gap.legs[0][0] === 1 && edge.gap.legs[0][1] === 0 && edge.gap.index === 2);
  assert(draft.resize(0, nested, wire.gap));
  assert.equal(draft.rungs[0].text, 'XIC(Start)[[XIC(A)XIC(C),XIO(B)],XIC(D)]OTE(Run);');
  assert(draft.undo());
  assert.equal(draft.rungs[0].text, original);
});

test('opening a draft is one reversible edit and preserves untouched rung identities', () => {
  const routine = fixture(), draft = draftModel.create(routine);
  const firstId = draft.rungs[0].nodes[0].draftId;
  const unchanged = draft.rungs[1];
  const opened = [
    {...routine.rungs[0], text: 'XIO(Other)OTE(Run);', comment: 'Saved comment',
      nodes: [op('XIO', 'Other'), op('OTE', 'Run')]},
    routine.rungs[1]
  ];
  assert.equal(draft.restore(opened), true);
  assert.equal(draft.rungs[0].comment, 'Saved comment');
  assert.equal(draft.rungs[0].text, opened[0].text);
  assert.notEqual(draft.rungs[0].nodes[0].draftId, firstId);
  assert.equal(draft.rungs[1], unchanged);
  assert.equal(draft.restore(opened), false);
  assert.deepEqual(opened[0].nodes[0], op('XIO', 'Other'));
  assert.throws(() => draft.restore([opened[0], {...opened[1], number: '99'}]), /does not match/);
  assert.equal(draft.undo(), true);
  assert.equal(draft.rungs[0].nodes[0].draftId, firstId);
  assert.equal(draft.changed, false);
  assert.equal(draft.canUndo, false);
  assert.equal(draft.redo(), true);
  assert.equal(draft.rungs[0].text, opened[0].text);
});

test('comment-only draft reopens keep instruction identity and count as a change', () => {
  const routine = fixture(), draft = draftModel.create(routine);
  const nodes = draft.rungs[0].nodes;
  assert(draft.restore([{...routine.rungs[0], comment: 'Different comment'}, routine.rungs[1]]));
  assert.equal(draft.changed, true);
  assert.equal(draft.rungs[0].nodes, nodes);
  assert(draft.undo());
  assert.equal(draft.changed, false);
});

test('rung insert, comment and deletion keep surviving nodes stable through history and reopen', () => {
  const routine = fixture();
  routine.rungs[0].number = '8';
  routine.rungs[1].number = '19';
  const draft = draftModel.create(routine);
  const originalGraph = graph.compile(draft.rungs[1], routine.key, true);
  assert(draft.insertRung(1));
  assert.deepEqual(draft.rungs.map(row => row.number), ['0', '1', '2']);
  const blank = graph.compile(draft.rungs[1], routine.key, true);
  assert.deepEqual(blank.order, []);
  assert(draft.insert(1, blank.edges[0].gap, 'MOV'));
  assert(draft.setComment(1, 'First line\nSecond line'));
  assert(draft.removeRung(0));
  assert.deepEqual(draft.rungs.map(row => row.base_index), [null, 1]);
  assert.deepEqual(graph.compile(draft.rungs[1], routine.key, true).order, originalGraph.order);
  const opened = draft.rungs.map(({number, base_index, text, comment, nodes}) => ({number, base_index, text, comment, nodes}));
  assert.equal(draft.restore(opened), false);
  assert(draft.undo());
  assert.equal(draft.rungs[1].comment, 'First line\nSecond line');
  assert(draft.undo());
  assert.equal(draft.rungs[1].comment, '');
  assert(draft.undo());
  assert.equal(draft.rungs[1].text, ';');
  assert(draft.undo());
  assert.equal(draft.changed, false);
  assert.deepEqual(draft.rungs.map(row => row.number), ['8', '19']);
  assert(draft.restore(opened));
  assert.equal(draft.rungs[0].text, 'MOV(?,?);');
  assert.equal(draft.rungs[0].comment, 'First line\nSecond line');
  assert(draft.removeRung(0));
  assert.equal(draft.removeRung(0), false);
  assert(draft.restore(routine.rungs));
  assert.equal(draft.changed, false);
});

test('draft moves retain authored pseudo-operands without changing monitor nodes', () => {
  const routine = fixture();
  const timer = {...op('TON', 'Timer', '?', '?'), source_args: ['Timer', '250', '0']};
  routine.rungs[0].nodes.push(timer);
  routine.rungs[0].text = 'XIC(Start)OTE(Run)TON(Timer,250,0);';
  const draft = draftModel.create(routine);
  const timerId = draft.rungs[0].nodes[2].draftId;
  assert(draft.move(0, timerId, 1, {legs: [], index: 0}));
  assert.equal(draft.rungs[1].text, 'TON(Timer,250,0)MOV(0,Count);');
  assert.deepEqual(timer.args, ['Timer', '?', '?']);
});
