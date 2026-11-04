"""Sequencer-specific narrow integer payloads, patterns and static guards."""
import itertools
import unittest
from xml.etree import ElementTree as E

import test_sequencer_operands as fixtures
import test_lreal_math as rollback
import test_aoi_sequencers as aoi
from logixlab.model import ModelError


class SequencerSourceTests(unittest.TestCase):
    setUp=fixtures.SequencerOperandTests.setUp
    checked=fixtures.SequencerOperandTests.checked
    snapshot=staticmethod(rollback.LrealMathTests.snapshot)
    fault=rollback.LrealMathTests.fault

    def engine(self,rungs=None,*,source_type='DINT',source_value=-1,mask_type='DINT',mask_value=-1,index=99,mutate=None,**options):
        def fields(root):
            tags=root.find('./Controller/Tags');tag=tags.find('Tag[@Name="Incoming"]');tag.set('DataType',source_type)
            node=tag.find('Data/DataValue');node.set('DataType',source_type);node.set('Value',str(source_value))
            tag=tags.find('Tag[@Name="Samples"]');tag.set('DataType',source_type);tag.find('Data/Array').set('DataType',source_type)
            tags.find('Tag[@Name="PayloadIndex"]/Data/DataValue').set('Value',str(index))
            tag=E.SubElement(tags,'Tag',Name='SelectMask',DataType=mask_type,TagType='Base')
            E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType=mask_type,Value=str(mask_value))
            if mutate:mutate(root)
        defaults=dict(length=2,queue=(-1,-1,0,999));defaults.update(options)
        return fixtures.SequencerOperandTests.engine(self,rungs or ['SQL(Queue[0],Incoming,Ctl,?,?);'],mutate=fields,**defaults)

    def test_sql_signed_narrow_inputs_load_startup_hold_and_cyclic_rows(self):
        for dtype,low in [('SINT',-128),('INT',-32768),('DINT',-2147483648)]:
            e=self.checked(source_type=dtype,source_value=low);e.step();self.assertEqual(e.memory.read('Queue[0]'),low);self.assertEqual(e.memory.read('Ctl.POS'),0)
            e.memory.write('Incoming',low+1);e.step();self.assertEqual(e.memory.read('Queue[0]'),low+1);self.assertEqual(e.memory.read('Ctl.POS'),0)
            e=self.checked(['XIC(StartPB)SQL(Queue[0],Incoming,Ctl,?,?);'],source_type=dtype);e.step()
            for pos,value in ((1,-1),(2,-2),(1,3)):
                e.memory.write('Incoming',value);e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read(f'Queue[{pos}]'),value);self.assertEqual(e.memory.read('Ctl.POS'),pos);self.assertEqual(e.memory.read('Ctl.DN'),pos==2)
                e.memory.write('StartPB',False);e.step()
            self.assertEqual(e.memory.read('Queue[3]'),999)

    def test_sqi_source_and_mask_types_retain_signed_source_mask_comparison(self):
        widths={'SINT':8,'INT':16,'DINT':32}
        for dtype,mask_type,row in itertools.product(widths,widths,(-1,255,65535,0x00ff00ff)):
            mask=(1<<widths[mask_type])-1
            e=self.checked(['SQI(Queue[0],SelectMask,Incoming,Ctl,?,?)OTE(RunLatch);'],source_type=dtype,mask_type=mask_type,queue=(row,0,0,999))
            before=e.memory.read('Incoming');e.step();self.assertIs(e.memory.read('RunLatch'),(row&mask)==((-1)&mask))
            self.assertEqual(e.memory.read('Incoming'),before);self.assertEqual(e.memory.read('Ctl.POS'),0)

    def test_complete_radix_patterns_and_signed_literals_in_source_positions(self):
        for token,want in [('16#FFFF_FFFF',-1),('8#37777777777',-1),('2#'+'1'*32,-1),('16#8000_0000',-2147483648),('16#0000_FFFF',65535),('-2147483648',-2147483648)]:
            e=self.checked([f'SQL(Queue[0],{token},Ctl,?,?);']);e.step();self.assertEqual(e.memory.read('Queue[0]'),want)
            e=self.checked([f'SQI(Queue[0],-1,{token},Ctl,?,?)OTE(RunLatch);'],queue=(want,0,0,999));e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_false_invalid_control_and_zero_masks_skip_live_narrow_references(self):
        for dtype in ('SINT','INT','DINT'):
            e=self.checked(['XIC(StartPB)SQL(Queue[0],Samples[PayloadIndex],Ctl,?,?);'],source_type=dtype);e.enter_run();e.step()
            e.memory.write('StartPB',True);self.fault(e,'outside bounds');e.memory.write('PayloadIndex',1);self.fault(e,'Unknown');e.memory.write('Samples[1]',-1);e.step();self.assertEqual(e.memory.read('Queue[1]'),-1)
            e=self.checked(['SQI(Queue[0],0,Samples[PayloadIndex],Ctl,?,?)OTE(RunLatch);'],source_type=dtype);e.memory.values['queue'][0]=None;e.step();self.assertTrue(e.memory.read('RunLatch'))
            for op in ('SQL','SQI'):
                call='SQL(Queue[0],Samples[PayloadIndex],Ctl,?,?);' if op=='SQL' else 'SQI(Queue[0],-1,Samples[PayloadIndex],Ctl,?,?);'
                e=self.checked([call],source_type=dtype,length=0);e.step();self.assertTrue(e.memory.read('Ctl.ER'));self.assertEqual(e.memory.read('PayloadIndex'),99)

    def test_full_unknown_table_writes_and_sqo_destination_rules(self):
        def unknown(root):
            array=root.find('./Controller/Tags/Tag[@Name="Queue"]/Data/Array');array.remove(array.find('Element[@Index="[0]"]'))
        e=self.checked(source_type='SINT',mutate=unknown);e.step();self.assertEqual(e.memory.read('Queue[0]'),-1)
        e=self.checked(['SQO(Queue[0],-1,Outputs[1],Ctl,?,?);']);e.step();self.assertEqual(e.memory.read('Outputs'),[None,-1,None])
        e=self.checked(['SQO(Queue[0],255,Outputs[1],Ctl,?,?);']);self.fault(e,'Unknown');e.memory.write('Outputs[1]',0x12340000);e.step();self.assertEqual(e.memory.read('Outputs[1]'),0x123400ff)
        e=self.checked(['SQO(Queue[0],0,Outputs[OutputIndex],Ctl,?,?);']);e.memory.values['queue'][0]=None;e.step();self.assertIsNone(e.memory.read('Outputs')[0])

    def test_alias_udt_member_and_late_fault_preserve_sources_and_table_guards(self):
        def packet(root):
            members=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='SmallPacket',Class='User'),'Members')
            E.SubElement(members,'Member',Name='Value',DataType='SINT',Dimension='0');E.SubElement(members,'Member',Name='Guard',DataType='DINT',Dimension='0')
            tags=root.find('./Controller/Tags');obj=E.SubElement(E.SubElement(E.SubElement(tags,'Tag',Name='Packet',DataType='SmallPacket',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='SmallPacket')
            E.SubElement(obj,'DataValueMember',Name='Value',DataType='SINT',Value='-1');E.SubElement(obj,'DataValueMember',Name='Guard',DataType='DINT',Value='777');E.SubElement(tags,'Tag',Name='Selected',DataType='SINT',TagType='Alias',AliasFor='Packet.Value')
        e=self.checked(['SQL(Queue[0],Selected,Ctl,?,?);','SQI(Queue[0],255,Selected,Ctl,?,?)OTE(RunLatch);'],mutate=packet);e.step();self.assertTrue(e.memory.read('RunLatch'));self.assertEqual(e.memory.read('Packet.Guard'),777);self.assertEqual(e.memory.read('Queue[3]'),999)
        e=self.checked(['SQL(Queue[0],Incoming,Ctl,?,?);','DIV(1,PayloadIndex,SpeedCommand);'],source_type='INT',index=0);self.fault(e,'zero');e.memory.write('PayloadIndex',1);e.step();self.assertEqual(e.memory.read('Queue[0]'),-1)

    def aoi(self,dtype='SINT'):
        f=aoi.AOISequencerTests();f.setUp();self.addCleanup(f.doCleanups)
        def fields(root):
            definition=root.find('.//AddOnInstructionDefinition')
            for name in ('Value','Feedback'):
                definition.find(f'Parameters/Parameter[@Name="{name}"]').set('DataType',dtype)
                for suffix in ('A','B'):
                    tag=root.find(f'./Controller/Tags/Tag[@Name="{name}{suffix}"]');tag.set('DataType',dtype);tag.find('Data/DataValue').set('DataType',dtype)
                    root.find(f'./Controller/Tags/Tag[@Name="Driver{suffix}"]/Data/Structure/DataValueMember[@Name="{name}"]').set('DataType',dtype)
        return f.engine(fields)

    def test_warm_aoi_copied_narrow_inputs_independent_tables_and_rollback(self):
        for dtype in ('SINT','INT'):
            e=self.aoi(dtype);self.assertEqual(e.blockers,[]);e.step();e.memory.write('ValueA',-1);e.memory.write('ValueB',-2);e.memory.write('Step',True);e.memory.write('Teach',True);e.step()
            self.assertEqual((e.memory.read('LearnedA[2]'),e.memory.read('LearnedB[3]'),e.memory.read('DriverA.Scratch[2]'),e.memory.read('DriverB.Scratch[3]')),(-1,-2,-1,-2))
            e.memory.write('FaultDivisor',0);self.fault(e,'zero');e.memory.write('FaultDivisor',1);e.memory.write('ValueA',3);e.step();self.assertEqual(e.memory.read('LearnedA[2]'),3)

    def test_noninteger_sources_and_non_dint_sqo_destinations_are_structurally_blocked(self):
        for dtype in ('BOOL','REAL','LREAL','LINT','USINT','UINT','UDINT','ULINT'):
            for op in ('SQL','SQI'):
                call='SQL(Queue[0],Incoming,Ctl,?,?);' if op=='SQL' else 'SQI(Queue[0],-1,Incoming,Ctl,?,?);'
                e=self.engine(['AFI()'+call],source_type=dtype,source_value=1);self.assertFalse(e.project.tags['incoming'].problem);self.assertTrue(e.blockers,(dtype,op))
        for dtype in ('SINT','INT','BOOL','REAL','LREAL','LINT','USINT','UINT','UDINT','ULINT'):
            def dest(root):
                tag=root.find('./Controller/Tags/Tag[@Name="Outgoing"]');tag.set('DataType',dtype);tag.find('Data/DataValue').set('DataType',dtype);tag.find('Data/DataValue').set('Value','0')
            self.assertTrue(self.engine(['AFI()SQO(Queue[0],0,Outgoing,Ctl,?,?);'],mutate=dest).blockers,dtype)

    def test_literal_shapes_permissions_and_other_languages_stay_guarded(self):
        for source in ('TRUE','1.0','2147483648','16#1_0000_0000','1L','Samples','Missing'):
            for call in (f'SQL(Queue[0],{source},Ctl,?,?);',f'SQI(Queue[0],0,{source},Ctl,?,?);'):
                self.assertTrue(self.engine(['AFI()'+call]).blockers,call)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Incoming"]').set('Constant','true')
        e=self.checked(mutate=constant);e.step();self.assertEqual(e.memory.read('Incoming'),-1)
        def readonly(root):root.find('./Controller/Tags/Tag[@Name="Queue"]').set('Constant','true')
        self.assertTrue(self.engine(mutate=readonly).blockers)
        for call in ('SQL(Queue[0],Incoming,Ctl,?,?);','SQI(Queue[0],-1,Incoming,Ctl,?,?);'):
            def structured(root):
                r=root.find('./Controller/Programs/Program/Routines/Routine');r.remove(r.find('RLLContent'));r.set('Type','ST');E.SubElement(E.SubElement(r,'STContent'),'Line',Number='0').text=call
            self.assertTrue(self.engine(['NOP();'],mutate=structured).blockers)

    def test_report_keeps_payload_widths_mask_rules_and_native_limits_explicit(self):
        d=self.checked().report()['sequencer_operations'];self.assertEqual(d['source_types'],['SINT','INT','DINT']);self.assertEqual(d['destination_type'],'SQO requires DINT');self.assertIn('signed narrow',d['source_conversion']);self.assertFalse(d['native_scan_parity'])
