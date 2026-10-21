"""Logical relations require complete source and matching original identities."""
import copy
from pathlib import Path
import struct
import unittest
from xml.etree import ElementTree as E
from logixlab.program_configuration import ProgramConfiguration
from logixlab.program_hierarchy import ProgramHierarchy

HASH='a'*64;ACD='b'*64


def source():
    root=E.parse(Path(__file__).resolve().parents[1]/'samples/ConveyorDemo.L5X').getroot()
    return root,root.find('Controller')


def parse(root,controller):
    config=ProgramConfiguration.from_source(root,controller,HASH)
    return ProgramHierarchy.from_source(root,controller,HASH,config)


def children(config,program='MainProgram',**updates):
    args=dict(source_sha256=HASH,source_acd_sha256=ACD,program_ids={'MainProgram':26038},
        program_source_l5x_sha256=HASH,program_source_acd_sha256=ACD)
    args.update(updates);return config.child_attributes(program,**args)


def graph_source():
    root,controller=source();programs=controller.find('Programs')
    for name in ('Second','Third'):
        node=copy.deepcopy(programs[0]);node.set('Name',name);programs.append(node)
    group=E.SubElement(programs[0],'ChildPrograms')
    for name in ('third','SECOND'):E.SubElement(group,'ChildProgram',Name=name)
    return root,controller


class ProgramHierarchyTests(unittest.TestCase):
    def test_complete_absence_or_explicit_empty_children_returns_zero_count_and_null_fault_only(self):
        root,controller=source();config=parse(root,controller)
        self.assertEqual(children(config),{32:bytes(2)})
        self.assertEqual(config.attributes('MAINPROGRAM',source_sha256=HASH),{9:bytes(4)})
        self.assertEqual(config.attributes('MainProgram',source_sha256='c'*64),{})
        self.assertEqual(config.attributes(None,source_sha256=HASH),{})
        program=controller.find('./Programs/Program');E.SubElement(program,'ChildPrograms')
        program.set('FaultRoutineName','')
        self.assertEqual(children(parse(root,controller)),{32:bytes(2)})
        program.set('FaultRoutineName','MainRoutine')
        other=parse(root,controller);self.assertEqual(other.attributes('MainProgram',source_sha256=HASH),{})
        self.assertEqual(children(other),{32:bytes(2)})

    def test_ordered_names_resolve_actual_ids_without_becoming_execution_schedules(self):
        root,controller=graph_source();config=parse(root,controller)
        ids={'MainProgram':26038,'Second':70000,'Third':0x12345678}
        self.assertEqual(children(config,program_ids=ids),{32:struct.pack('<HII',2,0x12345678,70000)})
        self.assertEqual(children(config,'SECOND',program_ids=ids),{32:bytes(2)})
        self.assertEqual(config.description()['child_targets'],2)
        self.assertFalse(config.description()['execution_schedule_changed'])
        controller.find('./Programs/Program/ChildPrograms').clear()
        self.assertEqual(children(config,program_ids=ids),{32:struct.pack('<HII',2,0x12345678,70000)})

    def test_bad_graphs_and_ambiguous_or_opaque_child_lists_never_invent_empty_results(self):
        for mode in ('cycle','self','missing','multi-parent','duplicate','namespace','alias','context','nested',
                     'unknown-group-field','unknown-entry-field','entry-child','entry-text','tail','second-group','shadow','opaque',
                     'program-text','group-tail','container-text','container-field'):
            root,controller=graph_source();programs=controller.find('Programs');group=programs[0].find('ChildPrograms');entry=group[0]
            if mode=='cycle':E.SubElement(E.SubElement(programs[2],'ChildPrograms'),'ChildProgram',Name='MainProgram')
            elif mode=='self':entry.set('Name','MainProgram')
            elif mode=='missing':entry.set('Name','Missing')
            elif mode=='multi-parent':E.SubElement(E.SubElement(programs[1],'ChildPrograms'),'ChildProgram',Name='Third')
            elif mode=='duplicate':entry.set('Name','Second')
            elif mode=='namespace':group.tag='{other}ChildPrograms'
            elif mode=='alias':entry.set('name','Second')
            elif mode=='context':entry.set('Use','Context')
            elif mode=='nested':E.SubElement(controller,'Wrapper').append(copy.deepcopy(group))
            elif mode=='unknown-group-field':group.set('Data','unmodeled')
            elif mode=='unknown-entry-field':entry.set('UId','42')
            elif mode=='entry-child':E.SubElement(entry,'Hidden')
            elif mode=='entry-text':entry.text='unmodeled'
            elif mode=='tail':entry.tail='unmodeled'
            elif mode=='second-group':E.SubElement(programs[0],'ChildPrograms')
            elif mode=='shadow':E.SubElement(controller,'ChildProgramsUId')
            elif mode=='program-text':programs[0].text='opaque'
            elif mode=='group-tail':group.tail='opaque'
            elif mode=='container-text':programs.text='opaque'
            elif mode=='container-field':programs.set('UId','opaque')
            else:E.SubElement(programs[0],'EncodedData')
            with self.subTest(mode=mode):
                self.assertEqual(children(parse(root,controller),program_ids={'MainProgram':1,'Second':2,'Third':3}),{})

    def test_incomplete_foreign_kind_and_noncanonical_fault_declarations_do_not_supply_nulls(self):
        for mode in ('context','Safety','phase','type-alias','fault-alias','fault-uid','class-alias','partial','major'):
            root,controller=source();program=controller.find('./Programs/Program')
            if mode=='context':root.set('ContainsContext','true')
            elif mode=='Safety':program.set('Class','Safety')
            elif mode=='phase':program.set('Type','EquipmentPhase')
            elif mode=='type-alias':program.set('type','Normal')
            elif mode=='fault-alias':program.set('{test}FaultRoutineName','MainRoutine')
            elif mode=='fault-uid':program.set('FaultRoutineNameUId','0')
            elif mode=='class-alias':program.set('class','Standard')
            elif mode=='partial':root.set('TargetType','Program')
            else:controller.set('MajorRev','36')
            config=parse(root,controller)
            with self.subTest(mode=mode):
                self.assertEqual(config.attributes('MainProgram',source_sha256=HASH),{})
                self.assertEqual(children(config),{})

    def test_mismatched_partial_and_ambiguous_identity_maps_are_unavailable_even_for_empty_lists(self):
        root,controller=source();config=parse(root,controller)
        cases=({'source_sha256':'c'*64},{'source_acd_sha256':'x'},
               {'program_source_l5x_sha256':'c'*64},{'program_source_acd_sha256':'c'*64},
               {'program_ids':{}},{'program_ids':{'MainProgram':True}},
               {'program_ids':{'MainProgram':0}},{'program_ids':{'MainProgram':0x100000000}},
               {'program_ids':{'MainProgram':1,'MAINPROGRAM':2}},
               {'program_ids':{'MainProgram':1,'Other':1}},{'program_ids':{'MainProgram':1,'Other':2}})
        for updates in cases:
            with self.subTest(updates=updates):self.assertEqual(children(config,**updates),{})
        self.assertEqual(children(config,None),{});self.assertEqual(children(config,'Missing'),{})

    def test_constructor_freezes_graph_and_rejects_cycles_multiparents_or_partial_names(self):
        rows={'main':('child',),'child':()};nulls={'main'};config=ProgramHierarchy(HASH,rows,nulls)
        rows.clear();nulls.clear();self.assertEqual(config._children['main'],('child',))
        self.assertEqual(config.attributes('main',source_sha256=HASH),{9:bytes(4)})
        for rows in ({'main':('main',)},{'main':('missing',)},
                     {'main':('child',),'child':(),'other':('child',)},{'Main':()},{'main':['child']}):
            with self.assertRaises(ValueError):ProgramHierarchy(HASH,rows)
        for nulls in ('main',None,{'Main'},{1}):
            with self.assertRaises(ValueError):ProgramHierarchy(HASH,_null_faults=nulls)
        with self.assertRaises(ValueError):ProgramHierarchy('')
        chain={f'p{i}':(f'p{i+1}',) if i<1500 else () for i in range(1501)}
        self.assertEqual(len(ProgramHierarchy(HASH,chain)._children),1501)


if __name__=='__main__':unittest.main()
