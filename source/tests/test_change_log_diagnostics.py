"""Native search failures are observable without changing the empty-history policy."""
import base64,hashlib,struct,tempfile,unittest
from pathlib import Path
from logixlab.server import Application
from logixlab.native_project import NativeProjectIdentity
from logixlab.native_session import NativeSession
from logixlab.ethernetip import Endpoint,Session


class ChangeLogDiagnosticsTests(unittest.TestCase):
    def test_empty_read_and_edited_history_guard_have_distinct_recorded_results(self):
        with tempfile.TemporaryDirectory() as folder:
            app=Application(folder)
            try:
                data=(Path(__file__).resolve().parents[1]/'samples/ConveyorDemo.L5X').read_bytes()
                identity=NativeProjectIdentity('a'*64,hashlib.sha256(data).hexdigest(),0,1,1,2,3,4,True)
                app.command('load',dict(name='test.L5X',content=base64.b64encode(data).decode(),native_project_identity=identity.manifest()))
                endpoint=Endpoint(app,0,False,'logix-v35-l85e',native_read_only=True);app.endpoint=endpoint
                native=NativeSession();native.stage='bound';cursor=struct.pack('<HH',0,2)
                query=bytes.fromhex('4f0220ac2401')+cursor
                call=lambda:endpoint.router.native_read(query,Session(),native,0,480,None)
                self.assertEqual(call(),b'\xcf\0\0\0'+cursor)
                app.engine.project.runtime_revision=1
                self.assertEqual(call(),bytes.fromhex('cf000c00'))
                self.assertEqual(endpoint.counts['native_change_log_search_queries'],2)
                rows=endpoint.state()['native_rejections'];self.assertEqual(rows[0]['reason'],'change_log_search_unavailable')
                events=[e for e in endpoint.trace_page(0,endpoint.trace_id)['events'] if e.get('kind')=='native_change_log_search']
                self.assertEqual([e['status'] for e in events],[0,12])
                self.assertTrue(all(e['history_supplied'] is False for e in events))
                self.assertEqual(app.engine.scan_count,0);self.assertIsNone(endpoint.programming_lease.owner)
            finally:app.close()


if __name__=='__main__':unittest.main()
