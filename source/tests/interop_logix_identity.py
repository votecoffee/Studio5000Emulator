"""Initialize an independent LogixDriver; full native tag upload is still pending."""
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


def check(target,profile):
    from pycomm3 import CIPDriver,LogixDriver,__version__
    if not ipaddress.ip_address(target.split(':')[0]).is_loopback:raise ValueError('Only loopback targets are accepted')
    discovery=CIPDriver.list_identity(target)
    assert discovery,discovery
    with LogixDriver(target+'/0',init_tags=False) as driver:
        assert driver.name=='TextLab',driver.info
        assert driver.revision_major==35,driver.info
        expected_code=168 if profile=='logix-v35-l85e' else 1
        expected_minor=11 if profile=='logix-v35-l85e' else 1
        assert driver.info['product_code']==expected_code,driver.info
        assert driver.info['revision']=={'major':35,'minor':expected_minor},driver.info
        result=driver.generic_message(service=3,class_code=1,instance=1,
            request_data=struct.pack('<HHHH',3,1,3,4),connected=True)
        assert result,result.error
        vendor=1 if profile=='logix-v35-l85e' else 0xFFFF
        assert result.value==struct.pack('<HHHHHHHH',3,1,0,vendor,3,0,expected_code,4)+b'\0\0'+bytes((35,expected_minor)),result.value
        info=dict(driver.info)
        try:driver.get_tag_list()
        except Exception as error:
            causes=[];cause=error
            while cause is not None:causes.append(str(cause));cause=cause.__cause__
            assert 'failed to get attribute list' in causes[0],causes
            rejected=causes
        else:raise AssertionError('Native address attributes must fail explicitly until implemented')
        assert driver._cfg['extended forward open']
        assert driver._forward_close(),'Forward Close failed'
    return {'client':'pycomm3.LogixDriver','client_version':__version__,'target':target,
        'profile':profile,'discovery':discovery,'controller_info':info,
        'init_tags':False,'controller_name':True,'identity_attribute_list':True,
        'large_forward_open':True,'forward_close':True,
        'native_tag_upload':'EXPECTED REJECTION','native_tag_upload_errors':rejected,'studio_go_online':'UNVERIFIED'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--target')
    p.add_argument('--profile',choices=('research','logix-v35-l85e'),default='research');args=p.parse_args()
    results=[]
    if args.target:results.append(check(args.target,args.profile))
    else:
        for profile in ('research','logix-v35-l85e'):
            with tempfile.TemporaryDirectory() as folder:
                app=Application(folder);app.command('demo',{'sample':'TextLab'})
                endpoint=Endpoint(app,0,False,profile).start()
                try:results.append(check(f'127.0.0.1:{endpoint.port}',profile))
                finally:endpoint.stop();app.close()
    Path(args.out).write_text(json.dumps(results,indent=2,default=str),encoding='utf-8')
    print(json.dumps(results,indent=2,default=str))
