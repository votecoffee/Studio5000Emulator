"""Source-authored v35 fixture for typed arrays, strings, expressions and jumps."""
from pathlib import Path
from xml.etree import ElementTree as E


def create(destination):
    root=E.Element('RSLogix5000Content',SchemaRevision='1.0',SoftwareRevision='35.01',TargetName='DataLab',TargetType='Controller',ContainsContext='false')
    c=E.SubElement(root,'Controller',Name='DataLab',ProcessorType='1756-L85E',MajorRev='35',MinorRev='11')
    E.SubElement(c,'DataTypes');E.SubElement(c,'Modules');E.SubElement(c,'AddOnInstructionDefinitions')
    tags=E.SubElement(c,'Tags')
    def tag(name,dtype,value=0):
        t=E.SubElement(tags,'Tag',Name=name,TagType='Base',DataType=dtype,Constant='false',ExternalAccess='Read/Write')
        d=E.SubElement(t,'Data',Format='Decorated')
        E.SubElement(d,'DataValue',DataType=dtype,Radix='Decimal',Value=str(value))
    def array(name,dims,values):
        t=E.SubElement(tags,'Tag',Name=name,TagType='Base',DataType='DINT',Dimensions=' '.join(map(str,dims)),Constant='false',ExternalAccess='Read/Write')
        d=E.SubElement(t,'Data',Format='Decorated');a=E.SubElement(d,'Array',DataType='DINT',Dimensions=','.join(map(str,dims)),Radix='Decimal')
        import itertools
        for idx,value in zip(itertools.product(*(range(n) for n in dims)),values):
            E.SubElement(a,'Element',Index='['+','.join(map(str,idx))+']',Value=str(value))
    def string(name,text):
        t=E.SubElement(tags,'Tag',Name=name,TagType='Base',DataType='STRING',Constant='false',ExternalAccess='Read/Write')
        raw=text.replace('$','$$').replace("'","$'")+'$00'*(82-len(text))
        E.SubElement(t,'Data',Format='L5K').text=f"[{len(text)},'{raw}']"
    array('Source',[6],[10,20,30,40,50,60]);array('Buffer',[6],[0]*6);array('Grid',[2,3],[0]*6)
    for name,value in [('Index',1),('Columns',0),('ParsedNumber',0),('LoopCount',0),('SkippedValue',0)]:tag(name,'DINT',value)
    tag('Scaled','REAL',0);tag('CopyEnable','BOOL',1);tag('Bypass','BOOL',1);tag('EarlyReturn','BOOL',0)
    tag('PackedStatus','UINT',65535);tag('HighBit','BOOL',0)
    tag('WideSource','LINT',9223372036854775806);tag('WideDest','LINT',0)
    for name,text in [('Prefix','VALUE '),('NumberText',''),('Message',''),('Snippet','')]:string(name,text)
    programs=E.SubElement(c,'Programs');p=E.SubElement(programs,'Program',Name='MainProgram',MainRoutineName='MainRoutine',Disabled='false',Class='Standard')
    E.SubElement(p,'Tags');routines=E.SubElement(p,'Routines');r=E.SubElement(routines,'Routine',Name='MainRoutine',Type='RLL');content=E.SubElement(r,'RLLContent')
    rungs=[
      ('Initialize a numeric array once.', 'XIC(S:FS)FLL(7,Buffer[0],6);'),
      ('Copy six elements into a two-dimensional array.', 'XIC(CopyEnable)COP(Source[0],Buffer[0],6)CPS(Buffer[0],Grid[0,0],6);'),
      ('Read the second dimension length.', 'SIZE(Grid,1,Columns);'),
      ('Evaluate an expression with an indexed array operand.', 'CPT(Scaled,(Grid[Index,1]+5)*2.0);'),
      ('Build text from a numeric value.', 'DTOS(Grid[Index,1],NumberText)CONCAT(Prefix,NumberText,Message);'),
      ('Extract text and convert a string back to a number.', 'MID(Message,3,1,Snippet)STOD(NumberText,ParsedNumber);'),
      ('Preserve wide integer values and read an unsigned word bit.', 'MOV(WideSource,WideDest)XIC(PackedStatus.15)OTE(HighBit);'),
      ('Prepare a bounded loop.', 'CLR(LoopCount);'),
      ('Repeat until the count reaches three.', 'LBL(Again)ADD(LoopCount,1,LoopCount)LES(LoopCount,3)JMP(Again);'),
      ('Skip the next write when Bypass is set.', 'XIC(Bypass)JMP(Finish);'),
      ('This write is skipped in the default demo.', 'MOV(999,SkippedValue);'),
      ('Temporary end exits only this routine.', 'LBL(Finish)XIC(EarlyReturn)TND();')]
    for i,(comment,text) in enumerate(rungs):
        rung=E.SubElement(content,'Rung',Number=str(i),Type='N');E.SubElement(rung,'Comment').text=comment;E.SubElement(rung,'Text').text=text
    tasks=E.SubElement(c,'Tasks');task=E.SubElement(tasks,'Task',Name='MainTask',Type='CONTINUOUS',Priority='10',Watchdog='500',Class='Standard',InhibitTask='false')
    scheduled=E.SubElement(task,'ScheduledPrograms');E.SubElement(scheduled,'ScheduledProgram',Name='MainProgram')
    E.indent(root,space='  ');E.ElementTree(root).write(destination,encoding='utf-8',xml_declaration=True)


if __name__=='__main__':create(Path(__file__).parent/'samples/DataLab.L5X')
