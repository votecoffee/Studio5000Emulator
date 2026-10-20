"""Driver observations, zero-field provenance, bounded ioctls and scan isolation."""
import copy
import ctypes
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from logixlab.ethernet_counters import (CounterCache, CounterSnapshot, e1000e_snapshot,
                                      linux_counters, MAX_STATS)
from logixlab.ethernetip import Endpoint, Session
from logixlab.network_objects import InterfaceSnapshot
from logixlab.server import Application


def stats():
    return dict(rx_packets=100, tx_packets=200, rx_bytes=10000, tx_bytes=20000,
                rx_broadcast=3, tx_broadcast=5, rx_multicast=7, tx_multicast=15,
                rx_errors=2, tx_errors=4, tx_dropped=6, rx_missed_errors=8,
                rx_align_errors=10, rx_crc_errors=11, tx_single_coll_ok=12,
                tx_multi_coll_ok=13, tx_deferred_ok=14, tx_abort_late_coll=15,
                tx_aborted_errors=16, tx_carrier_errors=17, rx_long_length_errors=18)


class EthernetCounterTests(unittest.TestCase):
    def test_wire_packet_categories_and_diagnostic_fields_are_explicit(self):
        snapshot=e1000e_snapshot(stats(),9)
        self.assertEqual(snapshot.attributes()[4],struct.pack('<11I',10000,90,10,17,2,0,20000,180,20,6,4))
        self.assertEqual(snapshot.attributes()[5],struct.pack('<12I',10,11,12,13,0,14,15,16,0,17,18,0))
        description=snapshot.description()
        self.assertEqual(description['unimplemented_interface'],['InUnknownProtos'])
        self.assertEqual(description['unimplemented_media'],['SQETestErrors','MACTransmitErrors','MACReceiveErrors'])
        self.assertIsNone(description['interface']['InUnknownProtos'])
        self.assertFalse(description['host_counters_cleared'])
        self.assertFalse(description['atomic_driver_and_sysfs_sample'])

    def test_rollover_is_uint32_without_clamping_the_observed_uint64_values(self):
        values=stats();values['rx_bytes']=(1<<32)+123
        values['tx_single_coll_ok']=(1<<40)+5
        snapshot=e1000e_snapshot(values,0)
        self.assertEqual(struct.unpack_from('<I',snapshot.attributes()[4])[0],123)
        self.assertEqual(struct.unpack_from('<I',snapshot.attributes()[5],8)[0],5)
        self.assertEqual(snapshot.description()['interface']['InOctets'],(1<<32)+123)

    def test_torn_missing_bad_and_overflowing_samples_are_not_healthy_zero_counters(self):
        for key,value in (('rx_packets',9),('tx_packets',19),('rx_bytes',-1),
                          ('rx_errors',True),('tx_errors',1<<64),('rx_packets',None)):
            values=stats();values[key]=value
            with self.assertRaises(ValueError):e1000e_snapshot(values,0)
        values=stats();del values['rx_crc_errors']
        with self.assertRaises(ValueError):e1000e_snapshot(values,0)
        for value in (-1,True,None,1<<64):
            with self.assertRaises(ValueError):e1000e_snapshot(stats(),value)
        for snapshot in ((tuple(range(10)),tuple(range(12))),
                         (tuple([True]*11),tuple(range(12)))):
            with self.assertRaises(ValueError):CounterSnapshot(*snapshot)

    def test_read_only_ioctl_abi_retains_names_and_rejects_unbounded_or_changed_tables(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);base=root/'test0';(base/'statistics').mkdir(parents=True)
            (base/'type').write_text('1');(base/'statistics/rx_dropped').write_text('9')
            observations=stats();keys=tuple(observations);calls=[];mode=['normal']
            def ioctl(probe,operation,request):
                self.assertEqual(operation,0x8946);self.assertEqual(len(request),40)
                name,pointer=struct.unpack_from('16sP',request);self.assertEqual(name.rstrip(b'\0'),b'test0')
                cmd=struct.unpack('=I',ctypes.string_at(pointer,4))[0];calls.append(cmd)
                if cmd==3:
                    raw=bytearray(196);struct.pack_into('=I',raw,0,3)
                    raw[4:11]=b'e1000e\0'
                    if mode[0]=='driver':raw[4:11]=b'other\0\0'
                    struct.pack_into('=I',raw,180,MAX_STATS+1 if mode[0]=='bound' else len(keys))
                elif cmd==0x1B:
                    raw=struct.pack('=III',0x1B,1,len(keys))+b''.join(k.encode().ljust(32,b'\0') for k in keys)
                    if mode[0]=='duplicate':raw=raw[:44]+raw[12:44]+raw[76:]
                    if mode[0]=='length':raw=raw[:8]+struct.pack('=I',len(keys)-1)+raw[12:]
                    if mode[0]=='unterminated':raw=raw[:12]+b'x'*32+raw[44:]
                elif cmd==0x1D:
                    raw=struct.pack('=II',0x1D,len(keys))+struct.pack('='+str(len(keys))+'Q',*observations.values())
                    if mode[0]=='stats_length':raw=raw[:4]+struct.pack('=I',len(keys)-1)+raw[8:]
                else:self.fail('Setter or unexpected ethtool command')
                ctypes.memmove(pointer,bytes(raw),len(raw))
            with patch('logixlab.ethernet_counters.Path',return_value=root),patch.dict(sys.modules,{'fcntl':SimpleNamespace(ioctl=ioctl)}):
                self.assertEqual(linux_counters('test0'),e1000e_snapshot(observations,9))
                self.assertEqual(calls,[3,0x1B,0x1D])
                for value in ('driver','bound','duplicate','length','unterminated','stats_length'):
                    mode[0]=value;self.assertIsNone(linux_counters('test0'),value)
                mode[0]='normal';(base/'statistics/rx_dropped').write_text('-1')
                self.assertIsNone(linux_counters('test0'))
                (base/'type').write_text('772');self.assertIsNone(linux_counters('test0'))
        for name in ('.','..','../eth0','eth0/file','x'*16,None):self.assertIsNone(linux_counters(name))

    def test_cache_limits_repeated_polling_and_discards_stale_samples_on_provider_failure(self):
        cache=CounterCache();snapshot=e1000e_snapshot(stats(),9)
        with patch('logixlab.ethernet_counters.linux_counters',return_value=snapshot) as provider,\
             patch('logixlab.ethernet_counters.time.monotonic',return_value=10):
            self.assertFalse(cache.description()['queried'])
            self.assertEqual(cache.read('test0'),snapshot.attributes())
            self.assertEqual(cache.read('test0'),snapshot.attributes());provider.assert_called_once_with('test0')
            cache.read('test1');self.assertEqual(provider.call_count,2)
        with patch('logixlab.ethernet_counters.linux_counters',return_value=None) as provider,\
             patch('logixlab.ethernet_counters.time.monotonic',return_value=11):
            self.assertEqual(cache.read('test1'),{})
            self.assertEqual(cache.read('test1'),{});provider.assert_called_once()
            self.assertFalse(cache.description()['available']);self.assertIsNone(cache.description()['captured_at'])
        with patch('logixlab.ethernet_counters.linux_counters',return_value=snapshot) as provider,\
             patch('logixlab.ethernet_counters.time.monotonic',return_value=5):
            cache.read('test1');provider.assert_called_once()  # A backwards clock cannot retain a cached sample.

    def test_router_batches_are_cached_and_clear_setters_or_bad_reads_never_touch_host_state(self):
        with tempfile.TemporaryDirectory() as folder:
            app=Application(folder);app.command('demo',{'sample':'ConveyorDemo'})
            endpoint=Endpoint(app,0,True);before=copy.deepcopy(app.engine.memory.values)
            snapshot=e1000e_snapshot(stats(),9)
            interface=InterfaceSnapshot('127.0.0.1','255.0.0.0',name='test0')
            def cip(raw,limit=480):return endpoint.router.handle(bytes.fromhex(raw),Session(),limit=limit)
            try:
                with patch('logixlab.ethernetip.interface_snapshot',return_value=(interface,None)),\
                     patch('logixlab.ethernet_counters.linux_counters',return_value=snapshot) as provider:
                    self.assertEqual(cip('030220f624010300050004000500'),b'\x83\0\0\0'+
                        struct.pack('<3H',3,5,0)+snapshot.attributes()[5]+struct.pack('<HH',4,0)+
                        snapshot.attributes()[4]+struct.pack('<HH',5,0)+snapshot.attributes()[5])
                    self.assertEqual(cip('0e0320f624013004'),b'\x8E\0\0\0'+snapshot.attributes()[4])
                    self.assertEqual(cip('0e0320f624013005'),b'\x8E\0\0\0'+snapshot.attributes()[5])
                    self.assertEqual(cip('0e0320f624013005',51)[2],0x1B)
                    self.assertEqual(provider.call_count,1)
                    for raw,status in (('4c0320f624013004',0x0F),('4c0320f624013005',0x0F),
                        ('100320f624013004',8),('040220f624010000',8),
                        ('030220f6240102000400',0x13),('0e0320f62401300400',0x15)):
                        self.assertEqual(cip(raw)[2],status,raw)
                    self.assertEqual(provider.call_count,1)
                self.assertEqual(app.engine.memory.values,before);self.assertEqual(app.engine.scan_count,0)
            finally:app.close()


if __name__=='__main__':unittest.main()
