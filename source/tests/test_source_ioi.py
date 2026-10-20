"""Known source identifiers translate; unknown paths never guess operands."""
import copy
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree as ET

from logixlab.model import Project
from logixlab.native_symbols import NativeSymbols,Symbol
from logixlab.native_routines import NativeRoutines
from logixlab.native_types import NativeTypes,Type,Member
from logixlab.routine_source import decode,resolve,validate_plan,SourceError
from test_routine_source import container,xml_source


class SourceIoiTests(unittest.TestCase):
    def setUp(self):
        self.project=Project(Path(__file__).resolve().parents[1]/'samples/ConveyorDemo.L5X');sha=self.project.sha256
        self.symbols=NativeSymbols('a'*64,sha,[Symbol('',0,'RunLatch',5),Symbol('',0,'StartDelay',12),
            Symbol('',0,'SpeedSetpoint',14)],programs=[{'name':'MainProgram','instance':300}])
        names=self.project.executable_configuration.routine_names('MainProgram',source_sha256=sha)
        self.routines=NativeRoutines('a'*64,sha,[dict(program='MainProgram',name=n,program_instance=300,instance=700+i)
                                               for i,n in enumerate(names)])
        fields=(Member('Control','DINT',0,None,(),'Read/Write',True),Member('PRE','DINT',4,None,(),'Read/Write',False),
            Member('ACC','DINT',8,None,(),'Read/Write',False),Member('EN','BOOL',0,31,(),'Read/Write',False),
            Member('TT','BOOL',0,30,(),'Read/Write',False),Member('DN','BOOL',0,29,(),'Read/Write',False))
        self.types=NativeTypes('a'*64,sha,[Type('TIMER',12,fields)],{'timer':3971})

    def source(self,text):return decode(container(ET.tostring(xml_source(text=text))))
    def translate(self,text,**overrides):
        return resolve(self.source(text),self.project,overrides.get('symbols',self.symbols),self.routines,
                       overrides.get('types',self.types),'MainProgram')

    def test_scalar_member_branch_and_routine_paths_preserve_neutral_logic(self):
        target=self.routines.lookup('MainProgram','Reporting').instance
        text='[XIC(@107 5 0 0 0 0@),XIC(@107 12 0 0 0 0@.@108 3971 34046 6 0 0@)]OTE(@107 5 0 0 0 0@)JSR(@104 300 109 '+str(target)+' 0 0@,0);'
        result=self.translate(text)
        self.assertEqual(result,('[XIC(RunLatch),XIC(StartDelay.DN)]OTE(RunLatch)JSR(Reporting,0);',))
        before=copy.deepcopy((self.project.routines,self.project.initial,self.project.instruction_counts))
        validate_plan(self.source(text),result,self.project,'MainProgram')
        self.assertEqual((self.project.routines,self.project.initial,self.project.instruction_counts),before)

    def test_program_symbol_scope_is_preserved_and_unknown_programs_are_rejected(self):
        # The synthetic symbol points at an existing global name only after a
        # real source declaration in that Program; a binding alone cannot add it.
        symbols=NativeSymbols('a'*64,self.project.sha256,[Symbol('MainProgram',300,'Missing',5)],
                              programs=[{'name':'MainProgram','instance':300}])
        with self.assertRaises(SourceError):self.translate('XIC(@104 300 107 5 0 0@);',symbols=symbols)

    def test_controller_ioi_cannot_rebind_to_shadowing_program_tag(self):
        with tempfile.TemporaryDirectory() as folder:
            root=ET.parse(self.project.path).getroot()
            program=root.find('./Controller/Programs/Program')
            tags=program.find('Tags')
            if tags is None:tags=ET.SubElement(program,'Tags')
            for name in ('SpeedSetpoint','StartDelay'):
                tag=copy.deepcopy(root.find('./Controller/Tags/Tag[@Name="'+name+'"]'))
                tag.set('Name',name.swapcase());tags.append(tag)
            path=Path(folder)/'shadow.L5X';ET.ElementTree(root).write(path)
            self.project=Project(path);sha=self.project.sha256
            self.symbols=NativeSymbols('a'*64,sha,[Symbol('',0,'SpeedSetpoint',14),
                Symbol('',0,'StartDelay',12),Symbol('MainProgram',300,'sPEEDsETPOINT',14)],
                programs=[{'name':'MainProgram','instance':300}])
            self.routines=NativeRoutines('a'*64,sha,[dict(program='MainProgram',name=n,program_instance=300,instance=700+i)
                for i,n in enumerate(('MainRoutine','Reporting'))])
            self.types=NativeTypes('a'*64,sha,list(self.types.types.values()),{'timer':3971})
            before=copy.deepcopy((self.project.initial,self.project.routines))
            for text in ('MOV(1,@107 14 0 0 0 0@);',
                    'CPT(@104 300 107 14 0 0@,@107 14 0 0 0 0@+1);',
                    'CMP(@107 14 0 0 0 0@>0);',
                    'MOV(@107 12 0 0 0 0@.@108 3971 34046 2 0 0@,@104 300 107 14 0 0@);'):
                with self.subTest(text=text),self.assertRaisesRegex(SourceError,'ioi_controller_symbol_shadowed'):
                    self.translate(text)
            text='CPT(@104 300 107 14 0 0@,@104 300 107 14 0 0@+7);'
            neutral=self.translate(text)
            self.assertEqual(neutral,('CPT(sPEEDsETPOINT,sPEEDsETPOINT+7);',))
            validate_plan(self.source(text),neutral,self.project,'MainProgram')
            from logixlab.routine_source import candidate_project
            from logixlab.runtime import Engine
            candidate,_=candidate_project(self.source(text),neutral,self.project,'MainProgram')
            engine=Engine(candidate,defer_prescan=True);engine.step()
            self.assertEqual(engine.memory.read('SpeedSetpoint'),50)
            self.assertEqual(engine.memory.read('Program:MainProgram.SpeedSetpoint'),57)
            self.assertEqual((self.project.initial,self.project.routines),before)

    def test_stale_or_unbound_catalogs_and_type_handles_cannot_translate_members(self):
        for symbols in (None,NativeSymbols('b'*64,self.project.sha256,())):
            with self.assertRaises(SourceError):self.translate('NOP();',symbols=symbols)
        text='XIC(@107 12 0 0 0 0@.@108 3971 34046 6 0 0@);'
        for types in (NativeTypes('a'*64,self.project.sha256,list(self.types.types.values())),
                      NativeTypes('a'*64,'b'*64,list(self.types.types.values()),{'timer':3971})):
            with self.assertRaises(SourceError):self.translate(text,types=types)

    def test_unknown_markers_indices_hidden_members_and_indirect_paths_fail_without_substitution(self):
        for operand in ('@107 99 0 0 0 0@','@107 5 1 0 0 0@','@107 5 0 0 0 0@[1]',
            '@107 12 0 0 0 0@.@108 3972 34046 6 0 0@','@107 12 0 0 0 0@.@108 3971 1 6 0 0@',
            '@107 12 0 0 0 0@.@108 3971 34046 1 0 0@','@107 12 0 0 0 0@.@108 3971 34046 7 0 0@',
            '@107 4294967296 0 0 0 0@','@bad@'):
            with self.subTest(operand=operand),self.assertRaises(SourceError):self.translate('XIC('+operand+');')

    def test_binding_a_real_tag_does_not_imply_its_instruction_is_executable(self):
        source=self.source('XIC(@107 14 0 0 0 0@);');neutral=self.translate(source.rungs[0].text_ioi)
        self.assertEqual(neutral,('XIC(SpeedSetpoint);',))
        with self.assertRaises(SourceError):validate_plan(source,neutral,self.project,'MainProgram')
        with self.assertRaises(SourceError):validate_plan(self.source('UNKNOWN();'),('UNKNOWN();',),self.project,'MainProgram')

    def test_cpt_expression_resolves_each_source_bound_scalar_and_member(self):
        text='CPT(@107 14 0 0 0 0@,(@107 14 0 0 0 0@*2)+@107 12 0 0 0 0@.@108 3971 34046 2 0 0@);'
        neutral=self.translate(text)
        self.assertEqual(neutral,('CPT(SpeedSetpoint,(SpeedSetpoint*2)+StartDelay.PRE);',))
        validate_plan(self.source(text),neutral,self.project,'MainProgram')
        from logixlab.routine_source import candidate_project
        from logixlab.runtime import Engine
        candidate,_=candidate_project(self.source(text),neutral,self.project,'MainProgram')
        engine=Engine(candidate,defer_prescan=True);engine.step()
        self.assertEqual(engine.memory.read('SpeedSetpoint'),1100)
        self.assertEqual(self.project.initial['speedsetpoint'],50)

    def test_cpt_expression_cannot_smuggle_unbound_names_paths_or_syntax(self):
        known='@107 14 0 0 0 0@'
        for expression in (known+'+Missing',known+'+SpeedSetpoint',known+'[1]',known+'.ACC',
                known+'+@107 99 0 0 0 0@',known+'+@bad@',known+';NOP()',
                'UNKNOWN('+known+')','"'+known+'"',known+'+'+'1'*4096):
            with self.subTest(expression=expression),self.assertRaises(SourceError):
                self.translate('CPT('+known+','+expression+');')
        with self.assertRaises(SourceError):self.translate('MOV('+known+'+1,'+known+');')

    def test_cmp_resolves_numeric_and_boolean_references_with_typed_condition_validation(self):
        text='CMP((@107 14 0 0 0 0@>55)&&@107 5 0 0 0 0@)MOV(7,@107 14 0 0 0 0@);'
        neutral=self.translate(text)
        self.assertEqual(neutral,('CMP((SpeedSetpoint>55)&&RunLatch)MOV(7,SpeedSetpoint);',))
        validate_plan(self.source(text),neutral,self.project,'MainProgram')
        from logixlab.routine_source import candidate_project
        from logixlab.runtime import Engine
        candidate,_=candidate_project(self.source(text),neutral,self.project,'MainProgram')
        engine=Engine(candidate,defer_prescan=True)
        engine.memory.write('SpeedSetpoint',60);engine.step();self.assertEqual(engine.memory.read('SpeedSetpoint'),60)
        engine.memory.write('RunLatch',True);engine.step();self.assertEqual(engine.memory.read('SpeedSetpoint'),7)
        numeric=self.source('CMP(@107 14 0 0 0 0@+1);')
        with self.assertRaises(SourceError):validate_plan(numeric,self.translate(numeric.rungs[0].text_ioi),self.project,'MainProgram')
        for instruction in ('CMP(@107 14 0 0 0 0@>Missing);','CMP(@107 14 0 0 0 0@>);',
                'CPT(@107 14 0 0 0 0@,@107 14 0 0 0 0@>55);'):
            with self.subTest(instruction=instruction),self.assertRaises(SourceError):self.translate(instruction)

    def test_integer_bits_resolve_with_source_type_width_and_boolean_execution(self):
        text='XIC(@107 14 0 0 0 0@.1)OTE(@107 5 0 0 0 0@)OTL(@107 14 0 0 0 0@.31);'
        neutral=self.translate(text)
        self.assertEqual(neutral,('XIC(SpeedSetpoint.1)OTE(RunLatch)OTL(SpeedSetpoint.31);',))
        validate_plan(self.source(text),neutral,self.project,'MainProgram')
        from logixlab.routine_source import candidate_project
        from logixlab.runtime import Engine
        candidate,_=candidate_project(self.source(text),neutral,self.project,'MainProgram')
        engine=Engine(candidate,defer_prescan=True);engine.step()
        self.assertTrue(engine.memory.read('RunLatch'))
        self.assertEqual(engine.memory.read('SpeedSetpoint'),-2147483598)
        text='CMP(@107 14 0 0 0 0@.1&&@107 12 0 0 0 0@.@108 3971 34046 2 0 0@.3)OTE(@107 5 0 0 0 0@);'
        neutral=self.translate(text)
        self.assertEqual(neutral,('CMP(SpeedSetpoint.1&&StartDelay.PRE.3)OTE(RunLatch);',))
        validate_plan(self.source(text),neutral,self.project,'MainProgram')
        for operand in ('@107 14 0 0 0 0@.32','@107 14 0 0 0 0@.-1',
                '@107 14 0 0 0 0@.0.1','@107 14 0 0 0 0@.[0]',
                '@107 5 0 0 0 0@.0','@107 12 0 0 0 0@.0',
                '@107 12 0 0 0 0@.@108 3971 34046 6 0 0@.0'):
            with self.subTest(operand=operand),self.assertRaises(SourceError):self.translate('XIC('+operand+');')
            with self.subTest(expression=operand),self.assertRaises(SourceError):self.translate('CMP('+operand+');')
        target=self.routines.lookup('MainProgram','Reporting').instance
        with self.assertRaises(SourceError):self.translate('JSR(@104 300 109 '+str(target)+' 0 0@.0,0);')

    def test_static_array_indices_use_source_bounds_in_direct_and_expression_operands(self):
        with tempfile.TemporaryDirectory() as folder:
            root=ET.parse(self.project.path).getroot();tags=root.find('./Controller/Tags')
            for name,dims,entries in (('Samples','4',[('[0]',10),('[1]',20),('[2]',30),('[3]',40)]),
                    ('Grid','2,2',[('[0,0]',1),('[0,1]',2),('[1,0]',3),('[1,1]',4)])):
                tag=ET.SubElement(tags,'Tag',Name=name,TagType='Base',DataType='DINT',Dimensions=dims)
                array=ET.SubElement(ET.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='DINT',Dimensions=dims)
                for index,value in entries:ET.SubElement(array,'Element',Index=index,Value=str(value))
            path=Path(folder)/'arrays.L5X';ET.ElementTree(root).write(path)
            self.project=Project(path);sha=self.project.sha256
            self.symbols=NativeSymbols('a'*64,sha,[Symbol('',0,'SpeedSetpoint',14),Symbol('',0,'Samples',17),
                Symbol('',0,'Grid',18)],programs=[{'name':'MainProgram','instance':300}])
            self.routines=NativeRoutines('a'*64,sha,[dict(program='MainProgram',name=n,program_instance=300,instance=700+i)
                for i,n in enumerate(('MainRoutine','Reporting'))])
            self.types=NativeTypes('a'*64,sha,[])
            text='MOV(@107 17 0 0 0 0@[2],@107 14 0 0 0 0@)CPT(@107 17 0 0 0 0@[1],@107 17 0 0 0 0@[0]+@107 18 0 0 0 0@[1,1]);'
            neutral=self.translate(text)
            self.assertEqual(neutral,('MOV(Samples[2],SpeedSetpoint)CPT(Samples[1],Samples[0]+Grid[1,1]);',))
            validate_plan(self.source(text),neutral,self.project,'MainProgram')
            from logixlab.routine_source import candidate_project
            from logixlab.runtime import Engine
            candidate,_=candidate_project(self.source(text),neutral,self.project,'MainProgram')
            engine=Engine(candidate,defer_prescan=True);engine.step()
            self.assertEqual(engine.memory.read('SpeedSetpoint'),30);self.assertEqual(engine.memory.read('Samples[1]'),14)
            text='XIC(@107 17 0 0 0 0@[2].1)OTL(@107 17 0 0 0 0@[1].31);'
            neutral=self.translate(text)
            self.assertEqual(neutral,('XIC(Samples[2].1)OTL(Samples[1].31);',))
            validate_plan(self.source(text),neutral,self.project,'MainProgram')
            candidate,_=candidate_project(self.source(text),neutral,self.project,'MainProgram')
            engine=Engine(candidate,defer_prescan=True);engine.step()
            self.assertEqual(engine.memory.read('Samples[1]'),-2147483628)
            for operand in ('@107 17 0 0 0 0@[4]','@107 17 0 0 0 0@[-1]','@107 17 0 0 0 0@[SpeedSetpoint]',
                    '@107 17 0 0 0 0@[1+1]','@107 17 0 0 0 0@[1][0]','@107 17 0 0 0 0@[1,0]',
                    '@107 18 0 0 0 0@[1]','@107 18 0 0 0 0@[2,0]','@107 14 0 0 0 0@[0]'):
                with self.subTest(operand=operand),self.assertRaises(SourceError):
                    self.translate('MOV('+operand+',@107 14 0 0 0 0@);')
                with self.subTest(expression=operand),self.assertRaises(SourceError):
                    self.translate('CPT(@107 14 0 0 0 0@,'+operand+'+1);')

    def test_integer_bit_limits_follow_each_declared_width(self):
        with tempfile.TemporaryDirectory() as folder:
            root=ET.parse(self.project.path).getroot();tags=root.find('./Controller/Tags')
            widths=(('SINT',8),('INT',16),('DINT',32),('LINT',64))
            for dtype,_ in widths:
                tag=ET.SubElement(tags,'Tag',Name='Bits_'+dtype,TagType='Base',DataType=dtype)
                ET.SubElement(ET.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType=dtype,Value='3')
            path=Path(folder)/'bits.L5X';ET.ElementTree(root).write(path)
            self.project=Project(path);sha=self.project.sha256
            self.symbols=NativeSymbols('a'*64,sha,[Symbol('',0,'Bits_'+dtype,20+i) for i,(dtype,_) in enumerate(widths)],
                programs=[{'name':'MainProgram','instance':300}])
            self.routines=NativeRoutines('a'*64,sha,[dict(program='MainProgram',name=n,program_instance=300,instance=700+i)
                for i,n in enumerate(('MainRoutine','Reporting'))]);self.types=NativeTypes('a'*64,sha,[])
            from logixlab.routine_source import candidate_project
            from logixlab.runtime import Engine
            for i,(dtype,width) in enumerate(widths):
                operand='@107 '+str(20+i)+' 0 0 0 0@.'
                text='OTL('+operand+str(width-1)+');';neutral=self.translate(text)
                validate_plan(self.source(text),neutral,self.project,'MainProgram')
                candidate,_=candidate_project(self.source(text),neutral,self.project,'MainProgram')
                engine=Engine(candidate,defer_prescan=True);engine.step()
                with self.subTest(dtype=dtype):self.assertEqual(engine.memory.read('Bits_'+dtype),3-(1<<(width-1)))
                with self.subTest(dtype=dtype),self.assertRaises(SourceError):self.translate('OTL('+operand+str(width)+');')


if __name__=='__main__':unittest.main()
