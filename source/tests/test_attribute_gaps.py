"""Field-level diagnostics are bounded, value-free and tied to a project load."""
import copy
import struct
import tempfile
import unittest

from logixlab.attribute_gaps import AttributeGaps, MAX_GAPS
from logixlab.ethernetip import Endpoint, Session, symbol_path
from logixlab.server import Application


class AttributeGapCollectorTests(unittest.TestCase):
    def record(self, collector, instance=1, missing=(1, 6), generation=0, scope='', program=None):
        collector.record(0x8E, instance, program, scope, missing, generation, 3)

    def test_duplicates_group_without_losing_read_counts_and_newest_order(self):
        collector=AttributeGaps()
        self.record(collector,missing=(6,1,6));self.record(collector,instance=2)
        self.record(collector,missing=(1,6))
        rows=collector.snapshot(0)
        self.assertEqual([row['instance'] for row in rows],[1,2])
        self.assertEqual(rows[0]['count'],2)
        self.assertEqual([a['id'] for a in rows[0]['attributes']],[1,6])
        self.assertEqual(rows[0]['class_name'],'Controller')
        self.assertEqual(rows[0]['attributes'][0],{'id':1,'status':0x14,'name':'Power-loss handler reference'})

    def test_capacity_evicts_oldest_and_project_generations_do_not_mix(self):
        collector=AttributeGaps()
        for instance in range(MAX_GAPS+3):self.record(collector,instance=instance)
        rows=collector.snapshot(0)
        self.assertEqual(len(rows),MAX_GAPS)
        self.assertNotIn(0,[r['instance'] for r in rows])
        self.record(collector,instance=7,generation=1)
        self.assertEqual([r['instance'] for r in collector.snapshot(1)],[7])
        self.assertTrue(all(row['generation']==0 for row in collector.snapshot(0)))
        self.assertEqual(collector.snapshot(2),[])

    def test_program_scope_and_read_service_remain_distinct(self):
        collector=AttributeGaps()
        self.record(collector);self.record(collector,program=17);self.record(collector,scope='Program:Main')
        collector.record(0x8E,1,None,'',(1,6),0,0x0E)
        self.assertEqual(len(collector.snapshot(0)),4)
        self.record(collector,missing=())
        self.assertEqual(len(collector.snapshot(0)),4)

    def test_unknown_ids_are_preserved_and_snapshots_cannot_mutate_collector(self):
        collector=AttributeGaps();collector.record(65534,70000,None,'',(65535,),0,3)
        rows=collector.snapshot(0)
        self.assertEqual(rows[0]['class_name'],'CIP object')
        self.assertEqual(rows[0]['attributes'][0]['name'],'Attribute 65535')
        rows[0]['attributes'][0]['name']='changed';rows[0]['count']=999
        self.assertEqual(collector.snapshot(0)[0]['count'],1)
        self.assertEqual(collector.snapshot(0)[0]['attributes'][0]['name'],'Attribute 65535')


class AttributeGapEndpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=Application(self.tmp.name)
        self.app.command('demo',{'sample':'TextLab'})
        self.endpoint=Endpoint(self.app,0,False,'logix-v35-l85e',native_read_only=True)
        self.router=self.endpoint.router

    def tearDown(self):self.app.close();self.tmp.cleanup()

    def cip(self,raw):return self.router.handle(bytes.fromhex(raw),Session())

    def test_partial_controller_response_records_exact_missing_ids_without_values(self):
        before=copy.deepcopy(self.app.engine.memory.values)
        raw='0302208e24010600030006000100070008001000'
        response=self.cip(raw);self.assertEqual(response[:4],b'\x83\0\x0A\0')
        self.cip(raw)
        row=self.endpoint.state()['attribute_gaps'][0]
        self.assertEqual([a['id'] for a in row['attributes']],[1,6])
        self.assertEqual(row['count'],2)
        self.assertEqual(row['class_id'],0x8E)
        self.assertNotIn('request_hex',row);self.assertNotIn('response_hex',row)
        self.assertNotIn('value',str(row))
        self.assertEqual(self.app.engine.memory.values,before)
        self.assertEqual(self.endpoint.state(True)['attribute_gaps'],self.endpoint.state()['attribute_gaps'])

    def test_single_unknown_attribute_is_recorded_and_success_or_malformed_requests_are_not(self):
        self.assertEqual(self.cip('0e03208e24013003')[2],0)
        self.assertEqual(self.endpoint.state()['attribute_gaps'],[])
        self.assertEqual(self.cip('0e03208e24013001')[2],0x14)
        self.assertEqual(self.endpoint.state()['attribute_gaps'][0]['service'],0x0E)
        for raw in ('0302208e24010000','0302208e240102000100','0e03208e2401300100','1003208e240130010000'):
            self.assertNotEqual(self.cip(raw)[2],0)
        self.assertEqual(len(self.endpoint.state()['attribute_gaps']),1)
        self.assertEqual(self.endpoint.state()['attribute_gaps'][0]['count'],1)

    def test_scoped_symbol_diagnostics_preserve_scope_and_source_replacement_hides_old_rows(self):
        path=symbol_path('Program:MainProgram')+bytes.fromhex('206b2401')
        # Use the real attribute reader; the scope must remain distinct from a
        # controller-scoped object with the same instance number.
        from logixlab.ethernetip import decode_path
        decoded=decode_path(path)
        status,_=self.router.attribute_read(3,decoded,struct.pack('<2H',1,4),{})
        self.assertEqual(status,0x0A)
        self.assertEqual(self.endpoint.state()['attribute_gaps'][0]['scope'],'Program:MainProgram')
        self.app.command('demo',{'sample':'ConveyorDemo'})
        self.assertEqual(self.endpoint.state()['attribute_gaps'],[])
        self.assertEqual(self.cip('0e03208e24013001')[2],0x14)
        self.assertEqual(self.endpoint.state()['attribute_gaps'][0]['count'],1)

    def test_new_or_stopped_endpoints_have_predictable_diagnostic_state(self):
        self.assertEqual(self.app.connectivity()['attribute_gaps'],[])
        self.assertEqual(self.endpoint.state()['attribute_gaps'],[])
        self.cip('0e03208e24013001')
        self.endpoint.stop()
        self.assertEqual(len(self.endpoint.state()['attribute_gaps']),1)
        replacement=Endpoint(self.app,0,False)
        self.assertEqual(replacement.state()['attribute_gaps'],[])


if __name__=='__main__':unittest.main()
