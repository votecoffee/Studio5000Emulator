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


test('signed DINT scalar context decodes full words in all three radices',()=>{
  const reader=create([]),options={integerRadix:true,dintRadix:true};
  for(const [ref,value] of [['16#FFFF_FFFF','-1'],['8#37777777777','-1'],['2#'+'1'.repeat(32),'-1'],
    ['16#80000000','-2147483648'],['16#0000FFFF','65535']]) {
    assert.deepEqual(reader.read(ref,options),{name:ref,type:'DINT radix literal',value});
  }
  for(const ref of ['16#100000000','2#2','8#8'])assert.equal(reader.read(ref,options),null,ref);
});

test('signed DINT scalar context keeps mask BCD default and typed source meanings',()=>{
  const tags=[{name:'Source',type:'DINT',value:7}],before=structuredClone(tags),reader=create(tags);
  assert.equal(reader.read('16#FFFFFFFF',{integerRadix:true,dintRadix:true}).value,'-1');
  for(const options of [{},{bitwiseRadix:true},{bcdRadix:true}])assert.equal(reader.read('16#FFFFFFFF',options).value,'4294967295');
  assert.equal(reader.read('16#FFFFFFFFL',{integerRadix:true,dintRadix:true}).value,'4294967295');
  assert.equal(reader.read('Source',{integerRadix:true,dintRadix:true}),tags[0]);assert.deepEqual(tags,before);
});

test('signed DINT public scalar source words retain their authored signs',()=>{
  const xml=readFileSync(join(__dirname,'../../samples/WideExpressionLab.L5X'),'utf8');
  const routine=xml.match(/<Routine Name="DintPatternConstants"[\s\S]*?<\/Routine>/)[0],reader=create([]),values=[];
  for(const match of routine.matchAll(/(?:ADD|SUB|MUL|DIV|MOD|NEG|ABS|EQU|NEQ|LES|LEQ|GRT|GEQ|LIM)\(([^)]+)\)/g)) {
    for(const ref of match[1].split(','))if(/^(?:2|8|16)#/.test(ref))values.push(reader.read(ref,{integerRadix:true,dintRadix:true}));
  }
  assert(values.length>=12);assert(values.every(row=>row!==null));
  assert(values.some(row=>row.type==='DINT radix literal'&&row.value==='-2147483648'));
  assert(values.some(row=>row.type==='DINT radix literal'&&row.value==='-1'));
});
