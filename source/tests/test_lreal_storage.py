"""Finite binary64 storage/MOV/CLR, bounded conversions and atomic CIP access."""
import base64
import copy
import math
import struct
import unittest
from xml.etree import ElementTree as E

import test_numeric_storage as storage
import test_ethernetip as wire
from logixlab.model import ModelError,coerce


class LrealStorageTests(unittest.TestCase):
    setUp=storage.NumericStorageTests.setUp
    engine=storage.NumericStorageTests.engine
    checked=storage.NumericStorageTests.checked
    snapshot=staticmethod(storage.NumericStorageTests.snapshot)

    def test_all_one_hundred_numeric_mov_pairs(self):
        types=('SINT','INT','DINT','LINT','USINT','UINT','UDINT','ULINT','REAL','LREAL')
        for source in types:
            for dest in types:
                with self.subTest(source=source,dest=dest):
                    value=3.5 if source in ('REAL','LREAL') else 3
                    expected=value if dest in ('REAL','LREAL') else round(value)
                    e=self.checked(source=source,dest=dest,value=value);e.step()
                    self.assertEqual(e.memory.read('Results'),[None,expected,None]);self.assertEqual(e.memory.read('Source'),value)

    def test_lreal_preserves_binary64_precision_range_and_sign_of_zero(self):
        for value in (1.0000000000000002,9007199254740991.0,1e308,5e-324,-0.0):
            e=self.checked(source='LREAL',dest='LREAL',value=value);e.step()
            self.assertEqual(struct.pack('<d',e.memory.read('Results[1]')),struct.pack('<d',value))
        e=self.checked(source='ULINT',dest='LREAL',value=18446744073709551615);e.step();self.assertEqual(e.memory.read('Results[1]'),float(1<<64))

    def test_declared_source_precision_controls_widening_and_narrowing(self):
        for source,dest,value,expected in [('LREAL','REAL',16777217.0,16777216.0),('LREAL','LINT',9007199254740991.0,9007199254740991),('REAL','LREAL',16777217.0,16777216.0),('DINT','LREAL',16777217,16777217.0)]:
            e=self.checked(source=source,dest=dest,value=value);e.step();self.assertEqual(e.memory.read('Results[1]'),expected)
        e=self.checked(['MOV(1.0000000000000002,Results[1]);'],dest='LREAL');e.step();self.assertEqual(e.memory.read('Results[1]'),1.0)

    def test_lreal_nearest_even_integer_conversion_and_range_rollback(self):
        for value,expected in ((2.5,2),(3.5,4),(-2.5,-2),(-3.5,-4)):
            e=self.checked(source='LREAL',dest='LINT',value=value);e.step();self.assertEqual(e.memory.read('Results[1]'),expected)
        for dest,value in (('USINT',-1.0),('LINT',float(1<<63)),('ULINT',float(1<<64)),('REAL',1e308)):
            e=self.checked(['MOV(99,SpeedCommand);','MOV(Source,Results[1]);'],source='LREAL',dest=dest,value=value);before=self.snapshot(e)
            with self.assertRaises(ModelError):e.step()
            self.assertEqual(self.snapshot(e),before)

    def test_lreal_clr_establishes_unknown_positive_zero_and_leaves_neighbors_unknown(self):
        e=self.checked(['CLR(Results[1]);'],dest='LREAL');e.step()
        self.assertEqual(e.memory.read('Results'),[None,0.0,None]);self.assertEqual(struct.pack('<d',e.memory.read('Results[1]')),bytes(8))

    def test_false_prescan_dormant_indices_and_complete_unknown_writes(self):
        e=self.checked(['XIC(StartPB)MOV(Inputs[Index],Results[Index]);'],source='LREAL',dest='LREAL')
        e.memory.write('Index',99);e.enter_run();e.step();self.assertEqual(e.memory.read('Results'),[None]*3)
        e.memory.write('StartPB',True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('Index',1);e.memory.write('Inputs[1]',1.0000000000000002);e.step();self.assertEqual(e.memory.read('Results'),[None,1.0000000000000002,None])

    def test_udt_member_alias_and_late_fault_preserve_values_and_scheduling(self):
        def member(root):
            c=root.find('Controller');members=E.SubElement(E.SubElement(c.find('DataTypes'),'DataType',Name='DoublePacket',Class='User'),'Members')
            E.SubElement(members,'Member',Name='Value',DataType='LREAL',Dimension='0');E.SubElement(members,'Member',Name='Guard',DataType='DINT',Dimension='0')
            obj=E.SubElement(E.SubElement(E.SubElement(c.find('Tags'),'Tag',Name='Packet',DataType='DoublePacket',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='DoublePacket')
            E.SubElement(obj,'DataValueMember',Name='Guard',DataType='DINT',Value='777')
            E.SubElement(c.find('Tags'),'Tag',Name='Selected',DataType='LREAL',TagType='Alias',AliasFor='Packet.Value')
        e=self.checked(['MOV(Source,Selected);','CLR(Results[1]);','DIV(1,Mask,SpeedCommand);'],source='LREAL',dest='LREAL',value=1.0000000000000002,mutate=member)
        e.memory.write('Mask',0);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('Mask',1);e.step()
        self.assertEqual((e.memory.read('Packet.Value'),e.memory.read('Packet.Guard')),(1.0000000000000002,777))

    def test_nonfinite_values_are_rejected_by_import_and_external_store(self):
        for value in (math.inf,-math.inf,math.nan):
            with self.assertRaisesRegex(ModelError,'Nonfinite LREAL'):coerce(value,'LREAL')
        e=self.checked(source='LREAL',dest='LREAL');before=self.snapshot(e)
        for value in (math.inf,-math.inf,math.nan):
            with self.assertRaisesRegex(ModelError,'Nonfinite LREAL'):e.memory.write('Source',value)
            self.assertEqual(self.snapshot(e),before)
        self.assertTrue(self.engine(source='LREAL',value='1e999').blockers)

    def test_unsupported_lreal_mixed_forms_fills_and_old_profile_do_not_fall_through(self):
        for rung in ('ADD(Source,Mask,SpeedCommand);','DIV(Source,1.0,Dest);','EQU(Source,TRUE);','CMP(Source=StartPB);','CPT(Dest,Source+1e999);','FLL(Source,Dest,1);','AND(Source,Source,Dest);'):
            self.assertTrue(self.engine([rung],source='LREAL',dest='LREAL').blockers,rung)
        def old(root):root.find('Controller').set('ProcessorType','1756-L75')
        self.assertTrue(self.engine(source='LREAL',dest='LREAL',mutate=old).blockers)

    def test_lreal_st_assignment_and_constant_destinations_remain_guarded(self):
        def st(root):
            routine=root.find('./Controller/Programs/Program/Routines/Routine');routine.set('Type','ST');routine.remove(routine.find('RLLContent'))
            E.SubElement(E.SubElement(routine,'STContent'),'Line',Number='0').text='Dest := Source;'
        self.assertTrue(self.engine(source='LREAL',dest='LREAL',mutate=st).blockers)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Results"]').set('Constant','true')
        self.assertTrue(self.engine(['AFI()MOV(Source,Results[1]);'],source='LREAL',dest='LREAL',mutate=constant).blockers)


class LrealWireTests(unittest.TestCase):
    setUp=wire.EtherNetIPTests.setUp
    tearDown=wire.EtherNetIPTests.tearDown
    client=wire.EtherNetIPTests.client
    cip=wire.EtherNetIPTests.cip

    def load(self):
        f=LrealStorageTests();f.setUp();self.addCleanup(f.doCleanups)
        e=f.checked(['NOP();'],source='LREAL',dest='LREAL',value=1.0000000000000002)
        state=self.app.command('load',dict(name='Doubles.L5X',content=base64.b64encode(e.project.path.read_bytes()).decode()))
        self.assertEqual(state['blockers'],[])

    def test_atomic_read_write_and_fragmented_double_precision(self):
        self.load();value=1.0000000000000002
        raw=self.cip(wire.request(0x4C,'Source',struct.pack('<H',1)))
        self.assertEqual(raw[:6],b'\xcc\0\0\0\xcb\0');self.assertEqual(raw[6:],struct.pack('<d',value))
        raw=self.cip(wire.request(0x52,'Source',struct.pack('<HI',1,4)));self.assertEqual(raw[6:],struct.pack('<d',value)[4:])
        raw=self.cip(wire.request(0x4D,'Results[1]',struct.pack('<HHd',0xCB,1,value)));self.assertEqual(raw[2],0);self.assertEqual(self.app.engine.memory.read('Results[1]'),value)
        raw=self.cip(wire.request(0x53,'Results[1]',struct.pack('<HHI',0xCB,1,0)+struct.pack('<d',2.0000000000000004)[:4]));self.assertEqual(raw[2],0)
        self.assertEqual(struct.pack('<d',self.app.engine.memory.read('Results[1]'))[:4],struct.pack('<d',2.0000000000000004)[:4])

    def test_nonfinite_multiwrite_is_atomic_unknown_partial_and_bit_service_rejected(self):
        self.load();before=copy.deepcopy(self.app.engine.memory.values)
        for raw in (wire.request(0x4D,'Results[0]',struct.pack('<HHdd',0xCB,2,3.0,math.nan)),
                    wire.request(0x53,'Results[1]',struct.pack('<HHI',0xCB,1,4)+b'\0'*4),
                    wire.request(0x4E,'Source',struct.pack('<H',8)+b'\xff'*16)):
            self.assertNotEqual(self.cip(raw)[2],0);self.assertEqual(self.app.engine.memory.values,before)

    def test_network_write_opt_in_and_declared_type_still_required(self):
        self.load();before=copy.deepcopy(self.app.engine.memory.values)
        self.assertNotEqual(self.cip(wire.request(0x4D,'Source',struct.pack('<HHf',0xCA,1,2.0)))[2],0)
        self.endpoint.allow_writes=False
        self.assertEqual(self.cip(wire.request(0x4D,'Source',struct.pack('<HHd',0xCB,1,2.0)))[2],0x0F)
        self.assertEqual(self.app.engine.memory.values,before)
