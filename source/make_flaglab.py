"""Generate the public packed-BIT fixture from source-authored data."""
from pathlib import Path
from xml.etree import ElementTree as E


def create(path):
    root = E.Element('RSLogix5000Content', SchemaRevision='1.0', SoftwareRevision='35.01',
                     TargetName='FlagLab', TargetType='Controller', ContainsContext='false')
    controller = E.SubElement(root, 'Controller', Name='FlagLab', ProcessorType='1756-L85E', MajorRev='35', MinorRev='11')
    types = E.SubElement(controller, 'DataTypes')
    def member(parent, name, dtype, **attrs):
        return E.SubElement(parent, 'Member', Name=name, DataType=dtype, Dimension='0', Hidden='false',
                            **attrs)
    def host(parent, suffix):
        name = 'ZZZZZZZZZZ' + suffix
        E.SubElement(parent, 'Member', Name=name, DataType='SINT', Dimension='0', Hidden='true')
        return name
    group = E.SubElement(E.SubElement(types, 'DataType', Name='FlagGroup', Class='User', Family='NoFamily'), 'Members')
    storage = host(group, 'Group')
    for name, bit in (('Enabled', 0), ('Valid', 2), ('High', 7)):
        member(group, name, 'BIT', Target=storage, BitNumber=str(bit))
    member(group, 'Code', 'INT')
    record = E.SubElement(E.SubElement(types, 'DataType', Name='FlagRecord', Class='User', Family='NoFamily'), 'Members')
    storage = host(record, 'State')
    for name, bit in (('Ready', 0), ('Running', 3), ('Fault', 7)):
        member(record, name, 'BIT', Target=storage, BitNumber=str(bit))
    storage = host(record, 'Mode'); member(record, 'Remote', 'BIT', Target=storage, BitNumber='1')
    member(record, 'Count', 'DINT'); member(record, 'Group', 'FlagGroup')
    E.SubElement(record, 'Member', Name='History', DataType='FlagGroup', Dimension='4', Hidden='false')
    E.SubElement(controller, 'Modules'); E.SubElement(controller, 'AddOnInstructionDefinitions')
    tags = E.SubElement(controller, 'Tags')
    def value(parent, name, dtype, number):
        E.SubElement(parent, 'DataValueMember', Name=name, DataType=dtype, Value=str(int(number)))
    def group_value(parent, seed):
        for name, bit in (('Enabled', 0), ('Valid', 2), ('High', 7)):
            value(parent, name, 'BOOL', (seed >> bit) & 1)
        value(parent, 'Code', 'INT', seed - 100)
    def record_value(parent, seed):
        for name, bit in (('Ready', 0), ('Running', 3), ('Fault', 7)):
            value(parent, name, 'BOOL', (seed >> bit) & 1)
        value(parent, 'Remote', 'BOOL', seed & 1); value(parent, 'Count', 'DINT', seed * 10)
        group_value(E.SubElement(parent, 'StructureMember', Name='Group', DataType='FlagGroup'), seed)
        history = E.SubElement(parent, 'ArrayMember', Name='History', DataType='FlagGroup', Dimensions='4')
        for index in range(4):
            element = E.SubElement(history, 'Element', Index=f'[{index}]')
            group_value(E.SubElement(element, 'Structure', DataType='FlagGroup'), seed + index + 1)
    tag = E.SubElement(tags, 'Tag', Name='Record', TagType='Base', DataType='FlagRecord', ExternalAccess='Read Only')
    record_value(E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'Structure', DataType='FlagRecord'), 137)
    tag = E.SubElement(tags, 'Tag', Name='Records', TagType='Base', DataType='FlagRecord', Dimensions='12', ExternalAccess='Read/Write')
    array = E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'Array', DataType='FlagRecord', Dimensions='12')
    for index in range(12):
        record_value(E.SubElement(E.SubElement(array, 'Element', Index=f'[{index}]'), 'Structure', DataType='FlagRecord'), index)
    for name, dtype in (('Observed', 'BOOL'), ('ObservedCount', 'DINT')):
        tag = E.SubElement(tags, 'Tag', Name=name, TagType='Base', DataType=dtype, ExternalAccess='Read Only')
        E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'DataValue', DataType=dtype, Value='0')
    program = E.SubElement(E.SubElement(controller, 'Programs'), 'Program', Name='MainProgram',
                           MainRoutineName='MainRoutine', Disabled='false', Class='Standard')
    E.SubElement(program, 'Tags')
    routine = E.SubElement(E.SubElement(program, 'Routines'), 'Routine', Name='MainRoutine', Type='RLL')
    content = E.SubElement(routine, 'RLLContent')
    for index, text in enumerate(('XIC(Records[0].Ready)OTE(Observed);', 'MOV(Records[0].Count,ObservedCount);')):
        E.SubElement(E.SubElement(content, 'Rung', Number=str(index), Type='N'), 'Text').text = text
    task = E.SubElement(E.SubElement(controller, 'Tasks'), 'Task', Name='MainTask', Type='CONTINUOUS',
                        Priority='10', Watchdog='500', Class='Standard', InhibitTask='false')
    E.SubElement(E.SubElement(task, 'ScheduledPrograms'), 'ScheduledProgram', Name='MainProgram')
    E.indent(root, space='  '); E.ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)


if __name__ == '__main__': create(Path(__file__).parent / 'samples/FlagLab.L5X')
