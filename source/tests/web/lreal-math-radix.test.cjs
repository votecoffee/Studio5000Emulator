const {test}=require('node:test'),assert=require('node:assert/strict');
const {create}=require('../../web/logic-values.js'),{lrealMathRadix}=require('../../web/logic-view.js');
const math=['ADD','SUB','MUL','DIV','MOD','NEG','ABS','XPY','SQR','LN','LOG','DEG','RAD','SIN','COS','TAN','ASN','ACS','ATN'];

test('nineteen binary64 math cards decode declared radix source signs',()=>{
  const reader=create([{name:'Result',type:'LREAL',value:null}]),word='16#FFFFFFFF';
  for(const opcode of math){
    const operands=['ADD','SUB','MUL','DIV','MOD','XPY'].includes(opcode)?[word,'1L','Result']:[word,'Result'];
    const node={opcode,operands};assert(lrealMathRadix(node,word,ref=>reader.read(ref)));
    assert.equal(reader.read(word,{integerRadix:true,dintRadix:true}).value,'-1');
    assert(!lrealMathRadix(node,'Result',ref=>reader.read(ref)));
  }
});

test('source LREAL tags and floating literals select advanced radix cards',()=>{
  const reader=create([{name:'DoubleInput',type:'LREAL',value:3},{name:'Count',type:'DINT',value:0}]);
  for(const operands of [['16#4U','0.5L','Count'],['DoubleInput','16#1L','Count'],['16#1L','DoubleInput','Count']]){
    const node={opcode:'XPY',operands},word=operands.find(x=>x.includes('#'));
    assert(lrealMathRadix(node,word,ref=>reader.read(ref)));
    const row=reader.read(word,{integerRadix:true,dintRadix:true});assert(row);assert(row.type.endsWith('radix literal'));
  }
});

test('REAL-only, integer-only, unrelated calls and ordinary references keep their context',()=>{
  const reader=create([{name:'Single',type:'REAL',value:0},{name:'Count',type:'DINT',value:0},{name:'Double',type:'LREAL',value:0}]);
  for(const result of ['Single','Count'])assert(!lrealMathRadix({opcode:'SQR',operands:['16#1L',result]},'16#1L',ref=>reader.read(ref)));
  for(const opcode of ['MOV','EQU','FRD','TOD','AND','JSR'])assert(!lrealMathRadix({opcode,operands:['16#1L','Double']},'16#1L',ref=>reader.read(ref)));
  assert(!lrealMathRadix({opcode:'ADD',operands:['Double','1','Double']},'Double',ref=>reader.read(ref)));
  assert.equal(reader.read('16#FFFFFFFF').value,'4294967295');
});
