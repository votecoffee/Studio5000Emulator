"""Independent client transfers using a documented-attribute atomic catalog.

The small test adapter supplies LogixDriver's tag cache from attributes 1, 2, 8
and 10. It does not implement or claim native firmware-address tag upload.
"""
import argparse
import hashlib
import ipaddress
import json
import struct
import sys
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from logixlab.server import Application
from logixlab.ethernetip import Endpoint


def atomic_catalog(driver):
    from pycomm3.cip import Array,DataTypes
    tags={};start=0
    for _ in range(100):
        result=driver.generic_message(service=0x55,class_code=0x6B,instance=start,
            request_data=struct.pack('<HHHHH',4,1,2,8,10),connected=True,return_response_packet=True)
        packet=result.value;assert packet.service_status in (0,6),result.error
        data=packet.data;pos=0;previous=start-1
        while pos<len(data):
            instance,length=struct.unpack_from('<IH',data,pos);pos+=6
            name=data[pos:pos+length].decode('ascii');pos+=length
            code,*dimensions,access=struct.unpack_from('<HIIIB',data,pos);pos+=15
            assert instance>previous;previous=instance
            dim=(code>>13)&3;dtype=DataTypes.get(code&0xFF);atom=DataTypes.get(dtype)
            assert atom is not None and not code&0x8000
            count=1
            for size in dimensions[:dim]:count*=size
            tags[name]={'tag_name':name,'instance_id':instance,'tag_type':'atomic',
                'data_type':dtype,'data_type_name':dtype,'dim':dim,'dimensions':dimensions,
                'external_access':{0:'Read/Write',2:'Read Only'}[access],
                'type_class':Array(length_=count,element_type_=atom) if dim else atom}
        if packet.service_status==0:return tags
        assert previous>=start,'Enumeration did not advance';start=previous+1
    raise AssertionError('Atomic catalog pagination bound exceeded')


def check(target,advance=None):
    from pycomm3 import LogixDriver,__version__
    from pycomm3.cip import USINT
    if not ipaddress.ip_address(target.split(':')[0]).is_loopback:raise ValueError('Only loopback targets are accepted')
    with LogixDriver(target+'/0',init_tags=False) as driver:
        assert driver.name=='NetworkLab',driver.info
        tags=atomic_catalog(driver)
        assert set(tags)=={'Command','ControlWord','Observed','Transfer'}
        assert tags['Transfer']['dimensions']==[1200,0,0]
        driver._tags=tags  # Test adapter; standard native tag upload remains pending.
        access=driver.generic_message(service=0x0E,class_code=0x6B,instance=tags['Observed']['instance_id'],attribute=10,data_type=USINT)
        assert access and access.value==2,access
        original=driver.read('Transfer{1200}');assert original,original.error
        controls=driver.read('ControlWord','Command');assert all(controls),controls
        expected=[(i*7919)%2**31-1000000 for i in range(1200)]
        try:
            written=driver.write(('Transfer{1200}',expected));assert written,written.error
            read=driver.read('Transfer{1200}');assert read and read.value==expected,read.error
            # pycomm3 1.2.16 rebuilds single scalar-write packets with duplicate
            # payload bytes. Use its valid Multi Service scalar-write path.
            scalars=driver.write(('ControlWord',32),('Command',7));assert all(scalars),scalars
            # The installed client's high-level RMW encoder emits an oversized
            # AND mask. Exercise its generic CIP path with exact protocol masks.
            bits=driver.generic_message(service=0x4E,class_code=0x6B,instance=tags['ControlWord']['instance_id'],
                request_data=struct.pack('<HII',4,4,0xFFFFFFDF),connected=True)
            assert bits,bits.error
            word=driver.read('ControlWord');assert word and word.value==4,word
            if advance:advance()
            observed=driver.read('Observed');assert observed,observed.error
            if advance:assert observed.value==7,observed
            denied=driver.write(('Observed',99),('Command',7))
            assert not denied[0] and denied[1],'Read Only tag unexpectedly accepted a write'
        finally:
            assert driver.write(('Transfer{1200}',original.value))
            assert driver.write(('ControlWord',controls[0].value),('Command',controls[1].value))
            if advance:advance()
        assert driver._cfg['extended forward open'] and driver._forward_close()
    return {'client':'pycomm3.LogixDriver','client_version':__version__,'target':target,
        'catalog_adapter':'Atomic definitions from wire attributes 1, 2, 8 and 10; native address upload not used',
        'scalar_write_path':'Multi Service; pycomm3 1.2.16 single-scalar duplicate-payload path is rejected',
        'mask_write_path':'Generic CIP; installed pycomm3 1.2.16 high-level RMW emits an oversized AND mask',
        'symbols':len(tags),'large_forward_open':True,'automatic_fragmented_write_bytes':4800,
        'automatic_fragmented_read_elements':1200,'roundtrip_sha256':hashlib.sha256(struct.pack('<1200i',*expected)).hexdigest(),
        'read_modify_write_word':4,'read_only_write_rejected':True,'scan_used_network_command':bool(advance),
        'observed_after_scan':observed.value if advance else None,'inputs_restored':True,'forward_close':True,
        'studio_go_online':'UNVERIFIED'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--target');p.add_argument('--write',action='store_true');args=p.parse_args()
    if args.target:
        if not args.write:p.error('Live transfer probe requires explicit --write against a NetworkLab endpoint')
        result=check(args.target)
    else:
        with tempfile.TemporaryDirectory() as folder:
            app=Application(folder);app.command('demo',{'sample':'NetworkLab'})
            endpoint=Endpoint(app,0,True,'logix-v35-l85e').start()
            try:
                result=check(f'127.0.0.1:{endpoint.port}',lambda:app.command('step',{}))
                trace=endpoint.state(True)
                for service in ('0x53','0x52','0x4E'):
                    assert any(e.get('service')==service and e.get('status') in (0,6) for e in trace['events']),service
                result['cip_service_counts']={service:sum(e.get('service')==service for e in trace['events']) for service in ('0x53','0x52','0x4E')}
            except Exception:
                Path(args.out).with_suffix('.failure-trace.json').write_text(json.dumps(endpoint.state(True),indent=2),encoding='utf-8')
                raise
            finally:endpoint.stop();app.close()
    Path(args.out).write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
