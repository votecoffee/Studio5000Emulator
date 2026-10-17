"""Source-authored v35 fixture for typed routine transfers and comparisons."""
from pathlib import Path
from xml.etree import ElementTree as E


def create(destination):
    root=E.Element('RSLogix5000Content',SchemaRevision='1.0',SoftwareRevision='35.01',TargetName='CallLab',TargetType='Controller',ContainsContext='false')
    c=E.SubElement(root,'Controller',Name='CallLab',ProcessorType='1756-L85E',MajorRev='35',MinorRev='11')
    types=E.SubElement(c,'DataTypes')
    udt=E.SubElement(types,'DataType',Name='LabPair',Family='NoFamily',Class='User');members=E.SubElement(udt,'Members')
    for name in ('A','B'):E.SubElement(members,'Member',Name=name,DataType='DINT',Dimension='0',Radix='Decimal',Hidden='false',ExternalAccess='Read/Write')
    E.SubElement(c,'Modules');E.SubElement(c,'AddOnInstructionDefinitions');tags=E.SubElement(c,'Tags')
    def tag(name,dtype,value):
        t=E.SubElement(tags,'Tag',Name=name,TagType='Base',DataType=dtype,Constant='false',ExternalAccess='Read/Write');data=E.SubElement(t,'Data',Format='Decorated')
        if isinstance(value,list):
            t.set('Dimensions',str(len(value)));a=E.SubElement(data,'Array',DataType=dtype,Dimensions=str(len(value)),Radix='Decimal')
            for i,v in enumerate(value):E.SubElement(a,'Element',Index=f'[{i}]',Value=str(v))
        elif isinstance(value,dict):
            s=E.SubElement(data,'Structure',DataType=dtype)
            for k,v in value.items():E.SubElement(s,'DataValueMember',Name=k,DataType='DINT',Radix='Decimal',Value=str(v))
        else:E.SubElement(data,'DataValue',DataType=dtype,Radix='Float' if dtype=='REAL' else 'Decimal',Value=str(value))
    for name,value in [('Enabled',1),('EarlyReturn',0),('CompareOK',0),('MaskOK',0)]:tag(name,'BOOL',value)
    for name,value in [('InputValue',7),('FormalInput',0),('WorkValue',0),('NestedInput',0),('NestedOutput',0),('Result',0),('CallCount',0),('PackedWord',0x1234)]:tag(name,'DINT',value)
    tag('RealInput','REAL',2.5);tag('FormalReal','REAL',0);tag('RealResult','REAL',0);tag('RealOutput','REAL',0)
    for name,value in [('ArrayInput',[10,20,30]),('ArrayFormal',[0,0,0]),('ArrayOutput',[0,0,0])]:tag(name,'DINT',value)
    for name,value in [('PairInput',{'A':4,'B':9}),('PairFormal',{'A':0,'B':0}),('PairOutput',{'A':0,'B':0})]:tag(name,'LabPair',value)
    p=E.SubElement(E.SubElement(c,'Programs'),'Program',Name='MainProgram',MainRoutineName='MainRoutine',Disabled='false',Class='Standard');E.SubElement(p,'Tags');rr=E.SubElement(p,'Routines')
    def routine(name,texts):
        r=E.SubElement(rr,'Routine',Name=name,Type='RLL');content=E.SubElement(r,'RLLContent')
        for i,text in enumerate(texts):
            rung=E.SubElement(content,'Rung',Number=str(i),Type='N');E.SubElement(rung,'Text').text=text
    routine('MainRoutine',[
        'XIC(Enabled)JSR(Calculate,2,InputValue,RealInput,Result,RealOutput);',
        'JSR(TransformData,2,ArrayInput,PairInput,ArrayOutput,PairOutput);',
        'CMP((Result>=24)&&(RealOutput=7.5))OTE(CompareOK);',
        'MEQ(PackedWord,16#00F0,16#0030)OTE(MaskOK);'])
    routine('Calculate',[
        'SBR(FormalInput,FormalReal);',
        'ADD(CallCount,1,CallCount)ADD(FormalInput,5,WorkValue);',
        'XIC(EarlyReturn)RET(WorkValue,FormalReal);',
        'JSR(DoubleValue,1,WorkValue,WorkValue);',
        'MUL(FormalReal,3.0,RealResult);',
        'RET(WorkValue,RealResult);'])
    routine('DoubleValue',['SBR(NestedInput);','MUL(NestedInput,2,NestedOutput);','RET(NestedOutput);'])
    routine('TransformData',[
        'SBR(ArrayFormal,PairFormal);',
        'ADD(ArrayFormal[1],5,ArrayFormal[1])ADD(PairFormal.A,PairFormal.B,PairFormal.A);',
        'RET(ArrayFormal,PairFormal);'])
    task=E.SubElement(E.SubElement(c,'Tasks'),'Task',Name='MainTask',Type='CONTINUOUS',Priority='10',Watchdog='500',Class='Standard',InhibitTask='false')
    E.SubElement(E.SubElement(task,'ScheduledPrograms'),'ScheduledProgram',Name='MainProgram')
    E.indent(root,space='  ');E.ElementTree(root).write(destination,encoding='utf-8',xml_declaration=True)


if __name__=='__main__':create(Path(__file__).parent/'samples/CallLab.L5X')
