"""Mixed integer tag bitwise widths; independent bit-string matrix oracle."""
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as E

import test_scalar_bitwise as fixtures
from logixlab.model import ModelError

TYPES = {'SINT':(1,True),'INT':(2,True),'DINT':(4,True),'LINT':(8,True),
         'USINT':(1,False),'UINT':(2,False),'UDINT':(4,False),'ULINT':(8,False)}
TRUTH = {'AND':{'00':'0','01':'0','10':'0','11':'1'},
         'OR':{'00':'0','01':'1','10':'1','11':'1'},
         'XOR':{'00':'0','01':'1','10':'1','11':'0'}}


def pattern(dtype, byte):
    size,signed=TYPES[dtype]
    return int.from_bytes(bytes([byte])*size,'big',signed=signed)


def expected(name, a, atype, b, btype, dest):
    # Byte encoding plus Boolean truth tables provide a separate oracle from
    # the runtime's integer masks/operators; no production conversion helper.
    def bits(value,dtype):
        size,signed=TYPES[dtype]
        return ''.join(format(x,'08b') for x in value.to_bytes(size,'big',signed=signed)).zfill(64)
    x=bits(a,atype)
    text=''.join('1' if c=='0' else '0' for c in x) if name=='NOT' else ''.join(TRUTH[name][i+j] for i,j in zip(x,bits(b,btype)))
    size,signed=TYPES[dest]
    return int.from_bytes(int(text[-size*8:],2).to_bytes(size,'big'),'big',signed=signed)


class MixedBitwiseTests(unittest.TestCase):
    setUp = fixtures.ScalarBitwiseTests.setUp
    checked = fixtures.ScalarBitwiseTests.checked
    snapshot = staticmethod(fixtures.ScalarBitwiseTests.snapshot)

    def engine(self, rungs=None, *, source='UDINT', other='USINT', dest='ULINT', value=0x80000001, mask=255, index=99, mutate=None):
        def fields(root):
            root.find('./Controller/Tags/Tag[@Name="Index"]/Data/DataValue').set('Value',str(index))
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='LateValues',DataType='DINT',Dimensions='3',TagType='Base')
            E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='DINT',Dimensions='3')
            if mutate:mutate(root)
        return fixtures.ScalarBitwiseTests.engine(self,rungs or ['XIC(StartPB)OR(Inputs[Index],Mask,Results[Index]);'],
                                                 source=source,other=other,dest=dest,value=value,mask=mask,mutate=fields)

    def test_all_1536_binary_tag_type_combinations_with_two_distinct_bit_patterns(self):
        rungs=[];slots={d:[] for d in TYPES}
        for a in TYPES:
            for b in TYPES:
                for d in TYPES:
                    for op in TRUTH:
                        index=len(slots[d]);slots[d].append((op,a,b));rungs.append(f'{op}(A_{a},B_{b},Out_{d}[{index}]);')
        self.assertEqual(len(rungs),1536)
        def matrix(root):
            tags=root.find('./Controller/Tags')
            for dtype in TYPES:
                for prefix,byte in (('A',0xa5),('B',0x3c)):
                    tag=E.SubElement(tags,'Tag',Name=prefix+'_'+dtype,DataType=dtype,TagType='Base')
                    E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType=dtype,Value=str(pattern(dtype,byte)))
                tag=E.SubElement(tags,'Tag',Name='Out_'+dtype,DataType=dtype,Dimensions='193',TagType='Base')
                E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType=dtype,Dimensions='193')
        e=self.checked(rungs,mutate=matrix)
        for dtype in TYPES:self.assertEqual(e.memory.read('Out_'+dtype),[None]*193)
        for byte in (0x3c,0xc3):
            for dtype in TYPES:e.memory.write('B_'+dtype,pattern(dtype,byte))
            e.step()
            for dest,operations in slots.items():
                values=[expected(op,pattern(a,0xa5),a,pattern(b,byte),b,dest) for op,a,b in operations]
                self.assertEqual(e.memory.read('Out_'+dest),values+[None],(dest,byte))
                self.assertEqual(e.memory.read('A_'+dest),pattern(dest,0xa5));self.assertEqual(e.memory.read('B_'+dest),pattern(dest,byte))
        self.assertEqual(e.scan_count,2)

    def test_all_64_not_tag_source_destination_combinations(self):
        rungs=[]
        for ai,a in enumerate(TYPES):
            for d in TYPES:rungs.append(f'NOT(A_{a},Out_{d}[{ai}]);')
        def matrix(root):
            tags=root.find('./Controller/Tags')
            for dtype in TYPES:
                tag=E.SubElement(tags,'Tag',Name='A_'+dtype,DataType=dtype,TagType='Base')
                E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType=dtype,Value=str(pattern(dtype,0xa5)))
                tag=E.SubElement(tags,'Tag',Name='Out_'+dtype,DataType=dtype,Dimensions='9',TagType='Base')
                E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType=dtype,Dimensions='9')
        e=self.checked(rungs,mutate=matrix);e.step()
        for dest in TYPES:self.assertEqual(e.memory.read('Out_'+dest),[expected('NOT',pattern(a,0xa5),a,0,'DINT',dest) for a in TYPES]+[None])

    def test_signed_unsigned_boundaries_and_widening_narrowing_examples(self):
        for op,source,other,dest,a,b,result in (
                ('AND','SINT','UDINT','ULINT',-1,65536,0),('OR','SINT','UDINT','ULINT',-1,65536,65791),
                ('XOR','LINT','UDINT','LINT',-1,65536,-65537),
                ('OR','UDINT','ULINT','ULINT',2147483648,9007199254740993,9007201402224641),
                ('AND','ULINT','SINT','USINT',18446744073709551615,-1,255),
                ('XOR','ULINT','SINT','USINT',18446744073709551615,-1,0)):
            e=self.checked([f'{op}(Source,Mask,Results[1]);'],source=source,other=other,dest=dest,value=a,mask=b);e.step()
            self.assertEqual(e.memory.read('Results'),[None,result,None])
        e=self.checked(['NOT(Source,Results[1]);'],source='SINT',value=-1);e.step()
        self.assertEqual(e.memory.read('Results[1]'),18446744073709551360)

    def test_exact_64_bit_values_never_use_the_real_math_path(self):
        e=self.checked(['OR(Source,Mask,Results[0]);','XOR(Source,Mask,Results[1]);'],source='ULINT',other='USINT',value=9007199254740993,mask=2)
        with patch('logixlab.scalar_math.real',side_effect=AssertionError('Bitwise used REAL')):e.step()
        self.assertEqual(e.memory.read('Results')[:2],[9007199254740995,9007199254740995])

    def test_legacy_wide_immediate_forms_and_restrictions_are_preserved(self):
        e=self.checked(['AND(Source,1,Results[0]);','NOT(7,Results[1]);'],source='ULINT',other='ULINT',value=9007199254740993,mask=1)
        e.step();self.assertEqual(e.memory.read('Results')[:2],[1,18446744073709551608])
        for text in ('AND(Source,-1,Results[0]);','OR(Source,16#FFFF_FFFF,Results[0]);','NOT(2147483648,Results[0]);'):
            self.assertTrue(self.engine([text],source='ULINT',other='ULINT',mask=1).blockers,text)
        self.assertTrue(self.engine(['OR(Source,1,Results[0]);'],source='LINT',value=7).blockers)
        self.assertTrue(self.engine(['OR(Source,1.0,Results[0]);']).blockers)

    def test_false_prescan_unknown_sources_and_actual_indices_for_all_four(self):
        for name,result in (('AND',1),('OR',2147483903),('XOR',2147483902),('NOT',18446744071562067966)):
            text=f'{name}(Inputs[Index],Results[Index])' if name=='NOT' else f'{name}(Inputs[Index],Mask,Results[Index])'
            e=self.checked(['XIC(StartPB)'+text+';']);self.assertEqual(e.memory.read('Results'),[None]*3)
            reads=[];original=e.memory.read
            def read(ref,scope=''):
                if not e.memory.structural:reads.append(ref)
                return original(ref,scope)
            with patch.object(e.memory,'read',side_effect=read):e.step()
            self.assertNotIn('Index',reads);self.assertFalse(e.memory.structural)
            e.memory.write('StartPB',True);before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
            self.assertEqual(self.snapshot(e),before)
            e.memory.write('Index',1);before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
            self.assertEqual(self.snapshot(e),before)
            e.memory.write('Inputs[1]',0x80000001);e.step();self.assertEqual(e.memory.read('Results'),[None,result,None])

    def test_second_unknown_tag_is_required_and_zero_does_not_skip_other_sources(self):
        def fields(root):
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='OtherInputs',DataType='USINT',Dimensions='3',TagType='Base')
            E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='USINT',Dimensions='3')
        for name in TRUTH:
            e=self.checked([f'{name}(Source,OtherInputs[Index],Results[Index]);'],index=1,mutate=fields);before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
            self.assertEqual(self.snapshot(e),before)
            e.memory.write('OtherInputs[1]',0);e.step()
        e=self.checked(['AND(Inputs[0],Mask,Results[0]);'],mask=0);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_unknown_udt_alias_outputs_overlap_and_neighbor_guards(self):
        def fields(root):
            members=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='Packet',Family='NoFamily',Class='User'),'Members')
            for name,dtype in (('Word','ULINT'),('Guard','DINT')):E.SubElement(members,'Member',Name=name,DataType=dtype,Dimension='0')
            tags=root.find('./Controller/Tags');tag=E.SubElement(tags,'Tag',Name='Packet1',DataType='Packet',TagType='Base')
            record=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='Packet')
            E.SubElement(record,'DataValueMember',Name='Guard',DataType='DINT',Value='987')
            E.SubElement(tags,'Tag',Name='AliasWord',DataType='ULINT',TagType='Alias',AliasFor='Packet1.Word')
        e=self.checked(['OR(Source,Mask,AliasWord);','NOT(AliasWord,AliasWord);'],mutate=fields);e.step()
        self.assertEqual(e.memory.read('Packet1'),{'Word':18446744071562067712,'Guard':987})
        self.assertEqual(e.memory.read('Results'),[None]*3)

    def test_later_failure_restores_exact_values_unknowns_and_scheduler(self):
        e=self.checked(['OR(Source,Mask,Results[0]);','NOT(Source,Results[1]);','DIV(1,LateValues[0],SpeedCommand);']);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('LateValues[0]',1);e.step();self.assertEqual(e.memory.read('Results'),[2147483903,18446744071562067966,None])

    @staticmethod
    def aoi_logic(root):
        import test_aoi_queues as queues
        queues.logic(root,['NOT(Value,Stack[0])AND(Stack[0],Value,Buffer[Index]);'])
        queues.logic(root,['AFI()NOT(Value,Stack[0])AND(Stack[0],Value,Buffer[Index]);'],name='EnableInFalse')
        root.find('.//AddOnInstructionDefinition/LocalTags/LocalTag[@Name="Stack"]').set('DataType','ULINT')
        for name in ('DriverA','DriverB'):
            arr=root.find(f'./Controller/Tags/Tag[@Name="{name}"]/Data/Structure/ArrayMember[@Name="Stack"]');arr.set('DataType','ULINT')
            arr.remove(arr.find('Element[@Index="[0]"]'))

    def test_aoi_mixed_local_inout_unknowns_false_index_and_binding_recovery(self):
        import test_aoi_queues as queues
        f=queues.AOIQueueTests();f.setUp();self.addCleanup(f.doCleanups);e=f.checked(self.aoi_logic);e.step()
        self.assertEqual(e.memory.read('DriverA.Stack[0]'),18446744073709551604);self.assertEqual(e.memory.read('BufferA[1]'),0)
        e.memory.write('EnabledB',False);e.memory.write('IndexB',999);e.step()
        e.memory.write('EnabledB',True);e.memory.write('ValueA',-1);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('IndexB',2);e.step();self.assertEqual(e.memory.read('DriverA.Stack[0]'),18446744069414584320)
        self.assertEqual(e.memory.read('BufferA[1]'),0);self.assertEqual(e.memory.read('DriverA.Stack[3]'),777)

    def test_shapes_permissions_float_and_arithmetic_profiles_remain_guarded(self):
        for text in ('OR(Inputs,Mask,Results[0]);','NOT(Source,Results);','AND(StartPB,Mask,Results[0]);','OR(Missing,Mask,Results[0]);'):
            self.assertTrue(self.engine(['AFI()'+text]).blockers,text)
        self.assertTrue(self.engine(source='REAL',value=1).blockers)
        self.assertTrue(self.engine(dest='REAL').blockers)
        self.assertTrue(self.engine(source='LREAL',other='UDINT',dest='DINT',value=1).blockers)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Results"]').set('Constant','true')
        self.assertTrue(self.engine(mutate=constant).blockers)
        self.assertTrue(self.engine(['ADD(Source,Mask,Results[1]);'],source='LINT').blockers)
        for processor,version in (('1756-L75','35'),('1756-L85E','34')):
            def old(root):root.find('Controller').set('ProcessorType',processor);root.find('Controller').set('MajorRev',version);root.set('SoftwareRevision',version+'.01')
            self.assertTrue(self.engine(mutate=old).blockers)
        report=self.checked().report()['scalar_math']['bitwise'];self.assertEqual(set(report['types']),set(TYPES));self.assertFalse(report['native_precision'])


if __name__=='__main__':unittest.main()
