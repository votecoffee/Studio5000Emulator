"""Source-authored v35 fixture for AOI instances, references and scan modes."""
from pathlib import Path
from xml.etree import ElementTree as E


def create(destination):
    root=E.Element('RSLogix5000Content',SchemaRevision='1.0',SoftwareRevision='35.01',TargetName='AOILab',TargetType='Controller',ContainsContext='false')
    c=E.SubElement(root,'Controller',Name='AOILab',ProcessorType='1756-L85E',MajorRev='35',MinorRev='11')
    E.SubElement(c,'DataTypes');E.SubElement(c,'Modules');definitions=E.SubElement(c,'AddOnInstructionDefinitions')
    def routine(parent,name,rungs):
        r=E.SubElement(parent,'Routine',Name=name,Type='RLL');content=E.SubElement(r,'RLLContent')
        for i,text in enumerate(rungs):
            rung=E.SubElement(content,'Rung',Number=str(i),Type='N');E.SubElement(rung,'Text').text=text
    def definition(name,params,locals,logic,prescan=None,false=None):
        d=E.SubElement(definitions,'AddOnInstructionDefinition',Name=name,Class='Standard',Revision='1.0',Vendor='LogixLab',
                       ExecutePrescan=str(prescan is not None).lower(),ExecutePostscan='false',
                       ExecuteEnableInFalse=str(false is not None).lower(),CreatedDate='2026-10-16T12:00:00.000Z',
                       CreatedBy='LogixLab',EditedDate='2026-10-16T12:00:00.000Z',EditedBy='LogixLab',SoftwareRevision='v35.01')
        pp=E.SubElement(d,'Parameters')
        for pname,dtype,usage,required,default in [('EnableIn','BOOL','Input',False,0),('EnableOut','BOOL','Output',False,0)]+params:
            p=E.SubElement(pp,'Parameter',Name=pname,TagType='Base',DataType=dtype,Usage=usage,
                           Required=str(required).lower(),Visible=str(required).lower(),Radix='Float' if dtype=='REAL' else 'Decimal')
            if usage=='InOut':p.set('Constant','false')
            else:p.set('ExternalAccess','Read Only' if pname in ('EnableIn','EnableOut') else 'Read/Write')
            if usage!='InOut' and pname not in ('EnableIn','EnableOut'):
                data=E.SubElement(p,'DefaultData',Format='Decorated')
                E.SubElement(data,'DataValue',DataType=dtype,Radix='Float' if dtype=='REAL' else 'Decimal',Value=str(default))
        ll=E.SubElement(d,'LocalTags')
        for lname,dtype,default in locals:
            local=E.SubElement(ll,'LocalTag',Name=lname,DataType=dtype,ExternalAccess='None')
            if dtype in ('DINT','REAL','BOOL'):
                local.set('Radix','Float' if dtype=='REAL' else 'Decimal')
                data=E.SubElement(local,'DefaultData',Format='Decorated')
                E.SubElement(data,'DataValue',DataType=dtype,Radix='Float' if dtype=='REAL' else 'Decimal',Value=str(default))
        rr=E.SubElement(d,'Routines');routine(rr,'Logic',logic)
        if prescan is not None:routine(rr,'Prescan',prescan)
        if false is not None:routine(rr,'EnableInFalse',false)
    definition('LabAccumulator',[
        ('Step','DINT','Input',True,1),('Total','DINT','Output',True,0),
        ('Shared','DINT','InOut',True,None),('Limit','DINT','Input',False,100)],
        [('Count','DINT',777)],
        ['ADD(Count,Step,Count)MOV(Count,Total)ADD(Shared,Step,Shared);','LES(Count,Limit)OTE(EnableOut);'],
        ['CLR(Count)CLR(Total);'],['MOV(-1,Total);'])
    definition('LabScale',[
        ('Raw','REAL','Input',True,0),('Gain','REAL','Input',True,1),('Result','REAL','Output',True,0)],
        [('Scaled','REAL',987)],['MUL(Raw,Gain,Scaled)MOV(Scaled,Result);'],['CLR(Scaled)CLR(Result);'])
    definition('LabWrapper',[('Raw','REAL','Input',True,0),('Result','REAL','Output',True,0)],
        [('Core','LabScale',None)],['LabScale(Core,Raw,2.0,Result);'])
    tags=E.SubElement(c,'Tags')
    def tag(name,dtype,value):
        t=E.SubElement(tags,'Tag',Name=name,TagType='Base',DataType=dtype,Constant='false',ExternalAccess='Read/Write')
        data=E.SubElement(t,'Data',Format='Decorated')
        E.SubElement(data,'DataValue',DataType=dtype,Radix='Float' if dtype=='REAL' else 'Decimal',Value=str(value))
    for name,value in [('EnableA',1),('EnableB',1),('AReady',0),('BReady',0)]:tag(name,'BOOL',value)
    for name,value in [('StepA',2),('StepB',3),('TotalA',99),('TotalB',88),('SharedA',10),('SharedB',20),('Truncated',0)]:tag(name,'DINT',value)
    tag('RawValue','REAL',12.75);tag('ScaledValue','REAL',0)
    def instance(name,dtype,members):
        t=E.SubElement(tags,'Tag',Name=name,TagType='Base',DataType=dtype,Constant='false',ExternalAccess='Read/Write')
        s=E.SubElement(E.SubElement(t,'Data',Format='Decorated'),'Structure',DataType=dtype)
        for mname,mt,mv in [('EnableIn','BOOL',0),('EnableOut','BOOL',0)]+members:
            E.SubElement(s,'DataValueMember',Name=mname,DataType=mt,Radix='Float' if mt=='REAL' else 'Decimal',Value=str(mv))
    instance('AccumulatorA','LabAccumulator',[('Step','DINT',1),('Total','DINT',0),('Limit','DINT',5)])
    instance('AccumulatorB','LabAccumulator',[('Step','DINT',1),('Total','DINT',0),('Limit','DINT',100)])
    instance('NestedScale','LabWrapper',[('Raw','REAL',0),('Result','REAL',0)])
    p=E.SubElement(E.SubElement(c,'Programs'),'Program',Name='MainProgram',MainRoutineName='MainRoutine',Disabled='false',Class='Standard')
    E.SubElement(p,'Tags');rr=E.SubElement(p,'Routines')
    routine(rr,'MainRoutine',[
        'XIC(EnableA)LabAccumulator(AccumulatorA,StepA,TotalA,SharedA)OTE(AReady);',
        'XIC(EnableB)LabAccumulator(AccumulatorB,StepB,TotalB,SharedB)OTE(BReady);',
        'LabWrapper(NestedScale,RawValue,ScaledValue);',
        'TRN(ScaledValue,Truncated);'])
    task=E.SubElement(E.SubElement(c,'Tasks'),'Task',Name='MainTask',Type='CONTINUOUS',Priority='10',Watchdog='500',Class='Standard',InhibitTask='false')
    E.SubElement(E.SubElement(task,'ScheduledPrograms'),'ScheduledProgram',Name='MainProgram')
    E.indent(root,space='  ');E.ElementTree(root).write(destination,encoding='utf-8',xml_declaration=True)


if __name__=='__main__':create(Path(__file__).parent/'samples/AOILab.L5X')
