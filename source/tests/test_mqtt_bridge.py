"""Bridge backpressure/reconnect policies without an optional MQTT dependency."""
import json
from types import SimpleNamespace
import unittest

from tools.mqtt_bridge import Bridge, HTTPSource, LatestPublisher


class Client:
    def __init__(self):self.connected=True;self.sent=[]
    def is_connected(self):return self.connected
    def publish(self,topic,payload,**kwargs):
        self.sent.append((topic,payload,kwargs))
        return SimpleNamespace(rc=0,is_published=lambda:False)


class BridgeTests(unittest.TestCase):
    def test_slow_broker_has_one_inflight_packet_and_coalesces_new_snapshots(self):
        client=Client();publisher=LatestPublisher('test')
        publisher.offer('test/snapshot',b'first',retain=True);publisher.pump(client)
        for i in range(2000):
            publisher.offer('test/snapshot',str(i).encode(),retain=True);publisher.pump(client)
        self.assertEqual(len(client.sent),1)
        self.assertEqual(len(publisher.pending),1)
        self.assertEqual(publisher.pending['test/snapshot'][0],b'1999')
        publisher.inflight.is_published=lambda:True;publisher.pump(client)
        self.assertEqual(client.sent[-1][1],b'1999')

    def test_broker_outage_never_accumulates_unbounded_messages(self):
        client=Client();client.connected=False;publisher=LatestPublisher('test')
        for i in range(500):
            publisher.offer('test/snapshot',b'latest',retain=True)
            publisher.offer('test/status',b'status',retain=True)
            publisher.offer(f'test/acks/r{i}',{'status':'applied'})
            publisher.pump(client)
        self.assertEqual(len(client.sent),0);self.assertLessEqual(len(publisher.pending),66)
        self.assertIn('test/snapshot',publisher.pending);self.assertIn('test/status',publisher.pending)
        self.assertGreater(publisher.dropped,0)

    def test_retained_commands_and_oversize_packets_cannot_enter_device_queue(self):
        bridge=Bridge(None,Client(),'test',allow_writes=True)
        bridge.on_message(None,None,SimpleNamespace(retain=True,payload=b'{}'))
        bridge.on_message(None,None,SimpleNamespace(retain=False,payload=bytes(65537)))
        self.assertTrue(bridge.commands.empty())
        for _ in range(100):bridge.on_message(None,None,SimpleNamespace(retain=False,payload=b'{}'))
        self.assertEqual(bridge.commands.qsize(),32)
        monitor=Bridge(None,Client(),'test')
        monitor.on_message(None,None,SimpleNamespace(retain=False,payload=b'{}'))
        self.assertTrue(monitor.commands.empty())

    def test_source_is_explicit_loopback_and_cannot_target_an_arbitrary_url(self):
        self.assertEqual(HTTPSource('http://127.0.0.1:8786/').url,'http://127.0.0.1:8786')
        for url in ('https://127.0.0.1:8786','http://example.com:80','http://127.0.0.1:8786/path',
                    'http://user:pw@127.0.0.1:8786','http://127.0.0.1:8786?token=secret'):
            with self.assertRaises(ValueError):HTTPSource(url)


if __name__=='__main__':unittest.main()
