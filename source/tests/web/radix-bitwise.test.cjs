const {test}=require('node:test'),assert=require('node:assert/strict');
const {readFileSync}=require('node:fs'),{join}=require('node:path');
const {create}=require('../../web/logic-values.js');

test('typed radix bitwise masks retain exact signed and unsigned source values',()=>{
  const reader=create([]);
  for(const [ref,type,value] of [['16#FFFFFFFFU','UDINT','4294967295'],['16#FFFFFFFFL','LINT','4294967295'],
    ['16#FFFFFFFFFFFFFFFFL','LINT','-1'],['8#1777777777777777777777UL','ULINT','18446744073709551615'],
    ['2#1'+'0'.repeat(63)+'UL','ULINT','9223372036854775808'],['16#8000000000000000L','LINT','-9223372036854775808']]) {
    assert.deepEqual(reader.read(ref,{bitwiseRadix:true}),{name:ref,type:type+' radix literal',value});
  }
});

test('typed radix bitwise views preserve default legacy and unsuffixed scope',()=>{
  const tags=[{name:'Mask',type:'ULINT',value:'18446744073709551615'}],before=structuredClone(tags),reader=create(tags);
  assert.equal(reader.read('Mask',{bitwiseRadix:true}),tags[0]);
  assert.equal(reader.read('16#FFFFFFFFU'),null);assert.equal(reader.read('16#FFFFFFFFU',{dintRadix:true}),null);
  assert.equal(reader.read('16#FFFFFFFF',{bitwiseRadix:true}).value,'4294967295');
  assert.equal(reader.read('16#FFFFFFFF',{movRadix:true}).value,'-1');
  assert.equal(reader.read('1L',{bitwiseRadix:true}).type,'LINT literal');
  assert.deepEqual(tags,before);
});

test('typed radix bitwise invalid widths digits suffixes and grouping remain unavailable',()=>{
  const reader=create([]);
  for(const ref of ['16#100000000U','16#10000000000000000L','2#2UL','8#8L',
    '16#FF U','16#FF_L','16#FFLU','-16#FFL','16#___L','LINT#16#FF']) assert.equal(reader.read(ref,{bitwiseRadix:true}),null,ref);
});

test('typed radix bitwise public masks use their authored declared source widths',()=>{
  const source=readFileSync(join(__dirname,'../../samples/BitLab.L5X'),'utf8'),reader=create([]);
  const expected={'16#FFFF_FFFFu':'4294967295','16#8000_0000u':'2147483648','8#37777777777U':'4294967295',
    '2#11111111111111111111111111111111U':'4294967295','16#FFFF_FFFFUL':'4294967295',
    '16#FFFF_FFFF_FFFF_FFFFL':'-1',
    ['2#1'+'0'.repeat(63)+'UL']:'9223372036854775808','16#8000000000000000L':'-9223372036854775808'};
  const seen=new Set();
  for(const match of source.matchAll(/XIC\(WideMaskEnabled\)(?:AND|OR|XOR|NOT|MEQ)\(([^)]+)\)/g)) {
    for(const ref of match[1].split(',')) if(ref in expected) {
      assert.equal(reader.read(ref,{bitwiseRadix:true}).value,expected[ref]);seen.add(ref);
    }
  }
  assert.deepEqual([...seen].sort(),Object.keys(expected).sort());
});
