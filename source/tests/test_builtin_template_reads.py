"""Source-checked TIMER/COUNTER discovery reads current interpreter values."""
import copy
from dataclasses import replace
import struct
import tempfile
from types import SimpleNamespace as NS
import unittest

from logixlab.download_installation import InstalledDownload
from logixlab.ethernetip import CIPError,Endpoint,Session,logical,symbol_path
from logixlab.model import ModelError,Tag
from logixlab.native_project import NativeProjectIdentity
from logixlab.native_templates import NativeTemplates
from logixlab.native_types import NativeTypes
from logixlab.server import Application
from logixlab.template_staging import Attributes,Template
import test_download_values as values


def snapshot(project):
    """Synthetic definitions with the same checked member-location dialect."""
    types=[];ids={};rows=[]
    for dtype in ('TIMER','COUNTER'):
        native=values.builtins(dtype);source=native.types[dtype.casefold()]
        instance=native.type_ids[dtype.casefold()];types.append(source);ids[dtype.casefold()]=instance
        info=b''.join(struct.pack('<HHI',m.bit%8 if m.bit is not None else 0,
            0xC1 if m.dtype=='BOOL' else 0xC4,m.offset+(m.bit//8 if m.bit is not None else 0)) for m in source.members)
        raw=info+(dtype+';opaque\0'+'\0'.join(m.name for m in source.members)+'\0').encode()
        raw+=b'\xED'*(-(len(raw)+3)%4)+b'XYZ'
        rows.append(Template(instance,(len(raw)+20)//4,Attributes(instance,len(source.members),12,7,1),raw))
    native=NativeTypes('a'*64,project.sha256,types,ids)
    return native,tuple(rows),NativeTemplates(native,rows)


class BuiltinTemplateReadTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.app=Application(self.tmp.name);self.addCleanup(self.app.close)
        self.app.command('demo',{'sample':'ConveyorDemo'})
        self.endpoint=Endpoint(self.app,0,False,'logix-v35-l85e',native_read_only=True);self.router=self.endpoint.router
        self.session=Session(handle=1,generation=self.app.generation)
        self.native,self.rows,self.snapshot=snapshot(self.app.engine.project)
        self.app.native_types=self.native;self.app.native_templates=self.snapshot

    def cip(self,service,path,data=b'',limit=480):
        return self.router.handle(bytes((service,len(path)//2))+path+data,self.session,limit=limit)

    def test_exact_source_definitions_ids_and_current_table_values_without_scans(self):
        engine=self.app.engine;before=copy.deepcopy(self.app.state())
        timer=dict(PRE=1000,ACC=123,EN=True,TT=False,DN=True)
        counter=dict(PRE=5,ACC=-1,CU=True,CD=True,DN=False,OV=True,UN=True)
        for name,value in (('StartDelay',timer),('Parts',counter)):
            for member,scalar in value.items():engine.memory.write(name+'.'+member,scalar)
            symbol=next(s for s in self.router.symbols() if s['name']==name)
            dtype='TIMER' if name=='StartDelay' else 'COUNTER';saved=next(t for t in self.rows if t.instance==self.native.type_ids[dtype.lower()])
            template=self.router.templates().for_type(dtype)
            self.assertEqual(symbol['type'],0x8000|saved.instance)
            path=b'\x20\x6c'+logical(0x24,saved.instance)
            self.assertEqual(self.cip(0x4C,path,struct.pack('<IH',0,65535))[4:],saved.definition)
            self.assertEqual(template.attributes()[6],b'\7\0');self.assertEqual(template.attributes()[8],b'\1')
            expected=values.encode_value(dtype,value,self.native)[1]
            self.assertEqual(self.cip(0x4C,symbol_path(name),b'\1\0')[8:],expected)
            cell=self.router.scalar_storage().by_ref[name.lower()]
            self.assertEqual(self.cip(0x4F,b'\x20\x6a'+logical(0x24,symbol['id']),struct.pack('<IH',0,12))[4:],expected)
            self.assertEqual(self.router.scalar_storage().read(cell.value_address,12,engine.memory.read),expected)
        after=self.app.state()
        for key in ('scan','ms','controller','routines'):self.assertEqual(before[key],after[key])
        self.assertNotEqual(self.cip(0x4C,symbol_path('StartDelay.Control'),b'\1\0')[2],0)

    def test_arrays_fragments_and_flags_keep_separate_current_backing(self):
        project=self.app.engine.project;memory=self.app.engine.memory
        a=dict(PRE=10,ACC=1,EN=True,TT=True,DN=False);b=dict(PRE=20,ACC=2,EN=False,TT=False,DN=True)
        tag=Tag('Delays','TIMER',[a,b]);project.tags['delays']=tag;memory.values['delays']=copy.deepcopy(tag.value)
        symbol=next(s for s in self.router.symbols() if s['name']=='Delays')
        self.assertEqual(symbol['dimensions'],[2,0,0])
        expected=struct.pack('<IiiIii',0xC0000000,10,1,0x20000000,20,2)
        self.assertEqual(self.cip(0x4C,symbol_path('Delays'),b'\2\0')[8:],expected)
        self.assertEqual(self.cip(0x52,symbol_path('Delays'),struct.pack('<HI',2,11),limit=15)[8:],expected[11:18])
        memory.write('Delays[1].DN',False)
        self.assertEqual(self.router.scalar_storage().by_ref['delays'].value(memory.read),expected[:12]+struct.pack('<Iii',0,20,2))
        self.assertEqual(self.cip(0x4D,symbol_path('Delays'),bytes(28))[2],15)

    def test_ordinary_model_and_missing_snapshots_do_not_invent_builtin_templates(self):
        self.endpoint.native_read_only=False
        self.assertNotIn('StartDelay',{s['name'] for s in self.router.symbols()})
        self.endpoint.native_read_only=True;self.app.native_templates=None
        self.assertNotIn('Parts',{s['name'] for s in self.router.symbols()})
        self.assertEqual(self.cip(0x4C,symbol_path('Parts'),b'\1\0')[2],8)

    def test_installed_definitions_supply_catalog_and_revoke_changed_definition_or_source(self):
        project=self.app.engine.project;identity=NativeProjectIdentity('a'*64,project.sha256,1,1,1,1,1,1)
        self.app.native_project_identity=identity;self.app.native_templates=None
        image=NS(templates=self.rows);installed=InstalledDownload(identity,project,NS(_image=image),identity,(),None,None)
        self.app.engine.installed_download=installed
        catalog=self.router.templates();self.assertIsNotNone(catalog.for_type('TIMER'))
        self.assertIs(self.router.templates(),catalog)
        image.templates=(replace(self.rows[0],definition=bytes(len(self.rows[0].definition))),self.rows[1])
        with self.assertRaises(CIPError):self.router.templates()
        image.templates=self.rows;self.native.type_ids['timer']-=1
        with self.assertRaises(ModelError):self.router.templates()

    def test_noncanonical_builtin_layout_or_member_access_is_not_bound(self):
        source=self.native.types['timer']
        for changed in (replace(source,members=(*source.members[:-1],replace(source.members[-1],bit=28))),
                        replace(source,members=(replace(source.members[0],hidden=False),*source.members[1:])),
                        replace(source,members=(replace(source.members[0],access='None'),*source.members[1:]))):
            native=NativeTypes('a'*64,self.app.engine.project.sha256,[changed,self.native.types['counter']],self.native.type_ids)
            with self.assertRaises(ModelError):NativeTemplates(native,self.rows).bind(self.app.engine.project,native)


if __name__=='__main__':unittest.main()
