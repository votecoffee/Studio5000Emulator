"""Exact typed AOI Inputs with existing copied-parameter lifecycle and rollback."""
import copy
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_addons as fixtures
from logixlab.model import ModelError

SAMPLE=Path(__file__).resolve().parents[1]/'samples/AOIConstantsLab.L5X'
VALUES={'Signed':9007199254740993,'Unsigned':4294967295,'Largest':18446744073709551615,'Precise':1.0000000000000002}
LITERALS=dict(zip(VALUES,('9007199254740993L','4294967295U','18446744073709551615UL','1.0000000000000002L')))


class AOILiteralTests(unittest.TestCase):
    setUp=fixtures.AddOnTests.setUp
    engine=fixtures.AddOnTests.engine

    def typed(self,values=None,*,mutate=None,logic=None,tail=(),checked=True):
        self.root=E.parse(SAMPLE).getroot();c=self.root.find('Controller')
        args=['TypedInputs',*(LITERALS|dict(values or {})).values(),*(name+'Result' for name in VALUES)]
        content=c.find('./Programs/Program/Routines/Routine/RLLContent');content.clear()
        for i,text in enumerate(['XIC(Enabled)LabTypedInputs('+','.join(args)+');',*tail]):
            E.SubElement(E.SubElement(content,'Rung',Number=str(i),Type='N'),'Text').text=text
        for name,value in (('TestDivisor',1),('TestGuard',0)):
            tag=E.SubElement(c.find('Tags'),'Tag',Name=name,DataType='DINT',TagType='Base')
            E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='DINT',Value=str(value))
        if logic is not None:
            c.find('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text').text=logic
        if mutate:mutate(self.root)
        e=self.engine()
        if checked:self.assertEqual(e.blockers,[])
        return e

    def snapshot(self,e):
        return copy.deepcopy((e.memory.values,e.memory.frames,e.addons.instances,e.last_timer,
                              e.scan_count,e.time_ms,e.trace,e.scheduler_description()))

    def enabled(self,e):e.memory.write('Enabled',True);e.step()

    def test_prescan_copies_all_typed_inputs_without_running_logic(self):
        e=self.typed()
        for name,value in VALUES.items():
            self.assertEqual(e.memory.read('TypedInputs.'+name),value)
            self.assertEqual(e.memory.read(name+'Result'),0)
        self.assertFalse(e.memory.read('TypedInputs.EnableIn'));self.assertFalse(e.memory.read('TypedInputs.EnableOut'))

    def test_enabled_logic_copies_exact_inputs_and_outputs(self):
        e=self.typed();self.enabled(e)
        for name,value in VALUES.items():self.assertEqual(e.memory.read(name+'Result'),value)
        self.assertNotEqual(e.memory.read('PreciseResult'),1.0)
        self.assertIs(type(e.memory.read('LargestResult')),int)

    def test_false_calls_refresh_inputs_but_retain_external_outputs(self):
        e=self.typed();e.memory.write('TypedInputs.Signed',-7);e.memory.write('SignedResult',-9);e.step()
        self.assertEqual(e.memory.read('TypedInputs.Signed'),VALUES['Signed'])
        self.assertEqual(e.memory.read('SignedResult'),-9);self.assertFalse(e.memory.read('TypedInputs.EnableOut'))

    def test_enableinfalse_routine_uses_existing_output_copy_rules(self):
        def false_mode(root):
            d=root.find('.//AddOnInstructionDefinition');d.set('ExecuteEnableInFalse','true')
            routine=E.SubElement(d.find('Routines'),'Routine',Name='EnableInFalse',Type='RLL')
            E.SubElement(E.SubElement(E.SubElement(routine,'RLLContent'),'Rung',Number='0',Type='N'),'Text').text='MOV(-1L,SignedOut);'
        e=self.typed(mutate=false_mode);e.step()
        self.assertEqual(e.memory.read('SignedResult'),-1);self.assertFalse(e.memory.read('TypedInputs.EnableOut'))

    def test_input_parameter_writes_do_not_change_the_configured_constant(self):
        e=self.typed(logic='MOV(Signed,SignedOut)MOV(7L,Signed);');self.enabled(e)
        self.assertEqual(e.memory.read('SignedResult'),VALUES['Signed']);self.assertEqual(e.memory.read('TypedInputs.Signed'),7)
        e.step();self.assertEqual(e.memory.read('SignedResult'),VALUES['Signed'])

    def test_signs_suffixes_and_declared_ranges(self):
        e=self.typed({'Signed':'-9223372036854775808l','Unsigned':'+4294967295u','Largest':'18446744073709551615uL','Precise':'-1.5e2l'})
        self.enabled(e)
        for name,value in {'Signed':-(1<<63),'Unsigned':(1<<32)-1,'Largest':(1<<64)-1,'Precise':-150.0}.items():
            self.assertEqual(e.memory.read(name+'Result'),value)

    def test_invalid_or_mismatched_typed_values_block_while_false(self):
        for name,text in [('Signed','9223372036854775808L'),('Unsigned','-1U'),
                          ('Largest','18446744073709551616UL'),('Precise','1e309L'),
                          ('Signed','1U'),('Unsigned','1L'),('Largest','1U'),('Precise','1L'),
                          ('Signed','16#1_0000_0000_0000_0000L')]:
            e=self.typed({name:text},checked=False);self.assertTrue(e.blockers,(name,text))

    def test_outputs_and_inout_parameters_still_reject_constants(self):
        def output(root):
            text=root.find('./Controller/Programs/Program/Routines/Routine/RLLContent/Rung/Text')
            text.text=text.text.replace(',SignedResult,',',0L,')
        self.assertTrue(self.typed(mutate=output,checked=False).blockers)
        def inout(root):root.find('.//Parameter[@Name="Signed"]').set('Usage','InOut')
        self.assertTrue(self.typed(mutate=inout,checked=False).blockers)

    def test_ordinary_real_literal_keeps_float32_before_lreal_copy(self):
        e=self.typed({'Precise':'16777217.0'});self.enabled(e)
        self.assertEqual(e.memory.read('PreciseResult'),16777216.0)
        e=self.typed({'Precise':'16777217.0L'});self.enabled(e)
        self.assertEqual(e.memory.read('PreciseResult'),16777217.0)

    def test_missing_saved_required_input_is_established_from_literal(self):
        def missing(root):
            obj=root.find('./Controller/Tags/Tag[@Name="TypedInputs"]/Data/Structure')
            obj.remove(obj.find('DataValueMember[@Name="Precise"]'))
        e=self.typed(mutate=missing);self.assertEqual(e.memory.read('TypedInputs.Precise'),VALUES['Precise'])
        self.enabled(e);self.assertEqual(e.memory.read('PreciseResult'),VALUES['Precise'])

    def test_later_fault_restores_copied_inputs_outputs_and_bindings(self):
        e=self.typed(tail=['DIV(1,TestDivisor,TestGuard);']);e.memory.write('Enabled',True)
        e.memory.write('TestDivisor',0);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('TestDivisor',1);e.step();self.assertEqual(e.memory.read('LargestResult'),VALUES['Largest'])

    def test_nested_aoi_can_use_typed_constants_in_its_own_call(self):
        def nested(root):
            c=root.find('Controller');defs=c.find('AddOnInstructionDefinitions')
            d=E.SubElement(defs,'AddOnInstructionDefinition',Name='TypedWrapper',Class='Standard',ExecutePrescan='false',ExecutePostscan='false',ExecuteEnableInFalse='false')
            params=E.SubElement(d,'Parameters')
            for name,usage,dtype,required in [('EnableIn','Input','BOOL','false'),('EnableOut','Output','BOOL','false'),('Result','Output','LINT','true')]:
                E.SubElement(params,'Parameter',Name=name,DataType=dtype,Usage=usage,Required=required,Visible=required)
            locals=E.SubElement(d,'LocalTags')
            for name,dtype in [('Core','LabTypedInputs'),('U','UDINT'),('UL','ULINT'),('R','LREAL')]:E.SubElement(locals,'LocalTag',Name=name,DataType=dtype)
            content=E.SubElement(E.SubElement(E.SubElement(d,'Routines'),'Routine',Name='Logic',Type='RLL'),'RLLContent')
            E.SubElement(E.SubElement(content,'Rung',Number='0',Type='N'),'Text').text='LabTypedInputs(Core,16#0020000000000001L,8#37777777777U,2#1111111111111111111111111111111111111111111111111111111111111111UL,1.0000000000000002L,Result,U,UL,R);'
            obj=E.SubElement(E.SubElement(E.SubElement(c.find('Tags'),'Tag',Name='Wrapped',DataType='TypedWrapper',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='TypedWrapper')
            core=copy.deepcopy(c.find('./Tags/Tag[@Name="TypedInputs"]/Data/Structure'));core.tag='StructureMember';core.set('Name','Core');obj.append(core)
            for name,dtype in [('EnableIn','BOOL'),('EnableOut','BOOL'),('Result','LINT'),('U','UDINT'),('UL','ULINT'),('R','LREAL')]:
                E.SubElement(obj,'DataValueMember',Name=name,DataType=dtype,Value='0')
            c.find('./Programs/Program/Routines/Routine/RLLContent/Rung/Text').text='XIC(Enabled)TypedWrapper(Wrapped,SignedResult);'
        e=self.typed(mutate=nested);self.enabled(e)
        self.assertEqual(e.memory.read('SignedResult'),VALUES['Signed'])
        self.assertEqual(e.memory.read('Wrapped.Core.Precise'),VALUES['Precise'])

    def test_existing_st_call_and_definition_use_typed_inputs(self):
        def st(root):
            main=root.find('./Controller/Programs/Program/Routines/Routine');call=main.find('RLLContent/Rung/Text').text.partition(')')[2]
            main.remove(main.find('RLLContent'));main.set('Type','ST')
            E.SubElement(E.SubElement(main,'STContent'),'Line',Number='0').text='IF Enabled THEN '+call+' END_IF;'
            routine=root.find('.//AddOnInstructionDefinition/Routines/Routine');routine.remove(routine.find('RLLContent'));routine.set('Type','ST')
            E.SubElement(E.SubElement(routine,'STContent'),'Line',Number='0').text='SignedOut:=Signed; UnsignedOut:=Unsigned; LargestOut:=Largest; CPS(Precise,PreciseOut,1);'
        e=self.typed(mutate=st);self.enabled(e)
        self.assertEqual(e.memory.read('PreciseResult'),VALUES['Precise']);self.assertEqual(e.memory.read('LargestResult'),VALUES['Largest'])

    def test_public_sample_registration_menu_and_report(self):
        from logixlab.server import SAMPLES
        self.assertIn('AOIConstantsLab',SAMPLES)
        self.root=E.parse(SAMPLE).getroot();e=self.engine();self.assertEqual(e.blockers,[]);self.enabled(e)
        report=e.report()['add_on_instructions']['typed_inputs']
        self.assertEqual(set(report['types']),{'LINT','UDINT','ULINT','LREAL'});self.assertFalse(report['native_runtime_parity'])
        html=(SAMPLE.parents[1]/'web/index.html').read_text(encoding='utf8')
        app=(SAMPLE.parents[1]/'web/app.js').read_text(encoding='utf8')
        self.assertIn('id="aoi-constants-demo"',html);self.assertIn("loadDemo('AOIConstantsLab')",app)


if __name__=='__main__':unittest.main()
