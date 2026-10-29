"""Whole native aggregate reads stay inside one checked current allocation."""
import copy
import struct
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from logixlab.download_image import ImageError
from logixlab.installed_memory import read_words
import test_installed_constants as constants
import test_installed_memory as memory


class AggregateValueTests(unittest.TestCase):
    def fixture(self,dtype,value,fmt):
        app,router,installed,ns,key,raw=constants.ConstantShapeTests.fixture(self,dtype,value,fmt)
        app.engine.project.tags[key].constant=False
        return app,router,installed,ns,key,raw

    def test_complete_scoped_numeric_arrays_use_current_bytes_and_exact_word_counts(self):
        cases=(('DINT',[-3,0,2147483647,17],'<i','<4i'),
               ('INT',[[-32768,32767,1],[-1,9,10]],'<h','<6h'),
               ('LINT',[-2**63,2**63-1],'<q','<2q'),
               ('REAL',[[[.25,-2.5]],[[8.0,0.0]]],'<f','<4f'))
        for dtype,value,fmt,packed in cases:
            with self.subTest(dtype=dtype):
                app,router,installed,ns,key,raw=self.fixture(dtype,value,fmt);before=copy.deepcopy(value)
                with patch('logixlab.installed_memory._verified_installation',return_value=(installed,ns)) as verify:
                    self.assertEqual(read_words(app,router,0x72000000,len(raw)//4),raw)
                    self.assertEqual(verify.call_count,1);self.assertEqual(value,before)
                    if dtype=='DINT':
                        value[-1]=-87
                        self.assertEqual(read_words(app,router,0x72000000,4),struct.pack(packed,-3,0,2147483647,-87))
                        self.assertEqual(verify.call_count,2)

    def test_unknown_interior_partial_crossing_constant_and_changed_bindings_are_rejected(self):
        app,router,installed,ns,key,raw=self.fixture('DINT',[1,2,3,4],'<i')
        with patch('logixlab.installed_memory._verified_installation',return_value=(installed,ns)):
            for address,words in ((0,4),(0x72000001,4),(0x72000004,3),(0x72000000,1),
                                  (0x72000000,3),(0x72000000,5),(0x72000000,0),(0x72000000,True)):
                with self.subTest(address=address,words=words),self.assertRaises(ImageError):read_words(app,router,address,words)
            tag=app.engine.project.tags[key];tag.constant=True
            with self.assertRaises(ImageError):read_words(app,router,0x72000000,4)
            tag.constant=False;ns._tables.append(NS(key=(3,5),value_address=0x72000000))
            with self.assertRaises(ImageError):read_words(app,router,0x72000000,4)
            ns._tables.pop();installed.values.values=((key,(2,5),0x20C3,raw),)
            with self.assertRaises(ImageError):read_words(app,router,0x72000000,4)
            installed.values.values=((key,(2,5),0x20C4,raw[:-4]),)
            with self.assertRaises(ImageError):read_words(app,router,0x72000000,4)

    def test_short_signed_arrays_require_complete_rounded_words_and_zero_tail_bytes(self):
        cases=(('SINT',[-128,0,-17],'<b',bytes.fromhex('8000ef00')),
               ('INT',[-32768,0,-22222],'<h',bytes.fromhex('0080000032a90000')),
               ('SINT',[-3,-1,0,1,-55],'<b',bytes.fromhex('fdff0001c9000000')),
               ('INT',[-32768],'<h',bytes.fromhex('00800000')),
               ('SINT',[-1],'<b',bytes.fromhex('ff000000')))
        for dtype,value,fmt,expected in cases:
            with self.subTest(dtype=dtype,size=len(value)):
                app,router,installed,ns,key,raw=self.fixture(dtype,value,fmt);before=copy.deepcopy(value)
                with patch('logixlab.installed_memory._verified_installation',return_value=(installed,ns)):
                    words=(len(raw)+3)//4
                    self.assertEqual(read_words(app,router,0x72000000,words),expected)
                    self.assertEqual(value,before);self.assertEqual(len(expected),4*words)
                    for wrong in (0,words+1):
                        with self.assertRaises(ImageError):read_words(app,router,0x72000000,wrong)
                    if words>1:
                        with self.assertRaises(ImageError):read_words(app,router,0x72000000,words-1)

    def test_tail_padding_never_reads_adjacent_storage_or_grants_interior_address_access(self):
        value=[1,2,-1];app,router,installed,ns,key,raw=self.fixture('SINT',value,'<b')
        ns._tables.append(NS(key=(2,8),value_address=0x72000003))
        installed.values.values+=(("neighbor",(2,8),0xC2,b'\xa5'),)
        original=app.engine.memory.read;reads=[]
        def read(ref):reads.append(ref);return original(ref)
        app.engine.memory.read=read
        with patch('logixlab.installed_memory._verified_installation',return_value=(installed,ns)):
            self.assertEqual(read_words(app,router,0x72000000,1),bytes.fromhex('0102ff00'))
            self.assertEqual(reads,[app.engine.project.tags[key].key])
            for address in (0x72000001,0x72000002,0x72000003):
                with self.assertRaises(ImageError):read_words(app,router,address,1)

    def test_changed_array_shapes_do_not_return_initial_values_or_synthetic_padding(self):
        value=[1,2,3,4];app,router,installed,ns,key,raw=self.fixture('DINT',value,'<i');value.pop()
        with patch('logixlab.installed_memory._verified_installation',return_value=(installed,ns)):
            with self.assertRaises(ImageError):read_words(app,router,0x72000000,4)


class AggregateStructureTests(unittest.TestCase):
    setUp=constants.ConstantStructureTests.setUp
    tearDown=constants.ConstantStructureTests.tearDown

    def test_complete_native_layout_and_every_member_access_are_checked(self):
        router,installed,ns,raw=constants.ConstantStructureTests.installed(self,'machine')
        self.app.engine.project.tags['machine'].constant=False
        with patch('logixlab.installed_memory._verified_installation',return_value=(installed,ns)):
            self.assertEqual(read_words(self.app,router,0x72000000,len(raw)//4),raw)
            current=self.app.engine.memory.values['machine'];current['History'][11]['Samples'][7]+=1
            changed=read_words(self.app,router,0x72000000,len(raw)//4);self.assertNotEqual(changed,raw)
            self.app.engine.project.udts['axisstate'].find('./Members/Member[@Name="Command"]').set('ExternalAccess','None')
            from logixlab.ethernetip import CIPError
            with self.assertRaises(CIPError):read_words(self.app,router,0x72000000,len(raw)//4)


class AggregateWireBudgetTests(memory.controls.logs.NamespaceFixture,unittest.TestCase):
    setUp=memory.InstalledMemoryTests.setUp
    read_value=memory.InstalledMemoryTests.read_value

    def test_full_reply_budget_is_required_before_resolving_or_reading_value(self):
        original=self.endpoint.router.native_read
        def limited(inner,session,native,depth,limit,budget,**kwargs):
            return original(inner,session,native,depth,15,budget,**kwargs)
        with patch('logixlab.installed_memory.read_words',return_value=bytes(12)) as read:
            with patch.object(self.endpoint.router,'native_read',side_effect=limited):
                self.assertEqual(self.read_value(words=3)[2],0x1B);read.assert_not_called()
            self.assertEqual(self.read_value(words=3),bytes.fromhex('cc000000')+bytes(12))
            self.assertEqual(read.call_count,1)


if __name__=='__main__':unittest.main()
