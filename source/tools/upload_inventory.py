"""SDK-free, read-only inventory of an owned loopback emulator.

The independent AnonymousClient performs the real TCP challenge/MAC exchange.
This reader never opens a remote target, imports an ACD, creates a project,
writes PLC data or claims a native Studio upload. It decodes bounded model
catalogs and supported scalar values; unavailable fields remain explicit.
"""
from dataclasses import dataclass
import math
import struct
import time

from .anonymous_client import AnonymousClient


class InventoryError(ValueError):
    pass


@dataclass(frozen=True)
class Limits:
    instances: int = 4096
    programs: int = 128
    pages: int = 128
    requests: int = 16384
    tasks: int = 32

    def __post_init__(self):
        for name, maximum in (('instances',4096),('programs',4096),('tasks',32),('pages',256),('requests',32768)):
            value=getattr(self,name)
            if type(value) is not int or not 1<=value<=maximum:
                raise InventoryError('Invalid inventory '+name+' limit')


def logical_path(class_id, instance, program=None):
    """Encode numeric model paths independently of the endpoint's encoder."""
    def segment(kind,value):
        if type(value) is not int or not 0<=value<=0xFFFFFFFF:
            raise InventoryError('Logical path ID is outside UDINT range')
        if value<=255:return bytes((kind,value))
        if value<=65535:return bytes((kind+1,0))+struct.pack('<H',value)
        return bytes((kind+2,0))+struct.pack('<I',value)
    prefix=b'' if program is None else segment(0x20,0x68)+segment(0x24,program)
    return prefix+segment(0x20,class_id)+segment(0x24,instance)


def decode_reply(raw, service):
    if (not isinstance(raw,bytes) or not 4<=len(raw)<=65535 or
            raw[0]!=(service|0x80) or raw[1]!=0 or 4+2*raw[3]>len(raw)):
        raise InventoryError('Malformed or mismatched CIP inventory response')
    end=4+2*raw[3]
    extra=list(struct.unpack_from('<'+'H'*raw[3],raw,4))
    return raw[2],raw[end:],extra


MAX_TASK_PROGRAMS=1028


def decode_task_program_list(data):
    """Decode the plain Task ADF's UINT count plus ordered UDINT references.

    These are Program path IDs, not array indices. Framing, uniqueness and
    bounds are checked independently; target resolution happens against the
    separately discovered Program catalog.
    """
    if not isinstance(data,bytes) or len(data)<2:
        raise InventoryError('Truncated Task Program list count')
    count=struct.unpack_from('<H',data)[0]
    if count>MAX_TASK_PROGRAMS or len(data)!=2+4*count:
        raise InventoryError('Task Program list exceeds its bound or exact framing')
    ids=list(struct.unpack_from('<'+'I'*count,data,2))
    if 0 in ids or len(set(ids))!=len(ids):
        raise InventoryError('Task Program references are zero or repeated')
    return ids


def decode_attribute_list(raw, requested, schema):
    """Preserve order/duplicates and absent fields; require exact framing."""
    status,data,extra=decode_reply(raw,3)
    result={'status':status,'additional_status':extra,'attributes':None}
    if status not in (0,0x0A):
        result['data_hex']=data.hex()
        return result
    if len(data)<2 or struct.unpack_from('<H',data)[0]!=len(requested):
        raise InventoryError('Inventory attribute count differs from its request')
    rows=[];offset=2
    for attribute in requested:
        if offset+4>len(data):raise InventoryError('Truncated inventory attribute header')
        number,field_status=struct.unpack_from('<HH',data,offset);offset+=4
        if number!=attribute:raise InventoryError('Inventory attribute order differs from its request')
        row={'attribute':number,'status':field_status,'value':None,'data_hex':None}
        if field_status==0:
            encoding=schema.get(number)
            start=offset
            if encoding=='task_program_list':
                if offset+2>len(data):raise InventoryError('Truncated Task Program list count')
                count=struct.unpack_from('<H',data,offset)[0]
                end=offset+2+4*count
                row['value']=decode_task_program_list(data[offset:end]);offset=end
            elif encoding in ('ascii16','ascii32'):
                width=2 if encoding=='ascii16' else 4
                if offset+width>len(data):raise InventoryError('Truncated inventory string length')
                size=int.from_bytes(data[offset:offset+width],'little');offset+=width
                if size>254 or offset+size>len(data):raise InventoryError('Inventory string exceeds its bound')
                text=data[offset:offset+size];offset+=size
                try:row['value']=text.decode('ascii')
                except UnicodeDecodeError as error:raise InventoryError('Inventory name is not ASCII') from error
                if b'\0' in text:raise InventoryError('Inventory name contains NUL')
            elif type(encoding) is int and encoding in (1,2,4,8,12):
                if offset+encoding>len(data):raise InventoryError('Truncated inventory attribute value')
                value=data[offset:offset+encoding];offset+=encoding
                row['value']=list(struct.unpack('<3I',value)) if encoding==12 else int.from_bytes(value,'little')
            else:
                raise InventoryError('Successful inventory attribute has no established decoder')
            row['data_hex']=data[start:offset].hex()
        rows.append(row)
    if offset!=len(data):raise InventoryError('Inventory attribute list has trailing data')
    if (status==0x0A)!=any(row['status'] for row in rows):
        raise InventoryError('Inventory general and attribute statuses disagree')
    result['attributes']=rows
    return result


def decode_instance_page(raw,cursor):
    status,data,extra=decode_reply(raw,0x4B)
    if status not in (0,6):
        return {'status':status,'instances':None,'additional_status':extra,'data_hex':data.hex()}
    if len(data)%4:raise InventoryError('Inventory instance list has a truncated UDINT')
    ids=list(struct.unpack('<'+'I'*(len(data)//4),data))
    if any(value==0 or value<cursor or index and value<=ids[index-1] for index,value in enumerate(ids)):
        raise InventoryError('Inventory instances are zero, repeated, unordered or behind the cursor')
    if status==6 and (not ids or ids[-1]==0xFFFFFFFF):
        raise InventoryError('Partial inventory page cannot advance its cursor')
    return {'status':status,'instances':ids,'additional_status':extra}


CLASS_SCHEMA={1:2,2:4,3:4}
REVISION_SCHEMA={1:2,2:2,3:4,4:4,10:4}
CONTROLLER_SCHEMA={3:2,7:2,8:2,9:1,13:4,15:1,16:2,17:1,23:1,25:4,26:4}
SYMBOL_SCHEMA={1:'ascii16',2:2,3:4,5:4,6:4,7:2,8:12,9:1,10:1,11:1,12:4,14:4}
TABLE_SCHEMA={1:12,2:2,3:4,6:2,7:4,8:4,9:2}
PROGRAM_SCHEMA={19:1,28:'ascii32'}
TASK_SCHEMA={1:'task_program_list',2:4,6:2,12:4,16:4,18:4,19:4}
ATOMS={0xC1:('BOOL','B'),0xC2:('SINT','b'),0xC3:('INT','h'),0xC4:('DINT','i'),
       0xC5:('LINT','q'),0xC6:('USINT','B'),0xC7:('UINT','H'),0xC8:('UDINT','I'),
       0xC9:('ULINT','Q'),0xCA:('REAL','f'),0xCB:('LREAL','d')}


def values(reply):
    return {row['attribute']:row['value'] for row in reply.get('attributes') or [] if row['status']==0}


def match_task_schedules(task_catalog,task_rows,program_catalog,program_rows):
    """Resolve every ordered Task reference against the observed Program IDs.

    Missing bindings and missing schedules remain unavailable. Unknown IDs
    and references shared by multiple tasks are explicit consistency errors;
    they never become empty lists or fabricated Program objects.
    """
    task_ids=task_catalog['instances'];program_ids=program_catalog['instances']
    summary={'state':'unavailable','consistent':None,
             'task_inventory_available':task_ids is not None,
             'program_inventory_available':program_ids is not None,
             'unavailable_task_instances':[],'unresolved_references':[],
             'multiply_scheduled_programs':[],'unscheduled_program_instances':None}
    if task_ids is None:return summary
    names={row['instance']:values(row['metadata']).get(28) for row in program_rows}
    known=set(program_ids or []);owners={};unavailable=program_ids is None
    for task in task_rows:
        attributes=task['metadata'].get('attributes')
        attribute=next((row for row in attributes or [] if row['attribute']==1),None)
        ids=values(task['metadata']).get(1)
        schedule={'state':'unavailable','attribute_status':attribute['status'] if attribute else None,
                  'program_instances':ids,'programs':None,'unresolved_program_instances':[]}
        task['schedule']=schedule
        if ids is None:
            unavailable=True;summary['unavailable_task_instances'].append(task['instance']);continue
        refs=[]
        for instance in ids:
            resolved=program_ids is not None and instance in known
            refs.append({'instance':instance,'name':names.get(instance),'resolved':resolved})
            if resolved:owners.setdefault(instance,[]).append(task['instance'])
            else:
                schedule['unresolved_program_instances'].append(instance)
                summary['unresolved_references'].append({'task_instance':task['instance'],
                    'program_instance':instance,'reason':'program_inventory_unavailable' if program_ids is None
                                                         else 'program_not_discovered'})
        schedule['programs']=refs
        schedule['state']='unavailable' if program_ids is None else 'unresolved' if schedule['unresolved_program_instances'] else 'resolved'
        if program_ids is None:unavailable=True
    summary['multiply_scheduled_programs']=[{'program_instance':instance,'task_instances':tasks}
                                            for instance,tasks in owners.items() if len(tasks)>1]
    errors=bool(summary['multiply_scheduled_programs'] or any(
        row['reason']=='program_not_discovered' for row in summary['unresolved_references']))
    if not unavailable and program_ids is not None:
        summary['unscheduled_program_instances']=[instance for instance in program_ids if instance not in owners]
    summary['state']='inconsistent' if errors else 'unavailable' if unavailable else 'consistent'
    summary['consistent']=False if errors else None if unavailable else True
    return summary


class _Reader:
    def __init__(self,client,limits,read_values):
        self.client=client;self.limits=limits;self.read_values=read_values;self.requests=[]

    def exchange(self,service,class_id,instance,data=b'',program=None,attribute=None):
        # Fixed read services only. In particular 0x4B is a list service only
        # for these catalog classes, never a Create/setup opcode elsewhere.
        if (service not in (1,3,0x0E,0x4B,0x4F) or
                service==0x4B and class_id not in (0x68,0x6A,0x6B,0x70) or
                service==0x4F and class_id!=0x6A or service==0x0E and attribute is None):
            raise InventoryError('Unsupported inventory read service')
        if len(self.requests)>=self.limits.requests:raise InventoryError('Inventory request budget exceeded')
        path=logical_path(class_id,instance,program)
        if attribute is not None:
            if type(attribute) is not int or not 1<=attribute<=255:
                raise InventoryError('Inventory single attribute must fit USINT')
            path+=bytes((0x30,attribute))
        request=bytes((service,len(path)//2))+path+data
        response=self.client.request(request)
        status,_,_=decode_reply(response,service)
        self.requests.append({'service':service,'class_id':class_id,'instance':instance,
                              'program_instance':program,'status':status,
                              'attribute':attribute,
                              'request_hex':request.hex(),'response_hex':response.hex()})
        return response

    def attributes(self,class_id,instance,schema,program=None):
        requested=tuple(schema)
        raw=self.exchange(3,class_id,instance,struct.pack('<'+'H'*(len(requested)+1),len(requested),*requested),program)
        return decode_attribute_list(raw,requested,schema)

    def catalog(self,class_id,program=None,max_instances=None):
        metadata=self.attributes(class_id,0,CLASS_SCHEMA,program)
        ids=[];cursor=0
        for _ in range(self.limits.pages):
            page=decode_instance_page(self.exchange(0x4B,class_id,cursor,program=program),cursor)
            if page['instances'] is None:
                return {'status':page['status'],'instances':None,'metadata':metadata}
            ids.extend(page['instances'])
            if len(ids)>min(self.limits.instances,max_instances or self.limits.instances):
                raise InventoryError('Inventory instance budget exceeded')
            if page['status']==0:
                expected=values(metadata)
                if 2 in expected and expected[2]!=max(ids,default=0) or 3 in expected and expected[3]!=len(ids):
                    raise InventoryError('Inventory class count or sparse maximum differs from its instance list')
                return {'status':0,'instances':ids,'metadata':metadata}
            cursor=ids[-1]+1
        raise InventoryError('Inventory page budget exceeded')

    def scope(self,program=None,name=None):
        symbols=self.catalog(0x6B,program);tables=self.catalog(0x6A,program)
        result={'program_instance':program,'program_name':name,'symbol_catalog':symbols,
                'data_table_catalog':tables,'symbols':None,'tables':None}
        if symbols['instances'] is None:return result
        symbol_rows=[{'instance':instance,'metadata':self.attributes(0x6B,instance,SYMBOL_SCHEMA,program)}
                     for instance in symbols['instances']]
        result['symbols']=symbol_rows
        if tables['instances'] is None:return result
        table_rows=[{'instance':instance,'metadata':self.attributes(0x6A,instance,TABLE_SCHEMA,program)}
                    for instance in tables['instances']]
        result['tables']=table_rows
        by_symbol={};symbol_ids=set(symbols['instances'])
        for table in table_rows:
            fields=values(table['metadata']);symbol=fields.get(8)
            if symbol is not None:
                if symbol not in symbol_ids or symbol in by_symbol:
                    raise InventoryError('Data Table has an absent or repeated Symbol link')
                by_symbol[symbol]=table
        for symbol in symbol_rows:
            fields=values(symbol['metadata']);table=by_symbol.get(symbol['instance'])
            symbol.update(value_state='table_unavailable',value=None)
            if table is None:continue
            table_fields=values(table['metadata'])
            for left,right in ((2,2),(8,1),(3,7)):
                if left in fields and right in table_fields and fields[left]!=table_fields[right]:
                    raise InventoryError('Symbol and Data Table descriptors disagree')
            if 12 in fields and fields[12]!=table['instance']:
                raise InventoryError('Symbol links to a different Data Table instance')
            symbol['table_instance']=table['instance']
            if not self.read_values:
                symbol['value_state']='not_requested';continue
            code=fields.get(2)
            if code not in ATOMS or fields.get(8)!=[0,0,0]:
                symbol['value_state']='non_scalar_or_unsupported_type';continue
            if any(number not in table_fields for number in (3,7)) or 7 not in fields:
                symbol['value_state']='storage_unavailable';continue
            dtype,fmt=ATOMS[code];width=struct.calcsize('<'+fmt)
            if fields[7]!=width:raise InventoryError('Scalar descriptor size differs from its atomic type')
            raw=self.exchange(0x4F,0x6A,table['instance'],struct.pack('<IH',0,width),program)
            status,data,extra=decode_reply(raw,0x4F)
            symbol['value_read']={'status':status,'additional_status':extra,'data_hex':data.hex()}
            symbol['data_type']=dtype
            if status:
                symbol['value_state']='read_failed';continue
            if len(data)!=width:raise InventoryError('Scalar read size differs from its atomic type')
            value=struct.unpack('<'+fmt,data)[0]
            if dtype=='BOOL':
                if value not in (0,1):raise InventoryError('Scalar BOOL is not zero or one')
                value=bool(value)
            symbol['value_state']='read'
            if isinstance(value,float) and not math.isfinite(value):
                symbol['value_state']='nonfinite';symbol['nonfinite']='NaN' if math.isnan(value) else 'Infinity' if value>0 else '-Infinity'
            else:symbol['value']=value
        return result

    def collect(self):
        before=self.attributes(0xAC,1,REVISION_SCHEMA)
        if before['status']:raise InventoryError('Catalog revision is unavailable')
        controller=self.attributes(0x8E,1,CONTROLLER_SCHEMA)
        # Preserve opaque GetAll/handler failures separately; there is no
        # invented aggregate or POINTER decoder to skip over unknown lengths.
        aggregate=self.exchange(1,0x8E,1)
        controller_all={'status':decode_reply(aggregate,1)[0],'response_hex':aggregate.hex()}
        handlers=[]
        for attribute in (1,6):
            raw=self.exchange(0x0E,0x8E,1,attribute=attribute)
            status,data,extra=decode_reply(raw,0x0E)
            handlers.append({'attribute':attribute,'status':status,'additional_status':extra,
                             'data_hex':data.hex(),'pointer_encoding':'UNRESOLVED'})
        programs=self.catalog(0x68)
        if programs['instances'] is not None and len(programs['instances'])>self.limits.programs:
            raise InventoryError('Inventory Program budget exceeded')
        program_rows=[];scopes=[self.scope()]
        for instance in programs['instances'] or []:
            metadata=self.attributes(0x68,instance,PROGRAM_SCHEMA)
            program_rows.append({'instance':instance,'metadata':metadata})
            scopes.append(self.scope(instance,values(metadata).get(28)))
        task_catalog=self.catalog(0x70,max_instances=self.limits.tasks)
        task_rows=None
        if task_catalog['instances'] is not None:
            task_rows=[{'instance':instance,'metadata':self.attributes(0x70,instance,TASK_SCHEMA)}
                       for instance in task_catalog['instances']]
        scheduling=match_task_schedules(task_catalog,task_rows,programs,program_rows)
        after=self.attributes(0xAC,1,REVISION_SCHEMA)
        if after!=before:raise InventoryError('Catalog revision changed during inventory')
        self.client.check_target()
        return {'evidence_scope':'owned emulator read inventory; not native Studio upload',
                'instance_id':self.client.instance,'source_l5x_sha256':self.client.source,
                'generation':self.client.generation,'catalog_consistent':True,'revision':before,
                'controller_configuration':controller,'controller_get_all':controller_all,
                'controller_handlers':handlers,
                'program_catalog':programs,'programs':program_rows,'scopes':scopes,
                'task_catalog':task_catalog,'tasks':task_rows,'scheduling_consistency':scheduling,
                'requests':self.requests,'request_count':len(self.requests),
                'scalar_values_requested':self.read_values,'values_are_one_snapshot':False,
                'project_upload_complete':False,'native_acceptance':'NOT ASSESSED'}


def collect_inventory(endpoint, *, read_values=True, limits=None):
    """Read an already-loaded, owned in-process Endpoint; never infer bindings.

    The caller supplies existing source-bound identity/program manifests.
    Unknown catalogs/attributes stay unavailable. Value reads are individually
    observed values and do not stop, start or freeze the simulation.
    """
    if type(read_values) is not bool:raise InventoryError('read_values must be boolean')
    limits=Limits() if limits is None else limits
    if not isinstance(limits,Limits):raise InventoryError('Use validated inventory limits')
    with AnonymousClient(endpoint) as client:
        client.bind()
        result=_Reader(client,limits,read_values).collect()
    # Only this client is closed. Other observers, if present, remain connected.
    deadline=time.monotonic()+.5
    while endpoint.state()['active_tcp_clients'] and time.monotonic()<deadline:
        time.sleep(.005)
    result['endpoint_clients_after_close']=endpoint.state()['active_tcp_clients']
    return result
