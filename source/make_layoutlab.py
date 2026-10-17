"""Source-authored mixed-width numeric fixture for aligned UDT transfers."""
from pathlib import Path
from xml.etree import ElementTree as E


SCHEMAS = {
    'SmallGroup': [('Byte', 'SINT', 0), ('Short', 'INT', 0), ('Code', 'USINT', 0), ('Samples', 'SINT', 3)],
    'MixedRecord': [('Prefix', 'SINT', 0), ('Short', 'INT', 0), ('Bytes', 'USINT', 3), ('Wide', 'LINT', 0),
                    ('Count', 'DINT', 0), ('Words', 'UINT', 3), ('Group', 'SmallGroup', 0), ('Huge', 'ULINT', 0),
                    ('Ratio', 'REAL', 0), ('Trailing', 'SINT', 0), ('Unsigned', 'UDINT', 0)]}


def values(dtype, seed):
    if dtype == 'SmallGroup':
        return {'Byte': -5 + seed, 'Short': -1234 - seed, 'Code': 200 + seed, 'Samples': [-4 - seed, 0, 5 + seed]}
    return {'Prefix': -8 + seed, 'Short': -30000 + seed, 'Bytes': [0, 127, 255 - seed],
            'Wide': -(1 << 63) + seed, 'Count': 100 + seed, 'Words': [1, 32768, 65535 - seed],
            'Huge': (1 << 64) - 1 - seed, 'Ratio': 1.25 + seed, 'Trailing': 120 - seed, 'Unsigned': (1 << 32) - 1 - seed}


def create(destination):
    root = E.Element('RSLogix5000Content', SchemaRevision='1.0', SoftwareRevision='35.01', TargetName='LayoutLab',
                     TargetType='Controller', ContainsContext='false')
    c = E.SubElement(root, 'Controller', Name='LayoutLab', ProcessorType='1756-L85E', MajorRev='35', MinorRev='11')
    E.SubElement(c, 'Description').text = 'LogixLab fixture: mixed-width numeric UDTs with scalar, array and nested alignment.'
    types = E.SubElement(c, 'DataTypes')
    for dtype, fields in SCHEMAS.items():
        members = E.SubElement(E.SubElement(types, 'DataType', Name=dtype, Family='NoFamily', Class='User'), 'Members')
        for name, member_type, count in fields:
            E.SubElement(members, 'Member', Name=name, DataType=member_type, Dimension=str(count),
                         Radix='Float' if member_type == 'REAL' else 'Decimal', Hidden='false', ExternalAccess='Read/Write')
    E.SubElement(c, 'Modules'); E.SubElement(c, 'AddOnInstructionDefinitions'); tags = E.SubElement(c, 'Tags')

    def structure(parent, dtype, seed, name=None):
        node = E.SubElement(parent, 'Structure' if name is None else 'StructureMember', DataType=dtype,
                            **({'Name': name} if name is not None else {}))
        data = values(dtype, seed)
        for field, member_type, count in SCHEMAS[dtype]:
            if count:
                array = E.SubElement(node, 'ArrayMember', Name=field, DataType=member_type, Dimensions=str(count), Radix='Decimal')
                for i, value in enumerate(data[field]): E.SubElement(array, 'Element', Index=f'[{i}]', Value=str(value))
            elif member_type in SCHEMAS:
                structure(node, member_type, seed, field)
            else:
                E.SubElement(node, 'DataValueMember', Name=field, DataType=member_type,
                             Radix='Float' if member_type == 'REAL' else 'Decimal', Value=str(data[field]))

    for name, count, access in [('Record', 0, 'Read Only'), ('Records', 8, 'Read/Write')]:
        tag = E.SubElement(tags, 'Tag', Name=name, TagType='Base', DataType='MixedRecord', ExternalAccess=access)
        data = E.SubElement(tag, 'Data', Format='Decorated')
        if count:
            tag.set('Dimensions', str(count)); array = E.SubElement(data, 'Array', DataType='MixedRecord', Dimensions=str(count))
            for i in range(count): structure(E.SubElement(array, 'Element', Index=f'[{i}]'), 'MixedRecord', i)
        else: structure(data, 'MixedRecord', 9)
    tag = E.SubElement(tags, 'Tag', Name='Observed', TagType='Base', DataType='DINT', ExternalAccess='Read Only')
    E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'DataValue', DataType='DINT', Radix='Decimal', Value='0')
    p = E.SubElement(E.SubElement(c, 'Programs'), 'Program', Name='MainProgram', MainRoutineName='MainRoutine', Disabled='false', Class='Standard')
    E.SubElement(p, 'Tags'); r = E.SubElement(E.SubElement(p, 'Routines'), 'Routine', Name='MainRoutine', Type='RLL')
    rung = E.SubElement(E.SubElement(r, 'RLLContent'), 'Rung', Number='0', Type='N')
    E.SubElement(rung, 'Text').text = 'MOV(Records[0].Count,Observed);'
    task = E.SubElement(E.SubElement(c, 'Tasks'), 'Task', Name='MainTask', Type='CONTINUOUS', Priority='10', Watchdog='500', Class='Standard', InhibitTask='false')
    E.SubElement(E.SubElement(task, 'ScheduledPrograms'), 'ScheduledProgram', Name='MainProgram')
    E.indent(root, space='  '); E.ElementTree(root).write(destination, encoding='utf-8', xml_declaration=True)


if __name__ == '__main__': create(Path(__file__).parent / 'samples/LayoutLab.L5X')
