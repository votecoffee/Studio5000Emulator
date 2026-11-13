const {test}=require('node:test'),assert=require('node:assert/strict');
const {readFileSync}=require('node:fs'),{join}=require('node:path');
const {create}=require('../../web/logic-values.js');

test('typed radix integer arithmetic and relation sources retain exact numeric signs',()=>{
  const reader=create([]);
  for(const [ref,type,value] of [['16#FFFFFFFFL','LINT','4294967295'],['16#FFFFFFFFFFFFFFFFL','LINT','-1'],
    ['16#0020000000000001L','LINT','9007199254740993'],['16#FFFFFFFFU','UDINT','4294967295'],
    ['8#1777777777777777777777UL','ULINT','18446744073709551615'],['2#1'+'0'.repeat(63)+'L','LINT','-9223372036854775808']]) {
    assert.deepEqual(reader.read(ref,{integerRadix:true}),{name:ref,type:type+' radix literal',value});
  }
});

test('typed radix integer views keep legacy and unrelated view interpretation separate',()=>{
  const tags=[{name:'Count1L',type:'LINT',value:'9007199254740993'}],before=structuredClone(tags),reader=create(tags);
  assert.equal(reader.read('16#FFUL'),null);assert.equal(reader.read('16#FFUL',{dintRadix:true}),null);
  assert.equal(reader.read('16#FFFFFFFF',{integerRadix:true}).value,'4294967295');
  assert.equal(reader.read('16#FFFFFFFF',{movRadix:true}).value,'-1');
  assert.equal(reader.read('1.0L',{integerRadix:true}).type,'LREAL literal');
  assert.equal(reader.read('Count1L',{integerRadix:true}),tags[0]);assert.deepEqual(tags,before);
});

test('typed radix integer invalid widths signs grouping and suffixes remain unavailable',()=>{
  const reader=create([]);
  for(const ref of ['16#100000000U','16#10000000000000000L','2#2UL','8#8L','16#FF U','16#FFLU',
    '-16#FFL','16#FF_L','LINT#16#FF','16#FFL+1L'])assert.equal(reader.read(ref,{integerRadix:true}),null,ref);
});

test('typed radix integer public operands retain their original exact values',()=>{
  const xml=readFileSync(join(__dirname,'../../samples/WideExpressionLab.L5X'),'utf8');
  const routine=xml.match(/<Routine Name="IntegerOperandConstants"[\s\S]*?<\/Routine>/)[0],reader=create([]);
  const expected={'16#0020000000000001L':'9007199254740993','16#FFFFFFFFFFFFFFFFUL':'18446744073709551615',
    '8#1777777777777777777777UL':'18446744073709551615','16#FFFFFFFEU':'4294967294','2#0L':'0','16#FFFFFFFFU':'4294967295',
    '16#0020000000000000L':'9007199254740992','16#8000000000000000L':'-9223372036854775808','16#7FFFFFFFFFFFFFFFL':'9223372036854775807',
    ['2#'+'1'.repeat(64)+'UL']:'18446744073709551615','16#FFFFFFFFFFFFFFFEL':'-2','2#10L':'2','8#1777777777777777777776L':'-2'};
  const seen=new Set();
  for(const match of routine.matchAll(/(?:ADD|SUB|MUL|DIV|MOD|NEG|ABS|EQU|NEQ|LES|LEQ|GRT|GEQ|LIM)\(([^)]+)\)/g)) {
    for(const ref of match[1].split(','))if(ref in expected){assert.equal(reader.read(ref,{integerRadix:true}).value,expected[ref]);seen.add(ref);}
  }
  assert.deepEqual([...seen].sort(),Object.keys(expected).sort());
});
