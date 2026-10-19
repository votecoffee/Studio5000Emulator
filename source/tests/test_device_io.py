"""Device updates commit at scan boundaries; consumers never take app.lock."""
import copy
import json
import tempfile
import threading
import unittest
from unittest.mock import patch

from logixlab.device_io import DeviceIO, DeviceIOError, MAX_PENDING
from logixlab.ethernetip import Endpoint, Session, symbol_path
from logixlab.model import ModelError, Tag
from logixlab.server import Application


class DeviceIOTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.app=Application(self.temp.name)
        self.app.command('demo',{'sample':'NetworkLab'})
        self.io=self.app.device_io;self.now=10.;self.io.clock=lambda:self.now
        self.app.command('device-io-configure',{'allow_writes':True})

    def tearDown(self):self.app.close();self.temp.cleanup()

    def transaction(self, request_id='device1', writes=None, **kwargs):
        return {'request_id':request_id,'instance_id':self.app.instance_id,'project_generation':self.app.generation,
                'writes':writes or [{'tag':'Command','value':42}],**kwargs}

    def snapshot(self):return json.loads(self.io.snapshot()[1])

    def test_readers_use_one_immutable_cache_even_while_application_lock_is_held(self):
        old=self.io.snapshot();completed=threading.Event();errors=[]
        def read():
            try:
                for _ in range(200):self.assertIs(self.io.snapshot()[1],old[1])
            except Exception as error:errors.append(error)
            finally:completed.set()
        with self.app.lock,patch.object(self.app.engine.memory,'leaves',side_effect=AssertionError('Consumer walked live memory')):
            thread=threading.Thread(target=read);thread.start()
            self.assertTrue(completed.wait(2),'Reader waited for runtime lock');thread.join()
        self.assertFalse(errors)
        self.app.command('write',{'tag':'Command','value':10})
        self.assertNotEqual(self.io.snapshot()[0],old[0])
        self.assertNotEqual(self.io.snapshot()[1],old[1])
        self.assertEqual(json.loads(old[1])['scan'],0)

    def test_queued_batch_is_visible_to_logic_only_before_next_scan(self):
        self.io.enqueue(self.transaction())
        self.assertNotEqual(self.app.engine.memory.read('Command'),42)
        self.assertEqual(self.io.receipt('device1')['status'],'queued')
        self.app.command('step',{'count':1,'dt':10})
        self.assertEqual(self.app.engine.memory.read('Observed'),42)
        receipt=self.io.receipt('device1')
        self.assertEqual((receipt['status'],receipt['applied_before_scan']),('applied',1))
        values={t['name']:t['value'] for t in self.snapshot()['tags']}
        self.assertEqual(values['Command'],42);self.assertEqual(values['Observed'],42)

    def test_entire_batch_rolls_back_if_later_value_is_invalid(self):
        before=copy.deepcopy(self.app.engine.memory.values)
        writes=[{'tag':'Command','value':99},{'tag':'ControlWord','value':1<<80}]
        self.io.enqueue(self.transaction(writes=writes))
        with self.app.lock:self.io.apply(self.app)
        self.assertEqual(self.app.engine.memory.values,before)
        self.assertEqual(self.io.receipt('device1')['status'],'rejected')

    def test_read_only_constant_hidden_and_alias_access_restrictions_are_preserved(self):
        self.app.engine.project.tags['command'].constant=True
        self.io.enqueue(self.transaction());self.app.command('step',{})
        self.assertEqual(self.io.receipt('device1')['status'],'rejected')
        self.app.engine.project.tags['command'].constant=False
        self.app.engine.project.tags['command'].external_access='Read Only'
        self.io.enqueue(self.transaction('readonly'));self.app.command('step',{})
        self.assertEqual(self.io.receipt('readonly')['status'],'rejected')
        alias=Tag('InputAlias','DINT',None,alias='Command');self.app.engine.project.tags['inputalias']=alias
        self.io.enqueue(self.transaction('alias',[{'tag':'InputAlias','value':3}]))
        self.app.command('step',{})
        self.assertEqual(self.io.receipt('alias')['status'],'rejected')

    def test_overlapping_alias_and_backing_destinations_are_rejected_atomically(self):
        alias=Tag('InputAlias','DINT',None,alias='Command');self.app.engine.project.tags['inputalias']=alias
        before=self.app.engine.memory.read('Command')
        self.io.enqueue(self.transaction(writes=[{'tag':'Command','value':1},{'tag':'InputAlias','value':2}]))
        self.app.command('step',{})
        self.assertEqual(self.io.receipt('device1')['status'],'rejected')
        self.assertEqual(self.app.engine.memory.read('Command'),before)

    def test_duplicate_requests_are_idempotent_and_conflicting_content_is_rejected(self):
        body=self.transaction();self.io.enqueue(body);self.io.enqueue(body)
        self.assertEqual(self.io.description()['pending_writes'],1)
        self.app.command('step',{})
        old=self.io.receipt('device1')
        self.assertEqual(self.io.enqueue(body),old)
        with self.assertRaises(DeviceIOError) as error:self.io.enqueue(self.transaction(writes=[{'tag':'Command','value':7}]))
        self.assertEqual(error.exception.status,409)
        self.assertEqual(self.io.description()['pending_writes'],0)

    def test_queue_bounds_and_expiration_do_not_require_a_scan(self):
        for i in range(MAX_PENDING):self.io.enqueue(self.transaction(f'q{i}',ttl_ms=100))
        with self.assertRaises(DeviceIOError) as error:self.io.enqueue(self.transaction('overflow'))
        self.assertEqual(error.exception.status,429)
        self.now+=.2
        self.assertEqual(self.io.receipt('q0')['status'],'rejected')
        self.assertEqual(self.io.description()['pending_writes'],0)
        self.io.enqueue(self.transaction('new'))

    def test_disable_and_project_replacement_cancel_pending_and_rotate_write_token(self):
        token=self.io.session()['write_token'];self.io.enqueue(self.transaction())
        self.app.command('device-io-configure',{'allow_writes':False})
        self.assertEqual(self.io.receipt('device1')['status'],'rejected')
        self.assertFalse(self.io.authorized(token,write=True))
        self.app.command('device-io-configure',{'allow_writes':True})
        body=self.transaction('stale');self.io.enqueue(body);token=self.io.session()['write_token']
        self.app.command('reset',{})
        self.assertEqual(self.io.receipt('stale')['status'],'rejected')
        self.assertFalse(self.io.authorized(token,write=True))
        with self.assertRaises(DeviceIOError):self.io.enqueue(self.transaction('wrong',project_generation=body['project_generation']))

    def test_invalid_scan_interval_cannot_consume_inputs(self):
        self.io.enqueue(self.transaction())
        with self.assertRaises(ModelError):self.app.command('step',{'dt':0})
        self.assertEqual(self.io.receipt('device1')['status'],'queued')
        self.assertNotEqual(self.app.engine.memory.read('Command'),42)

    def test_failed_scan_retains_committed_inputs_and_publishes_rolled_back_state(self):
        self.io.enqueue(self.transaction())
        with patch.object(self.app.engine,'_routine',side_effect=ModelError('test fault')):
            with self.assertRaises(ModelError):self.app.command('step',{})
        frame=self.snapshot()
        self.assertEqual(frame['scan'],0);self.assertIn('test fault',frame['fault'])
        self.assertEqual(self.io.receipt('device1')['status'],'applied')
        self.assertEqual(self.app.engine.memory.read('Command'),42)

    def test_bad_metadata_nonfinite_values_and_dynamic_paths_are_rejected(self):
        for body in (None,{},self.transaction(writes=[{'tag':'Items[Command]','value':3}]),
                     self.transaction(writes=[{'tag':'Command','value':float('nan')}]),
                     self.transaction(writes=[{'tag':'Command','value':[]}]),
                     self.transaction(ttl_ms=True),self.transaction(project_generation=True)):
            with self.assertRaises(DeviceIOError):self.io.enqueue(body)

    def test_cip_writes_publish_to_same_cache_without_consuming_device_inputs(self):
        endpoint=Endpoint(self.app,0,True).start();self.app.endpoint=endpoint
        self.io.enqueue(self.transaction())
        path=symbol_path('Command');raw=bytes((0x4D,len(path)//2))+path+bytes.fromhex('c400010007000000')
        self.assertEqual(endpoint.router.handle(raw,Session())[2],0)
        values={t['name']:t['value'] for t in self.snapshot()['tags']}
        self.assertEqual(values['Command'],7)
        self.assertEqual(self.io.receipt('device1')['status'],'queued')

    def test_snapshot_quality_and_large_integer_precision_are_explicit(self):
        tags=[{'name':'Huge','type':'LINT','value':'9223372036854775807'},
              {'name':'Unknown','type':'SINT','value':None},
              {'name':'Nonfinite','type':'REAL','value':float('inf')}]
        self.io.capture(self.app.engine,self.app.generation,tags)
        rows=self.snapshot()['tags']
        self.assertEqual(rows[0]['value'],'9223372036854775807')
        self.assertEqual([r['quality'] for r in rows],['good','unknown','bad'])


if __name__=='__main__':unittest.main()
