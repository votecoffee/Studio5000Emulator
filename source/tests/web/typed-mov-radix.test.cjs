const {test} = require('node:test'), assert = require('node:assert/strict');
const {readFileSync} = require('node:fs'), {join} = require('node:path');
const {create} = require('../../web/logic-values.js');

test('typed radix MOV source values retain exact declared widths and signs', () => {
  const reader = create([]);
  for (const [ref, type, value] of [
    ['16#FFFF_FFFFL', 'LINT', '4294967295'], ['16#FFFF_FFFFu', 'UDINT', '4294967295'],
    ['16#FFFF_FFFF_FFFF_FFFFl', 'LINT', '-1'], ['16#FFFF_FFFF_FFFF_FFFFuL', 'ULINT', '18446744073709551615'],
    ['2#1' + '0'.repeat(63) + 'L', 'LINT', '-9223372036854775808'],
    ['8#1777777777777777777777UL', 'ULINT', '18446744073709551615'],
    [' 16#0000_ffffUl ', 'ULINT', '65535'], ['2#1010_0101l', 'LINT', '165']
  ]) assert.deepEqual(reader.read(ref, {movRadix:true}), {name:ref.trim(), type:type + ' radix literal', value});
});

test('typed radix MOV masks reject invalid digits widths grouping and suffixes', () => {
  const reader = create([]);
  for (const ref of ['16#100000000U','16#10000000000000000L','2#1'+'0'.repeat(64)+'UL',
    '8#2000000000000000000000UL','2#2L','8#8UL','16#GUL','16#___L','16# FFU','16#FF U',
    '16#FF_L','16#FFLU','16#FFULL','16#FFL2','+16#FFL','-16#FFL','16#FF.0L',
    '10#42L','LINT#16#FF','(16#FFL)','16#FFL+1L']) {
    assert.equal(reader.read(ref,{movRadix:true}),null,ref);
  }
});

test('typed radix MOV interpretation stays local to the new viewer option', () => {
  const rows = [{name:'Value1L',type:'LINT',value:'9007199254740993'}], before=structuredClone(rows), reader=create(rows);
  for (const ref of ['16#FFL','16#FFU','16#FFUL']) {
    assert.equal(reader.read(ref),null);
    assert.equal(reader.read(ref,{dintRadix:true}),null);
  }
  assert.equal(reader.read('16#FFFFFFFF',{movRadix:true}).value,'-1');
  assert.equal(reader.read('16#FFFFFFFF').value,'4294967295');
  assert.equal(reader.read('4294967295U',{movRadix:true}).type,'UDINT literal');
  assert.equal(reader.read('Value1L',{movRadix:true}),rows[0]);
  assert.deepEqual(rows,before);
});

test('typed radix MOV public examples retain original spellings and exact monitor values', () => {
  const source = readFileSync(join(__dirname,'../../samples/WideExpressionLab.L5X'),'utf8'), reader=create([]);
  const expected = {RadixLongShort:'4294967295',RadixLongNegative:'-1',RadixDwordMax:'4294967295',
    RadixUlongMax:'18446744073709551615',RadixBinaryMin:'-9223372036854775808',RadixOctalMax:'18446744073709551615'};
  const seen=[];
  for (const match of source.matchAll(/XIC\(RadixEnabled\)MOV\(([^,]+),(Radix\w+)\);/g)) {
    if (!(match[2] in expected)) continue;
    const result=reader.read(match[1],{movRadix:true});
    assert.equal(result.name,match[1]);assert.equal(result.value,expected[match[2]]);seen.push(match[2]);
  }
  assert.deepEqual(seen.sort(),Object.keys(expected).sort());
});
