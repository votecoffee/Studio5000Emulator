const {test}=require('node:test'),assert=require('node:assert/strict');
const {readFileSync}=require('node:fs'),{join}=require('node:path');
const {create}=require('../../web/logic-values.js');

test('typed radix BCD sources retain declared numeric values and signs',()=>{
  const reader=create([]);
  for(const [ref,type,value] of [['16#9007199254740993UL','ULINT','10378291982571407763'],
    ['16#0020000000000001UL','ULINT','9007199254740993'],['8#1777777777777777777777L','LINT','-1'],
    ['16#FFFF_FFFFu','UDINT','4294967295'],['2#1100011U','UDINT','99']]) {
    assert.deepEqual(reader.read(ref,{bcdRadix:true}),{name:ref,type:type+' radix literal',value});
  }
});

test('typed radix BCD views retain unrelated and legacy context boundaries',()=>{
  const tags=[{name:'Packed',type:'ULINT',value:'10378291982571407763'}],before=structuredClone(tags),reader=create(tags);
  assert.equal(reader.read('16#FFUL'),null);assert.equal(reader.read('16#FFUL',{dintRadix:true}),null);
  assert.equal(reader.read('16#FFFFFFFF',{bcdRadix:true}).value,'4294967295');
  assert.equal(reader.read('16#FFFFFFFF',{movRadix:true}).value,'-1');
  assert.equal(reader.read('Packed',{bcdRadix:true}),tags[0]);assert.deepEqual(tags,before);
});

test('typed radix BCD invalid widths digits signs and suffixes remain unavailable',()=>{
  const reader=create([]);
  for(const ref of ['16#100000000U','16#10000000000000000L','2#2UL','8#8L','16#FF U','16#FF_L',
    '16#FFLU','-16#FFL','LINT#16#FF','16#FFL+1L'])assert.equal(reader.read(ref,{bcdRadix:true}),null,ref);
});

test('typed radix BCD public source operands retain exact declared values',()=>{
  const xml=readFileSync(join(__dirname,'../../samples/ConversionLab.L5X'),'utf8');
  const routine=xml.match(/<Routine Name="TypedImmediateConversions"[\s\S]*?<\/Routine>/)[0],reader=create([]);
  const expected={'16#0020000000000001UL':'9007199254740993','8#1777777777777777777777L':'-1',
    '16#9007199254740993UL':'10378291982571407763','16#FFFF_FFFFu':'4294967295','2#1100011U':'99'},seen=new Set();
  for(const match of routine.matchAll(/(?:FRD|TOD)\(([^,]+),[^)]+\)/g))if(match[1] in expected){
    assert.equal(reader.read(match[1],{bcdRadix:true}).value,expected[match[1]]);seen.add(match[1]);
  }
  assert.deepEqual([...seen].sort(),Object.keys(expected).sort());
});
