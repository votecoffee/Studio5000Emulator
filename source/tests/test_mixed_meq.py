"""Mixed integer ladder MEQ: independent bit-string oracle and lazy inputs."""
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as E

import test_numeric_comparisons as fixtures
from logixlab.model import ModelError

TYPES = {'SINT':(1,True),'INT':(2,True),'DINT':(4,True),'LINT':(8,True),
         'USINT':(1,False),'UINT':(2,False),'UDINT':(4,False),'ULINT':(8,False)}


def pattern(dtype, byte):
    size,signed=TYPES[dtype]
    return int.from_bytes(bytes([byte])*size,'big',signed=signed)


def expected(values, types):
    # Byte encoding and selected bit characters are independent of the
    # runtime's integer masking/promotion; no production conversion helper.
    bits=[]
    for value,dtype in zip(values,types):
        size,signed=TYPES[dtype]
        bits.append(''.join(format(b,'08b') for b in value.to_bytes(size,'big',signed=signed)).zfill(64))
    return all(a==b for a,m,b in zip(*bits) if m=='1')


class MixedMeqTests(unittest.TestCase):
    setUp=fixtures.NumericComparisonTests.setUp
    engine=fixtures.NumericComparisonTests.engine
    checked=fixtures.NumericComparisonTests.checked
    snapshot=staticmethod(fixtures.NumericComparisonTests.snapshot)

    def test_all_512_tag_type_combinations_with_three_bit_patterns(self):
        combinations=[(a,m,b) for a in TYPES for m in TYPES for b in TYPES]
        rungs=[f'MEQ(A_{a},M_{m},B_{b})OTE(Matches[{i}]);' for i,(a,m,b) in enumerate(combinations)]
        def matrix(root):
            tags=root.find('./Controller/Tags')
            for dtype in TYPES:
                for prefix,byte in (('A',0xa5),('M',0x3c),('B',0xa5)):
                    tag=E.SubElement(tags,'Tag',Name=prefix+'_'+dtype,DataType=dtype,TagType='Base',Constant='true')
                    E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType=dtype,Value=str(pattern(dtype,byte)))
            tag=E.SubElement(tags,'Tag',Name='Matches',DataType='BOOL',Dimensions='513',TagType='Base')
            E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='BOOL',Dimensions='513')
        e=self.checked(rungs,mutate=matrix)
        for mask,compare in ((0x3c,0xa5),(0xff,0xa4),(0,0x5a)):
            # External initialization of constant fixture tags bypasses writes
            # only here; the instruction must accept and preserve all three.
            for dtype in TYPES:
                e.memory.values['m_'+dtype.lower()]=pattern(dtype,mask)
                e.memory.values['b_'+dtype.lower()]=pattern(dtype,compare)
            inputs={k:v for k,v in e.memory.values.items() if k.startswith(('a_','m_','b_'))}
            e.step()
            results=[expected((pattern(a,0xa5),pattern(m,mask),pattern(b,compare)),(a,m,b)) for a,m,b in combinations]
            self.assertEqual(e.memory.read('Matches'),results+[None])
            self.assertEqual({k:e.memory.values[k] for k in inputs},inputs)
            if mask:self.assertIn(False,results)
            if mask!=0xff:self.assertIn(True,results)
        self.assertEqual(e.scan_count,3)

    def test_exact_high_bits_and_zero_extension_in_each_operand_position(self):
        for types,values,result in (
                (('SINT','ULINT','LINT'),(-1,65536,0),True),
                (('DINT','ULINT','LINT'),(-1,1<<63,-1),False),
                (('LINT','DINT','ULINT'),(-1,-1,4294967295),True),
                (('ULINT','LINT','DINT'),(1<<63,-1,-1),False),
                (('ULINT','USINT','LINT'),(9007199254740993,1,9007199254740992),False),
                (('ULINT','UINT','LINT'),(9007199254740993,1,9007199254740993),True),
                (('LINT','ULINT','SINT'),(-1,255,-1),True),
                (('USINT','ULINT','LINT'),(255,(1<<64)-1,-1),False)):
            e=self.checked(types=types,values=values)
            before=tuple(e.memory.read(t) for t in ('Source','Mask','Dest'))
            with patch('logixlab.scalar_math.real',side_effect=AssertionError('MEQ used REAL')):e.step()
            self.assertEqual(e.memory.read('RunLatch'),result,(types,values))
            self.assertEqual(tuple(e.memory.read(t) for t in ('Source','Mask','Dest')),before)

    def test_each_unknown_mixed_operand_is_required_even_with_zero_mask(self):
        for position in (0,1,2):
            args=['Source','Mask','Dest'];args[position]='Values[0]'
            e=self.checked(['XIC(StartPB)MEQ('+','.join(args)+')OTE(RunLatch);'],
                           types=('ULINT','USINT','DINT'),values=(7,0,7))
            e.step();self.assertFalse(e.memory.read('RunLatch'))
            e.memory.write('StartPB',True);before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
            self.assertEqual(self.snapshot(e),before)
            e.memory.write('Values[0]',0 if position==1 else 7);e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_false_and_prescan_skip_actual_indices_then_fault_and_retry(self):
        e=self.checked(['XIC(StartPB)MEQ(Values[Index],Mask,Dest)OTE(RunLatch);'],
                       types=('ULINT','USINT','DINT'),values=(7,15,7))
        reads=[];original=e.memory.read
        def read(ref,scope=''):
            if not e.memory.structural:reads.append(ref)
            return original(ref,scope)
        with patch.object(e.memory,'read',side_effect=read):e.step()
        self.assertNotIn('Index',reads);self.assertNotIn('Values[Index]',reads)
        e.memory.write('StartPB',True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('Index',1);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('Values[1]',7);e.step();self.assertTrue(e.memory.read('RunLatch'))
        self.assertEqual(e.memory.read('Values'),[None,7,None])

    def test_all_three_comparison_operands_may_be_constant(self):
        def constant(root):
            for name in ('Source','Mask','Dest'):root.find('./Controller/Tags/Tag[@Name="'+name+'"]').set('Constant','true')
        e=self.checked(types=('ULINT','USINT','DINT'),values=(7,15,7),mutate=constant)
        e.step();self.assertTrue(e.memory.read('RunLatch'))
        self.assertEqual(tuple(e.memory.read(t) for t in ('Source','Mask','Dest')),(7,15,7))

    def test_udt_members_program_aliases_and_selected_elements(self):
        def fields(root):
            c=root.find('Controller');members=E.SubElement(E.SubElement(c.find('DataTypes'),'DataType',Name='MatchPacket',Family='NoFamily',Class='User'),'Members')
            for name,dtype in (('Mask','USINT'),('Compare','LINT')):E.SubElement(members,'Member',Name=name,DataType=dtype,Dimension='0',Hidden='false')
            tag=E.SubElement(c.find('Tags'),'Tag',Name='Packet',DataType='MatchPacket',TagType='Base',Constant='true')
            struct=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='MatchPacket')
            for name,dtype,value in (('Mask','USINT',255),('Compare','LINT',-1)):E.SubElement(struct,'DataValueMember',Name=name,DataType=dtype,Value=str(value))
            E.SubElement(c.find('./Programs/Program/Tags'),'Tag',Name='View',DataType='ULINT',TagType='Alias',AliasFor='Values')
        e=self.checked(['XIC(StartPB)MEQ(View[Index],Packet.Mask,Packet.Compare)OTE(RunLatch);'],types=('ULINT','USINT','LINT'),mutate=fields)
        e.memory.write('Index',2);e.memory.write('Values[2]',9007199254741247);e.memory.write('StartPB',True);e.step()
        self.assertTrue(e.memory.read('RunLatch'));self.assertEqual(e.memory.read('Values'),[None,None,9007199254741247])

    def test_later_failure_rolls_back_comparison_coils_prior_writes_and_time(self):
        e=self.checked(['MOV(99,SpeedCommand);','MEQ(Source,Mask,Dest)OTE(RunLatch);','DIV(1,Index,SpeedCommand);'],
                       types=('ULINT','USINT','DINT'),values=(7,15,7))
        e.memory.write('Index',0);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('Index',1);e.step();self.assertTrue(e.memory.read('RunLatch'))

    @staticmethod
    def aoi_logic(root):
        import test_aoi_queues as queues
        aoi=root.find('./Controller/AddOnInstructionDefinitions/AddOnInstructionDefinition')
        aoi.find('./LocalTags/LocalTag[@Name="Stack"]').set('DataType','ULINT')
        for array in aoi.findall('.//ArrayMember[@Name="Stack"]'):
            array.set('DataType','ULINT')
        # Stack[0] supplies a wide read-only mask; Buffer is DINT InOut.
        queues.logic(root,['MEQ(Buffer[Index],Stack[0],Value)OTE(EnableOut);'])
        queues.logic(root,['AFI()MEQ(Buffer[Index],Stack[0],Value)OTE(EnableOut);'],name='EnableInFalse')

    def test_aoi_inout_and_wide_local_masks_roll_back_and_retry(self):
        import test_aoi_queues as queues
        f=queues.AOIQueueTests();f.setUp();self.addCleanup(f.doCleanups)
        e=f.checked(self.aoi_logic);e.step()
        e.memory.write('EnabledB',False);e.memory.write('IndexB',999);e.step()
        e.memory.write('EnabledB',True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('IndexB',2);e.step()

    def test_immediate_rules_remain_homogeneous_and_representable(self):
        e=self.checked(['MEQ(Source,15,7)OTE(RunLatch);'],types=('ULINT',)*3,values=(7,0,0));e.step();self.assertTrue(e.memory.read('RunLatch'))
        for types,text in ((('ULINT','USINT','DINT'),'MEQ(Source,1,Dest)'),
                           (('ULINT',)*3,'MEQ(Source,-1,Dest)'),
                           (('LINT',)*3,'MEQ(Source,16#FFFF_FFFF,Dest)'),
                           (('ULINT',)*3,'MEQ(Source,2147483648,Dest)'),
                           (('ULINT',)*3,'MEQ(Source,ULINT#7,Dest)')):
            self.assertTrue(self.engine(['AFI()'+text+'OTE(RunLatch);'],types=types,values=(7,0,7)).blockers,text)

    def test_noninteger_shape_profile_and_arithmetic_guards_remain(self):
        for types in (('ULINT','REAL','DINT'),('ULINT','BOOL','DINT')):
            self.assertTrue(self.engine(types=types,values=(7,0,7)).blockers)
        self.assertTrue(self.engine(['AFI()MEQ(Values,Mask,Dest)OTE(RunLatch);'],types=('ULINT','USINT','DINT')).blockers)
        for key,value in (('ProcessorType','1756-L75'),('MajorRev','34')):
            self.assertTrue(self.engine(types=('ULINT','USINT','DINT'),values=(7,15,7),mutate=lambda root:root.find('Controller').set(key,value)).blockers)
        self.assertTrue(self.engine(['ADD(Source,Mask,Dest);'],types=('ULINT','USINT','DINT')).blockers)
        report=self.checked(types=('ULINT','USINT','DINT')).report()['numeric_comparisons']
        self.assertEqual(set(report['meq_types']),set(TYPES));self.assertTrue(report['meq_mixed_integer_tags']);self.assertFalse(report['native_runtime_parity'])
