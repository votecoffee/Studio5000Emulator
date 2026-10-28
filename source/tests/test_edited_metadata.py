"""Current metadata removes only accepted old-rung Comments, with guarded streams."""
from dataclasses import replace
import copy
import struct
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET

from logixlab import metadata_query as mq,rung_metadata,routine_source
from logixlab.model import ModelError
from logixlab.routine_edits import prepare
import test_edited_controller_metadata as controller
import test_native_metadata_values as wire
from test_routine_source import container,xml_source


def removal(region,program=2,routine=1):
    encoded=((region&0xFFFF)<<16)|0xFF80|(region>>16)
    return struct.pack('<IIHHHHIHHIIIH',0x301,30,0x68,program,0x6D,routine,encoded,0,0x7F,0,0,0,4)


class EditedMetadataTests(controller.EditedControllerMetadataTests):
    def setUp(self):
        super().setUp()
        comment=replace(self.text,target=rung_metadata.target(2,1,1),data=b'Old rung comment')
        self.catalog=replace(self.catalog,rows=(*self.catalog.rows,replace(comment,record_word=len(self.catalog.rows)+1)))
        self.app.native_metadata_values=self.catalog

    def replacement(self,region=42,removed=1):
        tree=xml_source();tree.find('./RLLContent/Rung').set('RegionId',str(region));raw=container(ET.tostring(tree));old=self.app.engine
        candidate,_=prepare(old,routine_source.decode(raw),('NOP();',),'MainProgram',getattr(old.project,'runtime_revision',0),
            native_source=raw,native_target=(2,1),native_metadata=() if removed is None else (removal(removed),))
        self.app.engine=candidate;return old

    def read_all(self):
        original=self.endpoint.router.read_metadata_values
        def limited(payload,native,limit):return original(payload,native,min(limit,80))
        assembly=mq.Assembly();position=0
        with patch.object(self.endpoint.router,'read_metadata_values',side_effect=limited):
            while not assembly.complete:
                raw=wire.query('all-objects',position);response=self.send(raw);query,chunk,status=wire.frame(raw,response)
                self.assertEqual(status,0);assembly.accept(query,chunk);position+=len(chunk.data)
        return assembly

    def test_observed_region_encoding_roundtrips_without_confusing_the_opaque_address_with_xml_region(self):
        for value in (1,3971,0x4BCEDA,0x7FFFFF):
            target=rung_metadata.target(2,1,value);self.assertEqual(rung_metadata.region(target),value)
            row,decoded=rung_metadata.removal(removal(value),(2,1));self.assertEqual((row.target,decoded),(target,value))
        for value in (0,True,0x800000,0xFFFFFFFF):
            with self.assertRaises(ValueError):rung_metadata.target(2,1,value)

    def test_only_exact_removed_comment_disappears_and_original_catalog_views_remain_immutable(self):
        self.installed();installed=self.app.engine.installed_download;original=installed.metadata._all;catalog=self.catalog.body('all-objects')
        before_controller=installed.metadata._controller;self.replacement();assembly=self.read_all();self.assertGreater(assembly.frames,1)
        result=mq.records(assembly.data());expected=tuple(row for row in installed.metadata.rows if row.target!=rung_metadata.target(2,1,1))
        self.assertEqual(result,expected);self.assertEqual(self.catalog.body('all-objects'),catalog)
        self.assertEqual(installed.metadata._all,original)
        self.assertEqual(wire.frame(wire.query('controller-all'),self.query())[1].data,before_controller)
        self.assertTrue(all(row.record_word==old.record_word for row,old in zip(result,expected)))

    def test_missing_removal_keeps_the_all_object_view_guarded_and_wrong_removed_region_is_atomic(self):
        self.installed();old=self.app.engine;values=copy.deepcopy(old.memory.values)
        with self.assertRaises(ModelError):self.replacement(removed=99)
        self.assertIs(self.app.engine,old);self.assertEqual(old.memory.values,values)
        self.replacement(removed=None);self.assertIsNone(self.app.engine.installed_download.edited_metadata)
        self.assertEqual(self.query('all-objects')[2],12)

    def test_next_edit_preserves_prior_removal_and_revokes_existing_metadata_cursor(self):
        self.installed();self.replacement();old=self.app.engine.installed_download.edited_metadata
        original=self.endpoint.router.read_metadata_values
        def limited(payload,native,limit):return original(payload,native,min(limit,80))
        with patch.object(self.endpoint.router,'read_metadata_values',side_effect=limited):
            _,chunk,status=wire.frame(wire.query('all-objects'),self.query('all-objects'));self.assertEqual(status,0)
            self.replacement(region=43,removed=42)
            self.assertEqual(self.query('all-objects',len(chunk.data))[2],12)
        self.assertEqual(self.read_all().data(),old.data);self.assertEqual(len(old.removals),1)
        self.assertEqual(len(self.app.engine.installed_download.edited_metadata.removals),2)

    def test_changed_view_source_or_catalog_revokes_the_metadata_stream(self):
        self.installed();self.replacement();engine=self.app.engine;installed=engine.installed_download;view=installed.edited_metadata
        engine.installed_download=replace(installed,edited_metadata=replace(view,data=view.data+b'bad'))
        self.assertEqual(self.query('all-objects')[2],12)
        engine.installed_download=installed
        self.app.native_metadata_values=replace(self.catalog);self.assertEqual(self.query('all-objects')[2],12)
        self.app.native_metadata_values=self.catalog
        engine.project.routines['mainprogram/mainroutine'].rungs[0]['nodes']=[]
        self.assertEqual(self.query('all-objects')[2],12)

    def test_detached_metadata_does_not_rescan_transfer_ram_effects_on_every_fragment(self):
        self.installed();self.replacement();installed=self.app.engine.installed_download
        with patch.object(installed.namespace._image,'read_preparation_effect',side_effect=AssertionError('RAM effect scan')):
            self.assertTrue(self.read_all().complete)
            # Actual tag/control reads retain the full transfer-effect proof.
            with self.assertRaises(AssertionError):installed.tag_bindings.check(self.app,installed)

    def test_grouped_source_checks_preserve_individual_views_and_reject_later_catalog_or_engine_changes(self):
        from logixlab.routine_read import edited_sources,source
        from logixlab.download_image import ImageError
        self.installed();self.replacement();installed=self.app.engine.installed_download
        with self.app.lock:
            expected=tuple((row.target,source(self.app,*row.target,3)) for row in installed.routine_sources.sources)
            self.assertEqual(edited_sources(self.app),expected)
            self.app.engine.fault='current fault'
            with self.assertRaises(ImageError):edited_sources(self.app)
            self.app.engine.fault=''
            stamp=self.app.native_types.source_acd_sha256;self.app.native_types.source_acd_sha256='f'*64
            with self.assertRaises(ImageError):edited_sources(self.app)
            self.app.native_types.source_acd_sha256=stamp
            self.assertEqual(edited_sources(self.app),expected)


if __name__=='__main__':unittest.main()
