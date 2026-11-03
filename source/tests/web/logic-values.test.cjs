const {test} = require('node:test'), assert = require('node:assert/strict');
const {create} = require('../../web/logic-values.js');
const row = (name, value, type = 'DINT') => ({name, value, type});

test('a program aggregate shadows a same-named controller scalar', () => {
  const view = create([row('State', 99), row('Program:Main.State.ACC', 7)], {routine: 'Main/Logic'});
  assert.equal(view.read('State').aggregate, true);assert.equal(view.read('State.ACC').value, 7);
  assert.equal(view.resolve('State'), 'Program:Main.State');
});
test('unknown local members never fall back to matching global members', () => {
  const view = create([row('State.PRE', 1000), row('Program:Main.State.ACC', null)], {routine: 'Main/Logic'});
  assert.equal(view.read('State.PRE'), null);assert.equal(view.read('State.ACC').value, null);
  assert.equal(view.read('State').aggregate, true);
});
test('explicit program references and controller module tags retain their scopes', () => {
  const view = create([row('Program:Other.Input', 17), row('Local:1:I.Data', 33)], {routine: 'Main/Logic'});
  assert.equal(view.read('program:other.input').value, 17);assert.equal(view.read('Local:1:I.Data').value, 33);
});
test('AOI InOut arrays and controls resolve to real aggregate storage', () => {
  const view = create([row('BufferB[2]', 44), row('StateB.POS', 2)], {routine: 'AOI:Queue/Logic', context: 'DriverB', bindings: {Buffer: 'BufferB', State: 'StateB'}});
  assert.equal(view.read('buffer').name, 'BufferB');assert.equal(view.read('Buffer').aggregate, true);
  assert.equal(view.read('STATE').aggregate, true);assert.equal(view.read('State.POS').value, 2);
});
test('AOI bindings to selected structure members do not get rebound twice', () => {
  const view = create([row('Program:Main.Device.Data[1]', 52), row('Driver.Index', 1)], {routine: 'AOI:Queue/Logic', context: 'Driver', bindings: {Data: 'Program:Main.Device.Data', Index: 'Driver.Index'}});
  assert.equal(view.read('Data[Index]').value, 52);assert.equal(view.resolve('Data[Index]'), 'Program:Main.Device.Data[1]');
  assert.equal(view.read('Data').aggregate, true);
});
test('AOI locals and nested instances stay inside the selected instance', () => {
  const tags = [row('DriverA.Child.Ready', true, 'BOOL'), row('DriverB.Child.Ready', false, 'BOOL'), row('Child.Ready', true, 'BOOL')];
  const view = create(tags, {routine: 'AOI:Parent/Logic', context: 'DriverB'});
  assert.equal(view.read('Child.Ready').value, false);assert.equal(view.resolve('Child'), 'DriverB.Child');
  assert.equal(create(tags, {routine: 'AOI:Parent/Logic'}).read('Child.Ready'), null);
});
test('indirect indices use scoped integer snapshots and leave expressions unevaluated', () => {
  const view = create([row('Index', 0), row('Program:Main.Index', 1), row('Data[0]', 11), row('Data[1]', 22), row('RealIndex', 1, 'REAL')], {routine: 'Main/Logic'});
  assert.equal(view.read('Data[Index]').value, 22);assert.equal(view.read('Data[Index+1]'), null);
  assert.equal(view.read('Data[RealIndex]'), null);assert.equal(view.read('Data[Missing]'), null);
});
test('exact wide values and integer bits survive binding and scope resolution', () => {
  const view = create([row('Wide', '18446744073709551615', 'ULINT'), row('Signed', '-9223372036854775808', 'LINT')]);
  assert.equal(view.read('Wide').value, '18446744073709551615');assert.equal(view.read('Wide.63').value, true);
  assert.equal(view.read('Signed.63').value, true);assert.equal(view.read('Signed.0').value, false);assert.equal(view.read('Wide.64'), null);
});
test('unknown data and invalid literals stay unknown without mutating the snapshot', () => {
  const tags = [row('Bits', null), row('Program:Main.Flags[0]', null, 'BOOL')], original = structuredClone(tags);
  const view = create(tags, {routine: 'Main/Logic'});
  assert.equal(view.read('Bits.0'), null);assert.equal(view.read('Flags[0]').value, null);
  assert.equal(view.read('16#GG'), null);assert.equal(view.read('Missing'), null);assert.deepEqual(tags, original);
});
test('literal values remain exact strings and do not require an AOI instance', () => {
  const view = create([], {routine: 'AOI:Queue/Logic'});
  assert.equal(view.read('TRUE').value, true);assert.equal(view.read('9007199254740993').value, '9007199254740993');
  assert.equal(view.read('16#FFFF_FFFF_FFFF_FFFF').value, '18446744073709551615');assert.equal(view.read('-1.5e3').value, '-1.5e3');
});
