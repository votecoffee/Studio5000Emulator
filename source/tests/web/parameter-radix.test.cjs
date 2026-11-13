const {test}=require('node:test'),assert=require('node:assert/strict');
const {readFileSync}=require('node:fs'),{join}=require('node:path');
const {create}=require('../../web/logic-values.js'),{parameterRadix}=require('../../web/logic-view.js');
const graph=require('../../web/ladder-graph.js');

test('typed radix call values retain exact declared types and signed widths',()=>{
  const reader=create([]);
  for(const [ref,type,value] of [['16#0020000000000001L','LINT','9007199254740993'],
    ['8#37777777777U','UDINT','4294967295'],['2#'+'1'.repeat(64)+'UL','ULINT','18446744073709551615'],
    ['16#FFFFFFFFL','LINT','4294967295'],['16#FFFFFFFFFFFFFFFFL','LINT','-1']])
    assert.deepEqual(reader.read(ref,{callRadix:true}),{name:ref,type:type+' radix literal',value});
});

test('typed radix call monitoring selects JSR inputs and RET values only',()=>{
  const node={opcode:'JSR',operands:['Worker','1','16#FFL','Result']};
  assert(parameterRadix(node,'16#FFL'));assert(!parameterRadix(node,'Worker'));assert(!parameterRadix(node,'1'));
  assert(!parameterRadix(node,'Result'));assert(!parameterRadix(node,'Missing'));
  assert(parameterRadix({opcode:'RET',operands:['16#FFL']},'16#FFL'));
  assert(!parameterRadix({opcode:'RET',operands:['Value']},'Value'));
  assert(!parameterRadix({opcode:'SBR',operands:['16#FFL']},'16#FFL'));
  assert(!parameterRadix({opcode:'FOR',operands:['Worker','Index','16#FFL']},'16#FFL'));
});

test('typed radix AOI monitoring selects required Input fields only',()=>{
  const definitions={Lab:{name:'Lab',parameters:[
    {name:'Hidden',usage:'Input',type:'LINT',required:true,visible:false},
    {name:'Output',usage:'Output',type:'LINT',required:true,visible:true},
    {name:'Reference',usage:'InOut',type:'LINT',required:true,visible:true},
    {name:'Optional',usage:'Input',type:'LINT',required:false,visible:true}]}};
  const node={opcode:'LAB',operands:['Instance','16#FFL','Dest','Binding']};
  assert(parameterRadix(node,'16#FFL',definitions));
  for(const ref of ['Instance','Dest','Binding','Instance.Optional','Missing'])assert(!parameterRadix(node,ref,definitions),ref);
  assert(!parameterRadix(node,'16#FFL',{}));assert(!parameterRadix(undefined,'16#FFL'));
});

test('typed radix call option preserves invalid and unrelated literal boundaries',()=>{
  const reader=create([]);assert.equal(reader.read('16#FFUL'),null);
  assert.equal(reader.read('16#FFUL',{dintRadix:true}),null);
  for(const ref of ['16#100000000U','16#10000000000000000L','2#2UL','8#8L','16#FF U','16#FF_L','16#FFLU','-16#FFL'])
    assert.equal(reader.read(ref,{callRadix:true}),null,ref);
  assert.equal(reader.read('16#FFFFFFFF',{callRadix:true}).value,'4294967295');
});

test('typed radix public AOI and call operands preserve the original exact results',()=>{
  const reader=create([]);
  for(const name of ['AOIConstantsLab','CallLab']){
    const xml=readFileSync(join(__dirname,'../../samples/'+name+'.L5X'),'utf8');
    for(const [ref,value] of [['16#0020000000000001L','9007199254740993'],['8#37777777777U','4294967295'],
      ['2#'+'1'.repeat(64)+'UL','18446744073709551615']]){
      assert(xml.includes(ref));assert.equal(reader.read(ref,{callRadix:true}).value,value);
    }
  }
});

test('typed radix call trace values override constants without changing authored nodes',()=>{
  const text='JSR(Worker,1,16#0020000000000001L,Result);';
  const rung={number:'0',text,nodes:[{name:'JSR',args:['Worker','1','16#0020000000000001L','Result']}]};
  const model=graph.compile(rung,'Main/Main'),before=structuredClone(model),node=model.nodes.find(n=>n.opcode==='JSR');
  const samples=[null,null,{address:null,type:'LINT',value:'9007199254740993'},{address:'Result',type:'LINT',value:'9007199254740993'}];
  const visit={operand_source:model.source,rung_index:0,events:[{instruction:'JSR',args:rung.nodes[0].args,in:true,out:true,operand_samples:samples}]};
  assert.deepEqual(graph.power(model,visit,0).nodes[node.id].operandSamples,samples);assert.deepEqual(model,before);
});
