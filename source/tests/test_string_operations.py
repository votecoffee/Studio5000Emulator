"""Common RLL/ST string search/editing with bounded values and write effects."""
import copy
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

from logixlab.model import ModelError, Project
from logixlab.runtime import Engine

SAMPLES = Path(__file__).resolve().parents[1] / 'samples'


def string_data(parent, text, capacity=82, dtype='STRING', member=None):
    attrs = dict(DataType=dtype)
    if member is not None: attrs['Name'] = member
    obj = E.SubElement(parent, 'StructureMember' if member is not None else 'Structure', **attrs)
    E.SubElement(obj, 'DataValueMember', Name='LEN', DataType='DINT', Value=str(len(text)))
    data = E.SubElement(obj, 'ArrayMember', Name='DATA', DataType='SINT', Dimensions=str(capacity))
    raw = text.encode('latin-1')
    for i, byte in enumerate(raw + b'\0' * (capacity - len(raw))):
        E.SubElement(data, 'Element', Index=f'[{i}]', Value=str(byte if byte < 128 else byte - 256))
    return obj


class StringOperationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def engine(self, logic, *, st=False, mutate=None):
        root = E.parse(SAMPLES / 'ConveyorDemo.L5X').getroot()
        tags = root.find('./Controller/Tags')
        for name, text in (('SourceA','ABC123ABC'),('SourceB','XY'),('Search','ABC'),('Dest','TAIL')):
            tag = E.SubElement(tags,'Tag',Name=name,DataType='STRING',TagType='Base')
            string_data(E.SubElement(tag,'Data',Format='Decorated'),text)
        for name, value in (('Start',1),('Qty',3),('Result',99),('Index',0),('Limit',2),('Count',0)):
            tag=E.SubElement(tags,'Tag',Name=name,DataType='DINT',TagType='Base')
            E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='DINT',Value=str(value))
        routine=root.find('./Controller/Programs/Program/Routines/Routine')
        routine.remove(routine.find('RLLContent'))
        routine.set('Type','ST' if st else 'RLL')
        content=E.SubElement(routine,'STContent' if st else 'RLLContent')
        for i, text in enumerate(logic.split('\n') if isinstance(logic,str) else logic):
            if st:E.SubElement(content,'Line',Number=str(i)).text=text
            else:E.SubElement(E.SubElement(content,'Rung',Number=str(i),Type='N'),'Text').text=text
        if mutate:mutate(root)
        path=Path(self.tmp.name)/'fixture.L5X'
        E.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
        return Engine(Project(path))

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    def test_find_first_next_absent_and_case_sensitive(self):
        e=self.checked(['FIND(SourceA,Search,Start,Result);'])
        for start,result in ((1,1),(2,7),(7,7),(8,0),(82,0)):
            e.memory.write('Start',start);e.step();self.assertEqual(e.memory.read('Result'),result)
        e.memory.write('Search','abc');e.step();self.assertEqual(e.memory.read('Result'),0)

    def test_find_returns_one_based_position_and_leaves_sources(self):
        e=self.checked(['FIND(SourceA,SourceB,1,Result);'])
        e.memory.write('SourceB','123');e.step()
        self.assertEqual(e.memory.read('Result'),4)
        self.assertEqual(e.memory.string('SourceA'),'ABC123ABC');self.assertEqual(e.memory.string('SourceB'),'123')

    def test_find_empty_source_or_search_faults_and_false_rung_skips(self):
        for tag in ('SourceA','Search'):
            e=self.checked(['FIND(SourceA,Search,1,Result);']);e.memory.write(tag,'')
            with self.assertRaisesRegex(ModelError,'nonempty'):e.step()
            self.assertEqual(e.memory.read('Result'),99)
        e=self.checked(['AFI()FIND(SourceA,Search,1,Result);']);e.memory.write('SourceA','');e.step()
        self.assertEqual(e.memory.read('Result'),99)

    def test_find_result_can_establish_unknown_and_reject_narrow_overflow(self):
        e=self.checked(['FIND(SourceA,Search,1,Result);']);e.memory.values['result']=None;e.step()
        self.assertEqual(e.memory.read('Result'),1)
        def narrow(root):
            root.find('./Controller/Tags/Tag[@Name="Result"]').set('DataType','SINT')
            root.find('./Controller/Tags/Tag[@Name="Result"]/Data/DataValue').set('DataType','SINT')
            tag=root.find('./Controller/Tags/Tag[@Name="SourceA"]');tag.set('DataType','LongText')
            members=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='LongText',Class='User',Family='NoFamily'),'Members')
            E.SubElement(members,'Member',Name='LEN',DataType='DINT',Dimension='0');E.SubElement(members,'Member',Name='DATA',DataType='SINT',Dimension='160')
            data=tag.find('Data');data.clear();data.set('Format','Decorated');string_data(data,'X'*129+'ABC',160,'LongText')
        e=self.checked(['FIND(SourceA,Search,1,Result);'],mutate=narrow)
        with self.assertRaisesRegex(ModelError,'overflow'):e.step()
        self.assertEqual(e.memory.read('Result'),99)

    def test_insert_front_middle_and_append(self):
        for start,expected in ((1,'XYABC123ABC'),(4,'ABCXY123ABC'),(10,'ABC123ABCXY')):
            e=self.checked([f'INSERT(SourceA,SourceB,{start},Dest);']);e.step()
            self.assertEqual(e.memory.string('Dest'),expected)
            self.assertEqual(e.memory.string('SourceA'),'ABC123ABC');self.assertEqual(e.memory.string('SourceB'),'XY')

    def test_insert_empty_source_and_empty_addition(self):
        e=self.checked(['INSERT(SourceA,SourceB,1,Dest);']);e.memory.write('SourceA','');e.step()
        self.assertEqual(e.memory.string('Dest'),'XY')
        e.memory.write('SourceB','');e.memory.write('SourceA','ABC');e.step();self.assertEqual(e.memory.string('Dest'),'ABC')

    def test_insert_in_place_and_destination_aliases_either_source(self):
        for destination in ('SourceA','SourceB'):
            e=self.checked([f'INSERT(SourceA,SourceB,4,{destination});']);e.step()
            self.assertEqual(e.memory.string(destination),'ABCXY123ABC')
        def alias(root):E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Alias',DataType='STRING',TagType='Alias',AliasFor='SourceA')
        e=self.checked(['INSERT(SourceA,SourceA,2,Alias);'],mutate=alias);e.step()
        self.assertEqual(e.memory.string('SourceA'),'AABC123ABCBC123ABC')

    def test_delete_front_middle_end_and_whole_text(self):
        for qty,start,expected in ((3,1,'123ABC'),(3,4,'ABCABC'),(3,7,'ABC123'),(9,1,'')):
            e=self.checked([f'DELETE(SourceA,{qty},{start},Dest);']);e.step()
            self.assertEqual(e.memory.string('Dest'),expected);self.assertEqual(e.memory.string('SourceA'),'ABC123ABC')
        e=self.checked(['DELETE(SourceA,Qty,Start,SourceA);']);e.step();self.assertEqual(e.memory.string('SourceA'),'123ABC')

    def test_string_writes_preserve_unused_destination_bytes(self):
        e=self.checked(['DELETE(SourceA,3,1,Dest);']);e.memory.write('Dest','abcdefghijklmnop');e.step()
        self.assertEqual(e.memory.string('Dest'),'123ABC')
        self.assertEqual(e.memory.read('Dest.DATA[6]'),ord('g'))

    def test_string_writes_establish_unknown_active_destination(self):
        for instruction in ('INSERT(SourceA,SourceB,4,Dest);','DELETE(SourceA,3,1,Dest);'):
            e=self.checked([instruction]);e.memory.values['dest']['LEN']=None;e.memory.values['dest']['DATA'][0]=None
            e.step();self.assertTrue(e.memory.string('Dest'))

    def test_false_rungs_and_prescan_retain_outputs_and_rung_out(self):
        e=self.checked(['AFI()INSERT(SourceA,SourceB,0,Dest)OTE(RunLatch);',
                        'AFI()DELETE(SourceA,0,0,Dest);','AFI()FIND(SourceA,Search,0,Result);'])
        self.assertEqual(e.memory.string('Dest'),'TAIL');self.assertEqual(e.memory.read('Result'),99)
        e.step();self.assertEqual(e.memory.string('Dest'),'TAIL');self.assertFalse(e.memory.read('RunLatch'))
        e=self.checked(['INSERT(SourceA,SourceB,1,Dest)OTE(RunLatch);']);e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_single_byte_nul_and_high_bytes_are_not_c_strings(self):
        e=self.checked(['FIND(SourceA,Search,1,Result);','INSERT(SourceA,SourceB,2,Dest);'])
        e.memory.write('SourceA','A\0\xffZ');e.memory.write('Search','\0\xff');e.memory.write('SourceB','\x80')
        e.step();self.assertEqual(e.memory.read('Result'),2);self.assertEqual(e.memory.string('Dest'),'A\x80\0\xffZ')

    def test_capacity_overflow_rolls_back_previous_data_and_scheduler(self):
        e=self.checked(['MOV(77,SpeedCommand);','INSERT(SourceA,SourceB,1,Dest);'])
        e.memory.write('SourceA','A'*82);before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'capacity'):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual(e.scheduler_description()['tasks'][0]['executions'],0)
        self.assertEqual((e.time_ms,e.scan_count),(0,0))

    def test_ranges_rechecked_on_execution_and_unknown_data_not_zeroed(self):
        for instruction,value in (('FIND(SourceA,Search,Start,Result);',0),('FIND(SourceA,Search,Start,Result);',83),
                                  ('INSERT(SourceA,SourceB,Start,Dest);',11),('DELETE(SourceA,Qty,Start,Dest);',8)):
            e=self.checked([instruction]);e.memory.write('Start',value)
            with self.assertRaises(ModelError):e.step()
        for quantity in (0,-1,10):
            e=self.checked(['DELETE(SourceA,Qty,1,Dest);']);e.memory.write('Qty',quantity)
            with self.assertRaises(ModelError):e.step()
        e=self.checked(['DELETE(SourceA,3,1,Dest);']);e.memory.values['sourcea']['DATA'][0]=None
        with self.assertRaisesRegex(ModelError,'unknown'):e.step()
        self.assertIsNone(e.memory.values['sourcea']['DATA'][0])

    def test_invalid_source_len_and_unknown_position_fault_without_outputs(self):
        for length in (-1,83,None):
            e=self.checked(['FIND(SourceA,Search,Start,Result);']);e.memory.values['sourcea']['LEN']=length
            with self.assertRaisesRegex(ModelError,'LEN'):e.step()
            self.assertEqual(e.memory.read('Result'),99)
        e=self.checked(['INSERT(SourceA,SourceB,Start,Dest);']);e.memory.values['start']=None
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(e.memory.string('Dest'),'TAIL')

    def test_position_quantity_and_result_narrow_integer_types(self):
        for dtype in ('SINT','INT','DINT'):
            def narrow(root):
                for name in ('Start','Qty','Result'):
                    tag=root.find(f'./Controller/Tags/Tag[@Name="{name}"]');tag.set('DataType',dtype);tag.find('Data/DataValue').set('DataType',dtype)
            e=self.checked(['FIND(SourceA,Search,Start,Result);','DELETE(SourceA,Qty,Start,Dest);'],mutate=narrow)
            e.step();self.assertEqual(e.memory.read('Result'),1);self.assertEqual(e.memory.string('Dest'),'123ABC')

    def test_rejects_wrong_types_constants_literals_and_bad_arities(self):
        for text in ('FIND(SourceA,Search,TRUE,Result);','FIND(SourceA,Search,1.5,Result);',
                     'FIND(SourceA,Search,2147483648,Result);','FIND(SourceA,Search,1,StartPB);',
                     'FIND(S:FS,Search,1,Result);','FIND(SourceA,Search,S:FS,Result);',
                     'INSERT(SourceA,SourceB,1,Result);','INSERT(SourceA,SourceB,1,SourceA.DATA);',
                     'DELETE(SourceA,TRUE,1,Dest);','DELETE(SourceA,3,1,Result);','FIND(SourceA,Search,Result);'):
            self.assertTrue(self.engine([text]).blockers,text)
        for dtype in ('REAL','LINT','UDINT','BOOL'):
            def change(root):
                tag=root.find('./Controller/Tags/Tag[@Name="Start"]');tag.set('DataType',dtype);tag.find('Data/DataValue').set('DataType',dtype)
            self.assertTrue(self.engine(['FIND(SourceA,Search,Start,Result);'],mutate=change).blockers)
        for instruction,tag in (('FIND(SourceA,Search,1,Result);','Result'),('INSERT(SourceA,SourceB,1,Dest);','Dest'),('DELETE(SourceA,1,1,Dest);','Dest')):
            def constant(root):root.find(f'./Controller/Tags/Tag[@Name="{tag}"]').set('Constant','true')
            self.assertTrue(self.engine([instruction],mutate=constant).blockers)

    def test_st_calls_execute_after_assignments_without_placeholder_range_faults(self):
        e=self.checked('Start := 4; Qty := 3;\nINSERT(SourceA,SourceB,Start,Dest);\nFIND(Dest,SourceB,1,Result);\nDELETE(Dest,Qty,Start,Dest);',st=True)
        e.step();self.assertEqual(e.memory.read('Result'),4);self.assertEqual(e.memory.string('Dest'),'ABC23ABC')
        self.assertTrue(any(t.get('language')=='ST' for t in e.trace))

    def test_st_false_branch_does_not_execute_but_invalid_types_still_block(self):
        e=self.checked('IF FALSE THEN FIND(SourceA,Search,0,Result); INSERT(SourceA,SourceB,0,Dest); DELETE(SourceA,0,0,Dest); END_IF;',st=True)
        e.step();self.assertEqual(e.memory.read('Result'),99);self.assertEqual(e.memory.string('Dest'),'TAIL')
        self.assertTrue(self.engine('IF FALSE THEN FIND(SourceA,Search,TRUE,Result); END_IF;',st=True).blockers)

    def test_st_for_bounds_cannot_be_modified_by_find_result(self):
        for result in ('Limit','Start'):
            e=self.engine(f'FOR Index := 0 TO Limit BY Start DO FIND(SourceA,Search,1,{result}); END_FOR;',st=True)
            self.assertTrue(e.blockers)

    def test_st_for_bound_string_member_cannot_be_modified_by_insert_delete(self):
        for statement in ('INSERT(SourceA,SourceB,1,Dest);','DELETE(SourceA,1,1,Dest);'):
            self.assertTrue(self.engine('FOR Index := 0 TO Dest.LEN DO '+statement+' END_FOR;',st=True).blockers)

    def test_st_late_string_failure_rolls_back_earlier_writes(self):
        e=self.checked('SpeedCommand:=77; INSERT(SourceA,SourceB,1,Dest); DELETE(Dest,99,1,Dest);',st=True)
        before=copy.deepcopy(e.memory.values)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(e.memory.values,before)

    def test_report_scope_keeps_native_faults_and_special_cases_unqualified(self):
        e=self.checked(['FIND(SourceA,Search,1,Result);']);report=e.report()['string_operations']
        self.assertEqual(report['instructions'],['DELETE','FIND','INSERT']);self.assertEqual(report['languages'],['RLL','ST'])
        self.assertIn('Native minor faults and math/status parity',report['remaining'])

    @staticmethod
    def custom_strings(root):
        c=root.find('Controller');types=c.find('DataTypes');tags=c.find('Tags')
        members=E.SubElement(E.SubElement(types,'DataType',Name='UserText',Class='User',Family='NoFamily'),'Members')
        E.SubElement(members,'Member',Name='LEN',DataType='DINT',Dimension='0')
        E.SubElement(members,'Member',Name='DATA',DataType='SINT',Dimension='16')
        members=E.SubElement(E.SubElement(types,'DataType',Name='TextRecord',Class='User',Family='NoFamily'),'Members')
        E.SubElement(members,'Member',Name='Text',DataType='UserText',Dimension='0')
        tag=E.SubElement(tags,'Tag',Name='Texts',DataType='UserText',TagType='Base',Dimensions='2')
        array=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='UserText',Dimensions='2')
        for i,text in enumerate(('ABCD','zz')):string_data(E.SubElement(array,'Element',Index=f'[{i}]'),text,16,'UserText')
        tag=E.SubElement(tags,'Tag',Name='Record',DataType='TextRecord',TagType='Base')
        obj=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='TextRecord')
        string_data(obj,'old',16,'UserText',member='Text')
        E.SubElement(tags,'Tag',Name='Alias',DataType='UserText',TagType='Alias',AliasFor='Record.Text')

    def test_custom_strings_array_elements_udt_members_aliases_and_indirect_index(self):
        rungs=['INSERT(Texts[Index],SourceB,3,Record.Text);','FIND(Alias,SourceB,1,Result);','DELETE(Alias,2,3,Texts[1]);']
        for st in (False,True):
            e=self.checked(rungs,st=st,mutate=self.custom_strings);e.step()
            self.assertEqual(e.memory.string('Record.Text'),'ABXYCD')
            self.assertEqual(e.memory.read('Result'),3);self.assertEqual(e.memory.string('Texts[1]'),'ABCD')
        for rung in ('FIND(Texts,Search,1,Result);','INSERT(SourceA,SourceB,1,Texts);'):
            self.assertTrue(self.engine([rung],mutate=self.custom_strings).blockers)

    def test_custom_capacity_is_enforced_and_unrepresented_tail_remains_unknown(self):
        e=self.checked(['INSERT(SourceA,SourceB,1,Record.Text);'],mutate=self.custom_strings)
        e.memory.write('SourceA','A'*15)
        with self.assertRaisesRegex(ModelError,'capacity'):e.step()
        self.assertEqual(e.memory.string('Record.Text'),'old')
        e=self.checked(['DELETE(SourceA,3,1,Dest);'])
        e.memory.values['sourcea']['DATA'][9:]=[None]*73
        e.memory.values['dest']['DATA'][10:]=[None]*72
        e.step();self.assertEqual(e.memory.string('Dest'),'123ABC')
        self.assertIsNone(e.memory.values['sourcea']['DATA'][9]);self.assertIsNone(e.memory.values['dest']['DATA'][10])

    def test_full_source_append_beyond_capacity_and_invalid_indirect_index_fault(self):
        e=self.checked(['INSERT(SourceA,SourceB,Start,Dest);'])
        e.memory.write('SourceA','A'*82);e.memory.write('Start',83)
        with self.assertRaisesRegex(ModelError,'DATA capacity'):e.step()
        e=self.checked(['FIND(Texts[Index],Search,1,Result);'],mutate=self.custom_strings)
        e.memory.write('Index',2)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(e.memory.read('Result'),99)

    def test_aoi_string_inout_and_scalar_result_in_rll_and_st(self):
        for st in (False,True):
            def aoi(root):
                c=root.find('Controller')
                definition=E.SubElement(c.find('AddOnInstructionDefinitions'),'AddOnInstructionDefinition',Name='TextEdit',Class='Standard',ExecutePrescan='false',ExecutePostscan='false',ExecuteEnableInFalse='false')
                params=E.SubElement(definition,'Parameters')
                for name,dtype,usage,required in (('EnableIn','BOOL','Input','false'),('EnableOut','BOOL','Output','false'),
                                               ('Buffer','STRING','InOut','true'),('Position','DINT','Input','true'),('Match','DINT','Output','true')):
                    E.SubElement(params,'Parameter',Name=name,DataType=dtype,Usage=usage,Required=required,Visible=required,TagType='Base')
                E.SubElement(definition,'LocalTags')
                routine=E.SubElement(E.SubElement(definition,'Routines'),'Routine',Name='Logic',Type='ST' if st else 'RLL')
                content=E.SubElement(routine,'STContent' if st else 'RLLContent')
                for i,text in enumerate(('FIND(Buffer,Buffer,1,Match);','DELETE(Buffer,1,Position,Buffer);')):
                    if st:E.SubElement(content,'Line',Number=str(i)).text=text
                    else:E.SubElement(E.SubElement(content,'Rung',Number=str(i),Type='N'),'Text').text=text
                tag=E.SubElement(c.find('Tags'),'Tag',Name='Instance',DataType='TextEdit',TagType='Base')
                obj=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='TextEdit')
                for name,dtype,value in (('EnableIn','BOOL',0),('EnableOut','BOOL',0),('Position','DINT',1),('Match','DINT',0)):
                    E.SubElement(obj,'DataValueMember',Name=name,DataType=dtype,Value=str(value))
            e=self.checked(['TextEdit(Instance,SourceA,Start,Result);'],mutate=aoi)
            e.step();self.assertEqual(e.memory.string('SourceA'),'BC123ABC');self.assertEqual(e.memory.read('Result'),1)

    def test_bundled_string_lab_combines_rll_st_and_custom_capacity(self):
        from logixlab.server import SAMPLES as names
        self.assertIn('StringLab',names)
        e=Engine(Project(SAMPLES/'StringLab.L5X'));self.assertEqual(e.blockers,[]);e.step()
        self.assertEqual(e.memory.read('Location'),10);self.assertEqual(e.memory.read('StPosition'),10)
        self.assertEqual(e.memory.read('MissingPos'),0);self.assertTrue(e.memory.read('AllOK'))
        self.assertEqual(e.memory.string('RllEdited'),'PART=ABC;<OK>STATE=IDLE')
        self.assertEqual(e.memory.string('Cleaned'),e.memory.string('SourceText'))
        self.assertEqual(e.memory.string('StEdited'),e.memory.string('SourceText'))
        self.assertEqual(e.project.string_capacity('LabText32'),32)


if __name__=='__main__':unittest.main()
