const {test}=require('node:test'),assert=require('node:assert/strict');
const {create}=require('../../web/logic-values.js'),{realMathRadix}=require('../../web/logic-view.js');

test('nineteen REAL result cards decode signed radix source words',()=>{
  const reader=create([{name:'Result',type:'REAL',value:null}]),word='16#FFFFFFFF';
  for(const opcode of ['ADD','SUB','MUL','DIV','MOD','NEG','ABS','XPY','SQR','LN','LOG','DEG','RAD','SIN','COS','TAN','ASN','ACS','ATN']){
    const operands=['ADD','SUB','MUL','DIV','MOD','XPY'].includes(opcode)?[word,'1L','Result']:[word,'Result'];
    assert(realMathRadix({opcode,operands},word,ref=>reader.read(ref)));
    assert.equal(reader.read(word,{integerRadix:true,dintRadix:true}).value,'-1');
    assert(!realMathRadix({opcode,operands},'Result',ref=>reader.read(ref)));
  }
});

test('wide integer results require REAL source tags or unsuffixed floating constants',()=>{
  const reader=create([{name:'Input',type:'REAL',value:3},{name:'Result',type:'ULINT',value:'0'}]);
  for(const input of ['Input','0.5','.5','5e-1','+0.5']){
    assert(realMathRadix({opcode:'XPY',operands:['16#4U',input,'Result']},'16#4U',ref=>reader.read(ref)));
  }
  for(const input of ['1','1L','0.5L'])assert(!realMathRadix({opcode:'XPY',operands:['16#4U',input,'Result']},'16#4U',ref=>reader.read(ref)));
});

test('unrelated consumers and narrow integer destinations keep separate display contexts',()=>{
  const reader=create([{name:'Input',type:'REAL',value:3},{name:'Count',type:'DINT',value:0}]);
  assert(!realMathRadix({opcode:'XPY',operands:['16#4U','Input','Count']},'16#4U',ref=>reader.read(ref)));
  for(const opcode of ['MOV','EQU','FRD','AND','JSR'])assert(!realMathRadix({opcode,operands:['16#4U','Input']},'16#4U',ref=>reader.read(ref)));
  assert.equal(reader.read('16#FFFFFFFF').value,'4294967295');
});
