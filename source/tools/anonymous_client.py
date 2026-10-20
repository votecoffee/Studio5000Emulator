"""Independent test client for an owned, in-process anonymous emulator endpoint.

This never accepts a remote target. It uses a new RSA key and the emulator's
observed challenge dialect, without patching its nonce or sharing server keys.
It does not authenticate Rockwell devices or exercise Studio/SDK acceptance.
The optional cryptography package is needed only to generate the ephemeral key.
"""
import hmac
import secrets
import socket
import struct

from logixlab.ethernetip import Endpoint
from logixlab import signed_messages as signed

HEADER=struct.Struct('<HHII8sI')


class ProbeError(ValueError):pass


class AnonymousClient:
    def __init__(self,endpoint):
        if (not isinstance(endpoint,Endpoint) or not endpoint.enabled or
                endpoint.bind_address!='127.0.0.1' or not endpoint.native_read_only or
                endpoint.allow_writes or endpoint.profile!='logix-v35-l85e'):
            raise ProbeError('Select an owned loopback anonymous endpoint with writes disabled')
        self.endpoint=endpoint;self.instance=endpoint.app.instance_id
        self.source=endpoint.app.engine.project.sha256;self.generation=endpoint.app.generation;self.session=0
        self.sequence=None;self._key=None;self.socket=None
        self.check_target()
        self.socket=socket.create_connection(('127.0.0.1',endpoint.port),timeout=3)
        self.socket.settimeout(3)

    def check_target(self):
        e=self.endpoint
        if (not e.enabled or e.app.instance_id!=self.instance or e is not e.app.endpoint or
                e.app.engine.project.sha256!=self.source or e.app.generation!=self.generation or e.allow_writes or
                e.bind_address!='127.0.0.1' or not e.native_read_only):
            raise ProbeError('Owned emulator instance, endpoint, source or policy changed')

    def _read(self,size):
        data=bytearray()
        while len(data)<size:
            chunk=self.socket.recv(size-len(data))
            if not chunk:raise ProbeError('Research socket closed before its complete response')
            data.extend(chunk)
        return bytes(data)

    def _packet(self,command,body):
        self.check_target()
        if self.socket is None:raise ProbeError('Research client is closed')
        if len(body)>65535:raise ProbeError('Research packet exceeds the transport limit')
        context=secrets.token_bytes(8)
        self.socket.sendall(HEADER.pack(command,len(body),self.session,0,context,0)+body)
        fields=HEADER.unpack(self._read(HEADER.size));data=self._read(fields[1])
        if (fields[0]!=command or fields[3]!=0 or fields[4]!=context or fields[5]!=0 or
                command!=0x65 and fields[2]!=self.session):
            raise ProbeError('Unexpected research transport reply')
        self.check_target()
        return fields,data

    def exchange(self,request):
        if not self.session:raise ProbeError('Register the research transport first')
        if not isinstance(request,bytes) or not 2<=len(request)<=signed.MAX_MESSAGE:
            raise ProbeError('Research CIP request must be bounded immutable bytes')
        body=struct.pack('<IHHHHHH',0,0,2,0,0,0xB2,len(request))+request
        _,data=self._packet(0x6F,body)
        if len(data)<16 or data[:8]!=struct.pack('<IHH',0,0,2):
            raise ProbeError('Unexpected research CPF header')
        offset=8;items=[]
        for _ in range(2):
            if offset+4>len(data):raise ProbeError('Truncated research CPF item')
            kind,size=struct.unpack_from('<HH',data,offset);offset+=4
            if offset+size>len(data):raise ProbeError('Truncated research CPF data')
            items.append((kind,data[offset:offset+size]));offset+=size
        if offset!=len(data) or items[0]!=(0,b'') or items[1][0]!=0xB2:
            raise ProbeError('Unexpected research CPF reply')
        return items[1][1]

    def bind(self):
        if self._key is not None:raise ProbeError('Research client is already bound')
        try:from cryptography.hazmat.primitives.asymmetric import rsa
        except ImportError as error:raise ProbeError('Install optional cryptography for this probe') from error
        private=rsa.generate_private_key(public_exponent=65537,key_size=1024).private_numbers()
        public=private.public_numbers
        features=b''.join(struct.pack('<HH',n,1) for n in range(2,7))
        parameters=(struct.pack('<HH',0x8080,3)+public.e.to_bytes(3,'big')+
                    struct.pack('<HH',0x8081,128)+public.n.to_bytes(128,'big'))
        offer=struct.pack('<4H',8+len(features)+2+len(parameters),1,1,5)+features+b'\2\0'+parameters+bytes(128)
        header,data=self._packet(0x65,b'\1\0\0\0')
        if not header[2] or data!=b'\1\0\0\0':raise ProbeError('Research session registration failed')
        self.session=header[2]
        response=self.exchange(bytes.fromhex('4b0220642401')+offer)
        if len(response)!=134 or response[:6]!=bytes.fromhex('cb0000008000'):
            raise ProbeError('Unexpected anonymous challenge')
        value=pow(int.from_bytes(response[6:],'little'),private.d,public.n)
        if not 1<=value<1<<160:raise ProbeError('Unexpected anonymous challenge size')
        self._key=value.to_bytes(20,'little')
        acknowledgement=self.exchange(bytes.fromhex('4c02206424011400')+bytes(20))
        expected=bytes.fromhex('cc0000000500')+b''.join(struct.pack('<HI',n,1) for n in range(2,7))
        if acknowledgement!=expected:raise ProbeError('Anonymous compatibility acknowledgement failed')
        self.sequence=1
        if self.request(bytes.fromhex('5c02208e2401')+b'owned-research-client',wrapper=0x37)!=bytes.fromhex('dc000000'):
            raise ProbeError('Anonymous registration failed')
        context=self.request(bytes.fromhex('4b03210078032401')+b'owned-test-context')
        if len(context)!=8 or context[:4]!=bytes.fromhex('cb000000'):
            raise ProbeError('Anonymous context creation failed')
        if self.request(bytes.fromhex('6302208e2401')+context[4:])!=bytes.fromhex('e3000000'):
            raise ProbeError('Anonymous context binding failed')

    def _send_signed(self,body):
        if self._key is None or self.sequence is None:raise ProbeError('Bind the anonymous client first')
        raw=body+struct.pack('<I',self.sequence);raw+=hmac.digest(self._key,raw,'sha1')
        parsed=signed.parse_request(raw)
        response=self.exchange(raw)
        try:result=signed.verify_response(response,self._key,request=parsed)
        except signed.EnvelopeError as error:
            self._key=None;self.sequence=None
            raise ProbeError('Anonymous response framing, sequence or MAC failed') from error
        self.sequence+=1
        return result

    def request(self,inner,wrapper=0x36):
        if wrapper not in (0x36,0x37) or not isinstance(inner,bytes):
            raise ProbeError('Expected one immutable request in a supported wrapper')
        body=inner if wrapper==0x36 else struct.pack('<II',0x301,len(inner))+inner
        return self._send_signed(bytes((wrapper,2))+signed.ROUTER_PATH+body).inner

    def fragment(self,format_word,position,data):
        return self._send_signed(b'\x39\2'+signed.ROUTER_PATH+struct.pack('<II',format_word,position)+data)

    def transfer(self,inner,*,control=1):
        if type(control) is not int or control not in signed.TRANSFER_CONTROLS or not isinstance(inner,bytes):
            raise ProbeError('Expected one immutable request with an observed transfer control')
        return self._send_signed(b'\x39\2'+signed.ROUTER_PATH+struct.pack('<II',0x301,control)+inner).inner

    def close(self):
        self._key=None;self.sequence=None
        if self.socket:self.socket.close();self.socket=None

    def __enter__(self):return self
    def __exit__(self,*_):self.close()
