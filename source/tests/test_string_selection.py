"""Lazy represented-string operands, full logical writes and transactional calls."""
import copy
import unittest
from xml.etree import ElementTree as E

import test_string_operations as strings
import test_string_conversions as fixtures
from logixlab.model import ModelError

CALLS=[('CONCAT','CONCAT(TextCells[Index],SourceB,TextResults[Index]);','ABC123ABCXY'),
       ('MID','MID(TextCells[Index],3,1,TextResults[Index]);','ABC'),
       ('DTOS','DTOS(Numbers[Index],TextResults[Index]);','123'),
       ('DTOS_REAL','DTOS(RealCells[Index],TextResults[Index]);','2'),
       ('STOD','STOD(TextCells[Index],Numbers[Index]);',123),
       ('FIND','FIND(TextCells[Index],Search,1,Numbers[Index]);',1),
       ('INSERT','INSERT(TextCells[Index],SourceB,1,TextResults[Index]);','XYABC123ABC'),
       ('DELETE','DELETE(TextCells[Index],3,1,TextResults[Index]);','123ABC'),
       ('LOWER','LOWER(TextCells[Index],TextResults[Index]);','abc123abc'),
       ('UPPER','UPPER(TextCells[Index],TextResults[Index]);','ABC123ABC'),
       ('STOR','STOR(TextCells[Index],RealCells[Index]);',123.0),
       ('RTOS','RTOS(RealCells[Index],TextResults[Index]);','2.5')]


class StringSelectionTests(unittest.TestCase):
    setUp=fixtures.StringConversionTests.setUp

    @staticmethod
    def fields(root):
        tags=root.find('./Controller/Tags');tags.find('Tag[@Name="Index"]/Data/DataValue').set('Value','99')
        for name in ('TextCells','TextResults'):
            tag=E.SubElement(tags,'Tag',Name=name,DataType='STRING',TagType='Base',Dimensions='3')
            array=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='STRING',Dimensions='3')
            for i in range(3):
                obj=E.SubElement(E.SubElement(array,'Element',Index=f'[{i}]'),'Structure',DataType='STRING')
                data=E.SubElement(obj,'ArrayMember',Name='DATA',DataType='SINT',Dimensions='82')
                if name=='TextResults':E.SubElement(data,'Element',Index='[81]',Value='33')
        for name,dtype in [('Numbers','DINT'),('RealCells','REAL'),('Flags','BOOL')]:
            tag=E.SubElement(tags,'Tag',Name=name,DataType=dtype,TagType='Base',Dimensions='3')
            E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType=dtype,Dimensions='3')

    def engine(self,rungs,*,mutate=None,st=False):
        def fields(root):
            self.fields(root)
            if mutate:mutate(root)
        return fixtures.StringConversionTests.engine(self,rungs,st=st,mutate=fields)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);self.assertFalse(e.memory.structural);return e

    @staticmethod
    def snapshot(e):
        return copy.deepcopy((e.memory.values,e.memory.frames,e.memory._resolved,e.addons.instances,e.scan_count,e.time_ms,e.scheduler_description(),e.trace))

    def test_calls_skip_false_indices_require_sources_and_write_unknowns(self):
        for name,text,expected in CALLS:
            with self.subTest(name=name):
                e=self.checked(['XIC(StartPB)'+text]);e.step();self.assertIsNone(e.memory.read('TextResults')[0]['LEN']);e.memory.write('StartPB',True);before=self.snapshot(e)
                with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
                self.assertEqual(self.snapshot(e),before);e.memory.write('Index',0);before=self.snapshot(e)
                with self.assertRaisesRegex(ModelError,'(?i)unknown'):e.step()
                self.assertEqual(self.snapshot(e),before)
                if name=='DTOS':e.memory.write('Numbers[0]',123)
                elif name in ('DTOS_REAL','RTOS'):e.memory.write('RealCells[0]',2.5)
                else:e.memory.write('TextCells[0]','ABC123ABC')
                e.step()
                if isinstance(expected,str):
                    self.assertEqual(e.memory.string('TextResults[0]'),expected);self.assertEqual(e.memory.read('TextResults')[0]['DATA'][81],33)
                else:self.assertEqual(e.memory.read(('RealCells' if name=='STOR' else 'Numbers')+'[0]'),expected)
                self.assertIsNone(e.memory.read('TextResults')[1]['LEN']);self.assertFalse(e.memory.structural)

    def test_six_string_relations_and_string_cmp_are_lazy_but_not_identity_folded(self):
        for op,expected in [('EQU',False),('NEQ',True),('LES',True),('LEQ',True),('GRT',False),('GEQ',False)]:
            e=self.checked([f'XIC(StartPB){op}(TextCells[Index],SourceB)OTE(RunLatch);']);e.memory.write('RunLatch',True);e.step();self.assertFalse(e.memory.read('RunLatch'))
            e.memory.write('Index',0);e.memory.write('StartPB',True);before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'(?i)unknown'):e.step()
            self.assertEqual(self.snapshot(e),before);e.memory.write('TextCells[0]','ABC');e.step();self.assertEqual(e.memory.read('RunLatch'),expected)
        for expr in ('EQU(TextCells[0],TextCells[0])','CMP((1=1)||(TextCells[0]=SourceB))'):
            e=self.checked([expr+'OTE(RunLatch);']);before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'(?i)unknown'):e.step()
            self.assertEqual(self.snapshot(e),before)

    def test_prescan_does_not_consume_enabled_unknowns_or_dynamic_indices(self):
        for name,text,_ in CALLS:
            with self.subTest(name=name):
                e=self.checked([text]);self.assertEqual(e.prescan_count,1);self.assertEqual(e.scan_count,0)
                self.assertIsNone(e.memory.read('TextResults')[0]['LEN']);before=self.snapshot(e)
                with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
                self.assertEqual(self.snapshot(e),before)

    def test_cmp_string_bool_bit_and_unknown_right_operands_remain_eager(self):
        e=self.checked(['XIC(StartPB)CMP((SourceA=SourceA)||Flags[Index])OTE(RunLatch);']);e.step();e.memory.write('Index',0);e.memory.write('StartPB',True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('Flags[0]',False);e.step();self.assertTrue(e.memory.read('RunLatch'))
        self.assertTrue(self.engine(['CMP((SourceA=SourceA)||Flags)OTE(RunLatch);']).blockers)
        e=self.checked(['CMP((SourceA=SourceA)||S:FS)OTE(RunLatch);']);e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_mid_dynamic_positions_are_runtime_values_and_immediate_bounds_stay_static(self):
        e=self.checked(['XIC(StartPB)MID(SourceA,Qty,Start,TextResults[0]);'],mutate=lambda root:root.find('./Controller/Tags/Tag[@Name="Start"]/Data/DataValue').set('Value','0'))
        e.step();e.memory.write('StartPB',True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'MID range'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('Start',1);e.step();self.assertEqual(e.memory.string('TextResults[0]'),'ABC')
        for text in ('MID(SourceA,-1,1,Dest);','MID(SourceA,1,0,Dest);','MID(SourceA,1.0,1,Dest);'):
            self.assertTrue(self.engine(['AFI()'+text]).blockers)
        e=self.checked(['MID(SourceA,Numbers[0],Numbers[1],TextResults[0]);']);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('Numbers[0]',3);e.memory.write('Numbers[1]',1);e.step();self.assertEqual(e.memory.string('TextResults[0]'),'ABC')

    def test_active_bytes_required_unused_bytes_preserved_and_zero_mid_not_folded(self):
        e=self.checked(['CONCAT(TextCells[0],SourceB,TextResults[0]);']);e.memory.write('TextCells[0].LEN',3);e.memory.write('TextCells[0].DATA[0]',65);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'unknown active'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('TextCells[0].DATA[1]',66);e.memory.write('TextCells[0].DATA[2]',67);e.step();self.assertEqual(e.memory.string('TextResults[0]'),'ABCXY');self.assertEqual(e.memory.read('TextResults')[0]['DATA'][81],33)
        e=self.checked(['MID(TextCells[0],0,1,TextResults[0]);']);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'(?i)unknown'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('TextCells[0]','ABC');e.step();self.assertEqual(e.memory.string('TextResults[0]'),'');self.assertIsNone(e.memory.read('TextResults')[0]['DATA'][0])

    def test_capacity_and_later_fault_restore_lengths_data_numeric_results_and_schedule(self):
        e=self.checked(['CONCAT(SourceA,SourceB,TextResults[0]);','STOD(SourceA,Numbers[0]);','DELETE(TextResults[0],99,1,TextResults[0]);']);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'DELETE'):e.step()
        self.assertEqual(self.snapshot(e),before)
        e=self.checked(['CONCAT(SourceA,SourceB,TextResults[0]);']);e.memory.write('SourceA','A'*82);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'exceeds capacity'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_aliases_constant_sources_and_custom_string_udt_members(self):
        def fields(root):
            strings.StringOperationTests.custom_strings(root)
            root.find('./Controller/Tags/Tag[@Name="SourceA"]').set('Constant','true')
            E.SubElement(root.find('./Controller/Programs/Program/Tags'),'Tag',Name='View',DataType='STRING',TagType='Alias',AliasFor='TextCells')
            rec=root.find('./Controller/Tags/Tag[@Name="Record"]/Data/Structure/StructureMember');rec.remove(rec.find('DataValueMember[@Name="LEN"]'))
            for element in list(rec.find('ArrayMember')):rec.find('ArrayMember').remove(element)
        e=self.checked(['XIC(StartPB)CONCAT(View[Index],SourceB,Alias);'],mutate=fields);e.step();e.memory.write('Index',0);e.memory.write('View[0]','ABC','MainProgram');e.memory.write('StartPB',True);e.step()
        self.assertEqual(e.memory.string('Record.Text'),'ABCXY');self.assertEqual(e.memory.string('SourceA'),'ABC123ABC');self.assertIsNone(e.memory.read('Record.Text.DATA')[15])

    @staticmethod
    def aoi_logic(root):
        c=root.find('Controller');tags=c.find('Tags')
        tags.find('Tag[@Name="Start"]/Data/DataValue').set('Value','0');tags.find('Tag[@Name="Qty"]/Data/DataValue').set('Value','1')
        definition=E.SubElement(c.find('AddOnInstructionDefinitions'),'AddOnInstructionDefinition',Name='TextWorker',Class='Standard',ExecutePrescan='false',ExecutePostscan='false',ExecuteEnableInFalse='false')
        params=E.SubElement(definition,'Parameters')
        for name,dtype,usage,required in [('EnableIn','BOOL','Input','false'),('EnableOut','BOOL','Output','false'),('Buffer','STRING','InOut','true'),('Position','DINT','Input','true'),('Match','DINT','Output','true')]:E.SubElement(params,'Parameter',Name=name,DataType=dtype,Usage=usage,Required=required,Visible=required,TagType='Base')
        E.SubElement(E.SubElement(definition,'LocalTags'),'LocalTag',Name='Work',DataType='STRING',Dimensions='3')
        content=E.SubElement(E.SubElement(E.SubElement(definition,'Routines'),'Routine',Name='Logic',Type='RLL'),'RLLContent')
        for i,text in enumerate(['CONCAT(Buffer,Buffer,Work[Position]);','LOWER(Work[Position],Buffer);','FIND(Buffer,Buffer,1,Match);']):E.SubElement(E.SubElement(content,'Rung',Number=str(i),Type='N'),'Text').text=text
        for instance,position in [('First',0),('Second',1)]:
            obj=E.SubElement(E.SubElement(E.SubElement(tags,'Tag',Name=instance,DataType='TextWorker',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='TextWorker')
            for name,dtype,value in [('EnableIn','BOOL',0),('EnableOut','BOOL',0),('Position','DINT',position),('Match','DINT',0)]:E.SubElement(obj,'DataValueMember',Name=name,DataType=dtype,Value=str(value))
            E.SubElement(obj,'ArrayMember',Name='Work',DataType='STRING',Dimensions='3')

    def test_aoi_local_unknown_outputs_inout_strings_false_indices_and_binding_rollback(self):
        e=self.checked(['XIC(StartPB)TextWorker(First,TextCells[0],Start,Result);','XIC(PartSensor)TextWorker(Second,TextCells[1],Qty,Count);'],mutate=self.aoi_logic)
        e.memory.write('StartPB',True);e.memory.write('PartSensor',True);e.memory.write('TextCells[0]','Ab');before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'(?i)unknown'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('TextCells[1]','Cd');e.step();self.assertEqual((e.memory.string('TextCells[0]'),e.memory.string('TextCells[1]')),('abab','cdcd'));self.assertEqual((e.memory.read('Result'),e.memory.read('Count')),(1,1))
        e.memory.write('PartSensor',False);e.memory.write('Qty',99);e.step();e.memory.write('PartSensor',True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('Qty',1);e.step();self.assertIsNone(e.memory.read('Second.Work')[2]['LEN'])

    def test_static_types_permissions_shapes_literals_and_controller_scope_remain_strict(self):
        for text in ('CONCAT(TextCells,SourceB,Dest);','MID(SourceA,Qty/2,1,Dest);','DTOS(2.5,Dest);','DTOS(RealCells,Dest);','STOD(SourceA,RealDest);',
                     'FIND(SourceA,Search,1,Flags[0]);','LOWER(TextCells[99],Dest);','EQU(SourceA,Result)OTE(RunLatch);','CMP(SourceA=1)OTE(RunLatch);'):
            e=self.engine(['AFI()'+text]);self.assertTrue(e.blockers,text);self.assertFalse(e.memory.structural)
        for text in ('CONCAT(SourceA,SourceB,Dest);','LOWER(SourceA,Dest);','MID(SourceA,3,1,Dest);'):
            self.assertTrue(self.engine(['AFI()'+text],mutate=lambda root:root.find('./Controller/Tags/Tag[@Name="Dest"]').set('Constant','true')).blockers)
        def older(root):root.find('Controller').set('ProcessorType','1756-L75')
        self.assertTrue(self.engine(['AFI()CONCAT(TextCells[Index],SourceB,Dest);'],mutate=older).blockers)
        report=self.checked(['AFI()CONCAT(SourceA,SourceB,Dest);']).report()['string_operations']['operand_selection'];self.assertEqual(len(report['instructions']),18);self.assertFalse(report['native_runtime_parity'])


if __name__=='__main__':unittest.main()
