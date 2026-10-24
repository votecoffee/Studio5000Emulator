"""Native catalog dialect selection preserves source availability and authority."""
import copy
import struct
import unittest

from logixlab.ethernetip import Session,logical
import test_download_installation as installed
import test_download_changelog as logs


def query(class_id,attribute=1,program=None):
    path=(logical(0x20,0x68)+logical(0x24,program) if program is not None else b'')
    path+=logical(0x20,class_id)+logical(0x24,0)+logical(0x30,attribute)
    return bytes((14,len(path)//2))+path


class CatalogLayoutWireTests(logs.NamespaceFixture,unittest.TestCase):
    setUp=installed.InstallationSignedTests.setUp

    def test_native_layout_revisions_and_legacy_profiles_are_distinct_read_only_dialects(self):
        before=copy.deepcopy(self.app.state())
        for cls,native,legacy in ((0x64,6,1),(0x68,9,1),(0x69,17,1),(0x6A,6,1),(0x6B,7,1),(0x6C,5,1),(0x70,7,2)):
            with self.subTest(class_id=cls):
                self.assertEqual(self.send(query(cls)),b'\x8e\0\0\0'+struct.pack('<H',native))
                self.endpoint.native_read_only=False
                self.assertEqual(self.cip(query(cls)),b'\x8e\0\0\0'+struct.pack('<H',legacy))
                self.endpoint.native_read_only=True
                raw=query(cls);write=bytes((0x10,))+raw[1:]+bytes(2)
                self.assertNotEqual(self.send(write)[2],0)
        for key in ('tags','scan','ms','routines','controller','routine_edits'):
            self.assertEqual(self.app.state()[key],before[key])

    def test_scoped_symbol_and_table_classes_keep_dialect_and_backed_counts(self):
        for cls,revision in ((0x6A,6),(0x6B,7)):
            for parent in (None,2):
                self.assertEqual(self.send(query(cls,program=parent)),b'\x8e\0\0\0'+struct.pack('<H',revision))
                self.assertEqual(self.send(query(cls,3,parent))[2],0)
            self.assertNotEqual(self.send(query(cls,program=3))[2],0)
        self.assertEqual(self.endpoint.state()['data_table']['object_revision'],6)
        self.endpoint.native_read_only=False
        self.assertEqual(self.endpoint.state()['data_table']['object_revision'],1)

    def test_schema_revision_does_not_invent_missing_program_or_task_inventories(self):
        self.app.native_symbols=None;self.app.native_tasks=None
        for cls,revision in ((0x68,9),(0x70,7)):
            self.assertEqual(self.send(query(cls)),b'\x8e\0\0\0'+struct.pack('<H',revision))
            for attribute in (2,3):self.assertEqual(self.send(query(cls,attribute))[2],0x14)
        self.assertEqual(self.app.engine.scan_count,0)

    def test_unknown_fields_truncated_payloads_and_insufficient_reply_budget_remain_denied(self):
        for cls in (0x64,0x68,0x69,0x6A,0x6B,0x6C,0x70):
            raw=query(cls)
            self.assertEqual(self.send(query(cls,99))[2],0x14)
            self.assertNotEqual(self.send(raw+b'X')[2],0)
            self.assertNotEqual(self.cip(raw[:-1])[2],0)
            self.assertEqual(self.endpoint.router.handle(raw,Session(),limit=5)[2],0x1B)


if __name__=='__main__':unittest.main()
