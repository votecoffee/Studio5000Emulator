"""SDK-free, read-only inventory of an owned loopback emulator.

The independent AnonymousClient performs the real TCP challenge/MAC exchange.
This reader never opens a remote target, imports an ACD, creates a project,
writes PLC data or claims a native Studio upload. It decodes bounded model
catalogs, Template definitions and bounded values; unavailable fields remain explicit.
"""
from dataclasses import asdict,dataclass
import hashlib
import math
import struct
import time

from .anonymous_client import AnonymousClient
from logixlab.template_layout import decode as decode_template,LayoutError

MAX_VALUE_BYTES=32768
MAX_TEMPLATE_BYTES=32768
MAX_TOTAL_TEMPLATE_BYTES=1024*1024


class InventoryError(ValueError):
    pass


@dataclass(frozen=True)
class Limits:
    instances: int = 4096
    programs: int = 128
    pages: int = 128
    requests: int = 16384
    tasks: int = 32
    routines: int = 4096
    templates: int = 1024
    aois: int = 1024

    def __post_init__(self):
        for name, maximum in (('instances',4096),('programs',4096),('tasks',32),('routines',4096),('templates',1024),('aois',1024),('pages',256),('requests',32768)):
            value=getattr(self,name)
            if type(value) is not int or not 1<=value<=maximum:
                raise InventoryError('Invalid inventory '+name+' limit')


def logical_path(class_id, instance, program=None, *, aoi=None):
    """Encode numeric model paths independently of the endpoint's encoder."""
    def segment(kind,value):
        if type(value) is not int or not 0<=value<=0xFFFFFFFF:
            raise InventoryError('Logical path ID is outside UDINT range')
        if value<=255:return bytes((kind,value))
        if value<=65535:return bytes((kind+1,0))+struct.pack('<H',value)
        return bytes((kind+2,0))+struct.pack('<I',value)
    if aoi is not None and (program is not None or class_id!=0x6D or type(aoi) is not int or not 1<=aoi<=0xFFFFFFFF):
        raise InventoryError('AOI scope requires one numeric AOI parent and Executable child')
    prefix=(segment(0x20,0x338)+segment(0x24,aoi) if aoi is not None else
            b'' if program is None else segment(0x20,0x68)+segment(0x24,program))
    return prefix+segment(0x20,class_id)+segment(0x24,instance)


def decode_reply(raw, service):
    if (not isinstance(raw,bytes) or not 4<=len(raw)<=65535 or
            raw[0]!=(service|0x80) or raw[1]!=0 or 4+2*raw[3]>len(raw)):
        raise InventoryError('Malformed or mismatched CIP inventory response')
    end=4+2*raw[3]
    extra=list(struct.unpack_from('<'+'H'*raw[3],raw,4))
    return raw[2],raw[end:],extra


MAX_TASK_PROGRAMS=1028
MAX_EXECUTABLE_DESCRIPTION_BYTES=128


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
            elif encoding=='null32':
                if data[offset:offset+4]!=bytes(4):raise InventoryError('Unsupported nonnull Template code reference')
                offset+=4;row['encoding']='NULL_UINT32'
            elif encoding in ('ascii16','ascii32','description16'):
                width=4 if encoding=='ascii32' else 2
                if offset+width>len(data):raise InventoryError('Truncated inventory string length')
                size=int.from_bytes(data[offset:offset+width],'little');offset+=width
                maximum=MAX_EXECUTABLE_DESCRIPTION_BYTES if encoding=='description16' else 254
                if size>maximum or offset+size>len(data):raise InventoryError('Inventory string exceeds its bound')
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
# Only the software model's exact null Multiply Code reference is decoded.
# Other references retain no inferred execution or address semantics.
TEMPLATE_SCHEMA={1:2,2:2,4:4,5:4,6:2,7:'null32',8:1}
AOI_SCHEMA={1:2,12:2,13:2,19:'ascii16',21:'ascii16'}
PROGRAM_SCHEMA={19:1,27:4,28:'ascii32'}
TASK_SCHEMA={1:'task_program_list',2:4,6:2,12:4,16:4,18:4,19:4}
# Only the legacy Description attribute has an established source decoder.
# Successful values for the unknown fields are rejected rather than skipped
# using an invented Type, UID or compiled-address representation.
EXECUTABLE_SCHEMA={1:None,2:None,4:None,6:None,7:'description16'}
ATOMS={0xC1:('BOOL','B'),0xC2:('SINT','b'),0xC3:('INT','h'),0xC4:('DINT','i'),
       0xC5:('LINT','q'),0xC6:('USINT','B'),0xC7:('UINT','H'),0xC8:('UDINT','I'),
       0xC9:('ULINT','Q'),0xCA:('REAL','f'),0xCB:('LREAL','d')}


def values(reply):
    return {row['attribute']:row['value'] for row in reply.get('attributes') or [] if row['status']==0}


def array_shape(code,dimensions):
    """Check the Symbol rank against its three padded UDINT dimensions."""
    if (type(code) is not int or not 0<=code<=0xFFFF or not isinstance(dimensions,(list,tuple))
            or len(dimensions)!=3 or any(type(d) is not int or not 0<=d<=0xFFFFFFFF for d in dimensions)):
        raise InventoryError('Invalid value type or dimensions')
    shape=tuple(d for d in dimensions if d)
    if tuple(dimensions)!=shape+(0,)*(3-len(shape)) or (code>>13)&3!=len(shape):
        raise InventoryError('Value dimensions disagree with encoded rank')
    return shape


def decode_atomic_value(data,code,shape):
    """Decode row-major atoms, preserving JSON-safe locations of nonfinite reals."""
    if code not in ATOMS or not isinstance(shape,tuple) or len(shape)>3 or any(type(d) is not int or d<=0 for d in shape):
        raise InventoryError('Unsupported atomic value shape')
    dtype,fmt=ATOMS[code];count=math.prod(shape);width=struct.calcsize('<'+fmt)
    if code==0xC1 and shape:raise InventoryError('Packed BOOL arrays have no inventory decoder')
    if not isinstance(data,bytes) or not 1<=count*width<=MAX_VALUE_BYTES or len(data)!=count*width:
        raise InventoryError('Value read size differs from its declared atomic shape')
    items=[];nonfinite=[]
    for index,(value,) in enumerate(struct.iter_unpack('<'+fmt,data)):
        if dtype=='BOOL':
            if value not in (0,1):raise InventoryError('Scalar BOOL is not zero or one')
            value=bool(value)
        if isinstance(value,float) and not math.isfinite(value):
            coordinates=[];position=index
            for dimension in reversed(shape):coordinates.append(position%dimension);position//=dimension
            label='NaN' if math.isnan(value) else 'Infinity' if value>0 else '-Infinity'
            nonfinite.append({'index':list(reversed(coordinates)),'value':label});value=None
        items.append(value)
    def reshape(offset,depth):
        if depth==len(shape):return items[offset]
        stride=math.prod(shape[depth+1:])
        return [reshape(offset+i*stride,depth+1) for i in range(shape[depth])]
    return reshape(0,0),nonfinite


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
    def __init__(self,client,limits,read_values,*,saved_templates=False):
        self.client=client;self.limits=limits;self.read_values=read_values;self.requests=[]
        self.saved_templates=saved_templates
        self.template_rows={};self.template_catalog=None;self.template_bytes=0;self.template_reserved_bytes=0

    def exchange(self,service,class_id,instance,data=b'',program=None,attribute=None,*,aoi=None):
        # Fixed read services only. In particular 0x4B is a list service only
        # for these catalog classes, never a Create/setup opcode elsewhere.
        if (service not in (1,3,0x0E,0x4B,0x4C,0x4F) or
                service==0x4B and class_id not in (0x68,0x6A,0x6B,0x6C,0x6D,0x70,0x338) or
                service==0x4C and class_id!=0x6C or class_id==0x6C and program is not None or
                class_id==0x6D and aoi is None and (type(program) is not int or not 1<=program<=0xFFFFFFFF) or
                service==0x4F and class_id!=0x6A or service==0x0E and attribute is None):
            raise InventoryError('Unsupported inventory read service')
        if len(self.requests)>=self.limits.requests:raise InventoryError('Inventory request budget exceeded')
        path=logical_path(class_id,instance,program,aoi=aoi)
        if attribute is not None:
            if type(attribute) is not int or not 1<=attribute<=255:
                raise InventoryError('Inventory single attribute must fit USINT')
            path+=bytes((0x30,attribute))
        request=bytes((service,len(path)//2))+path+data
        response=self.client.request(request)
        status,_,_=decode_reply(response,service)
        self.requests.append({'service':service,'class_id':class_id,'instance':instance,
                              'program_instance':program,'aoi_instance':aoi,'status':status,
                              'attribute':attribute,
                              'request_hex':request.hex(),'response_hex':response.hex()})
        return response

    def attributes(self,class_id,instance,schema,program=None,*,aoi=None):
        requested=tuple(schema)
        raw=self.exchange(3,class_id,instance,struct.pack('<'+'H'*(len(requested)+1),len(requested),*requested),program,aoi=aoi)
        return decode_attribute_list(raw,requested,schema)

    def catalog(self,class_id,program=None,max_instances=None,*,aoi=None):
        metadata=self.attributes(class_id,0,CLASS_SCHEMA,program,aoi=aoi)
        ids=[];cursor=0
        for _ in range(self.limits.pages):
            page=decode_instance_page(self.exchange(0x4B,class_id,cursor,program=program,aoi=aoi),cursor)
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

    def templates(self):
        self.template_catalog=self.catalog(0x6C,max_instances=self.limits.templates)
        rows=None if self.template_catalog['instances'] is None else []
        names=set()
        for instance in self.template_catalog['instances'] or []:
            if instance>0xFFF:raise InventoryError('Template instance exceeds its Symbol type field')
            metadata=self.attributes(0x6C,instance,TEMPLATE_SCHEMA);fields=values(metadata)
            row={'instance':instance,'metadata':metadata,'definition_state':'metadata_unavailable','definition':None,
                 'unavailable_attributes':[item['attribute'] for item in metadata.get('attributes') or [] if item['status']]}
            rows.append(row);self.template_rows[instance]=row
            if any(number not in fields for number in (2,4,5)):continue
            size=4*fields[4]-20;compact=size-3
            if not (1<=fields[2]<=4096 and 1<=fields[5]<=MAX_VALUE_BYTES and 1<=compact<size<=MAX_TEMPLATE_BYTES):
                raise InventoryError('Template sizes or member count exceed inventory bounds')
            if self.template_reserved_bytes+size>MAX_TOTAL_TEMPLATE_BYTES:raise InventoryError('Template aggregate byte budget exceeded')
            self.template_reserved_bytes+=size;data=bytearray();row['definition_state']='reading'
            for _ in range(self.limits.pages):
                remaining=size-len(data)
                raw=self.exchange(0x4C,0x6C,instance,struct.pack('<IH',len(data),remaining))
                status,chunk,extra=decode_reply(raw,0x4C)
                if status not in (0,6):
                    row.update(definition_state='read_failed',definition_error={'status':status,'additional_status':extra});break
                if not chunk or len(chunk)>remaining:raise InventoryError('Template read has empty or oversized progress')
                data.extend(chunk);self.template_bytes+=len(chunk)
                if status==0 and len(data)!=size:raise InventoryError('Template read ended before its advertised aligned extent')
                if status==6 and len(data)==size:raise InventoryError('Template partial status continues beyond its allocation')
                if status==0:
                    if not self.saved_templates and data[-3:]!=bytes(3):raise InventoryError('Template reserved alignment bytes are nonzero')
                    try:definition=decode_template(bytes(data),fields[2])
                    except LayoutError as error:raise InventoryError('Invalid Template definition: '+error.reason) from error
                    if definition.name.lower() in names:raise InventoryError('Template names are repeated')
                    names.add(definition.name.lower())
                    row.update(definition_state='read',definition={'name':definition.name,
                        'members':[asdict(member) for member in definition.members],
                        'trailer_bytes':definition.trailer_bytes,'compact_bytes':None if self.saved_templates else compact,'allocated_bytes':size,
                        'sha256':hashlib.sha256(data).hexdigest(),'data_hex':data.hex(),
                        'reserved_padding_zero':None if self.saved_templates else True,
                        'definition_profile':'saved_native' if self.saved_templates else 'software_model',
                        'member_offsets_interpreted':False})
                    break
            else:raise InventoryError('Template definition page budget exceeded')
        return rows

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
            code=fields.get(2);dimensions=fields.get(8)
            if code is None or dimensions is None:
                symbol['value_state']='metadata_unavailable';continue
            shape=array_shape(code,dimensions);atom=code&0x1FFF
            structured=bool(code&0x8000)
            if not structured and atom not in ATOMS or code&0x1000:
                symbol['value_state']='unsupported_type';continue
            symbol.update(array_dimensions=list(shape),element_count=math.prod(shape))
            if atom==0xC1 and shape and not structured:
                symbol['value_state']='unsupported_packed_bool_array';continue
            if any(number not in table_fields for number in (3,7)) or 7 not in fields:
                symbol['value_state']='storage_unavailable';continue
            if structured:
                template=self.template_rows.get(code&0xFFF)
                if template is None:
                    if self.template_catalog and self.template_catalog['instances'] is not None:
                        raise InventoryError('Symbol references an absent Template')
                    symbol['value_state']='template_unavailable';continue
                metadata=values(template['metadata']);width=metadata.get(5)
                if width is None or template['definition'] is None:
                    symbol['value_state']='template_unavailable';continue
                dtype=template['definition']['name'];symbol['template_instance']=template['instance']
            else:
                dtype,fmt=ATOMS[atom];width=struct.calcsize('<'+fmt)
            if fields[7]!=width:raise InventoryError('Symbol element size differs from its data type')
            size=math.prod(shape)*width
            if not 1<=size<=MAX_VALUE_BYTES:
                symbol['value_state']='value_byte_limit';continue
            raw=self.exchange(0x4F,0x6A,table['instance'],struct.pack('<IH',0,size),program)
            status,data,extra=decode_reply(raw,0x4F)
            symbol['value_read']={'status':status,'additional_status':extra,'data_hex':data.hex()}
            symbol['data_type']=dtype
            if status:
                symbol['value_state']='read_failed';continue
            if len(data)!=size:raise InventoryError('Value read size differs from its declared shape')
            if structured:
                symbol['value_state']='raw_structure';continue
            value,nonfinite=decode_atomic_value(data,atom,shape)
            symbol['value_state']='read'
            symbol['value']=value
            if nonfinite:
                symbol['value_state']='nonfinite'
                if not shape:symbol['nonfinite']=nonfinite[0]['value']
                else:symbol['nonfinite_elements']=nonfinite
        return result

    def collect(self):
        before=self.attributes(0xAC,1,REVISION_SCHEMA)
        if before['status']:raise InventoryError('Catalog revision is unavailable')
        controller=self.attributes(0x8E,1,CONTROLLER_SCHEMA)
        # GetAll remains opaque. Decode only the observed four-byte null;
        # configured or differently shaped handler references stay unresolved.
        aggregate=self.exchange(1,0x8E,1)
        controller_all={'status':decode_reply(aggregate,1)[0],'response_hex':aggregate.hex()}
        handlers=[]
        for attribute in (1,6):
            raw=self.exchange(0x0E,0x8E,1,attribute=attribute)
            status,data,extra=decode_reply(raw,0x0E)
            handlers.append({'attribute':attribute,'status':status,'additional_status':extra,
                             'data_hex':data.hex(),'pointer_encoding':
                                 'NULL_UINT32' if status==0 and data==bytes(4) else 'UNRESOLVED'})
        programs=self.catalog(0x68)
        if programs['instances'] is not None and len(programs['instances'])>self.limits.programs:
            raise InventoryError('Inventory Program budget exceeded')
        template_rows=self.templates()
        aoi_catalog=self.catalog(0x338,max_instances=self.limits.aois)
        aoi_rows=None if aoi_catalog['instances'] is None else []
        aoi_routine_count=0;unavailable_aoi_routines=[]
        for instance in aoi_catalog['instances'] or []:
            executables=self.catalog(0x6D,max_instances=self.limits.routines,aoi=instance)
            executable_rows=None
            if executables['instances'] is not None:
                aoi_routine_count+=len(executables['instances'])
                if aoi_routine_count>self.limits.routines:raise InventoryError('Inventory AOI Routine budget exceeded')
                executable_rows=[{'aoi_instance':instance,'instance':routine,
                    'metadata':self.attributes(0x6D,routine,EXECUTABLE_SCHEMA,aoi=instance)} for routine in executables['instances']]
            else:unavailable_aoi_routines.append(instance)
            aoi_rows.append({'instance':instance,'metadata':self.attributes(0x338,instance,AOI_SCHEMA),
                             'executable_catalog':{'aoi_instance':instance,**executables},'executables':executable_rows})
        program_rows=[];scopes=[self.scope()];routine_count=0;unavailable_routine_programs=[]
        for instance in programs['instances'] or []:
            metadata=self.attributes(0x68,instance,PROGRAM_SCHEMA)
            executables=self.catalog(0x6D,instance,max_instances=self.limits.routines)
            executable_rows=None
            if executables['instances'] is not None:
                routine_count+=len(executables['instances'])
                if routine_count+aoi_routine_count>self.limits.routines:raise InventoryError('Inventory scoped Routine budget exceeded')
                executable_rows=[{'program_instance':instance,'instance':routine,
                                  'metadata':self.attributes(0x6D,routine,EXECUTABLE_SCHEMA,instance)}
                                 for routine in executables['instances']]
            else:unavailable_routine_programs.append(instance)
            program_rows.append({'instance':instance,'metadata':metadata,
                                 'executable_catalog':{'program_instance':instance,**executables},
                                 'executables':executable_rows})
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
                'template_catalog':self.template_catalog,'templates':template_rows,
                'template_definition_bytes':self.template_bytes,'template_reserved_bytes':self.template_reserved_bytes,
                'structured_values_decoded':False,
                'aoi_catalog':aoi_catalog,'aois':aoi_rows,'aoi_definition_upload':False,
                'aoi_executable_inventory':{'discovered_count':aoi_routine_count,
                    'unavailable_aoi_instances':unavailable_aoi_routines,'parent_inventory_available':aoi_rows is not None,
                    'scoped_by_aoi':True,'names_inferred':False,'compiled_definition_upload':False},
                'program_catalog':programs,'programs':program_rows,'scopes':scopes,
                'executable_inventory':{'state':'unavailable' if programs['instances'] is None or
                                       unavailable_routine_programs and len(unavailable_routine_programs)==len(program_rows) else
                                       'partial' if unavailable_routine_programs else 'available',
                                       'discovered_count':routine_count,
                                       'unavailable_program_instances':unavailable_routine_programs,
                                       'scoped_by_program':True,'names_inferred':False,
                                       'compiled_definition_upload':False},
                'task_catalog':task_catalog,'tasks':task_rows,'scheduling_consistency':scheduling,
                'requests':self.requests,'request_count':len(self.requests),
                'scalar_values_requested':self.read_values,'values_requested':self.read_values,'values_are_one_snapshot':False,
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
    client=AnonymousClient(endpoint)
    try:
        with client:
            client.bind()
            result=_Reader(client,limits,read_values,saved_templates=bool(
                endpoint.native_read_only and getattr(endpoint.app,'native_templates',None))).collect()
    finally:
        # Wait for this socket's asynchronous server cleanup on both success
        # and decode failure. Other observers are never disconnected.
        deadline=time.monotonic()+.5
        while endpoint.state()['active_tcp_clients'] and time.monotonic()<deadline:
            time.sleep(.005)
    result['endpoint_clients_after_close']=endpoint.state()['active_tcp_clients']
    return result
