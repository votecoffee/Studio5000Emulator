const {test} = require('node:test'), assert = require('node:assert/strict');
const {create} = require('../../web/logic-values.js');
const row = (name, value, type = 'DINT') => ({name, value, type});

test('MOV DINT radix monitoring is scoped and retains entered references', () => {
  const tags=[row('Value',7)], before=structuredClone(tags), view=create(tags);
  for(const [ref,value] of [['16#FFFF','65535'],['16#ffff ffff','-1'],['16#8000_0000','-2147483648'],['8#37777777777','-1'],['2#1010','10']]) {
    assert.deepEqual(view.read(ref,{dintRadix:true}),{name:ref,type:'DINT radix literal',value});
  }
  assert.equal(view.read('16#FFFFFFFF').value,'4294967295');
  assert.equal(view.read('Value',{dintRadix:true}).value,7);
  assert.deepEqual(tags,before);
});

test('MOV radix snapshots reject invalid digits overwide words and excluded forms', () => {
  const view=create([]);
  for(const ref of ['2#2','8#8','16#G','16#100000000','8#40000000000','2#1'+'0'.repeat(32),'16#FFU','16#___']) {
    assert.equal(view.read(ref,{dintRadix:true}),null,ref);
  }
  assert.equal(view.read('4294967295U',{dintRadix:true}).type,'UDINT literal');
});

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
test('indirect indices and supported expressions use scoped integer snapshots', () => {
  const view = create([row('Index', 0), row('Program:Main.Index', 1), row('Data[0]', 11), row('Data[1]', 22), row('Data[2]', 33), row('RealIndex', 1, 'REAL')], {routine: 'Main/Logic'});
  assert.equal(view.read('Data[Index]').value, 22);assert.equal(view.read('Data[Index+1]').value, 33);
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
test('division and bitwise indices select snapshot rows with checked DINT arithmetic', () => {
  const tags = [row('Index', 7), row('Divisor', 2), row('Negative', -7), ...[10,11,22,33,44,55,66,77].map((v,i) => row('Data['+i+']',v))];
  const view = create(tags);
  for (const [expr,want] of [['Index/Divisor',33],['Index AND 3',33],['(Index XOR 3) OR 1',55],['(NOT Index) AND 7',10],['Negative/Divisor+5',22],['-2147483648/-2147483648',11]]) {
    assert.equal(view.read('Data['+expr+']').value,want,expr);
  }
});
test('simple wide indices remain exact and are excluded from arithmetic', () => {
  const view = create([row('Wide','18446744073709551615','ULINT'),row('Small','1','ULINT'),row('Data[1]',77),row('Unsafe',9007199254740992,'ULINT')]);
  assert.equal(view.read('Data[Small]').value,77);assert.equal(view.resolve('Data[Wide]'),'Data[18446744073709551615]');
  assert.equal(view.read('Data[Wide]'),null);assert.equal(view.read('Data[Small+0]'),null);assert.equal(view.resolve('Data[Unsafe]'),null);
});
test('unknowns zero divisors overflow and excluded syntax remain unavailable without effects', () => {
  const tags = [row('Index',2147483647),row('Zero',0),row('Unknown',null),row('Data[0]',44)], before = structuredClone(tags), view = create(tags);
  for (const expr of ['Index/Zero','(Index/Zero) AND 0','(Index+1)/2','-2147483648/-1','Unknown AND 0','Index MOD 2','SQRT(Index)','Index/2.0','Index**2','globalThis.value()']) {
    assert.equal(view.read('Data['+expr+']'),null,expr);
  }
  assert.deepEqual(tags,before);
});
test('nested and multidimensional references resolve each selected index', () => {
  const view = create([row('Index',3),row('Chosen','1','ULINT'),row('Indices[1]',6),row('Data[3]',33),row('Matrix[1,1]',42)]);
  assert.equal(view.read('Data[Indices[Chosen]/2]').value,33);assert.equal(view.read('Matrix[Index/2,Chosen]').value,42);
});
test('AOI index expressions use selected-instance locals and InOut bindings', () => {
  const view = create([row('Driver.Index',7),row('Driver.Divisor',2),row('Index',0),row('BufferB[3]',55)], {routine:'AOI:Queue/Logic',context:'Driver',bindings:{Buffer:'BufferB'}});
  assert.equal(view.read('Buffer[Index/Divisor]').value,55);assert.equal(view.resolve('Buffer[Index/Divisor]'),'BufferB[3]');
});
test('BCD and root index functions compose over checked DINT snapshots', () => {
  const view=create([row('Index',21),row('Data[21]',221),row('Data[33]',233),row('Data[4]',44),row('Data[1]',11)]);
  assert.equal(view.read('Data[TOD(Index)]').value,233);assert.equal(view.read('Data[FRD(TOD(Index))]').value,221);
  assert.equal(view.read('Data[SQR(15)]').value,44);assert.equal(view.read('Data[SQR(-16)]').value,44);
  assert.equal(view.read('Data[TOD(99999999) AND 7]').value,11);assert.equal(view.resolve('Data[FRD(-1)]'),'Data[166666665]');
});
test('root index rounding retains float32 inputs and modern-controller integer results', () => {
  const view=create([row('Data[1]',1),row('Data[2]',2),row('Data[3]',3),row('Data[4096]',4096),row('Data[46341]',46341)]);
  for(const [input,want] of [[2,1],[3,2],[8,3],[16777217,4096],[2147483647,46341],[-2147483648,46341]])assert.equal(view.read('Data[SQR('+input+')]').value,want);
});
test('function ranges unknowns wide operands and unsupported functions remain unavailable', () => {
  const tags=[row('Unknown',null),row('Wide','1','ULINT'),row('Real',1,'REAL'),row('Data[0]',10)],before=structuredClone(tags),view=create(tags);
  for(const expr of ['TOD(-1)','TOD(100000000)','TOD(2147483647+1)','FRD(Unknown) AND 0','SQR(Wide)','TOD(Real)','FRD(1.0)','SQRT(1)','ABS(1)','FRD(1,2)','FRD()'])assert.equal(view.read('Data['+expr+']'),null,expr);
  assert.equal(view.read('FRD(1)'),null);assert.deepEqual(tags,before);
});
test('function indices retain nested references scoped locals and AOI bindings', () => {
  const view=create([row('Driver.Index',1),row('Driver.Codes[1]',2),row('BufferB[2]',55)],{routine:'AOI:Queue/Logic',context:'Driver',bindings:{Buffer:'BufferB'}});
  assert.equal(view.read('Buffer[FRD(Codes[SQR(Index)])]').value,55);assert.equal(view.resolve('Buffer[FRD(TOD(2))]'),'BufferB[2]');
});
