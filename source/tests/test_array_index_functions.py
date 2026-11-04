"""Scoped DINT BCD/root functions in existing array references."""
import unittest
from xml.etree import ElementTree as E

import test_array_index_expressions as fixtures
from logixlab.expressions import Expression
from logixlab.model import ModelError,Project
from logixlab.runtime import Engine


class ArrayIndexFunctionTests(unittest.TestCase):
    setUp=fixtures.ArrayIndexExpressionTests.setUp
    checked=fixtures.ArrayIndexExpressionTests.checked
    snapshot=staticmethod(fixtures.ArrayIndexExpressionTests.snapshot)
    fault=fixtures.ArrayIndexExpressionTests.fault

    def engine(self,rungs=None,**options):
        options.setdefault('index',1)
        return fixtures.ArrayIndexExpressionTests.engine(self,rungs,**options)

    def test_three_functions_promote_all_narrow_tag_inputs_to_dint(self):
        for dtype in ('SINT','INT','DINT'):
            e=self.checked(['NOP();'],index_type=dtype)
            for value,expr,want in ((26,'FRD(Index)',20),(21,'TOD(Index)',33),(3,'SQR(Index)',2),
                                    (-1,'FRD(Index)',166666665),(-16,'SQR(Index)',4)):
                e.memory.write('Index',value);self.assertEqual(e.memory.index(expr,''),want,(dtype,value,expr))

    def test_constants_composition_and_nested_round_trip(self):
        e=self.checked(['NOP();'])
        for expr,want in [('FRD(16#12345678)',12345678),('FRD(16#1A)',20),('FRD(-1)',166666665),
                          ('TOD(0)',0),('TOD(99999999)',-1717986919),('TOD(99999999) AND 7',1),
                          ('FRD(TOD(99999999))',99999999),('FRD(TOD(Index+3))+SQR(16)',8),
                          ('SQR(SQR(81))',3),('TOD(Index/Divisor)',0)]:
            self.assertEqual(e.memory.index(expr,''),want,expr)

    def test_root_uses_finite_real_input_result_and_nearest_even_integer_conversion(self):
        e=self.checked(['NOP();'])
        for value,want in ((0,0),(2,1),(3,2),(8,3),(15,4),(-3,2),(16777217,4096),(2147483647,46341),(-2147483648,46341)):
            e.memory.write('Index',value);self.assertEqual(e.memory.index('SQR(Index)',''),want,value)

    def test_selected_source_destination_and_common_consumers_establish_unknowns(self):
        for function in ('FRD','TOD','SQR'):
            for instruction,want in ((f'MOV(Inputs[{function}(Index)],Results[{function}(Index)]);',77),
                                     (f'ADD(Inputs[{function}(Index)],1,Results[{function}(Index)]);',78),
                                     (f'COP(Inputs[{function}(Index)],Results[{function}(Index)],1);',77),
                                     (f'FLL(Inputs[{function}(Index)],Results[{function}(Index)],1);',77)):
                e=self.checked([instruction]);e.memory.write('Inputs[1]',77);e.step();self.assertEqual(e.memory.read('Results'),[None,want,None])

    def test_multidimensional_alias_members_and_nested_references(self):
        def fields(root):
            tags=root.find('./Controller/Tags');E.SubElement(tags,'Tag',Name='Selected',DataType='DINT',TagType='Alias',AliasFor='Index')
            members=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='Selection',Class='User'),'Members');E.SubElement(members,'Member',Name='Index',DataType='DINT',Dimension='0')
            obj=E.SubElement(E.SubElement(E.SubElement(tags,'Tag',Name='Packet',DataType='Selection',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='Selection');E.SubElement(obj,'DataValueMember',Name='Index',DataType='DINT',Value='1')
            arr=E.SubElement(E.SubElement(E.SubElement(tags,'Tag',Name='Matrix',DataType='DINT',Dimensions='3,3',TagType='Base'),'Data',Format='Decorated'),'Array',DataType='DINT',Dimensions='3,3');E.SubElement(arr,'Element',Index='[1,1]',Value='42')
        e=self.checked(['MOV(Matrix[FRD(Selected),SQR(Packet.Index)],Results[TOD(Selected)]);'],mutate=fields);e.step();self.assertEqual(e.memory.read('Results'),[None,42,None])
        e=self.checked(['MOV(Source,Results[FRD(Inputs[SQR(Index)])]);']);e.memory.write('Inputs[1]',2);e.step();self.assertEqual(e.memory.read('Results'),[None,None,7])

    def test_false_prescan_unknowns_zero_divisors_and_invalid_tod_ranges_are_lazy(self):
        e=self.checked(['XIC(StartPB)MOV(Source,Results[TOD(Index/Divisor)]);'],divisor=0)
        e.memory.values['index']=None;e.enter_run();e.step();self.assertEqual(e.memory.read('Results'),[None]*3)
        e.memory.write('StartPB',True);self.fault(e,'Unknown');e.memory.write('Index',1);self.fault(e,'zero')
        e.memory.write('Divisor',1);e.step();self.assertEqual(e.memory.read('Results'),[None,7,None])
        for value in (-1,100000000):
            e=self.checked(['XIC(StartPB)MOV(Source,Results[TOD(Index)]);'],index=value);e.step();e.memory.write('StartPB',True);self.fault(e,'qualified')

    def test_required_values_intermediate_overflow_bounds_and_late_failures_rollback(self):
        for expr,index,text in [('FRD(Index*2)',1073741824,'overflow'),('TOD(Index+1)',2147483647,'overflow'),
                                ('FRD(Index)',-1,'outside bounds'),('SQR(Index)',2147483647,'outside bounds')]:
            e=self.checked(['MOV(99,SpeedCommand);',f'MOV(Source,Results[{expr}]);'],index=index);self.fault(e,text)
        e=self.checked(['MOV(Source,Results[FRD(Index) AND 0]);']);e.memory.values['index']=None;self.fault(e,'Unknown')
        e=self.checked(['MOV(Source,Results[FRD(TOD(Index))]);','DIV(1,LateDivisor,SpeedCommand);']);e.memory.write('LateDivisor',0);self.fault(e,'zero');e.memory.write('LateDivisor',1);e.step();self.assertEqual(e.memory.read('Results'),[None,7,None])

    def test_existing_st_references_use_functions_without_new_bcd_call_forms(self):
        e=self.checked('IF StartPB THEN Results[FRD(TOD(Index))]:=Inputs[SQR(Index)]; END_IF;',st=True);e.step();e.memory.write('Inputs[1]',88);e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Results'),[None,88,None])
        for text in ('Dest:=FRD(Index);','Dest:=TOD(Index);'):
            self.assertTrue(self.engine(text,st=True).blockers,text)

    def aoi(self):
        helper=fixtures.ArrayIndexExpressionTests();helper.setUp();self.addCleanup(helper.doCleanups);original=helper.aoi();root=E.parse(original.project.path).getroot()
        fixtures.advanced.queues.logic(root,['MOV(Value,Buffer[FRD(TOD(Index))]);','MOV(Value,Stack[SQR(Index*Index)]);'])
        E.ElementTree(root).write(original.project.path,encoding='utf8',xml_declaration=True);return Engine(Project(original.project.path))

    def test_warm_aoi_function_indices_retain_independent_bindings_and_rollback(self):
        e=self.aoi();self.assertEqual(e.blockers,[]);e.memory.write('ValueA',4);e.memory.write('ValueB',9);e.step()
        self.assertEqual((e.memory.read('BufferA[1]'),e.memory.read('BufferB[2]'),e.memory.read('DriverA.Stack[1]'),e.memory.read('DriverB.Stack[2]')),(4,9,4,9))
        e.memory.write('FaultDivisor',0);self.fault(e,'zero');e.memory.write('FaultDivisor',1);e.step();self.assertEqual(e.memory.read('DriverB.Stack[2]'),9)

    def test_opt_in_reference_guard_detects_control_pos_inside_functions(self):
        import test_queue_references as queues
        f=queues.QueueReferenceTests();f.setUp();self.addCleanup(f.doCleanups)
        e=f.checked(['XIC(StartPB)FFL(Incoming,Queue[FRD(TOD(Index))],Ctl,?,?);'],length=3);e.step();e.memory.write('Incoming',88);e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Queue[1]'),88)
        from logixlab.control_operations import check_start_indices
        for function in ('FRD','TOD','SQR'):
            with self.assertRaisesRegex(ModelError,'CONTROL.POS'):check_start_indices(e.memory,f'Queue[{function}(Ctl.POS)]','')

    def test_wide_float_other_functions_and_generic_bcd_expressions_stay_blocked(self):
        for dtype in ('LINT','USINT','UINT','UDINT','ULINT','BOOL','REAL','LREAL'):
            for function in ('FRD','TOD','SQR'):
                self.assertTrue(self.engine([f'AFI()MOV(Source,Results[{function}(Index)]);'],index_type=dtype).blockers,(dtype,function))
        for expr in ('SQRT(Index)','ABS(Index)','TRN(Index)','FRD(1.0)','TOD(Index MOD 2)','SQR(Index**2)'):
            self.assertTrue(self.engine([f'AFI()MOV(Source,Results[{expr}]);']).blockers,expr)
        for call in ('CMP(FRD(Index)>0);','CMP(TOD(Index)>0);'):
            self.assertTrue(self.engine([call]).blockers,call)
        e=self.checked(['NOP();'])
        with self.assertRaisesRegex(ModelError,'subscript'):Expression('FRD(Index)',subscript=True).validate(e.memory)
        def old(root):root.find('Controller').set('ProcessorType','1756-L75')
        self.assertTrue(self.engine(['AFI()MOV(Source,Results[FRD(Index)]);'],mutate=old).blockers)

    def test_report_records_conversion_width_root_rounding_and_native_boundary(self):
        d=self.checked().report()['integer_expression_execution']['array_indices'];self.assertEqual(d['functions'],['FRD','TOD','SQR']);self.assertIn('eight weighted nibbles',d['function_profile']);self.assertIn('nearest-even',d['function_profile']);self.assertFalse(d['native_runtime_parity'])
