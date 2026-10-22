"""Controller GSV uses the same source-bound values as native metadata reads."""
import copy
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock,patch
from xml.etree import ElementTree as E

from logixlab.ethernetip import Router,Session
from logixlab.model import ModelError,Project
from logixlab.runtime import Engine

SEED=0x80000001fffffffe
MASK=0xfedcba9876543210


def tag(parent,name,dtype,value=91,*,count=None,constant=False):
    node=E.SubElement(parent,'Tag',Name=name,TagType='Base',DataType=dtype,Constant=str(constant).lower())
    data=E.SubElement(node,'Data',Format='Decorated')
    if count is None:E.SubElement(data,'DataValue',DataType=dtype,Radix='Decimal',Value=str(value))
    else:
        node.set('Dimensions',str(count));array=E.SubElement(data,'Array',DataType=dtype,Dimensions=str(count),Radix='Decimal')
        for i in range(count):E.SubElement(array,'Element',Index=f'[{i}]',Value=str(value+i))
    return node


class SystemValueTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=E.parse(Path(__file__).resolve().parents[1]/'samples/ConveyorDemo.L5X').getroot()
        controller=self.root.find('Controller')
        E.SubElement(controller,'Security',Code='0',ChangesToDetect='16#fedc_ba98_7654_3210')
        tags=controller.find('Tags')
        tag(tags,'GsvWords','DINT',count=4);tag(tags,'GsvWide','LINT')
        tag(tags,'GsvIndex','DINT',0);tag(tags,'GsvSmall','SINT')
        self.routine=controller.find('./Programs/Program/Routines/Routine[@Name="MainRoutine"]')
        routines=controller.find('./Programs/Program/Routines')
        for other in list(routines):
            if other is not self.routine:routines.remove(other)

    def engine(self,text,*,st=False):
        for node in list(self.routine):self.routine.remove(node)
        if st:
            self.routine.set('Type','ST');content=E.SubElement(self.routine,'STContent')
            E.SubElement(content,'Line',Number='0').text=text
        else:
            self.routine.set('Type','RLL');content=E.SubElement(self.routine,'RLLContent')
            E.SubElement(E.SubElement(content,'Rung',Number='0',Type='N'),'Text').text=text
        path=Path(self.tmp.name)/'fixture.L5X';E.ElementTree(self.root).write(path,encoding='utf8',xml_declaration=True)
        with patch('logixlab.change_detection.secrets.randbits',return_value=SEED):
            return Engine(Project(path),defer_prescan=True)

    def test_ladder_reads_signed_lint_and_two_dints_without_losing_bits_or_neighbor_elements(self):
        e=self.engine('GSV(CONTROLLER,,AuditValue,GsvWide)GSV(Controller,,ChangesToDetect,GsvWords[1]);')
        self.assertFalse(e.blockers);e.step()
        self.assertEqual(e.memory.read('GsvWide'),struct.unpack('<q',struct.pack('<Q',SEED))[0])
        words=struct.unpack('<ii',struct.pack('<Q',MASK))
        self.assertEqual(e.memory.read('GsvWords'),[91,*words,94])
        self.assertEqual(e.change_detection.description()['updates'],0)

    def test_prescan_retains_saved_destinations_and_each_scan_reads_current_epoch(self):
        e=self.engine('GSV(CONTROLLER,,AuditValue,GsvWords[0]);')
        self.assertFalse(e.blockers);initial=copy.deepcopy(e.memory.values)
        e.enter_run();self.assertEqual(e.memory.values,initial)
        e.step();self.assertEqual(e.memory.read('GsvWords')[:2],list(struct.unpack('<ii',struct.pack('<Q',SEED))))
        self.assertTrue(e.change_detection.record('remote_mode'));e.step()
        self.assertEqual(e.memory.read('GsvWords')[:2],list(struct.unpack('<ii',struct.pack('<Q',SEED+1))))
        self.assertEqual(e.change_detection.description()['updates'],1)

    def test_false_ladder_and_st_paths_do_not_write_destinations(self):
        for text,st in (('AFI()GSV(Controller,,AuditValue,GsvWide);',False),
                        ('IF StartPB THEN GSV(Controller,,AuditValue,GsvWide); END_IF;',True)):
            e=self.engine(text,st=st);self.assertFalse(e.blockers);e.step();self.assertEqual(e.memory.read('GsvWide'),91)

    def test_structured_text_reads_the_same_values_and_keeps_for_loop_contract(self):
        e=self.engine('FOR GsvIndex:=0 TO 2 DO GSV(Controller,,AuditValue,GsvWide); END_FOR; GSV(Controller,,ChangesToDetect,GsvWords);',st=True)
        self.assertFalse(e.blockers);e.step()
        self.assertEqual(e.memory.read('GsvIndex'),3)
        self.assertEqual(e.memory.read('GsvWide'),struct.unpack('<q',struct.pack('<Q',SEED))[0])
        self.assertEqual(e.memory.read('GsvWords')[:2],list(struct.unpack('<ii',struct.pack('<Q',MASK))))
        self.assertEqual(e.change_detection.description()['updates'],0)

    def test_gsv_cannot_overwrite_either_word_of_a_for_bound_or_step(self):
        for expr in ('TO GsvWords[0]','TO GsvWords[1]','TO 2 BY GsvWords[1]'):
            e=self.engine('FOR GsvIndex:=0 '+expr+' DO GSV(Controller,,AuditValue,GsvWords[0]); END_FOR;',st=True)
            self.assertTrue(any('bounds/step' in b for b in e.blockers),e.blockers)

    def test_cip_and_logic_share_the_identical_audit_epoch_and_mask_bytes(self):
        e=self.engine('GSV(Controller,,AuditValue,GsvWords)GSV(Controller,,ChangesToDetect,GsvWide);');e.step()
        router=Router(NS(engine=e),NS(native_read_only=False,record_attribute_gap=Mock()))
        for number,value in ((27,struct.pack('<ii',*e.memory.read('GsvWords')[:2])),(28,struct.pack('<q',e.memory.read('GsvWide')))):
            self.assertEqual(router.dispatch(bytes.fromhex('0e03208e240130')+bytes((number,)),Session()),(0,value))

    def test_missing_or_malformed_source_mask_blocks_even_an_unreachable_instruction(self):
        security=self.root.find('./Controller/Security')
        for value in (None,'','16#10000000000000000'):
            if value is None:security.attrib.pop('ChangesToDetect',None)
            else:security.set('ChangesToDetect',value)
            for attribute in ('AuditValue','ChangesToDetect'):
                e=self.engine(f'AFI()GSV(Controller,,{attribute},GsvWide);')
                self.assertTrue(any('unavailable' in b for b in e.blockers),e.blockers)

    def test_unknown_classes_instances_attributes_and_operand_counts_remain_blocked(self):
        for text in ('GSV(Task,,AuditValue,GsvWide);','GSV(Controller,This,AuditValue,GsvWide);',
            'GSV(Controller,,Unknown,GsvWide);','GSV(Controller,,AuditValue);','GSV(Controller,,AuditValue,GsvWide,0);',
            'SSV(Controller,,ChangesToDetect,GsvWide);'):
            e=self.engine(text);self.assertTrue(e.blockers,text)

    def test_readonly_bit_small_scalar_and_short_array_destinations_are_rejected_before_execution(self):
        tag(self.root.find('./Controller/Tags'),'GsvConst','LINT',constant=True)
        for dest in ('GsvConst','GsvWide.0','GsvSmall','SpeedSetpoint','GsvWords[3]','StartPB'):
            e=self.engine(f'GSV(Controller,,AuditValue,{dest});')
            self.assertTrue(e.blockers,dest);self.assertEqual(e.scan_count,0)
            self.assertEqual(e.memory.read('GsvWords'),[91,92,93,94])

    def test_indirect_bounds_are_rechecked_without_partial_destination_or_prior_rung_writes(self):
        e=self.engine('MOV(123,SpeedSetpoint)GSV(Controller,,AuditValue,GsvWords[GsvIndex]);')
        self.assertFalse(e.blockers);e.memory.write('GsvIndex',3)
        before=copy.deepcopy(e.memory.values)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual(e.time_ms,0);self.assertEqual(e.scan_count,0)
        self.assertFalse(e.change_detection.description()['audit_value_available'])

    def test_later_fault_rolls_back_gsv_results_and_invalidates_unclassified_history(self):
        e=self.engine('GSV(Controller,,AuditValue,GsvWide)DIV(SpeedSetpoint,0,SpeedCommand);')
        self.assertFalse(e.blockers);before=copy.deepcopy(e.memory.values)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(e.memory.values,before);self.assertFalse(e.change_detection.description()['audit_value_available'])

    def test_program_local_shadow_and_alias_destinations_use_normal_scope_resolution(self):
        tags=self.root.find('./Controller/Programs/Program/Tags');tag(tags,'GsvWide','LINT')
        e=self.engine('GSV(Controller,,AuditValue,GsvWide);');e.step()
        self.assertEqual(e.memory.read('GsvWide'),91)
        self.assertEqual(e.memory.read('GsvWide','MainProgram'),struct.unpack('<q',struct.pack('<Q',SEED))[0])
        tags.remove(tags.find('./Tag[@Name="GsvWide"]'))
        E.SubElement(self.root.find('./Controller/Tags'),'Tag',Name='GsvAlias',TagType='Alias',DataType='DINT',AliasFor='GsvWords[1]')
        e=self.engine('GSV(Controller,,AuditValue,GsvAlias);');self.assertFalse(e.blockers);e.step()
        self.assertEqual(e.memory.read('GsvWords'),[91,*struct.unpack('<ii',struct.pack('<Q',SEED)),94])


if __name__=='__main__':unittest.main()
