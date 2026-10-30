"""ASCII case, decimal/REAL exchange, typed calls and whole-advance rollback."""
import copy
import math
import random
import struct
import unittest
from xml.etree import ElementTree as E

import test_string_operations as fixtures
from logixlab.model import ModelError, coerce


class StringConversionTests(unittest.TestCase):
    setUp=fixtures.StringOperationTests.setUp
    checked=fixtures.StringOperationTests.checked

    def engine(self,logic,*,st=False,mutate=None):
        def extra(root):
            for name,value in (('RealSource',15.3001),('RealDest',99.0)):
                tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name=name,DataType='REAL',TagType='Base')
                E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='REAL',Value=str(value))
            if mutate:mutate(root)
        return fixtures.StringOperationTests.engine(self,logic,st=st,mutate=extra)

    def test_ascii_case_conversion_preserves_nonletters_and_other_bytes(self):
        text='AzZ09 -_!\0\xc0\xdf\xe9\xff'
        for name,expected in (('LOWER','azz09 -_!\0\xc0\xdf\xe9\xff'),('UPPER','AZZ09 -_!\0\xc0\xdf\xe9\xff')):
            for st in (False,True):
                e=self.checked([f'{name}(SourceA,Dest);'],st=st);e.memory.write('SourceA',text);e.step()
                self.assertEqual(e.memory.string('Dest'),expected);self.assertEqual(e.memory.string('SourceA'),text)
                self.assertEqual(e.memory.read('Dest.LEN'),len(text))

    def test_empty_case_conversion_sets_length_zero_and_preserves_tail(self):
        for name in ('LOWER','UPPER'):
            e=self.checked([f'{name}(SourceA,Dest);']);e.memory.write('SourceA','');e.step()
            self.assertEqual(e.memory.string('Dest'),'');self.assertEqual(e.memory.read('Dest.DATA[0]'),ord('T'))

    def test_in_place_and_alias_case_conversions_snapshot_source(self):
        def alias(root):E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Alias',DataType='STRING',TagType='Alias',AliasFor='SourceA')
        e=self.checked(['LOWER(SourceA,Alias);','UPPER(Alias,SourceA);'],mutate=alias);e.step()
        self.assertEqual(e.memory.string('SourceA'),'ABC123ABC')

    def test_output_overwrites_unknown_active_bytes_and_keeps_unused_bytes(self):
        e=self.checked(['LOWER(SourceA,Dest);']);e.memory.values['dest']['LEN']=None;e.memory.values['dest']['DATA'][0]=None
        e.memory.values['dest']['DATA'][20]=None;e.step()
        self.assertEqual(e.memory.string('Dest'),'abc123abc');self.assertIsNone(e.memory.values['dest']['DATA'][20])

    def test_false_rung_and_prescan_retain_all_outputs_and_rung_power(self):
        e=self.checked(['AFI()LOWER(SourceA,Dest);','AFI()UPPER(SourceA,SourceB);',
                        'AFI()STOR(SourceA,RealDest);','AFI()RTOS(RealSource,Search);'])
        before=copy.deepcopy(e.memory.values);e.memory.values['sourcea']['LEN']=None;before=copy.deepcopy(e.memory.values)
        e.step();self.assertEqual(e.memory.values,before)
        e=self.checked(['LOWER(SourceA,Dest)OTE(RunLatch);']);e.step();self.assertTrue(e.memory.read('RunLatch'))
        e=self.checked('IF FALSE THEN STOR(SourceA,RealDest); RTOS(RealSource,Dest); END_IF;',st=True)
        e.memory.write('SourceA','invalid');e.step();self.assertEqual(e.memory.read('RealDest'),99.0);self.assertEqual(e.memory.string('Dest'),'TAIL')

    def test_stor_first_decimal_run_with_sign_fraction_prefix_and_delimiters(self):
        for source,expected in (('WEIGHT=-12.5 kg / 99',-12.5),('abc +12.25/34',12.25),('\0\x80-.75 rest',-.75),
                                ('+.125',.125),('12.',12.0),('1,234.5',1.0),('A=428.259;B=7',428.259),('000.50',.5)):
            for st in (False,True):
                e=self.checked(['STOR(SourceA,RealDest);'],st=st);e.memory.write('SourceA',source);e.step()
                self.assertEqual(e.memory.read('RealDest'),coerce(expected,'REAL'))

    def test_stor_float32_rounding_matches_the_saved_binary_value(self):
        e=self.checked(['STOR(SourceA,RealDest);']);e.memory.write('SourceA','15.3001');e.step()
        self.assertEqual(e.memory.read('RealDest'),15.300100326538086)

    def test_stor_establishes_unknown_destination(self):
        e=self.checked(['STOR(SourceA,RealDest);']);e.memory.values['realdest']=None;e.step()
        self.assertEqual(e.memory.read('RealDest'),123.0)

    def test_stor_no_digits_malformed_and_scientific_input_fail_explicitly(self):
        for source in ('','abc','-','.', '--12.5','1.2.3','1.25e3','1.25E-3'):
            e=self.checked(['STOR(SourceA,RealDest);']);e.memory.write('SourceA',source);before=copy.deepcopy(e.memory.values)
            with self.assertRaises(ModelError):e.step()
            self.assertEqual(e.memory.values,before)

    def test_stor_overflow_rolls_back_and_underflow_uses_float32_rounding(self):
        e=self.checked(['STOR(SourceA,RealDest);']);e.memory.write('SourceA','9'*40);before=copy.deepcopy(e.memory.values)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(e.memory.values,before)
        e=self.checked(['STOR(SourceA,RealDest);']);e.memory.write('SourceA','0.'+'0'*60+'1');e.step()
        self.assertEqual(e.memory.read('RealDest'),0.0)

    def test_rtos_fixed_nine_digit_profile_matches_reference_example(self):
        e=self.checked(['RTOS(RealSource,Dest);']);e.step();self.assertEqual(e.memory.string('Dest'),'15.3001003')
        for value,text in ((2.75,'2.75'),(-2.75,'-2.75'),(0.0,'0'),(-0.0,'-0'),(100.0,'100')):
            e.memory.write('RealSource',value);e.step();self.assertEqual(e.memory.string('Dest'),text)

    def test_rtos_expands_exponents_to_fixed_decimal_without_locale(self):
        e=self.checked(['RTOS(RealSource,Dest);','STOR(Dest,RealDest);'])
        for value in (1e20,1e-20,3.4028234663852886e38,1.401298464324817e-45,-1.401298464324817e-45):
            e.memory.write('RealSource',value);e.step();text=e.memory.string('Dest')
            self.assertNotIn('e',text.lower());self.assertNotIn(',',text)
            self.assertEqual(struct.pack('<f',e.memory.read('RealDest')),struct.pack('<f',e.memory.read('RealSource')))

    def test_finite_binary32_round_trip_property_across_exponent_range(self):
        e=self.checked(['RTOS(RealSource,Dest);','STOR(Dest,RealDest);']);rng=random.Random(648)
        words=[0,0x80000000,1,0x80000001,0x7f7fffff,0xff7fffff]+[rng.getrandbits(32) for _ in range(256)]
        for word in words:
            value=struct.unpack('<f',struct.pack('<I',word))[0]
            if not math.isfinite(value):continue
            e.memory.write('RealSource',value);e.step()
            self.assertEqual(struct.pack('<f',e.memory.read('RealDest')),struct.pack('<I',word))

    def test_rtos_unknown_nonfinite_source_and_inactive_data_fail_without_output(self):
        for value in (None,float('inf'),float('nan')):
            e=self.checked(['RTOS(RealSource,Dest);']);e.memory.values['realsource']=value
            with self.assertRaises(ModelError):e.step()
            self.assertEqual(e.memory.string('Dest'),'TAIL')

    def test_invalid_source_len_or_active_bytes_fault_and_inactive_tail_is_not_read(self):
        for name in ('LOWER','UPPER','STOR'):
            for length in (-1,83,None):
                e=self.checked([f'{name}(SourceA,{"RealDest" if name=="STOR" else "Dest"});']);e.memory.values['sourcea']['LEN']=length
                with self.assertRaises(ModelError):e.step()
            e=self.checked([f'{name}(SourceA,{"RealDest" if name=="STOR" else "Dest"});']);e.memory.values['sourcea']['DATA'][0]=None
            with self.assertRaisesRegex(ModelError,'unknown'):e.step()
            e=self.checked([f'{name}(SourceA,{"RealDest" if name=="STOR" else "Dest"});']);e.memory.values['sourcea']['DATA'][20]=None;e.step()

    def test_custom_string_elements_udt_members_and_aliases(self):
        for st in (False,True):
            e=self.checked(['LOWER(Texts[Index],Alias);','UPPER(Alias,Texts[1]);','RTOS(RealSource,Alias);','STOR(Alias,RealDest);'],
                           st=st,mutate=fixtures.StringOperationTests.custom_strings)
            e.step();self.assertEqual(e.memory.string('Texts[1]'),'ABCD');self.assertEqual(e.memory.string('Record.Text'),'15.3001003')
            self.assertEqual(e.memory.read('RealDest'),e.memory.read('RealSource'))

    def test_user_string_capacity_failure_rolls_back_earlier_numeric_and_text_writes(self):
        for name in ('LOWER','UPPER','RTOS'):
            e=self.checked(['MOV(77,SpeedCommand);',f'{name}({"RealSource" if name=="RTOS" else "SourceA"},Record.Text);'],
                           mutate=fixtures.StringOperationTests.custom_strings)
            if name=='RTOS':e.memory.write('RealSource',1e30)
            else:e.memory.write('SourceA','A'*17)
            before=copy.deepcopy(e.memory.values)
            with self.assertRaisesRegex(ModelError,'capacity'):e.step()
            self.assertEqual(e.memory.values,before);self.assertEqual((e.time_ms,e.scan_count),(0,0))
            self.assertEqual(e.scheduler_description()['tasks'][0]['executions'],0)

    def test_real_aliases_and_constant_sources_are_supported(self):
        def aliases(root):
            tags=root.find('./Controller/Tags');tags.find('Tag[@Name="SourceA"]').set('Constant','true')
            for name,target in (('RealAlias','RealSource'),('DestAlias','RealDest')):
                E.SubElement(tags,'Tag',Name=name,DataType='REAL',TagType='Alias',AliasFor=target)
        e=self.checked(['RTOS(RealAlias,Dest);','STOR(SourceA,DestAlias);'],mutate=aliases);e.step()
        self.assertEqual(e.memory.string('Dest'),'15.3001003');self.assertEqual(e.memory.read('RealDest'),123.0)

    def test_st_executes_calls_after_assignments_and_late_failure_rolls_back(self):
        e=self.checked("SourceA := 'value=-12.5'; STOR(SourceA,RealDest); RTOS(RealDest,Dest); LOWER(Dest,SourceB);",st=True);e.step()
        self.assertEqual(e.memory.string('Dest'),'-12.5');self.assertEqual(e.memory.read('RealDest'),-12.5)
        e=self.checked("SpeedCommand := 77; LOWER(SourceA,Dest); RTOS(RealSource,SourceB); SourceA := 'invalid'; STOR(SourceA,RealDest);",st=True)
        before=copy.deepcopy(e.memory.values)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(e.memory.values,before)

    def test_st_for_dependency_contract_includes_all_four_destinations(self):
        for name in ('LOWER','UPPER','RTOS'):
            source='RealSource' if name=='RTOS' else 'SourceA'
            e=self.engine(f'FOR Index := 0 TO Dest.LEN DO {name}({source},Dest); END_FOR;',st=True)
            self.assertTrue(e.blockers);self.assertIn('bounds',str(e.blockers))
        e=self.engine('FOR Index := 0 TO TRUNC(RealDest) DO STOR(SourceA,RealDest); END_FOR;',st=True)
        self.assertTrue(e.blockers);self.assertIn('bounds',str(e.blockers))
        e=self.checked('FOR Index := 0 TO Limit DO STOR(SourceA,RealDest); LOWER(SourceA,Dest); END_FOR;',st=True);e.step()
        self.assertEqual(e.memory.read('RealDest'),123.0);self.assertEqual(e.memory.string('Dest'),'abc123abc')

    def test_wrong_types_constants_literals_and_arities_remain_blocked(self):
        for text in ('LOWER(SourceA,RealDest);','UPPER(RealSource,Dest);','STOR(SourceA,Result);','RTOS(Result,Dest);',
                     'RTOS(15.3,Dest);','STOR(SourceA,RealDest,Result);','LOWER(SourceA);','LOWER(SourceA,SourceA.DATA);'):
            self.assertTrue(self.engine([text]).blockers,text)
        for name,dest in (('LOWER','Dest'),('UPPER','Dest'),('STOR','RealDest'),('RTOS','Dest')):
            def constant(root):root.find(f'./Controller/Tags/Tag[@Name="{dest}"]').set('Constant','true')
            source='RealSource' if name=='RTOS' else 'SourceA'
            self.assertTrue(self.engine([f'{name}({source},{dest});'],mutate=constant).blockers)
        for dtype in ('LINT','LREAL','DINT','BOOL'):
            def dtype_change(root):
                tag=root.find('./Controller/Tags/Tag[@Name="RealSource"]');tag.set('DataType',dtype);tag.find('Data/DataValue').set('DataType',dtype)
            self.assertTrue(self.engine(['RTOS(RealSource,Dest);'],mutate=dtype_change).blockers)

    def test_profile_and_report_keep_native_formatting_and_status_unqualified(self):
        def old(root):root.find('Controller').set('ProcessorType','1756-L75')
        self.assertTrue(self.engine(['LOWER(SourceA,Dest);'],mutate=old).blockers)
        report=self.checked(['LOWER(SourceA,Dest);']).report()['string_conversions']
        self.assertEqual(report['instructions'],['LOWER','RTOS','STOR','UPPER']);self.assertEqual(report['languages'],['RLL','ST'])
        for name in ('native_formatting_parity','native_math_status','native_fault_classification'):self.assertFalse(report[name])

    def test_aoi_string_inout_real_input_and_real_output_bindings(self):
        for st in (False,True):
            def aoi(root):
                c=root.find('Controller')
                definition=E.SubElement(c.find('AddOnInstructionDefinitions'),'AddOnInstructionDefinition',Name='ConvertText',Class='Standard',ExecutePrescan='false',ExecutePostscan='false',ExecuteEnableInFalse='false')
                params=E.SubElement(definition,'Parameters')
                for name,dtype,usage,required in (('EnableIn','BOOL','Input','false'),('EnableOut','BOOL','Output','false'),
                                               ('Buffer','STRING','InOut','true'),('Value','REAL','Input','true'),('Result','REAL','Output','true')):
                    E.SubElement(params,'Parameter',Name=name,DataType=dtype,Usage=usage,Required=required,Visible=required,TagType='Base')
                E.SubElement(definition,'LocalTags')
                routine=E.SubElement(E.SubElement(definition,'Routines'),'Routine',Name='Logic',Type='ST' if st else 'RLL')
                content=E.SubElement(routine,'STContent' if st else 'RLLContent')
                for i,text in enumerate(('LOWER(Buffer,Buffer);','UPPER(Buffer,Buffer);','RTOS(Value,Buffer);','STOR(Buffer,Result);')):
                    if st:E.SubElement(content,'Line',Number=str(i)).text=text
                    else:E.SubElement(E.SubElement(content,'Rung',Number=str(i),Type='N'),'Text').text=text
                tag=E.SubElement(c.find('Tags'),'Tag',Name='Instance',DataType='ConvertText',TagType='Base')
                obj=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='ConvertText')
                for name,dtype in (('EnableIn','BOOL'),('EnableOut','BOOL'),('Value','REAL'),('Result','REAL')):
                    E.SubElement(obj,'DataValueMember',Name=name,DataType=dtype,Value='0')
            e=self.checked(['ConvertText(Instance,SourceA,RealSource,RealDest);'],mutate=aoi);e.step()
            self.assertEqual(e.memory.string('SourceA'),'15.3001003');self.assertEqual(e.memory.read('RealDest'),e.memory.read('RealSource'))


    def test_bundled_string_lab_conversion_examples(self):
        from pathlib import Path
        from logixlab.model import Project
        from logixlab.runtime import Engine
        e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/StringLab.L5X'));self.assertEqual(e.blockers,[]);e.step()
        for prefix in ('','St'):
            self.assertEqual(e.memory.string(prefix+'Lowered'),'abc 09')
            self.assertEqual(e.memory.string(prefix+'Uppered'),'ABC 09')
            self.assertEqual(e.memory.read(prefix+'ParsedReal'),-12.5)
            self.assertEqual(e.memory.string(prefix+'FormattedReal'),'15.3001003')


if __name__=='__main__':unittest.main()
