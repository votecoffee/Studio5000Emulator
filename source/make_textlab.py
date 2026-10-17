"""Source-authored v35 Structured Text and mixed-language fixture."""
import copy
from pathlib import Path
from xml.etree import ElementTree as E


def create(destination):
    root=E.Element('RSLogix5000Content',SchemaRevision='1.0',SoftwareRevision='35.01',TargetName='TextLab',TargetType='Controller',ContainsContext='false')
    c=E.SubElement(root,'Controller',Name='TextLab',ProcessorType='1756-L85E',MajorRev='35',MinorRev='11')
    E.SubElement(c,'DataTypes');E.SubElement(c,'Modules');definitions=E.SubElement(c,'AddOnInstructionDefinitions')
    a=copy.deepcopy(E.parse(Path(__file__).parent/'samples/AOILab.L5X').find('./Controller/AddOnInstructionDefinitions/AddOnInstructionDefinition[@Name="LabAccumulator"]'))
    a.set('Name','LabSTAccumulator');a.set('ExecuteEnableInFalse','true');definitions.append(a)
    params=a.find('Parameters');params.remove(params.find('./Parameter[@Name="Shared"]'));a.find('Routines').clear()
    def st(parent,name,text):
        r=E.SubElement(parent,'Routine',Name=name,Type='ST');content=E.SubElement(r,'STContent')
        for i,line in enumerate(text.strip('\n').split('\n')):E.SubElement(content,'Line',Number=str(i)).text=line
    st(a.find('Routines'),'Logic','Count := Count + Step;\nTotal := Count;\nEnableOut := Count < Limit;')
    st(a.find('Routines'),'Prescan','Count := 0;\nTotal := 0;')
    st(a.find('Routines'),'EnableInFalse','Total := -1;')
    tags=E.SubElement(c,'Tags')
    def tag(name,dtype,value):
        t=E.SubElement(tags,'Tag',Name=name,TagType='Base',DataType=dtype,Constant='false',ExternalAccess='Read/Write');d=E.SubElement(t,'Data',Format='Decorated')
        E.SubElement(d,'DataValue',DataType=dtype,Radix='Float' if dtype=='REAL' else 'Decimal',Value=str(value))
    for name,value in [('Enable',1),('Done',0),('Truth',0)]:tag(name,'BOOL',value)
    values={'ScanTotal':0,'ClearedOnRun':99,'Sum':0,'Index':99,'Selector':3,'State':0,'CaseResult':0,'WhileCount':0,
            'RepeatCount':0,'SearchResult':-1,'SearchIndex':99,'FormalSum':0,'ScaleWork':0,'Scaled':0,'AdjustInput':0,
            'AdjustOutput':0,'Step':2,'AOITotal':0,'Packed':0,'BitIndex':99}
    for name,value in values.items():tag(name,'DINT',value)
    t=E.SubElement(tags,'Tag',Name='Values',TagType='Base',DataType='DINT',Dimensions='5',Constant='false',ExternalAccess='Read/Write')
    arr=E.SubElement(E.SubElement(t,'Data',Format='Decorated'),'Array',DataType='DINT',Dimensions='5',Radix='Decimal')
    for i in range(5):E.SubElement(arr,'Element',Index=f'[{i}]',Value='0')
    for name,text in [('Prefix','SCAN '),('NumberText',''),('Message',''),('Shadow','')]:
        t=E.SubElement(tags,'Tag',Name=name,TagType='Base',DataType='STRING',Constant='false',ExternalAccess='Read/Write')
        E.SubElement(t,'Data',Format='L5K').text=f"[{len(text)},'{text}"+'$00'*(82-len(text))+"']"
    t=E.SubElement(tags,'Tag',Name='Accumulator',TagType='Base',DataType='LabSTAccumulator',Constant='false',ExternalAccess='Read/Write')
    s=E.SubElement(E.SubElement(t,'Data',Format='Decorated'),'Structure',DataType='LabSTAccumulator')
    for name,dtype,value in [('EnableIn','BOOL',0),('EnableOut','BOOL',0),('Step','DINT',1),('Total','DINT',0),('Limit','DINT',100)]:
        E.SubElement(s,'DataValueMember',Name=name,DataType=dtype,Radix='Decimal',Value=str(value))
    p=E.SubElement(E.SubElement(c,'Programs'),'Program',Name='MainProgram',MainRoutineName='MainRoutine',Disabled='false',Class='Standard')
    E.SubElement(p,'Tags');rr=E.SubElement(p,'Routines')
    st(rr,'MainRoutine',r"""// Text Lab: assignments, selection, iteration and mixed-language calls.
ScanTotal := ScanTotal + 1;
ClearedOnRun [:=] 17;
Sum := 0;
FOR Index := 0 TO 4 DO
    Values[Index] := Index * 3;
    Sum := Sum + Values[Index];
END_FOR;
IF Enable THEN
    IF Sum >= 30 THEN State := 2;
    ELSIF Sum > 0 THEN State := 1;
    ELSE State := 0;
    END_IF;
    LabSTAccumulator(Accumulator,Step,AOITotal);
ELSE
    State := -1;
END_IF;
CASE Selector OF
    1,2: CaseResult := 10;
    3..5: CaseResult := 20;
    ELSE CaseResult := -1;
END_CASE;
WhileCount := 0;
WHILE WhileCount < 3 DO
    WhileCount := WhileCount + 1;
END_WHILE;
RepeatCount := 0;
REPEAT
    RepeatCount := RepeatCount + 1;
UNTIL RepeatCount >= 2 END_REPEAT;
SearchResult := -1;
FOR SearchIndex := 0 TO 4 DO
    IF Values[SearchIndex] = 9 THEN
        SearchResult := SearchIndex;
        EXIT;
    END_IF;
END_FOR;
JSR(LadderScale,1,Sum,Scaled);
DTOS(ScanTotal,NumberText);
CONCAT(Prefix,NumberText,Message);
Shadow := Message;
Packed := 0;
FOR BitIndex := 0 TO 3 DO
    Packed.[BitIndex] := 1;
END_FOR;
Done := Enable AND (Sum = 30);
Truth := TRUE;
""")
    r=E.SubElement(rr,'Routine',Name='LadderScale',Type='RLL');content=E.SubElement(r,'RLLContent')
    for i,text in enumerate(['SBR(FormalSum);','MUL(FormalSum,2,ScaleWork);','JSR(TextAdjust,1,ScaleWork,ScaleWork);','RET(ScaleWork);']):
        rung=E.SubElement(content,'Rung',Number=str(i),Type='N');E.SubElement(rung,'Text').text=text
    st(rr,'TextAdjust','SBR(AdjustInput);\nAdjustOutput := AdjustInput + 1;\nRET(AdjustOutput);')
    task=E.SubElement(E.SubElement(c,'Tasks'),'Task',Name='MainTask',Type='CONTINUOUS',Priority='10',Watchdog='500',Class='Standard',InhibitTask='false')
    E.SubElement(E.SubElement(task,'ScheduledPrograms'),'ScheduledProgram',Name='MainProgram')
    E.indent(root,space='  ');E.ElementTree(root).write(destination,encoding='utf-8',xml_declaration=True)


if __name__=='__main__':create(Path(__file__).parent/'samples/TextLab.L5X')
