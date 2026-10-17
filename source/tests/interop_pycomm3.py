"""Optional independent client acceptance. pycomm3 is not an app dependency."""
import argparse
import ipaddress
import json
import struct
import sys
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from logixlab.server import Application
from logixlab.ethernetip import Endpoint


def check(target,write=False,advance=None):
    from pycomm3 import CIPDriver,__version__
    address=target.split(':')[0]
    if not ipaddress.ip_address(address).is_loopback:raise ValueError('Acceptance probe is restricted to loopback')
    identity=CIPDriver.list_identity(target)
    assert identity and 'LogixLab' in identity['product_name'],identity
    with CIPDriver(target+'/1/0') as driver:
        symbols=[];start=0
        while True:
            result=driver.generic_message(service=0x55,class_code=0x6B,instance=start,
                request_data=struct.pack('<HHH',2,1,2),connected=False,route_path=False,
                return_response_packet=True)
            response=result.value
            assert response.service_status in (0,6),(result.error,response)
            data=response.data;pos=0
            while pos<len(data):
                instance,size=struct.unpack_from('<IH',data,pos);pos+=6
                name=data[pos:pos+size].decode('ascii');pos+=size
                dtype=struct.unpack_from('<H',data,pos)[0];pos+=2
                symbols.append({'id':instance,'name':name,'type':dtype})
            if response.service_status==0:break
            next_start=symbols[-1]['id']+1
            if next_start<=start:raise AssertionError('Enumeration did not advance')
            start=next_start
            if start>10000:raise AssertionError('Enumeration bound exceeded')
        step=next(s['id'] for s in symbols if s['name']=='Step')
        def read(instance):
            r=driver.generic_message(service=0x4C,class_code=0x6B,instance=instance,request_data=b'\1\0',connected=True)
            assert r,r.error
            code,value=struct.unpack('<Hi',r.value);assert code==0xC4;return value
        initial=read(step)
        if write:
            result=driver.generic_message(service=0x4D,class_code=0x6B,instance=step,
                request_data=struct.pack('<HHi',0xC4,1,7),connected=True)
            assert result,result.error;assert read(step)==7
            if advance:advance()
            total=next(s['id'] for s in symbols if s['name']=='AOITotal')
            after=read(total)
            if advance:assert after==7,after
            restore=driver.generic_message(service=0x4D,class_code=0x6B,instance=step,
                request_data=struct.pack('<HHi',0xC4,1,initial),connected=True)
            assert restore,restore.error
        else:after=None
        assert driver._cfg['extended forward open'],'Client fell back from Large Forward Open'
        assert driver._forward_close(),'Independent client did not complete Forward Close'
    return {'client':'pycomm3','client_version':__version__,'target':target,'identity':identity,
            'atomic_symbols':len(symbols),'large_forward_open':True,'connected_tag_read':True,
            'connected_tag_write':write,'scan_used_network_write':bool(advance),'aoi_total_after_scan':after,
            'forward_close':True,'studio_go_online':'NOT TESTED OR CLAIMED'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--target');p.add_argument('--write',action='store_true');p.add_argument('--out',required=True);args=p.parse_args()
    if args.target:result=check(args.target,args.write)
    else:
        with tempfile.TemporaryDirectory() as d:
            app=Application(d);app.command('demo',{'sample':'TextLab'});endpoint=Endpoint(app,0,True).start()
            try:result=check(f'127.0.0.1:{endpoint.port}',True,lambda:app.command('step',{}))
            finally:endpoint.stop()
    Path(args.out).write_text(json.dumps(result,indent=2,default=lambda x:x.hex() if isinstance(x,bytes) else str(x)),encoding='utf-8')
    print(json.dumps(result,indent=2,default=str))
