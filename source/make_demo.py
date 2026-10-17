"""Generate the transparent v35 demonstration fixture (no proprietary source)."""
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, indent, ElementTree


def create(destination):
    root = Element('RSLogix5000Content', SchemaRevision='1.0', SoftwareRevision='35.01', TargetName='ConveyorDemo', TargetType='Controller', ContainsContext='false')
    c = SubElement(root, 'Controller', Name='ConveyorDemo', ProcessorType='1756-L85E', MajorRev='35', MinorRev='11')
    SubElement(c, 'DataTypes')
    SubElement(c, 'Modules')
    SubElement(c, 'AddOnInstructionDefinitions')
    tags = SubElement(c, 'Tags')
    def tag(name, dtype, value=0):
        t = SubElement(tags, 'Tag', Name=name, TagType='Base', DataType=dtype, ExternalAccess='Read/Write', Constant='false')
        d = SubElement(t, 'Data', Format='Decorated')
        if dtype in ('TIMER','COUNTER'):
            s = SubElement(d, 'Structure', DataType=dtype)
            members = {'PRE':value,'ACC':0, **({'EN':0,'TT':0,'DN':0} if dtype=='TIMER' else {'CU':0,'CD':0,'DN':0,'OV':0,'UN':0})}
            for key, v in members.items(): SubElement(s, 'DataValueMember', Name=key, DataType='DINT' if key in ('PRE','ACC') else 'BOOL', Radix='Decimal', Value=str(v))
        else: SubElement(d,'DataValue', DataType=dtype, Radix='Decimal', Value=str(value))
    for name in ('StartPB','StopPB','RunLatch','MotorRunning','PartSensor','SensorMemory','PartPulse','BatchComplete','ResetPB'):
        tag(name,'BOOL')
    tag('StartDelay','TIMER',1000)
    tag('Parts','COUNTER',5)
    tag('SpeedSetpoint','DINT',50)
    tag('SpeedCommand','DINT',0)
    tag('DisplayedPartCount','DINT',0)
    programs=SubElement(c,'Programs')
    p=SubElement(programs,'Program', Name='MainProgram', MainRoutineName='MainRoutine', Disabled='false', Class='Standard')
    SubElement(p,'Tags')
    routines=SubElement(p,'Routines')
    r=SubElement(routines,'Routine', Name='MainRoutine', Type='RLL')
    content=SubElement(r,'RLLContent')
    rungs=[
      ('Hold run request until Stop is pressed.', 'XIO(StopPB)[XIC(StartPB),XIC(RunLatch)]OTE(RunLatch);'),
      ('Delay motor start by 1,000 simulated milliseconds.', 'XIC(RunLatch)TON(StartDelay,?,?);'),
      ('Motor runs after the startup delay.', 'XIC(StartDelay.DN)XIC(RunLatch)OTE(MotorRunning);'),
      ('Detect one pulse per passing part.', 'XIC(PartSensor)ONS(SensorMemory)OTE(PartPulse);'),
      ('Count pulses only while the motor is running.', 'XIC(MotorRunning)XIC(PartPulse)CTU(Parts,?,?);'),
      ('Indicate when the five-part batch is complete.', 'XIC(Parts.DN)OTE(BatchComplete);'),
      ('Reset the batch counter on operator request.', 'XIC(ResetPB)RES(Parts);'),
      ('Drive the speed command, or clear it when stopped.', '[XIC(MotorRunning)MOV(SpeedSetpoint,SpeedCommand),XIO(MotorRunning)CLR(SpeedCommand)];'),
      ('Execute the reporting routine.', 'JSR(Reporting,0);')]
    for i,(comment,text) in enumerate(rungs):
        rung=SubElement(content,'Rung', Number=str(i), Type='N')
        SubElement(rung,'Comment').text=comment
        SubElement(rung,'Text').text=text
    r=SubElement(routines,'Routine',Name='Reporting',Type='RLL')
    content=SubElement(r,'RLLContent')
    rung=SubElement(content,'Rung',Number='0',Type='N')
    SubElement(rung,'Comment').text='A simple arithmetic calculation in a called routine.'
    SubElement(rung,'Text').text='ADD(Parts.ACC,0,DisplayedPartCount);'
    tasks=SubElement(c,'Tasks')
    task=SubElement(tasks,'Task',Name='MainTask',Type='Continuous',Priority='10',Watchdog='500',DisableUpdateOutputs='false',InhibitTask='false',Class='Standard')
    scheduled=SubElement(task,'ScheduledPrograms')
    SubElement(scheduled,'ScheduledProgram',Name='MainProgram')
    indent(root, space='  ')
    Path(destination).parent.mkdir(parents=True, exist_ok=True)
    ElementTree(root).write(destination,encoding='utf-8',xml_declaration=True)


if __name__ == '__main__': create(Path(__file__).parent / 'samples' / 'ConveyorDemo.L5X')
