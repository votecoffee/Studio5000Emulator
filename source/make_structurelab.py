"""Source-authored numeric UDT fixture for template and structured-read probes."""
from pathlib import Path
from xml.etree import ElementTree as E


def create(destination):
    root = E.Element('RSLogix5000Content', SchemaRevision='1.0', SoftwareRevision='35.01',
                     TargetName='StructureLab', TargetType='Controller', ContainsContext='false')
    c = E.SubElement(root, 'Controller', Name='StructureLab', ProcessorType='1756-L85E', MajorRev='35', MinorRev='11')
    E.SubElement(c, 'Description').text = 'LogixLab fixture: nested numeric UDT templates and fragmented structure reads.'
    types = E.SubElement(c, 'DataTypes')
    schemas = {
        'AxisState': [('Command', 'DINT', 0), ('Actual', 'REAL', 0), ('Samples', 'DINT', 8)],
        'MachineState': [('Axis', 'AxisState', 0), ('History', 'AxisState', 12), ('Counters', 'UDINT', 4)]}
    for dtype, fields in schemas.items():
        members = E.SubElement(E.SubElement(types, 'DataType', Name=dtype, Family='NoFamily', Class='User'), 'Members')
        for name, member_type, count in fields:
            E.SubElement(members, 'Member', Name=name, DataType=member_type, Dimension=str(count),
                         Radix='Float' if member_type == 'REAL' else 'Decimal', Hidden='false', ExternalAccess='Read/Write')
    E.SubElement(c, 'Modules'); E.SubElement(c, 'AddOnInstructionDefinitions'); tags = E.SubElement(c, 'Tags')

    def structure(parent, dtype, seed, **attrs):
        node = E.SubElement(parent, 'Structure' if not attrs else 'StructureMember', DataType=dtype, **attrs)
        for name, member_type, count in schemas[dtype]:
            if count:
                array = E.SubElement(node, 'ArrayMember', Name=name, DataType=member_type, Dimensions=str(count))
                for i in range(count):
                    if member_type in schemas:
                        element = E.SubElement(array, 'Element', Index=f'[{i}]')
                        structure(element, member_type, seed + i + 1)
                    else:
                        E.SubElement(array, 'Element', Index=f'[{i}]', Value=str(seed + i))
            elif member_type in schemas:
                structure(node, member_type, seed, Name=name)
            else:
                E.SubElement(node, 'DataValueMember', Name=name, DataType=member_type,
                             Radix='Float' if member_type == 'REAL' else 'Decimal',
                             Value=str(seed + 0.5 if member_type == 'REAL' else seed))
        return node

    command = E.SubElement(tags, 'Tag', Name='Command', TagType='Base', DataType='DINT', ExternalAccess='Read/Write')
    E.SubElement(E.SubElement(command, 'Data', Format='Decorated'), 'DataValue', DataType='DINT', Radix='Decimal', Value='7')
    for name, count, access in [('Machine', 0, 'Read Only'), ('Machines', 2, 'Read/Write')]:
        tag = E.SubElement(tags, 'Tag', Name=name, TagType='Base', DataType='MachineState', ExternalAccess=access)
        data = E.SubElement(tag, 'Data', Format='Decorated')
        if count:
            tag.set('Dimensions', str(count))
            array = E.SubElement(data, 'Array', DataType='MachineState', Dimensions=str(count))
            for i in range(count): structure(E.SubElement(array, 'Element', Index=f'[{i}]'), 'MachineState', i * 100)
        else: structure(data, 'MachineState', 10)
    program = E.SubElement(E.SubElement(c, 'Programs'), 'Program', Name='MainProgram', MainRoutineName='MainRoutine',
                           Disabled='false', Class='Standard')
    E.SubElement(program, 'Tags')
    routine = E.SubElement(E.SubElement(program, 'Routines'), 'Routine', Name='MainRoutine', Type='RLL')
    rung = E.SubElement(E.SubElement(routine, 'RLLContent'), 'Rung', Number='0', Type='N')
    E.SubElement(rung, 'Text').text = 'MOV(Command,Machine.Axis.Command)MOV(Command,Machine.Axis.Actual);'
    task = E.SubElement(E.SubElement(c, 'Tasks'), 'Task', Name='MainTask', Type='CONTINUOUS', Priority='10',
                        Watchdog='500', Class='Standard', InhibitTask='false')
    E.SubElement(E.SubElement(task, 'ScheduledPrograms'), 'ScheduledProgram', Name='MainProgram')
    E.indent(root, space='  ')
    E.ElementTree(root).write(destination, encoding='utf-8', xml_declaration=True)


if __name__ == '__main__': create(Path(__file__).parent / 'samples/StructureLab.L5X')
