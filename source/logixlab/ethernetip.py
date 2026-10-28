"""Experimental local EtherNet/IP explicit-message target.

This is a protocol research endpoint, not a complete Logix controller. Unknown
services return CIP errors and are traced; no upload/download is acknowledged.
The wire implementation uses only Python's standard library.
"""
from __future__ import annotations

import copy
import math
import re
import secrets
import socket
import socketserver
import struct
import sys
import threading
import time
from collections import Counter, deque
from dataclasses import dataclass, field
from .model import ModelError,operations
from .identity import Identity
from .templates import Catalog, MAX_BYTES
from .catalog_revision import CatalogRevision
from .network_objects import interface_snapshot, port_attributes, cip_string
from .broadcast_discovery import prepare_broadcasts
from . import routine_state
from . import read_transport,routine_read
from .download_namespace import DownloadNamespace
from .download_headers import HeaderBindings
from .download_routines import RoutineBindings
from .download_map import MapBindings
from .download_changelog import ChangelogBindings
from .download_tasks import TaskBindings
from .download_controller import ControllerBindings
from .download_setup import SetupBindings,PROFILES as SETUP_PROFILES,write_profile as setup_write_profile
from .download_image import ImageError,Source
from . import metadata_query
from . import program_query
from . import alarm_catalog, attribute_gaps, controller_configuration, controller_schemas, data_table, device_metadata, edit_transfer, energy_catalog, ethernet_counters, file_manager, key_exchange, library_staging, metadata_staging, native_rejections, native_session, programming_lease, resilient_transport, signed_messages, software_clock, symbol_metadata, wall_clock

HEADER = struct.Struct('<HHII8sI')
TYPES = {'BOOL':(0xC1,'B'), 'SINT':(0xC2,'b'), 'INT':(0xC3,'h'),
         'DINT':(0xC4,'i'), 'LINT':(0xC5,'q'), 'USINT':(0xC6,'B'),
         'UINT':(0xC7,'H'), 'UDINT':(0xC8,'I'), 'ULINT':(0xC9,'Q'), 'REAL':(0xCA,'f')}
REPLY_LIMIT = 480
TRACE_EVENT_LIMIT = 2000
TRACE_PACKET_LIMIT = signed_messages.MAX_MESSAGE
TRACE_BYTE_LIMIT = 2*1024*1024  # Retained binary bytes; hex encoding uses twice this.


class CIPError(Exception):
    def __init__(self,status,detail):self.status=status;super().__init__(detail)


def need(data,size):
    if len(data)<size:raise CIPError(0x13,'Request data is too short')


def exact(data,size):
    need(data,size)
    if len(data)!=size:raise CIPError(0x15,'Request data has trailing bytes')


def reply(service,status=0,data=b''):return bytes((service|0x80,0,status,0))+data


def logical(kind,value):
    if value<256:return bytes((kind,value))
    if value<65536:return bytes((kind+1,0))+struct.pack('<H',value)
    return bytes((kind+2,0))+struct.pack('<I',value)


def symbol_path(name):
    """Client/test helper. Production parsing does not trust this encoder."""
    result=b''
    for part in name.split('.'):
        match=re.fullmatch(r'([A-Za-z_][\w:]*)(?:\[([\d,]+)\])?',part)
        if not match:raise ValueError('Static symbolic name required')
        text=match[1].encode('ascii');result+=bytes((0x91,len(text)))+text+b'\0'*(len(text)%2)
        if match[2]:
            for index in match[2].split(','):result+=logical(0x28,int(index))
    return result


@dataclass
class Path:
    class_id:int|None=None
    instance:int|None=None
    attribute:int|None=None
    symbols:list=field(default_factory=list)
    program_instance:int|None=None
    io_map_instance:int|None=None
    controller_instance:int|None=None
    aoi_instance:int|None=None
    routine_instance:int|None=None

    def reference(self,base=''):
        result=base;indices=[]
        def flush():
            nonlocal result
            if indices:result+='['+','.join(map(str,indices))+']';indices.clear()
        for part in self.symbols:
            if isinstance(part,int):indices.append(part)
            else:flush();result+=('.' if result else '')+part
        flush();return result


def decode_path(raw):
    p=Path();pos=0
    while pos<len(raw):
        code=raw[pos];pos+=1
        if code==0x91:
            need(raw[pos:],1);size=raw[pos];pos+=1;need(raw[pos:],size+size%2)
            try:name=raw[pos:pos+size].decode('ascii')
            except UnicodeDecodeError:raise CIPError(4,'Non-ASCII symbol')
            if not re.fullmatch(r'[A-Za-z_][\w:]*',name):raise CIPError(4,'Invalid symbol')
            if size%2 and raw[pos+size]!=0:raise CIPError(4,'Nonzero symbolic padding')
            p.symbols.append(name);pos+=size+size%2
        elif code in (0x20,0x21,0x22,0x24,0x25,0x26,0x28,0x29,0x2A,0x30,0x31,0x32):
            width=(1,2,4)[code&3]
            if width>1:
                need(raw[pos:],1)
                if raw[pos]!=0:raise CIPError(4,'Nonzero logical padding')
                pos+=1
            need(raw[pos:],width);value=int.from_bytes(raw[pos:pos+width],'little');pos+=width
            kind=code&0xFC
            if kind==0x28:p.symbols.append(value)
            else:
                attr={0x20:'class_id',0x24:'instance',0x30:'attribute'}[kind]
                if (attr=='class_id' and p.class_id==0x6D and value==0x8C and p.instance
                        and p.program_instance is not None and p.routine_instance is None
                        and p.aoi_instance is None and p.io_map_instance is None and p.controller_instance is None
                        and p.attribute is None and not p.symbols):
                    p.routine_instance=p.instance;p.class_id=value;p.instance=None
                    continue
                # These child classes have two logical object pairs. Keep the
                # parent scope; never flatten a child into a global object.
                scope = ('program_instance' if p.class_id==0x68 and value in (*energy_catalog.CLASSES,*alarm_catalog.PROGRAM_CLASSES,0x6A,0x6B,0x6D,0x74,0x8D,0x36E)
                         else 'aoi_instance' if p.class_id==0x338 and value==0x6D
                         else 'io_map_instance' if p.class_id==0x69 and value==0x7E
                         else 'controller_instance' if p.class_id==0x8E and value==0x74 else None)
                if (attr=='class_id' and scope and p.instance and p.attribute is None and not p.symbols
                        and p.program_instance is None and p.io_map_instance is None and p.controller_instance is None
                        and p.aoi_instance is None):
                    setattr(p,scope,p.instance);p.class_id=value;p.instance=None
                    continue
                if getattr(p,attr) is not None:raise CIPError(4,'Duplicate logical segment')
                setattr(p,attr,value)
        else:raise CIPError(4,f'Unsupported path segment 0x{code:02X}')
    if p.attribute is not None and p.class_id is None:raise CIPError(4,'Attribute without class')
    if p.program_instance is not None and p.instance is None:raise CIPError(4,'Program object requires a child instance')
    if p.io_map_instance is not None and p.instance is None:raise CIPError(4,'I/O Map object requires a child instance')
    if p.controller_instance is not None and p.instance is None:raise CIPError(4,'Controller object requires a child instance')
    if p.aoi_instance is not None and p.instance is None:raise CIPError(4,'AOI object requires a child instance')
    if p.routine_instance is not None and p.instance is None:raise CIPError(4,'Routine object requires a child instance')
    return p


def route_ok(raw,router=False):
    # One modeled backplane route: port 1, slot 0. Never forward externally.
    if raw.startswith(b'\x01\x00'):raw=raw[2:]
    if router:
        if raw!=b'\x20\x02\x24\x01':raise CIPError(5,'Class 3 connection must end at Message Router instance 1')
        return
    if raw:raise CIPError(5,'Only local backplane slot 0 is modeled')


@dataclass
class Connection:
    incoming:int
    outgoing:int
    identity:bytes
    incoming_size:int=500
    outgoing_size:int=500
    last_sequence:int|None=None
    last_request:bytes=b''
    last_reply:bytes=b''


@dataclass
class Session:
    handle:int=0
    generation:int=0
    connections:dict=field(default_factory=dict)
    peer:str=''


class Router:
    def __init__(self,app,endpoint):
        self.app=app;self.endpoint=endpoint;self._catalog=None;self._storage=None;self._storage_key=None

    def templates(self):
        project=self.app.engine.project
        snapshot=getattr(self.app,'native_templates',None) if self.endpoint.native_read_only else None
        installed=getattr(self.app.engine,'installed_download',None) if self.endpoint.native_read_only else None
        if installed is not None:
            try:installed.check(self.app.native_project_identity,project)
            except ImageError as error:raise CIPError(0x0C,error.reason) from error
            definitions=installed.namespace._image.templates
            if getattr(self,'_template_installation',None) is not installed:
                from .native_templates import NativeTemplates
                self._installed_templates=NativeTemplates(self.app.native_types,definitions) if definitions else None
                self._template_installation=installed
            snapshot=self._installed_templates
            if snapshot is not None and snapshot._templates!=definitions:
                raise CIPError(0x0C,'Installed Template definitions changed')
        if snapshot:snapshot.check_source(project,self.app.native_types)
        if self._catalog is None or self._catalog.project is not project or getattr(self,'_catalog_snapshot',None) is not snapshot:
            self._catalog=snapshot.bind(project,self.app.native_types) if snapshot else Catalog(project)
            self._catalog_snapshot=snapshot
        return self._catalog

    def identity_attributes(self):
        attributes=self.endpoint.identity.attributes()
        if self.endpoint.native_read_only:
            mode=self.app.controller_state()['mode']
            # Logix Status: bits 12..13 Remote, bits 4..7 Run/Program/Faulted.
            attributes[5]=struct.pack('<H',0x3000 | {'Run':0x60,'Program':0x70,'Faulted':0x450}[mode])
        return attributes

    def identity(self):
        attributes=self.identity_attributes()
        return b''.join(attributes[n] for n in range(1,8))

    def native_read(self,inner,session,native,depth,limit,budget,*,registration=True,transfer_control=None):
        """Apply the same native policy to single packets and batch children."""
        path=None
        def reject(status,reason):
            self.endpoint.record_native_rejection(inner[0],path,status,reason)
            return reply(inner[0],status)
        try:
            end=2+2*inner[1];path=decode_path(inner[2:end]);payload=inner[end:]
            if registration:
                result=native.registration(inner[0],path,payload)
                if result is not None:return reply(inner[0],0,result)
            elif native.stage!='bound':return reject(0x0F,'unbound_context')
            if inner[0]==0x59 and path.class_id==0x8E:
                if (path.instance!=1 or path.attribute is not None or path.symbols or path.program_instance is not None
                        or path.io_map_instance is not None or path.controller_instance is not None):
                    return reject(4,'invalid_request')
                exact(payload,4)
                if payload!=bytes(4):return reject(3,'unsupported_edit_completion_profile')
                if not self.app.allow_routine_edits:return reject(0x0F,'supported_routine_edits_disabled')
                if self.app.controller_state()['mode']!='Program':return reject(0x0C,'program_mode_required')
                with self.endpoint.lock:
                    lease=self.endpoint.programming_lease;source=self.app.engine.project.sha256
                    lease.require_edit_owner(native,self.app.generation,source)
                    if not lease.edit_phase_open or lease.program_reservations:
                        return reject(0x0C,'edit_preparation_not_released')
                    if lease.applied_edit is not None:return reply(inner[0])
                    stage=lease.edit_transfer
                    if not stage.ready() or not stage.program_released:return reject(0x0C,'complete_routine_candidate_required')
                    program=self.source_bound_program(stage.target[0])
                    if not self.zero_program_stack_supported(program):return reject(0x0C,'source_correlation_unavailable')
                    routine=next((r for r in self.routines(stage.target[0]) if r['id']==stage.target[1]),None)
                    if routine is None or routine['name'].casefold()!=stage.source.name.casefold():return reject(0x0C,'source_correlation_changed')
                    from .routine_source import resolve,SourceError
                    from .routine_edits import prepare
                    try:
                        neutral=resolve(stage.source,self.app.engine.project,self.app.native_symbols,
                            self.app.native_routines,self.app.native_types,program['name'])
                        if neutral!=stage.translated_rungs:return reject(0x0C,'source_correlation_changed')
                        candidate,receipt=prepare(self.app.engine,stage.source,neutral,program['name'],stage.base_revision,
                            native_source=stage.source_bytes(),native_target=stage.target)
                    except (SourceError,ModelError):return reject(0x0C,'routine_replacement_validation_failed')
                    self.app.engine=candidate;self.app._io_dirty=True
                    candidate.change_detection.record('routine_transaction')
                    self._catalog=None;self._storage=None;self._storage_key=None
                    lease.applied_edit=receipt;stage.clear()
                    self.endpoint.record('native_routine_edit_applied',**receipt)
                return reply(inner[0])
            if inner[0]==0x5C and path.class_id==0x6D:
                if transfer_control!=8:return reject(0x0F,'edit_transfer_control_required')
                if (path.program_instance is None or not path.instance or path.attribute is not None or path.symbols
                        or path.io_map_instance is not None or path.controller_instance is not None):
                    return reject(4,'invalid_request')
                if self.app.controller_state()['mode']!='Program':return reject(0x0C,'program_mode_required')
                with self.endpoint.lock:
                    lease=self.endpoint.programming_lease
                    lease.require_edit_owner(native,self.app.generation,self.app.engine.project.sha256)
                    if not lease.edit_phase_open or path.program_instance not in lease.program_reservations:
                        return reject(0x0C,'edit_program_reservation_required')
                    # Recheck original catalogs, as for the fragments. The
                    # record is opaque and cannot update executable identity.
                    program=self.source_bound_program(path.program_instance)
                    if not self.zero_program_stack_supported(program):return reject(0x0C,'source_correlation_unavailable')
                    routine=next((row for row in self.routines(path.program_instance) if row['id']==path.instance),None)
                    if routine is None:return reject(5,'unknown_source_routine')
                    stage=lease.edit_transfer
                    if stage.source is not None:
                        from .routine_source import resolve,SourceError
                        try:neutral=resolve(stage.source,self.app.engine.project,self.app.native_symbols,
                            self.app.native_routines,self.app.native_types,routine['program'])
                        except SourceError:return reject(0x0C,'source_correlation_unavailable')
                        if neutral!=stage.translated_rungs:return reject(0x0C,'source_correlation_changed')
                    lease.edit_transfer.attach(payload,target=(path.program_instance,path.instance))
                    self.endpoint.record('native_edit_post_source_record',
                        **lease.edit_transfer.description()['post_source_record'])
                return reply(inner[0])
            if inner[0] in (0x55,0x57) and path.class_id==0x8E:
                if (path.attribute is not None or path.symbols or path.program_instance is not None
                        or path.io_map_instance is not None or path.controller_instance is not None):
                    return reject(4,'invalid_request')
                if path.instance!=1:return reject(5,'invalid_request')
                exact(payload,0)
                identity=self.app.native_project_identity
                if identity is None or identity.source_l5x_sha256!=self.app.engine.project.sha256:
                    return reject(0x0C,'source_correlation_unavailable')
                if self.app.controller_state()['mode']!='Program':return reject(0x0C,'program_mode_required')
                with self.endpoint.lock:
                    lease=self.endpoint.programming_lease
                    operation=lease.open_edit_preparation if inner[0]==0x55 else lease.close_edit_preparation
                    operation(native,self.app.generation,self.app.engine.project.sha256)
                    self.endpoint.counts['native_edit_preparation_open' if inner[0]==0x55 else 'native_edit_preparation_close']+=1
                return reply(inner[0])
            if inner[0]==4 and path.class_id==0x68 and payload[:4]==b'\1\0\x1b\0':
                if (path.attribute is not None or path.symbols or path.program_instance is not None
                        or path.io_map_instance is not None or path.controller_instance is not None):
                    return reject(4,'invalid_request')
                exact(payload,8)
                program=self.source_bound_program(path.instance)
                if not self.zero_program_stack_supported(program):return reject(0x0C,'zero_udi_stack_source_unavailable')
                if self.app.controller_state()['mode']!='Program':return reject(0x0C,'program_mode_required')
                with self.endpoint.lock:
                    self.endpoint.programming_lease.prepare_zero_program_stack(native,self.app.generation,
                        self.app.engine.project.sha256,path.instance,struct.unpack_from('<I',payload,4)[0])
                    self.endpoint.counts['native_zero_program_stack_preparations']+=1
                return reply(4,0,b'\1\0\x1b\0\0\0')
            if inner[0] in (6,7) and path.class_id==0x8E:
                if (path.attribute is not None or path.symbols or path.program_instance is not None
                        or path.io_map_instance is not None or path.controller_instance is not None):
                    return reject(4,'invalid_request')
                if path.instance!=1:return reject(5,'invalid_request')
                exact(payload,0)
                identity=self.app.native_project_identity
                if identity is None or identity.source_l5x_sha256!=self.app.engine.project.sha256:
                    return reject(0x0C,'source_correlation_unavailable')
                with self.endpoint.lock:
                    self.endpoint.programming_lease.require_owner(native,self.app.generation,self.app.engine.project.sha256)
                mode='Run' if inner[0]==6 else 'Program'
                try:self.app.set_controller_mode(mode,remote_request=True)
                except ModelError:return reject(0x0C,'controller_mode_unavailable')
                with self.endpoint.lock:self.endpoint.counts['native_mode_'+mode.lower()]+=1
                return reply(inner[0])
            if inner[0]==0x3B and path.class_id in energy_catalog.CLASSES:
                if (path.instance!=0 or path.attribute is not None or path.symbols or payload or
                        path.io_map_instance is not None or path.controller_instance is not None or path.aoi_instance is not None):
                    return reject(0x0F,'read_only_policy')
                if path.program_instance is not None:self.source_bound_program(path.program_instance)
                if path.class_id in energy_catalog.EMPTY_PROBE_CLASSES and self.app.engine.project.energy_catalog.empty:
                    return reply(0x3B)
                # Unknown/nonempty sources and unobserved newer profiles keep
                # their negative reply. No Energy readings or writes dispatch.
                return reject(8,'unsupported_probe')
            if path.class_id==0x74 and path.program_instance is not None and inner[0] in (0x4B,0x4C):
                if path.symbols or path.attribute is not None:
                    return reject(4,'invalid_request')
                if path.instance!=1:return reject(5,'invalid_request')
                exact(payload,1 if inner[0]==0x4B else 0)
                if inner[0]==0x4B and payload!=b'\0':return reject(3,'invalid_program_semaphore_selector')
                source=self.app.engine.project.sha256
                self.source_bound_program(path.program_instance)
                if self.app.controller_state()['mode']!='Program':return reject(0x0C,'program_mode_required')
                with self.endpoint.lock:
                    lease=self.endpoint.programming_lease
                    action=lease.reserve_program if inner[0]==0x4B else lease.release_program
                    action(native,self.app.generation,source,path.program_instance)
                    self.endpoint.counts['native_program_reserve' if inner[0]==0x4B else 'native_program_release']+=1
                return reply(inner[0])
            if path.class_id==0x74 and path.controller_instance is not None and inner[0] in (0x4B,0x4C):
                if path.symbols or path.attribute is not None:
                    return reject(4,'invalid_request')
                if path.controller_instance!=1 or path.instance!=1:
                    return reject(5,'invalid_request')
                exact(payload,1 if inner[0]==0x4B else 0)
                if inner[0]==0x4B:
                    if payload not in (b'\0',b'\1'):return reject(3,'invalid_request')
                    identity=self.app.native_project_identity
                    if identity is None or identity.source_l5x_sha256!=self.app.engine.project.sha256:
                        return reject(0x0C,'source_correlation_unavailable')
                with self.endpoint.lock:
                    lease=self.endpoint.programming_lease
                    if inner[0]==0x4B:
                        lease.acquire(native,self.app.generation,self.app.engine.project.sha256,selector=payload[0])
                    else:lease.release(native,self.app.generation,self.app.engine.project.sha256)
                    self.endpoint.counts['native_semaphore_acquire' if inner[0]==0x4B else 'native_semaphore_release']+=1
                return reply(inner[0])
            if inner[0] in (8,9) and path.class_id in (0x37D,0x349):
                if (path.attribute is not None or path.symbols or path.program_instance is not None
                        or path.io_map_instance is not None or path.controller_instance is not None):
                    return reject(4,'invalid_request')
                maximum=65535 if path.class_id==0x37D else 0xFFFFFFFF
                if path.instance is None or not 1<=path.instance<=maximum:return reject(5,'invalid_request')
                identity=self.app.native_project_identity
                if identity is None or identity.source_l5x_sha256!=self.app.engine.project.sha256:
                    return reject(0x0C,'source_correlation_unavailable')
                with self.endpoint.lock:
                    lease=self.endpoint.programming_lease
                    lease.require_prepared(native,self.app.generation,self.app.engine.project.sha256)
                    staging=lease.libraries if path.class_id==0x37D else lease.metadata
                    if inner[0]==8:
                        value=staging.create(path.instance,payload)
                    else:
                        exact(payload,0);staging.delete(path.instance);value=b''
                    kind='library' if path.class_id==0x37D else 'metadata'
                    self.endpoint.counts[f'native_{kind}_'+('create' if inner[0]==8 else 'delete')]+=1
                return reply(inner[0],0,value)
            if inner[0]==0x4F and path.class_id==0x349:
                if (path.attribute is not None or path.symbols or path.program_instance is not None
                        or path.io_map_instance is not None or path.controller_instance is not None):
                    return reject(4,'invalid_request')
                if path.instance is None:return reject(5,'invalid_request')
                identity=self.app.native_project_identity
                if identity is None or identity.source_l5x_sha256!=self.app.engine.project.sha256:
                    return reject(0x0C,'source_correlation_unavailable')
                with self.endpoint.lock:
                    lease=self.endpoint.programming_lease
                    if lease.selector==1:
                        if not self.app.allow_routine_edits:return reject(0x0F,'supported_routine_edits_disabled')
                        lease.require_edit_owner(native,self.app.generation,self.app.engine.project.sha256)
                        if path.instance!=1:return reject(5,'unsupported_edit_metadata_field')
                        stage=lease.edit_transfer
                        if (self.app.controller_state()['mode']!='Program' or not lease.edit_phase_open
                                or stage.target is None or stage.target[0] not in lease.program_reservations):
                            return reject(0x0C,'edit_program_reservation_required')
                        self.source_bound_program(stage.target[0])
                        stage.retain_metadata(payload)
                        self.endpoint.record('native_edit_metadata_retained',**stage.description()['routine_metadata'])
                        return reply(inner[0])
                    lease.require_prepared(native,self.app.generation,self.app.engine.project.sha256)
                    namespace=lease.download_namespace
                    if (namespace is not None and namespace.controller.description()['configured']
                            and payload[8:10]==b'\x8e\0'):
                        self.require_download_namespace(lease,identity)
                        namespace.tasks.require_configured(self.download_task_bindings(lease))
                        if self.app.controller_state()['mode']!='Program':return reject(0x0C,'program_mode_required')
                        source=Source(identity.source_acd_sha256,self.app.engine.project.sha256)
                        namespace.properties.stage(payload,path.instance,source,getattr(self.app,'native_metadata_values',None),
                            self.app.engine.project,identity=self.endpoint.identity)
                        self.endpoint.record('native_download_controller_properties',**namespace.properties.description())
                        return reply(inner[0])
                    lease.metadata.stage_values(payload,path.instance)
                    self.endpoint.counts['native_metadata_value_packets']+=1
                return reply(inner[0])
            if inner[0] in (0x4B,9,6,0x4D) and path.class_id==0x412:
                if (path.attribute is not None or path.symbols or path.program_instance is not None
                        or path.io_map_instance is not None or path.controller_instance is not None):
                    return reject(4,'invalid_request')
                if path.instance!=0:return reject(5,'invalid_request')
                identity=self.app.native_project_identity
                if identity is None or identity.source_l5x_sha256!=self.app.engine.project.sha256:
                    return reject(0x0C,'source_correlation_unavailable')
                with self.endpoint.lock:
                    lease=self.endpoint.programming_lease
                    lease.require_prepared(native,self.app.generation,self.app.engine.project.sha256)
                    if lease.download_namespace is not None and inner[0] in (0x4B,6,0x4D):
                        self.require_download_namespace(lease,identity)
                        if inner[0] in (6,0x4D):
                            exact(payload,0)
                            inspection=lease.transport.inspect_incremental_payload()
                            self.endpoint.record('native_incremental_transport_inspection',**inspection)
                            if lease.download_namespace._incremental is not None:
                                if lease.download_namespace._routine_batch is not None:
                                    return reject(0x0F,'incremental_batch_sequence_unimplemented')
                                lease.download_namespace.setup.require_complete(self.download_setup_bindings(lease))
                                bindings=self.download_routine_bindings(lease)
                                if inner[0]==6:
                                    state=lease.transport.start_routine_payload(bindings)
                                    self.endpoint.record('native_routine_batch_preparation',**state)
                                    return reply(inner[0])
                                status,state=lease.transport.routine_execution_status(bindings)
                                self.endpoint.record('native_routine_batch_result',**state)
                                self.endpoint.counts['native_routine_completed_status']+=1
                                return reply(inner[0],0,status)
                            source=Source(identity.source_acd_sha256,self.app.engine.project.sha256)
                            bindings=self.download_header_bindings(lease)
                            values=getattr(self.app,'native_metadata_values',None)
                            staged=lease.transport.prepare_incremental_payload(lease.download_namespace._image,source,values,bindings)
                            self.endpoint.record('native_incremental_download_staging',**staged)
                            if inner[0]==6:
                                state=lease.transport.start_incremental_payload(lease.download_namespace._image,source,values,bindings)
                                self.endpoint.record('native_incremental_download_preparation',**state)
                                return reply(inner[0])
                            status,state=lease.transport.incremental_execution_status(lease.download_namespace._image,source,values,bindings)
                            self.endpoint.record('native_incremental_download_result',**state)
                            self.endpoint.counts['native_incremental_completed_status']+=1
                            return reply(inner[0],0,status)
                    if inner[0]==0x4D:
                        exact(payload,0)
                        native_types=getattr(self.app,'native_types',None)
                        if native_types and (native_types.source_acd_sha256!=identity.source_acd_sha256
                                or native_types.source_l5x_sha256!=self.app.engine.project.sha256):
                            return reject(0x0C,'native_type_source_mismatch')
                        status,image=lease.transport.execution_status(native_types,
                            native_symbols=self.app.native_symbols,native_routines=self.app.native_routines,
                            native_auxiliary_symbols=self.app.native_auxiliary_symbols,native_tables=self.app.native_tables)
                        self.endpoint.record('native_download_result_query',**image)
                        self.endpoint.counts['native_download_completed_status']+=1
                        return reply(inner[0],0,status)
                    if inner[0]==6:
                        exact(payload,0)
                        native_types=getattr(self.app,'native_types',None)
                        if native_types and (native_types.source_acd_sha256!=identity.source_acd_sha256
                                or native_types.source_l5x_sha256!=self.app.engine.project.sha256):
                            return reject(0x0C,'native_type_source_mismatch')
                        inspection=lease.transport.inspect_payload(native_types,
                            native_symbols=self.app.native_symbols,native_routines=self.app.native_routines,
                            native_auxiliary_symbols=self.app.native_auxiliary_symbols,native_tables=self.app.native_tables)
                        self.endpoint.record('native_transport_inspection',expanded_bytes=inspection['expanded_bytes'],
                            record_count=inspection['record_count'],scoped_records=inspection['scoped_records'],records_executed=0)
                        staged=lease.transport.templates.description()
                        self.endpoint.record('native_template_staging',templates=staged['templates'],definition_bytes=staged['definition_bytes'],
                            records_modeled=staged['records_modeled'],write_fragments=staged['write_fragments'],unsupported_records=staged['unsupported_records'])
                        self.endpoint.record('native_template_layout_inspection',**staged['layout_inspection'])
                        self.endpoint.record('native_source_type_verification',**lease.transport.source_type_verification)
                        self.endpoint.record('native_source_object_verification',**lease.transport.source_object_verification)
                        diagnostics=lease.transport.diagnostics.description()
                        modeled=staged['records_modeled']+diagnostics['records_modeled']
                        self.endpoint.record('native_diagnostic_staging',messages=diagnostics['messages'],text_bytes=diagnostics['text_bytes'],
                            records_modeled=diagnostics['records_modeled'],total_records_modeled=modeled,unsupported_records=inspection['record_count']-modeled)
                        objects=lease.transport.objects.description();modeled+=objects['records_modeled']
                        self.endpoint.record('native_object_staging',symbols=objects['symbols'],tables=objects['tables'],programs=objects['programs'],
                            routines=objects['routines'],coordination_records=objects['coordination_records'],records_modeled=objects['records_modeled'],
                            total_records_modeled=modeled,unsupported_records=inspection['record_count']-modeled,references_validated=objects['references_validated'])
                        image=lease.transport.start_prepared_image()
                        self.endpoint.record('native_download_image_preparation',**image)
                        return reply(inner[0])
                    if inner[0]==0x4B:
                        lease.transport.open(payload)
                    else:
                        exact(payload,0)
                        try:
                            if (lease.download_namespace is None and lease.transport.execution_status_reported
                                    and lease.transport.source_object_verification['status']=='matched'):
                                lease.download_namespace=DownloadNamespace(lease.transport,self.app.native_types,
                                    native_symbols=self.app.native_symbols,native_routines=self.app.native_routines,
                                    native_auxiliary_symbols=self.app.native_auxiliary_symbols,native_tables=self.app.native_tables)
                                self.endpoint.record('native_download_namespace_retained',**lease.download_namespace.description())
                            elif lease.download_namespace is not None and lease.transport.routine_status_reported:
                                self.require_download_namespace(lease,identity)
                                lease.download_namespace.retain_routines(lease.transport,self.download_routine_bindings(lease),
                                    self.download_setup_bindings(lease))
                                self.endpoint.record('native_routine_namespace_retained',**lease.download_namespace.description())
                            elif lease.download_namespace is not None and lease.transport.incremental_status_reported:
                                self.require_download_namespace(lease,identity)
                                lease.download_namespace.retain_incremental(lease.transport,
                                    Source(identity.source_acd_sha256,self.app.engine.project.sha256),
                                    getattr(self.app,'native_metadata_values',None),self.download_header_bindings(lease))
                                self.endpoint.record('native_incremental_namespace_retained',**lease.download_namespace.description())
                        finally:lease.transport.clear()
                    self.endpoint.counts['native_transport_'+('setup' if inner[0]==0x4B else 'delete')]+=1
                return reply(inner[0])
            if inner[0] in (0x60,0x62) and path.class_id==0x8E:
                if (path.attribute is not None or path.symbols or path.program_instance is not None
                        or path.io_map_instance is not None or path.controller_instance is not None):
                    return reject(4,'invalid_request')
                if path.instance!=1:return reject(5,'invalid_request')
                exact(payload,0)
                identity=self.app.native_project_identity
                if identity is None or identity.source_l5x_sha256!=self.app.engine.project.sha256:
                    return reject(0x0C,'source_correlation_unavailable')
                with self.endpoint.lock:
                    operation=(self.endpoint.programming_lease.begin_preparation if inner[0]==0x60
                               else self.endpoint.programming_lease.end_preparation)
                    operation(native,self.app.generation,self.app.engine.project.sha256)
                    self.endpoint.counts['native_preparation_begin' if inner[0]==0x60 else 'native_preparation_end']+=1
                return reply(inner[0])
            if (inner[0]==4 and path.class_id==0x8E and path.instance==1 and path.attribute is None
                    and not path.symbols and payload[:4]==b'\1\0\x09\0'):
                exact(payload,5)
                identity=self.app.native_project_identity
                if identity is None or identity.source_l5x_sha256!=self.app.engine.project.sha256:
                    return reject(0x0C,'source_correlation_unavailable')
                with self.endpoint.lock:
                    self.endpoint.programming_lease.require_prepared(native,self.app.generation,self.app.engine.project.sha256)
                    if payload[4]!=0:return reject(0x0F,'configuration_change_not_permitted')
                    if self.app.engine.project.controller_configuration.redundancy_configured is not False:
                        return reject(0x0C,'source_configuration_unavailable')
                    self.endpoint.counts['native_configuration_retained']+=1
                return reply(4,0,b'\1\0\x09\0\0\0')
            if (inner[0]==4 and path.class_id==0x8E and path.instance==1 and path.attribute is None
                    and not path.symbols and payload[:4]==b'\1\0\7\0'):
                exact(payload,6)
                identity=self.app.native_project_identity
                if identity is None or identity.source_l5x_sha256!=self.app.engine.project.sha256:
                    return reject(0x0C,'source_correlation_unavailable')
                with self.endpoint.lock:
                    self.endpoint.programming_lease.set_run_inhibit(native,self.app.generation,
                        self.app.engine.project.sha256,struct.unpack_from('<H',payload,4)[0])
                    self.endpoint.counts['native_run_inhibit_updates']+=1
                    if payload[4:]==b'\1\0':self.app.set_controller_mode('Program')
                return reply(4,0,b'\1\0\7\0\0\0')
            if (inner[0]==4 and path.class_id==0xAC and path.instance==1 and path.attribute is None
                    and not path.symbols and path.program_instance is None and payload[:4]==b'\1\0\x0A\0'):
                exact(payload,8)
                identity=self.app.native_project_identity
                if identity is None or identity.source_l5x_sha256!=self.app.engine.project.sha256:
                    return reject(0x0C,'source_correlation_unavailable')
                value=native_session.acknowledge_existing_timeline(payload,identity.timeline_uid)
                with self.endpoint.lock:self.endpoint.counts['native_timeline_retained']+=1
                return reply(4,0,value)
            if inner[0]==0x50 and path.class_id==0x68:
                if (not path.instance or path.attribute is not None or path.symbols or
                        any(getattr(path,key) is not None for key in
                            ('program_instance','io_map_instance','controller_instance','aoi_instance'))):
                    return reject(4,'invalid_program_query_scope')
                try:selector=program_query.selection(payload)
                except ValueError:return reject(3,'unsupported_program_query')
                if limit<20:return reject(0x1B,'program_query_reply_budget')
                self.source_bound_program(path.instance)
                # Only the captured selector-token profile is implemented.
                # The CRC protects these four payload bytes, not the Program.
                return reply(inner[0],0,program_query.body(selector))
            if inner[0]==4 and path.class_id==0x6B:
                with self.endpoint.lock:
                    lease=self.endpoint.programming_lease;namespace=lease.download_namespace
                    if namespace is not None and namespace.tasks.description()['created']:
                        lease.require_prepared(native,self.app.generation,self.app.engine.project.sha256)
                        if (type(path.instance) is not int or not 1<=path.instance<=0xFFFF or path.attribute is not None or path.symbols
                                or any(getattr(path,key) is not None for key in
                                       ('program_instance','io_map_instance','controller_instance','aoi_instance'))):
                            return reject(4,'invalid_download_task_symbol_scope')
                        identity=self.app.native_project_identity
                        if identity is None:return reject(0x0C,'source_correlation_unavailable')
                        self.require_download_namespace(lease,identity)
                        if self.app.controller_state()['mode']!='Program':return reject(0x0C,'program_mode_required')
                        if limit<14:return reject(0x1B,'download_task_symbol_reply_budget')
                        value=namespace.tasks.link_symbol(path.instance,payload,self.download_task_bindings(lease))
                        self.endpoint.record('native_download_task_symbol_updated',**namespace.tasks.description())
                        return reply(inner[0],0,value)
            if inner[0] in (8,4) and path.class_id==0x70:
                if (type(path.instance) is not int or not 1<=path.instance<=0xFFFF or path.attribute is not None or path.symbols
                        or any(getattr(path,key) is not None for key in
                               ('program_instance','io_map_instance','controller_instance','aoi_instance'))):
                    return reject(4,'invalid_download_task_scope')
                if inner[0]==8:exact(payload,0)
                identity=self.app.native_project_identity
                if identity is None:return reject(0x0C,'source_correlation_unavailable')
                with self.endpoint.lock:
                    lease=self.endpoint.programming_lease
                    lease.require_prepared(native,self.app.generation,self.app.engine.project.sha256)
                    if lease.download_namespace is None or lease.download_namespace._incremental is None:
                        return reject(0x0C,'completed_incremental_download_required')
                    self.require_download_namespace(lease,identity)
                    if self.app.controller_state()['mode']!='Program':return reject(0x0C,'program_mode_required')
                    if limit<(12 if inner[0]==8 else 6+4*9):return reject(0x1B,'download_task_reply_budget')
                    tasks=lease.download_namespace.tasks;bindings=self.download_task_bindings(lease)
                    value=(tasks.create(path.instance,bindings) if inner[0]==8 else tasks.configure(path.instance,payload,bindings))
                    self.endpoint.record('native_download_task_'+('created' if inner[0]==8 else 'configured'),**tasks.description())
                    return reply(inner[0],0,value)
            if (inner[0]==4 and path.class_id==0x8E and (payload[:2]==b'\x0e\0' or
                    payload[:4] in (b'\1\0\x0a\0',b'\1\0\x0b\0',b'\1\0\x0c\0'))):
                if (path.instance!=1 or path.attribute is not None or path.symbols or any(getattr(path,key) is not None
                        for key in ('program_instance','io_map_instance','controller_instance','aoi_instance'))):
                    return reject(4,'invalid_download_controller_scope')
                identity=self.app.native_project_identity
                if identity is None:return reject(0x0C,'source_correlation_unavailable')
                with self.endpoint.lock:
                    lease=self.endpoint.programming_lease
                    lease.require_prepared(native,self.app.generation,self.app.engine.project.sha256)
                    namespace=lease.download_namespace
                    if namespace is None:return reject(0x0C,'completed_download_namespace_required')
                    self.require_download_namespace(lease,identity)
                    namespace.tasks.require_configured(self.download_task_bindings(lease))
                    if self.app.controller_state()['mode']!='Program':return reject(0x0C,'program_mode_required')
                    if limit<6+4*struct.unpack_from('<H',payload)[0]:return reject(0x1B,'download_controller_reply_budget')
                    value=namespace.controller.configure(payload,ControllerBindings(self.app.engine,namespace,identity))
                    self.endpoint.record('native_download_controller_configured',**namespace.controller.description())
                return reply(inner[0],0,value)
            if (inner[0],path.class_id)==(0x4B,0x378) or (inner[0],path.class_id)==(4,0x64) and payload[:2]==b'\1\0':
                if (path.instance!=1 or path.attribute is not None or path.symbols or any(getattr(path,key) is not None
                        for key in ('program_instance','io_map_instance','controller_instance','aoi_instance'))):
                    return reject(4,'invalid_download_repository_scope')
                identity=self.app.native_project_identity
                if identity is None:return reject(0x0C,'source_correlation_unavailable')
                with self.endpoint.lock:
                    lease=self.endpoint.programming_lease
                    lease.require_prepared(native,self.app.generation,self.app.engine.project.sha256)
                    namespace=lease.download_namespace
                    if namespace is None:return reject(0x0C,'completed_download_namespace_required')
                    self.require_download_namespace(lease,identity)
                    if not namespace.controller.description()['configured']:
                        return reject(0x0C,'download_controller_configuration_required')
                    if self.app.controller_state()['mode']!='Program':return reject(0x0C,'program_mode_required')
                    if limit<(8 if inner[0]==0x4B else 10):return reject(0x1B,'download_repository_reply_budget')
                    operation=namespace.repository.register if inner[0]==0x4B else namespace.repository.link
                    value=operation(payload,namespace._source,self.app.engine.project,self.endpoint.identity)
                    self.endpoint.record('native_download_device_repository',**namespace.repository.description())
                return reply(inner[0],0,value)
            if inner[0]==4 and path.class_id in SETUP_PROFILES:
                if (path.instance!=1 or path.attribute is not None or path.symbols or any(getattr(path,key) is not None
                        for key in ('program_instance','io_map_instance','controller_instance','aoi_instance'))):
                    return reject(4,'invalid_download_setup_scope')
                identity=self.app.native_project_identity
                if identity is None:return reject(0x0C,'source_correlation_unavailable')
                with self.endpoint.lock:
                    lease=self.endpoint.programming_lease
                    lease.require_prepared(native,self.app.generation,self.app.engine.project.sha256)
                    namespace=lease.download_namespace
                    if namespace is None:return reject(0x0C,'completed_download_namespace_required')
                    self.require_download_namespace(lease,identity)
                    if self.app.controller_state()['mode']!='Program':return reject(0x0C,'program_mode_required')
                    if limit<6+4*len(setup_write_profile(path.class_id,payload)):return reject(0x1B,'download_setup_reply_budget')
                    if path.class_id==0xF6:self.network_interface()
                    value=namespace.setup.stage(path.class_id,payload,self.download_setup_bindings(lease))
                    self.endpoint.record('native_download_setup_configured',class_id=path.class_id,**namespace.setup.description())
                return reply(inner[0],0,value)
            if inner[0]==0x10 and path.class_id==0xF5:
                if (path.instance!=0 or path.attribute!=101 or path.symbols or any(getattr(path,key) is not None
                        for key in ('program_instance','io_map_instance','controller_instance','aoi_instance'))):
                    return reject(4,'invalid_download_http_scope')
                exact(payload,1)
                if payload!=b'\0':return reject(0x0F,'embedded_http_enable_unsupported')
                identity=self.app.native_project_identity
                if identity is None:return reject(0x0C,'source_correlation_unavailable')
                with self.endpoint.lock:
                    lease=self.endpoint.programming_lease
                    lease.require_prepared(native,self.app.generation,self.app.engine.project.sha256)
                    if lease.download_namespace is None:return reject(0x0C,'completed_download_namespace_required')
                    self.require_download_namespace(lease,identity)
                    lease.download_namespace.tasks.require_configured(self.download_task_bindings(lease))
                    if self.app.controller_state()['mode']!='Program':return reject(0x0C,'program_mode_required')
                    # This endpoint has no embedded HTTP service. Retaining its
                    # existing disabled value does not touch the management UI.
                    self.endpoint.record('native_download_http_disabled',embedded_http_enabled=False)
                return reply(inner[0])
            if inner[0]==0x55 and path.class_id in (0x68,0x6A,0x6B,0x6D):
                with self.endpoint.lock:
                    lease=self.endpoint.programming_lease
                    if (lease.live(self.app.generation,self.app.engine.project.sha256)
                            and lease.owner is native and lease.download_namespace is not None):
                        lease.require_prepared(native,self.app.generation,self.app.engine.project.sha256)
                        if (path.attribute is not None or path.symbols or any(getattr(path,key) is not None
                                for key in ('io_map_instance','controller_instance','aoi_instance'))):
                            return reject(4,'invalid_download_catalog_scope')
                        if path.class_id==0x68 and path.program_instance is not None:
                            return reject(4,'invalid_download_catalog_scope')
                        if path.class_id==0x6D and path.program_instance is None:
                            return reject(4,'download_routine_program_required')
                        if path.class_id==0x6B:self.symbol_scope(path)
                        expected={0x68:b'\1\0\x10\0',0x6A:b'\2\0\3\0\7\0',0x6B:b'\1\0\5\0',0x6D:b'\1\0\x08\0'}
                        if payload!=expected[path.class_id]:return reject(0x14,'unsupported_download_catalog_attributes')
                        identity=self.app.native_project_identity
                        if identity is None:return reject(0x0C,'source_correlation_unavailable')
                        namespace=lease.download_namespace
                        self.require_download_namespace(lease,identity)
                        if path.class_id==0x6B:
                            partial,value=namespace.symbol_page(path.program_instance or 0,path.instance or 0,limit-4)
                            self.endpoint.counts['native_download_symbol_pages']+=1
                        elif path.class_id==0x6A:
                            partial,value=namespace.table_page(path.instance or 0,limit-4,path.program_instance or 0)
                            self.endpoint.counts['native_download_table_pages']+=1
                        elif path.class_id==0x6D:
                            partial,value=namespace.routine_page(path.program_instance,path.instance or 0,limit-4)
                            self.endpoint.counts['native_download_routine_pages']+=1
                        else:
                            partial,value=namespace.program_page(path.instance or 0,limit-4)
                            self.endpoint.counts['native_download_program_pages']+=1
                        return reply(inner[0],6 if partial else 0,value)
            if path.class_id==0xAC and path.instance==1 and inner[0] in (8,4,1,3,0x0E):
                lease=self.endpoint.programming_lease
                created=lease.download_namespace is not None and lease.download_namespace.change_log.description()['created']
                if inner[0]==8 or created or inner[0]==4 and payload[:2]==b'\7\0':
                    if path.symbols or any(getattr(path,key) is not None for key in ('program_instance','io_map_instance','controller_instance','aoi_instance')):
                        return reject(4,'invalid_download_changelog_scope')
                    if inner[0]!=0x0E and path.attribute is not None:return reject(4,'invalid_download_changelog_scope')
                    identity=self.app.native_project_identity
                    if identity is None or identity.source_l5x_sha256!=self.app.engine.project.sha256:
                        return reject(0x0C,'source_correlation_unavailable')
                    with self.endpoint.lock:
                        lease.require_prepared(native,self.app.generation,self.app.engine.project.sha256)
                        if lease.download_namespace is None:return reject(0x0C,'completed_download_namespace_required')
                        self.require_download_namespace(lease,identity)
                        bindings=self.download_changelog_bindings(lease);stage=lease.download_namespace.change_log
                        if inner[0] in (8,4):
                            if self.app.controller_state()['mode']!='Program':return reject(0x0C,'program_mode_required')
                            if limit<(12 if inner[0]==8 else 34):return reject(0x1B,'download_changelog_reply_budget')
                            operation=stage.create if inner[0]==8 else stage.configure
                            value=operation(payload,bindings)
                            self.endpoint.record('native_download_changelog_'+('created' if inner[0]==8 else 'configured'),**stage.description())
                            return reply(inner[0],0,value)
                        values=stage.read(bindings)
                        if inner[0]==1:
                            exact(payload,0);value=b''.join(values[n] for n in range(1,11))
                            if limit<len(value)+4:return reject(0x1B,'download_changelog_reply_budget')
                            return reply(inner[0],0,value)
                        status,value=self.attribute_read(inner[0],path,payload,values,limit=limit)
                        self.endpoint.record('native_download_changelog_readback',**stage.description())
                        return reply(inner[0],status,value)
            if (inner[0]==0x61 and path.class_id==0x8E
                    and self.endpoint.programming_lease.download_namespace is not None):
                if (path.instance!=1 or path.attribute is not None or path.symbols or any(getattr(path,key) is not None
                        for key in ('program_instance','io_map_instance','controller_instance','aoi_instance'))):
                    return reject(4,'invalid_download_commit_scope')
                exact(payload,0);identity=self.app.native_project_identity
                if identity is None:return reject(0x0C,'source_correlation_unavailable')
                with self.endpoint.lock:
                    lease=self.endpoint.programming_lease
                    lease.require_prepared(native,self.app.generation,self.app.engine.project.sha256)
                    if lease.download_namespace is None:return reject(0x0C,'completed_download_namespace_required')
                    self.require_download_namespace(lease,identity)
                    lease.download_namespace.change_log.require_configured(self.download_changelog_bindings(lease))
                    if self.app.controller_state()['mode']!='Program':return reject(0x0C,'program_mode_required')
                    if limit<4:return reject(0x1B,'download_installation_reply_budget')
                    if lease.download_committed:
                        installed=getattr(self.app.engine,'installed_download',None)
                        if installed is None or installed.namespace is not lease.download_namespace:
                            return reject(0x0C,'installed_download_binding_changed')
                        installed.check(identity,self.app.engine.project)
                        return reply(inner[0])
                    from .download_installation import prepare
                    old=self.app.engine
                    candidate,installed=prepare(self.app,self.download_changelog_bindings(lease),self.app.native_types)
                    try:self.app.install_native_download(candidate,installed,old,lease)
                    except ModelError:return reject(0x0C,'download_installation_candidate_changed')
                    self._catalog=None;self._storage=None;self._storage_key=None
                    self.endpoint.record('native_download_installed',**installed.description())
                    return reply(inner[0])
            if path.class_id==0x69 and path.instance==1 and inner[0] in (4,3,0x0E):
                lease=self.endpoint.programming_lease
                configured=lease.download_namespace is not None and lease.download_namespace.local_map.description()['configured']
                if inner[0]==4 or configured:
                    if path.symbols or any(getattr(path,key) is not None for key in ('program_instance','io_map_instance','controller_instance','aoi_instance')):
                        return reject(4,'invalid_download_map_scope')
                    if inner[0]!=0x0E and path.attribute is not None:return reject(4,'invalid_download_map_scope')
                    identity=self.app.native_project_identity
                    if identity is None or identity.source_l5x_sha256!=self.app.engine.project.sha256:
                        return reject(0x0C,'source_correlation_unavailable')
                    with self.endpoint.lock:
                        lease.require_prepared(native,self.app.generation,self.app.engine.project.sha256)
                        if lease.download_namespace is None:return reject(0x0C,'completed_download_namespace_required')
                        self.require_download_namespace(lease,identity)
                        bindings=self.download_map_bindings(lease);stage=lease.download_namespace.local_map
                        if inner[0]==4:
                            if self.app.controller_state()['mode']!='Program':return reject(0x0C,'program_mode_required')
                            if limit<10:return reject(0x1B,'download_map_reply_budget')
                            response=stage.configure(payload,bindings)
                            self.endpoint.record('native_download_local_map_configured',**stage.description())
                            self.endpoint.counts['native_download_local_map_writes']+=1
                            return reply(inner[0],0,response)
                        attributes=self.app.engine.runtime_references.io_map_attributes(self.app.engine.project,self.endpoint.identity)
                        attributes[7]=stage.read(bindings)
                        status,value=self.attribute_read(inner[0],path,payload,attributes,limit=limit)
                        return reply(inner[0],status,value)
            if inner[0]==0x4C and path.class_id==0x72:
                if (path.instance!=0 or path.attribute is not None or path.symbols or any(getattr(path,key) is not None for key in
                        ('program_instance','io_map_instance','controller_instance','aoi_instance','routine_instance'))):
                    return reject(4,'installed_memory_controller_scope_required')
                exact(payload,6);address,words=struct.unpack('<IH',payload)
                if words!=1:return reject(3,'installed_memory_scalar_word_request_required')
                if limit<8:return reject(0x1B,'installed_memory_reply_budget')
                from .installed_memory import read_scalar
                return reply(inner[0],0,read_scalar(self.app,self,address,words))
            if (inner[0] in (1,3,0x0E) and path.class_id is not None or
                inner[0] in (0x4C,0x52) and path.class_id in (None,0x6B) or
                inner[0]==0x55 and path.class_id==0x6B or inner[0]==0x4C and path.class_id==0x6C or
                inner[0]==0x4B and path.class_id in (*alarm_catalog.CLASSES,*energy_catalog.CLASSES,0x68,0x69,0x6A,0x6B,0x6C,0x6D,0x6E,0x70,0x71,0x8D,0xB0,0xB1,0x32B,0x338,0x349,0x36A,0x36E,0x3B0,0x3B1,0x3B2) or
                inner[0]==0x4B and path.class_id==0x8C and path.routine_instance is not None or
                inner[0]==0x4F and path.class_id in (0x6A,0xAC)):
                return self.handle(inner,session,depth+1,limit,budget)
            if (inner[0]==0x53 and path.class_id==0x349 and path.instance==0 and
                path.attribute is None and not path.symbols and all(getattr(path,key) is None for key in
                    ('program_instance','io_map_instance','controller_instance','aoi_instance'))):
                if getattr(self.app,'native_metadata_values',None) is not None:
                    return self.read_metadata_values(payload,native,limit)
                if controller_configuration.empty_metadata_query(payload):
                    return reply(inner[0],0,struct.pack('<II',0x301,0))
            return reject(0x0F,'read_only_policy')
        except CIPError as error:return reject(error.status,'invalid_request')
        except native_session.NativeError as error:return reject(error.status,'compatibility_context')
        except programming_lease.LeaseError as error:return reject(error.status,error.reason)
        except (library_staging.LibraryError,metadata_staging.MetadataError,resilient_transport.TransportError,edit_transfer.EditTransferError) as error:return reject(error.status,error.reason)
        except ImageError as error:return reject(0x0C,error.reason)

    def network_interface(self):
        if not self.endpoint.interface_queried:
            snapshot,error=interface_snapshot(self.endpoint.bind_address)
            with self.endpoint.lock:
                self.endpoint.interface=snapshot;self.endpoint.interface_error=error;self.endpoint.interface_queried=True
        return self.endpoint.interface

    def attribute_read(self,service,path,data,attributes,*,limit=None):
        if service==0x0E:
            exact(data,0)
            if path.attribute not in attributes:
                self.endpoint.record_attribute_gap(path,[path.attribute],service)
                raise CIPError(0x14,'Unsupported attribute')
            return 0,attributes[path.attribute]
        if service==3 and path.attribute is None:
            need(data,2);count=struct.unpack_from('<H',data)[0];exact(data,2+2*count)
            if not 1<=count<=32:raise CIPError(3,'Attribute count must be 1..32')
            result=bytearray(2);failed=False;missing=[];returned=0
            for number in struct.unpack_from('<'+'H'*count,data,2):
                value=attributes.get(number);status=0 if value is not None else 0x14
                entry=struct.pack('<HH',number,status)+(value if value is not None else b'')
                if limit is not None and 4+len(result)+len(entry)>limit:
                    if not returned:raise CIPError(0x1B,'First attribute exceeds negotiated connection size')
                    break
                if status:missing.append(number)
                failed|=status!=0;result+=entry;returned+=1
            if missing:self.endpoint.record_attribute_gap(path,missing,service)
            struct.pack_into('<H',result,0,returned)
            return (6 if returned<count else 0x0A if failed else 0),bytes(result)
        raise CIPError(8,'Unsupported attribute service')

    def symbols(self,scope=''):
        result=[];engine=self.app.engine
        if not engine:return result
        native=getattr(self.app,'native_symbols',None)
        if native and native.source_l5x_sha256!=engine.project.sha256:raise CIPError(0x0C,'Native symbol source changed')
        for tag in sorted(engine.project.tags.values(),key=lambda t:t.key.lower()):
            if tag.scope.lower()!=scope.lower() or tag.problem or tag.tag_class!='Standard':continue
            mapping=native.by_key.get(tag.key.lower()) if native else None
            if native and mapping is None:continue
            try:
                self.access(tag.key)
                key,parts,dtype=engine.memory.resolve(tag.key);value=engine.memory.values[key]
                for part in parts:
                    if isinstance(part,tuple):value=None;break
                    value=value[part]
                dims=[]
                while isinstance(value,list):dims.append(len(value));value=value[0] if value else None
                template=self.templates().for_type(dtype) if dtype not in TYPES else None
                if dtype not in TYPES and template is None or len(dims)>3:continue
                if dtype=='BOOL' and dims and (len(dims)!=1 or not 32<=dims[0]<=65536 or dims[0]%32):continue
                try:self.access(tag.key,True);access=0
                except (CIPError,ModelError):access=2
                code=(0x8000|template.instance) if template else TYPES[dtype][0]
                result.append({'id':mapping.instance if mapping else len(result)+1,'name':tag.name,'ref':tag.key,'type':code|(len(dims)<<13),
                               'dimensions':(dims+[0,0,0])[:3],'external_access':access})
            except ModelError:continue
            except CIPError:continue
        for row in self.reference_symbols(scope):
            result.append({'id':row.instance,'name':row.name,'type':row.type_code,'dimensions':(0,0,0),
                           'external_access':0,'object_reference':row})
        return sorted(result,key=lambda item:item['id'])

    def reference_symbols(self,scope=''):
        if scope:
            catalog=getattr(self.app,'native_routine_reference_symbols',None);engine=self.app.engine
            if catalog is None:
                engine.runtime_references.bind_scoped_reference_catalog(None)
                return ()
            if not catalog.current(engine.project,self.app.native_project_identity,self.app.native_symbols,
                    self.app.native_routines,self.app.native_auxiliary_symbols):
                engine.runtime_references.bind_scoped_reference_catalog(None)
                raise CIPError(0x0C,'Scoped Routine reference Symbol source binding changed')
            engine.runtime_references.bind_scoped_reference_catalog(catalog)
            return tuple(row for row in catalog.rows if row.program.casefold()==scope.casefold())
        catalog=getattr(self.app,'native_reference_symbols',None);engine=self.app.engine
        if catalog is None:
            engine.runtime_references.bind_reference_catalog(None)
            return ()
        if not catalog.current(engine.project,self.app.native_project_identity,self.app.native_symbols,
                self.app.native_tasks,self.app.native_auxiliary_symbols):
            engine.runtime_references.bind_reference_catalog(None)
            raise CIPError(0x0C,'Reference Symbol source binding changed')
        engine.runtime_references.bind_reference_catalog(catalog)
        return catalog.rows

    def access(self,ref,write=False,seen=()):
        """Honor root, alias target, member and AOI external-access restrictions."""
        memory=self.app.engine.memory;project=self.app.engine.project
        match=re.match(r'^(?:Program:([\w]+)\.)?([A-Za-z_][\w:]*)(.*)$',ref,re.I)
        if not match:raise CIPError(4,'Invalid static tag path')
        scope,name,tail=match.groups();key=(f'Program:{scope}.{name}' if scope else name).lower()
        if scope:
            program=next((p for n,p in project.programs.items() if n.lower()==scope.lower()),None)
            if program is None:raise CIPError(5,'Unknown program scope')
            if program['class']!='Standard':raise CIPError(0x0F,'Program is not externally accessible')
        tag=project.tags.get(key)
        if tag is None:raise CIPError(5,'Unknown tag')
        if key in seen:raise CIPError(5,'Alias cycle')
        if tag.external_access not in ('Read/Write','Read Only') or tag.tag_class!='Standard':raise CIPError(0x0F,'Tag is not externally accessible')
        if write and (tag.external_access!='Read/Write' or tag.constant):raise CIPError(0x0F,'Tag is externally read-only')
        if tag.alias:
            alias=tag.alias
            if tag.scope and not alias.lower().startswith('program:'):
                root=re.match(r'[A-Za-z_][\w:]*',alias)[0]
                if (f'Program:{tag.scope}.{root}').lower() in project.tags:alias=f'Program:{tag.scope}.'+alias
            return self.access(alias+tail,write,seen+(key,))
        dtype=tag.dtype
        for item in re.findall(r'\.([A-Za-z_][\w]*)',tail):
            if dtype.upper() in ('TIMER','COUNTER','STRING'):
                dtype='DINT' if item.upper() in ('LEN','PRE','ACC') else 'SINT' if item.upper()=='DATA' else 'BOOL';continue
            udt=project.udts.get(dtype.lower())
            member=next((m for m in udt.findall('./Members/Member') if m.get('Name','').lower()==item.lower()),None) if udt is not None else None
            if member is None:raise CIPError(5,'Unknown member')
            access=member.get('ExternalAccess','Read/Write')
            if member.get('Hidden','false').lower()=='true' or member.get('AOILocal','false')=='true' or access not in ('Read/Write','Read Only'):raise CIPError(0x0F,'Member is not externally accessible')
            if write and access!='Read/Write':raise CIPError(0x0F,'Member is externally read-only')
            dtype=member.get('DataType','')
        return memory.resolve(ref)

    def reference(self,path):
        if path.attribute is not None:raise CIPError(4,'Tag service does not take an attribute')
        if path.class_id==0x6B:
            scope=self.symbol_scope(path,tag=True);parts=path.symbols
            if parts and isinstance(parts[0],str) and parts[0].lower().startswith('program:'):
                parts=parts[1:]
            symbol=next((s for s in self.symbols(scope) if s['id']==path.instance),None)
            if symbol is None:raise CIPError(5,'Unknown symbol instance')
            if symbol.get('object_reference') is not None:raise CIPError(0x0F,'Object reference is not a readable or writable tag value')
            return Path(symbols=parts).reference(symbol['ref'])
        if path.class_id is not None or path.instance is not None:raise CIPError(4,'Unsupported logical tag path')
        return path.reference()

    def region(self,ref,count,write=False):
        if not 1<=count<=4096:raise CIPError(3,'Element count must be 1..4096')
        key,parts,dtype=self.access(ref,write);memory=self.app.engine.memory
        if key is None or dtype not in TYPES:raise CIPError(8,'Only atomic data and atomic members are implemented')
        if dtype=='BOOL':
            value=memory.read(ref) if any(isinstance(p,tuple) for p in parts) else memory.at(key,parts)
            if count!=1 or isinstance(value,list):raise CIPError(8,'Packed BOOL arrays are not implemented')
            return dtype,[ref]
        value=memory.at(key,parts)
        if count==1 and not isinstance(value,list):return dtype,[ref]
        start=ref
        while isinstance(value,list):
            if not value:raise CIPError(0x0C,'Empty atomic array')
            start+='[0]';value=value[0]
        key,paths,dtype=memory.region(start,count)
        return dtype,[memory.address(key,p) for p in paths]

    def read_tag(self,path,data,fragment=False,limit=REPLY_LIMIT):
        exact(data,6 if fragment else 2);count=struct.unpack_from('<H',data)[0]
        if not 1<=count<=4096:raise CIPError(3,'Element count must be 1..4096')
        ref=self.reference(path);_,_,dtype=self.access(ref)
        template=self.templates().for_type(dtype) if dtype not in TYPES else None
        if template:
            memory=self.app.engine.memory;refs=self.structure_region(ref,count,template)
            def read_member(member_ref):
                self.access(member_ref)
                return memory.read(member_ref)
            encoded=b''.join(self.templates().encode(template,item,read_member) for item in refs)
            type_data=struct.pack('<HH',0x02A0,template.handle)
        else:
            dtype,refs=self.region(ref,count)
            fmt='<'+TYPES[dtype][1];encoded=b''
            for ref in refs:
                value=self.app.engine.memory.read(ref)
                if value is None or isinstance(value,(dict,list)):raise CIPError(0x0C,'Unknown or aggregate data')
                encoded+=struct.pack(fmt,int(value) if dtype=='BOOL' else value)
            type_data=struct.pack('<H',TYPES[dtype][0])
        offset=struct.unpack_from('<I',data,2)[0] if fragment else 0
        if offset>=len(encoded):raise CIPError(0x20,'Fragment offset outside data')
        capacity=limit-4-len(type_data)
        if capacity<1:raise CIPError(0x1B,'Response cannot hold a tag data byte')
        chunk=encoded[offset:offset+capacity]
        return 6 if offset+len(chunk)<len(encoded) else 0,type_data+chunk

    def structure_region(self,ref,count,template,write=False):
        if not 1<=count<=4096:raise CIPError(3,'Element count must be 1..4096')
        if count*template.size>MAX_BYTES:raise CIPError(3,'Structured transfer exceeds 32768 bytes')
        key,parts,_=self.access(ref,write);memory=self.app.engine.memory;value=memory.at(key,parts)
        if isinstance(value,dict) and (not parts or not isinstance(parts[-1],int)):
            if count!=1:raise CIPError(3,'Scalar structure count must be one')
            paths=[parts]
        else:
            start=ref
            while isinstance(value,list):
                if not value:raise CIPError(0x0C,'Empty structured array')
                start+='[0]';value=value[0]
            key,paths,_=memory.region(start,count)
        return [memory.address(key,p) for p in paths]

    def template_service(self,service,path,data,limit):
        if path.symbols or path.program_instance is not None:raise CIPError(4,'Template paths must be controller scoped')
        if path.instance is None:raise CIPError(4,'Template path requires an instance')
        templates=self.exposed_templates()
        if path.instance==0:
            return self.attribute_read(service,path,data,self.catalog_class_attributes(templates,0x6C))
        template=templates.get(path.instance)
        if template is None:raise CIPError(5,'Unknown or unexposed template instance')
        if service in (3,0x0E):return self.attribute_read(service,path,data,template.attributes())
        if service!=0x4C:raise CIPError(8,'Unsupported template service')
        if path.attribute is not None:raise CIPError(4,'Template reads do not take an attribute')
        exact(data,6);offset,count=struct.unpack('<IH',data)
        if not count:raise CIPError(3,'Template byte count must be positive')
        storage=template.definition_storage
        if offset>=len(storage):raise CIPError(0x20,'Template offset outside definition')
        if limit<=4:raise CIPError(0x1B,'Response cannot hold a template data byte')
        end=min(offset+count,len(storage));chunk=storage[offset:min(end,offset+limit-4)]
        return 6 if offset+len(chunk)<end else 0,chunk

    def store_atomic(self,dtype,refs,values):
        if dtype=='BOOL' and any(v not in (0,1) for v in values):raise CIPError(9,'BOOL value must be 0 or 1')
        self.store_values([(ref,bool(value) if dtype=='BOOL' else value) for ref,value in zip(refs,values)])

    def store_values(self,values):
        memory=self.app.engine.memory;before=copy.deepcopy(memory.values)
        try:
            for ref,value in values:memory.write(ref,value)
        except Exception:
            memory.values=before;raise
        self.app._io_dirty=True
        self.app.publish_device_io()

    def write_tag(self,path,data,fragment=False):
        if not self.endpoint.allow_writes:raise CIPError(0x0F,'Network writes are disabled')
        ref=self.reference(path);_,_,declared=self.access(ref,True)
        if declared not in TYPES:
            template=self.templates().for_type(declared)
            if template is None:raise CIPError(8,'Unsupported structured wire layout')
            return self.write_structure(ref,template,data,fragment)
        header=8 if fragment else 4;need(data,header);type_code,count=struct.unpack_from('<HH',data)
        dtype,refs=self.region(ref,count,True)
        if type_code!=TYPES[dtype][0]:raise CIPError(0xFF,'Tag type does not match declared type')
        fmt='<'+TYPES[dtype][1];size=struct.calcsize(fmt)
        offset=struct.unpack_from('<I',data,4)[0] if fragment else 0;payload=data[header:]
        if not fragment:exact(data,header+count*size)
        if not payload:raise CIPError(0x13,'Fragment contains no data')
        if offset>=count*size or len(payload)>count*size-offset:raise CIPError(0x20,'Fragment exceeds requested atomic region')
        first=offset//size;last=(offset+len(payload)-1)//size;values=[]
        for index in range(first,last+1):
            start=max(offset,index*size);end=min(offset+len(payload),(index+1)*size)
            lo=start-index*size;hi=end-index*size;chunk=payload[start-offset:end-offset]
            if lo==0 and hi==size:raw=chunk
            else:
                # Partial atoms preserve known backing bytes. Unknown bytes are
                # never filled with zeros just to accept an incomplete write.
                old=self.app.engine.memory.read(refs[index])
                raw=bytearray(struct.pack(fmt,int(old) if dtype=='BOOL' else old));raw[lo:hi]=chunk
            values.append(struct.unpack(fmt,raw)[0])
        self.store_atomic(dtype,refs[first:last+1],values)
        return 0,b''

    def write_structure(self,ref,template,data,fragment=False):
        header=10 if fragment else 6;need(data,header)
        type_code,handle,count=struct.unpack_from('<HHH',data)
        if type_code!=0x02A0 or handle!=template.handle:raise CIPError(0xFF,'Structure type or handle does not match the template')
        refs=self.structure_region(ref,count,template,True);total=count*template.size
        offset=struct.unpack_from('<I',data,6)[0] if fragment else 0;payload=data[header:]
        if not fragment:exact(data,header+total)
        if not payload:raise CIPError(0x13,'Fragment contains no data')
        if offset>=total or len(payload)>total-offset:raise CIPError(0x20,'Fragment exceeds requested structured region')
        end=offset+len(payload);values=[];memory=self.app.engine.memory;covered=bytearray(len(payload))
        first=offset//template.size;last=(end-1)//template.size
        for index in range(first,last+1):
            for member_offset,dtype,member_ref,bit in self.templates().leaves(template,refs[index],index*template.size):
                if bit is not None:
                    if offset<=member_offset<end:
                        self.access(member_ref,True)
                        mask=1<<bit;position=member_offset-offset;covered[position]|=mask
                        values.append((member_ref,bool(payload[position]&mask)))
                    continue
                fmt='<'+TYPES[dtype][1];size=struct.calcsize(fmt)
                start=max(offset,member_offset);stop=min(end,member_offset+size)
                if start>=stop:continue
                self.access(member_ref,True)
                chunk=payload[start-offset:stop-offset];covered[start-offset:stop-offset]=b'\xFF'*(stop-start)
                if stop-start==size:raw=chunk
                else:
                    # Preserve known bytes in split atoms; untouched members may
                    # remain unknown and are never read merely to fill a packet.
                    raw=bytearray(struct.pack(fmt,memory.read(member_ref)))
                    raw[start-member_offset:stop-member_offset]=chunk
                values.append((member_ref,struct.unpack(fmt,raw)[0]))
        if any(value&(~used&0xFF) for value,used in zip(payload,covered)):
            raise CIPError(9,'Reserved layout padding and unused host bits must be zero')
        if values:self.store_values(values)
        return 0,b''

    def read_modify_write(self,path,data):
        if not self.endpoint.allow_writes:raise CIPError(0x0F,'Network writes are disabled')
        need(data,2);mask_size=struct.unpack_from('<H',data)[0]
        dtype,refs=self.region(self.reference(path),1,True)
        if dtype in ('BOOL','REAL'):raise CIPError(8,'Read Modify Write supports integer atoms only')
        fmt='<'+TYPES[dtype][1];size=struct.calcsize(fmt)
        if mask_size not in (1,2,4,8) or mask_size>size:raise CIPError(3,'Mask size exceeds the integer atom')
        exact(data,2+2*mask_size)
        or_mask=int.from_bytes(data[2:2+mask_size],'little');and_mask=int.from_bytes(data[2+mask_size:],'little')
        old=self.app.engine.memory.read(refs[0]);low_mask=(1<<(mask_size*8))-1
        value=((old&~low_mask)|(((old&low_mask)|or_mask)&and_mask))&((1<<(size*8))-1)
        value=struct.unpack(fmt,value.to_bytes(size,'little'))[0]
        self.store_atomic(dtype,refs,[value])
        return 0,b''

    def symbol_scope(self,path,tag=False):
        scope=''
        if path.program_instance is not None:
            native=getattr(self.app,'native_symbols',None)
            if native is None or path.program_instance not in native.program_ids:raise CIPError(5,'Unknown native program instance')
            scope=native.program_ids[path.program_instance]
        if path.symbols:
            named=isinstance(path.symbols[0],str) and path.symbols[0].lower().startswith('program:')
            if named:
                if path.program_instance is not None:raise CIPError(4,'Cannot combine native and symbolic program scope')
                scope=path.symbols[0][8:]
                if not scope:raise CIPError(5,'Unknown program scope')
            if not tag and (not named or len(path.symbols)!=1):raise CIPError(4,'Unsupported symbol enumeration path')
        if scope:
            program=next((p for n,p in self.app.engine.project.programs.items() if n.lower()==scope.lower()),None)
            if program is None:raise CIPError(5,'Unknown program scope')
            if program['class']!='Standard':raise CIPError(0x0F,'Program is not externally accessible')
        return scope

    def symbol_attributes(self,symbol):
        row=symbol.get('object_reference')
        if row is not None:
            scope=getattr(row,'program','')
            catalog=getattr(self.app,'native_routine_reference_symbols' if scope else 'native_reference_symbols',None)
            if row not in self.reference_symbols(scope):raise CIPError(0x0C,'Reference Symbol is no longer current')
            addresses=self.app.engine.runtime_references.symbol_addresses(self.app.engine.project,catalog,row)
            if addresses is None:raise CIPError(0x0C,'Reference Symbol backing is unavailable')
            return row.attributes(*addresses)
        tag=self.app.engine.project.tags[symbol['ref'].lower()]
        storage=self.scalar_storage().by_ref.get(symbol['ref'].lower())
        attributes=symbol_metadata.attributes(symbol,tag.constant,storage)
        if storage is not None:
            control=self.installed_symbol_control(symbol,storage)
            if control is not None:attributes[6]=control
        return attributes

    def installed_symbol_control(self,symbol,storage=None):
        """Read an original opaque control word from a committed source view.

        The download already retained this field without interpreting its bits.
        Do not turn it into a model flag or alter the backed value/header links.
        """
        engine=self.app.engine;project=engine.project
        installed=getattr(engine,'installed_download',None)
        if not self.endpoint.native_read_only or installed is None:return None
        try:
            installed.check(self.app.native_project_identity,project)
            catalog=self.app.native_symbols;row=catalog.by_key.get(symbol['ref'].casefold()) if catalog else None
            if row is None or row.instance!=symbol['id']:raise ImageError('installed_symbol_identity_changed')
            if getattr(project,'runtime_revision',0) or getattr(project,'runtime_edited_routines',()):
                from .installed_memory import _verified_installation
                installation=_verified_installation(self.app,self)
                if storage is None:storage=self.scalar_storage(_verified_installation=installation).by_ref.get(symbol['ref'].casefold())
                if storage is None or storage.code!=symbol['type']:raise ImageError('installed_symbol_type_changed')
                return installed.tag_bindings.control(symbol['ref'].casefold(),storage.table_code)
            ns=installed.namespace;incremental=ns._incremental
            if incremental is None:raise ImageError('installed_symbol_header_required')
            bindings=HeaderBindings(engine,ns,catalog,self.app.native_routines,self.app.native_auxiliary_symbols,
                self.app.native_tasks,self.app.native_tables)
            expected=bindings.expected(0x6B,row.program_instance,row.instance)
            if storage is None:storage=self.scalar_storage().by_ref.get(symbol['ref'].casefold())
            if (storage is None or storage.code!=symbol['type']
                    or expected[2]!=struct.pack('<H',storage.table_code)):
                raise ImageError('installed_symbol_type_changed')
            incremental.verify_effects(ns._image,ns._source,self.app.native_metadata_values,bindings)
            value=incremental.read_attribute(0x6B,row.program_instance,row.instance,6,
                ns._image,ns._source,self.app.native_metadata_values,bindings)
            if not isinstance(value,bytes) or len(value)!=4:raise ImageError('installed_symbol_control_invalid')
            return value
        except ImageError as error:raise CIPError(0x0C,error.reason) from error

    def programs(self):
        native=getattr(self.app,'native_symbols',None)
        if native is None:raise CIPError(0x0C,'Native program bindings are unavailable; import the matching ACD')
        project=self.app.engine.project
        if native.source_l5x_sha256!=project.sha256:raise CIPError(0x0C,'Native program source changed')
        rows=[]
        for name,program in project.programs.items():
            if program['class']!='Standard':continue
            instance=native.programs.get(name.lower())
            if instance is None:raise CIPError(0x0C,'Native program inventory is incomplete')
            rows.append({'id':instance,'name':name})
        return sorted(rows,key=lambda row:row['id'])

    def program_service(self,service,path,data,limit):
        if (path.symbols or path.program_instance is not None or path.io_map_instance is not None or
                path.controller_instance is not None or path.aoi_instance is not None or path.instance is None):
            raise CIPError(4,'Program metadata requires a controller-scoped instance path')
        if service==0x4B:return self.instance_list(path,data,limit)
        if path.instance==0:
            revision=controller_schemas.object_revision(0x68,native_compatibility=self.endpoint.native_read_only)
            attributes={1:struct.pack('<H',revision)}
            try:attributes=self.catalog_class_attributes([p['id'] for p in self.programs()],0x68)
            except CIPError as error:
                if error.status!=0x0C:raise
            attributes.update(self.app.engine.project.program_forces.attributes())
            return self.attribute_read(service,path,data,attributes)
        program=next((p for p in self.programs() if p['id']==path.instance),None)
        if program is None:raise CIPError(5,'Unknown or unexposed Program instance')
        name=program['name'].encode('ascii')
        attributes={22:struct.pack('<I',program['id'])}
        if len(name)<=40:attributes[28]=struct.pack('<I',len(name))+name
        attributes.update(self.app.engine.project.program_forces.attributes(program['name']))
        attributes.update(self.app.engine.project.program_configuration.attributes(
            program['name'],source_sha256=self.app.engine.project.sha256))
        attributes.update(self.app.engine.project.program_configuration.type_attributes(
            program['name'],source_sha256=self.app.engine.project.sha256))
        project=self.app.engine.project;source=project.sha256
        attributes.update(project.program_configuration.memory_attributes(program['name'],source_sha256=source))
        attributes.update(project.program_configuration.flag_attributes(program['name'],source_sha256=source))
        attributes.update(self.app.engine.program_timing_attributes(program['name'],source_sha256=source))
        attributes.update(self.app.engine.program_fault_attributes(program['name'],source_sha256=source))
        attributes.update(project.program_diagnostics.output_attributes(program['name'],source_sha256=source))
        idle=self.endpoint.programming_lease.program_edits_idle(self.app.generation,source,program['id'])
        attributes.update(project.program_diagnostics.edit_attributes(program['name'],source_sha256=source,idle=idle))
        attributes.update(project.program_hierarchy.attributes(program['name'],source_sha256=source))
        identity=getattr(self.app,'native_project_identity',None);symbols=self.app.native_symbols
        if identity is not None and identity.source_l5x_sha256==source:
            attributes.update(project.program_hierarchy.child_attributes(program['name'],source_sha256=source,
                source_acd_sha256=identity.source_acd_sha256,program_ids=symbols.programs,
                program_source_l5x_sha256=symbols.source_l5x_sha256,program_source_acd_sha256=symbols.source_acd_sha256))
            tasks=getattr(self.app,'native_tasks',None)
            if tasks is not None and symbols.source_acd_sha256==identity.source_acd_sha256:
                attributes.update(project.task_configuration.owner_attributes(program['name'],source_sha256=source,
                    source_acd_sha256=identity.source_acd_sha256,task_ids=tasks.tasks,
                    task_source_l5x_sha256=tasks.source_l5x_sha256,task_source_acd_sha256=tasks.source_acd_sha256))
        owner=attributes.get(13)
        attributes.update(self.app.engine.program_status_attributes(program['name'],source_sha256=source,
            task_owner=int.from_bytes(owner,'little') if isinstance(owner,bytes) and len(owner)==4 else None,idle=idle))
        attributes.update(self.program_reference_attributes(program,idle=idle))
        if self.zero_program_stack_supported(program):attributes[27]=bytes(4)
        return self.attribute_read(service,path,data,attributes)

    def program_reference_attributes(self,program,*,idle):
        engine=self.app.engine;project=engine.project;source=project.sha256
        if (engine.mode!='project' or engine.blockers or project.aois or not idle or
                not project.program_configuration.type_attributes(program['name'],source_sha256=source) or
                not project.program_diagnostics.edit_attributes(program['name'],source_sha256=source,idle=idle)):
            return {}
        try:
            self.source_bound_program(program['id'])
            routines=self.routines(program['id'])
        except CIPError:return {}
        if (not routines and not project.program_diagnostics.is_empty(program['name'],source_sha256=source)
                or any(project.routines.get((program['name']+'/'+row['name']).casefold()) is None or
                project.routines[(program['name']+'/'+row['name']).casefold()].kind!='RLL' for row in routines)):
            return {}
        return engine.runtime_references.program_attributes(project,program['name'])

    def require_download_namespace(self,lease,identity):
        lease.download_namespace.validate(Source(identity.source_acd_sha256,self.app.engine.project.sha256),self.app.native_types,
            native_metadata_values=getattr(self.app,'native_metadata_values',None),header_bindings=self.download_header_bindings(lease),
            task_bindings=self.download_task_bindings(lease),
            controller_bindings=ControllerBindings(self.app.engine,lease.download_namespace,identity),
            device_identity=self.endpoint.identity,
            setup_bindings=self.download_setup_bindings(lease),
            routine_bindings=self.download_routine_bindings(lease),
            map_bindings=self.download_map_bindings(lease),
            changelog_bindings=self.download_changelog_bindings(lease),
            native_symbols=self.app.native_symbols,native_routines=self.app.native_routines,
            native_auxiliary_symbols=self.app.native_auxiliary_symbols,native_tables=self.app.native_tables)

    def download_setup_bindings(self,lease):
        return SetupBindings(self.app.engine.project,lease.download_namespace,self.endpoint.identity,self.endpoint.interface)

    def download_routine_bindings(self,lease):
        return RoutineBindings(self.download_header_bindings(lease),self.app.native_types)

    def download_map_bindings(self,lease):
        return MapBindings(self.download_header_bindings(lease),self.app.native_types,
            getattr(self.app,'native_metadata_values',None),self.endpoint.identity,self.download_setup_bindings(lease))

    def download_changelog_bindings(self,lease):
        return ChangelogBindings(self.download_map_bindings(lease),self.app.native_project_identity)

    def download_header_bindings(self,lease):
        return HeaderBindings(self.app.engine,lease.download_namespace,self.app.native_symbols,self.app.native_routines,
            self.app.native_auxiliary_symbols,getattr(self.app,'native_tasks',None),self.app.native_tables)

    def download_task_bindings(self,lease):
        return TaskBindings(self.app.engine,lease.download_namespace,getattr(self.app,'native_tasks',None),
            self.app.native_project_identity,self.app.native_symbols,self.app.native_auxiliary_symbols)

    def source_bound_program(self,instance):
        identity=self.app.native_project_identity;symbols=self.app.native_symbols
        source=self.app.engine.project.sha256
        if (identity is None or identity.source_l5x_sha256!=source or symbols is None
                or symbols.source_acd_sha256!=identity.source_acd_sha256):
            raise CIPError(0x0C,'Original Program source correlation unavailable')
        program=next((row for row in self.programs() if row['id']==instance),None)
        if program is None:raise CIPError(5,'Unknown source-bound Program')
        return program

    def zero_program_stack_supported(self,program):
        project=self.app.engine.project
        return (project.aoi_catalog.empty and not project.aois and not self.app.engine.blockers
                and project.executable_configuration.routine_names(program['name'],source_sha256=project.sha256) is not None)

    def receive_edit_fragment(self,envelope,native,lease):
        source=self.app.engine.project.sha256
        lease.require_edit_owner(native,self.app.generation,source)
        if not lease.edit_phase_open:raise CIPError(0x0C,'Edit preparation phase required')
        if self.app.controller_state()['mode']!='Program':raise CIPError(0x0C,'Program mode required')
        prefix=None;target=lease.edit_transfer.target;kind=lease.edit_transfer.kind or 'code'
        if envelope.container_format==0x101:
            raw=envelope.fragment
            if len(raw)<2:raise CIPError(0x13,'Truncated edit operation')
            end=2+2*raw[1];need(raw,end+8)
            path=decode_path(raw[2:end]);payload=raw[end:]
            if (raw[0]!=0x5C or path.class_id!=0x6D or path.program_instance is None or not path.instance
                    or path.attribute is not None or path.symbols or path.io_map_instance is not None
                    or path.controller_instance is not None):
                raise CIPError(0x0F,'Unsupported compiled edit target')
            if payload[:8]==struct.pack('<II',3,1):
                need(payload,16)
                if payload[12:16]!=bytes(4):raise CIPError(3,'Unsupported compiled edit setup')
                kind='code';prefix=raw[:end+16]
            elif payload[:8]==struct.pack('<II',1,3):kind='source';prefix=raw[:end+8]
            else:raise CIPError(3,'Unsupported compiled edit setup')
            target=(path.program_instance,path.instance)
        if target is None:raise CIPError(0x0C,'Compiled edit first fragment required')
        program=self.source_bound_program(target[0])
        if not self.zero_program_stack_supported(program):raise CIPError(0x0C,'Compiled edit source unavailable')
        if target[0] not in lease.program_reservations:raise CIPError(0x0F,'Program reservation required')
        routine=next((row for row in self.routines(target[0]) if row['id']==target[1]),None)
        if routine is None:raise CIPError(5,'Unknown source-bound edit Routine')
        active=self.app.engine.project.routines.get((routine['program']+'/'+routine['name']).lower())
        if active is None or active.kind!='RLL':raise CIPError(0x0F,'Compiled edit Routine type unsupported')
        lease.edit_transfer.accept(envelope,target=target,prefix=prefix,kind=kind)
        decoded=lease.edit_transfer.source
        if decoded and decoded.name.casefold()!=routine['name'].casefold():raise CIPError(0x0C,'Routine source target mismatch')
        if decoded:
            from .routine_source import resolve,validate_plan,SourceError
            try:lease.edit_transfer.translated_rungs=resolve(decoded,self.app.engine.project,self.app.native_symbols,
                    self.app.native_routines,self.app.native_types,routine['program'])
            except SourceError as error:lease.edit_transfer.reference_error=str(error)
            if lease.edit_transfer.translated_rungs is not None:
                try:validate_plan(decoded,lease.edit_transfer.translated_rungs,self.app.engine.project,routine['program'])
                except SourceError as error:lease.edit_transfer.plan_error=str(error)
                else:
                    lease.edit_transfer.plan_validated=True
                    lease.edit_transfer.base_revision=getattr(self.app.engine.project,'runtime_revision',0)
        state=lease.edit_transfer.description()
        self.endpoint.record('native_edit_fragment',container_format=envelope.container_format,
            position=envelope.position,received_bytes=state['received_bytes'],total_bytes=state['total_bytes'],
            fragments=state['fragments'],complete=state['complete'],container_sha256=state['container_sha256'],
            component_kind=kind,retained_bytes=state['retained_bytes'],source_description=state['source_description'])
        return state

    def tasks(self):
        project=self.app.engine.project
        native=getattr(self.app,'native_tasks',None)
        configuration=project.task_configuration
        if native is None or native.source_l5x_sha256!=project.sha256 or not configuration.source_complete:
            raise CIPError(0x0C,'Native Task identities require the matching complete source')
        rows=[]
        for name in configuration.names:
            instance=native.lookup(name)
            if instance is None:raise CIPError(0x0C,'Native Task inventory is incomplete')
            rows.append({'id':instance,'name':name})
        return sorted(rows,key=lambda row:row['id'])

    def routines(self,program_instance):
        program=next((row for row in self.programs() if row['id']==program_instance),None)
        if program is None:raise CIPError(5,'Unknown or unexposed Program for Executable inventory')
        project=self.app.engine.project
        names=project.executable_configuration.routine_names(program['name'],source_sha256=project.sha256)
        native=getattr(self.app,'native_routines',None)
        symbols=self.app.native_symbols
        if (names is None or native is None or native.source_l5x_sha256!=project.sha256
                or native.source_acd_sha256!=symbols.source_acd_sha256):
            raise CIPError(0x0C,'Executable inventory requires matching complete source and native identities')
        rows=[]
        for name in names:
            routine=native.lookup(program['name'],name)
            if routine is None or routine.program_instance!=program_instance:
                raise CIPError(0x0C,'Native Executable inventory is incomplete for this Program')
            rows.append({'id':routine.instance,'name':name,'program':program['name'],'program_instance':program_instance,
                         'type_word':routine.type_word,'source_key':routine.source_key})
        return sorted(rows,key=lambda row:row['id'])

    def aoi_routines(self,aoi_instance):
        parent=next((row for row in self.aoi_definitions() if row['id']==aoi_instance),None)
        if parent is None:raise CIPError(5,'Unknown AOI parent for Executable inventory')
        metadata=parent['metadata'];native=getattr(self.app,'native_aoi_routines',None)
        binding=self.app.native_aois;project=self.app.engine.project
        if (metadata.routines is None or native is None or native.source_l5x_sha256!=project.sha256
                or native.source_acd_sha256!=binding.source_acd_sha256):
            raise CIPError(0x0C,'AOI Executable inventory requires complete readable source and native identities')
        expected={r.name.casefold() for r in metadata.routines}
        found=[r for r in native.rows if r.aoi.casefold()==metadata.name.casefold()]
        if {r.name.casefold() for r in found}!=expected or any(r.aoi_instance!=aoi_instance for r in found):
            raise CIPError(0x0C,'AOI Executable inventory differs from the selected parent')
        by_name={r.name.casefold():r for r in metadata.routines}
        return sorted(({'id':r.instance,'metadata':by_name[r.name.casefold()],'type_word':r.type_word} for r in found),key=lambda r:r['id'])

    def routine_identity_attributes(self,binding,type_word,instance,name=None):
        identity=getattr(self.app,'native_project_identity',None);source=self.app.engine.project.sha256
        if (binding is None or identity is None or identity.source_l5x_sha256!=source or
                binding.source_l5x_sha256!=source or binding.source_acd_sha256!=identity.source_acd_sha256):return {}
        attributes={9:struct.pack('<I',instance),**({1:struct.pack('<H',type_word)} if type_word is not None else {})}
        # The v35 Executable layout pairs Name with a BITS32 byte count.
        # This is source metadata, independent of runtime code/edit buffers.
        if isinstance(name,str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,39}',name):
            raw=name.encode('ascii');attributes[25]=struct.pack('<I',len(raw))+raw
        return attributes

    def routine_class_revision(self):
        project=self.app.engine.project
        if (not self.endpoint.native_read_only or project.version!='35' or project.processor!='1756-L85E'
                or not project.executable_configuration.source_complete or project.aois):
            return 1
        # The v35 RLL instance schema is paired with Executable class revision
        # 11 in the observed upload. Keep the legacy profile when the complete
        # current typed, unprotected Routine inventory cannot be established.
        found=False
        try:
            for program in self.programs():
                for row in self.routines(program['id']):
                    target=project.routines[(row['program']+'/'+row['name']).casefold()]
                    if (target.kind!='RLL' or row['type_word']!=0x7FF or row['source_key'] is None or
                            not self.routine_identity_attributes(self.app.native_routines,row['type_word'],row['id'],row['name'])):
                        return 1
                    if ((getattr(project,'runtime_revision',0) or getattr(project,'runtime_edited_routines',()))
                            and not routine_state.current_source(self.app,self.app.engine,row['program'],row['name'],(program['id'],row['id']))):
                        return 1
                    found=True
        except CIPError:return 1
        return 11 if found else 1

    def routine_service(self,service,path,data,limit):
        if path.symbols or path.instance is None or path.io_map_instance is not None or path.controller_instance is not None:
            raise CIPError(4,'Executable metadata requires a numeric instance path')
        if path.aoi_instance is not None:
            if service==0x4B:return self.instance_list(path,data,limit)
            rows=self.aoi_routines(path.aoi_instance)
            if path.instance==0:attributes=self.catalog_class_attributes([row['id'] for row in rows])
            else:
                row=next((row for row in rows if row['id']==path.instance),None)
                if row is None:raise CIPError(5,'Unknown Executable instance in the selected AOI')
                attributes=row['metadata'].attributes()
                attributes.update(self.routine_identity_attributes(self.app.native_aoi_routines,row['type_word'],row['id'],row['metadata'].name))
            return self.attribute_read(service,path,data,attributes)
        if path.program_instance is None:
            if path.instance==0 and service in (3,0x0E):
                # Class revision describes the selected schema, never a Routine
                # instance Type word. Global discovery does not flatten Programs.
                return self.attribute_read(service,path,data,{1:struct.pack('<H',self.routine_class_revision())})
            raise CIPError(4,'Executable inventory and instance reads require a parent Program')
        if service==0x4B:return self.instance_list(path,data,limit)
        rows=self.routines(path.program_instance)
        if path.instance==0:
            attributes=self.catalog_class_attributes([row['id'] for row in rows])
            attributes[1]=struct.pack('<H',self.routine_class_revision())
        else:
            routine=next((row for row in rows if row['id']==path.instance),None)
            if routine is None:raise CIPError(5,'Unknown Executable instance in the selected Program')
            attributes=self.app.engine.project.executable_configuration.attributes(
                routine['program'],routine['name'],source_sha256=self.app.engine.project.sha256)
            identity_fields=self.routine_identity_attributes(self.app.native_routines,routine['type_word'],routine['id'],routine['name'])
            attributes.update(identity_fields)
            if identity_fields:
                source=self.app.engine.project.sha256
                idle=self.endpoint.programming_lease.program_edits_idle(self.app.generation,source,path.program_instance)
                state_fields=routine_state.attributes(self.app.engine,routine['program'],routine['name'],
                    source_sha256=source,idle=idle,type_bound=routine['type_word'] is not None,
                    app=self.app,native_target=(path.program_instance,routine['id']))
                attributes.update(state_fields)
                if state_fields:
                    key=routine_state.source_key(self.app,path.program_instance,routine['id'])
                    if key is not None:attributes[22]=struct.pack('<H',len(key))+key
        return self.attribute_read(service,path,data,attributes)

    def routine_labels_service(self,service,path,data):
        if (self.endpoint.native_read_only and path.program_instance is None and path.routine_instance is None
                and path.instance==0 and not path.symbols and path.aoi_instance is None
                and path.io_map_instance is None and path.controller_instance is None
                and service in (3,0x0E) and self.app.engine.project.version=='35'
                and self.app.engine.project.processor=='1756-L85E'):
            return self.attribute_read(service,path,data,{1:struct.pack('<H',1)})
        if (not self.endpoint.native_read_only or path.program_instance is None or path.routine_instance is None
                or path.symbols or path.attribute is not None or path.aoi_instance is not None
                or path.io_map_instance is not None or path.controller_instance is not None):
            raise CIPError(4,'Label discovery requires a numeric Program/Routine parent')
        if service!=0x4B:raise CIPError(8,'Only empty Label discovery is supported')
        exact(data,0)
        if path.instance!=0:raise CIPError(5,'No Label instance is exposed')
        row=next((row for row in self.routines(path.program_instance) if row['id']==path.routine_instance),None)
        if row is None:raise CIPError(5,'Unknown Routine for Label discovery')
        engine=self.app.engine;source=engine.project.sha256
        identity=self.routine_identity_attributes(self.app.native_routines,row['type_word'],row['id'],row['name'])
        idle=self.endpoint.programming_lease.program_edits_idle(self.app.generation,source,path.program_instance)
        state=routine_state.attributes(engine,row['program'],row['name'],source_sha256=source,idle=idle,
            type_bound=row['type_word']==0x7FF,app=self.app,native_target=(path.program_instance,row['id']))
        key=(row['program']+'/'+row['name']).casefold()
        target=engine.project.routines.get(key)
        if (not identity or not state or target is None or
                any(op.name in ('LBL','JMP') for rung in target.rungs for op in operations(rung['nodes']))):
            raise CIPError(0x0C,'Complete verified source without LBL instructions is required')
        return 0,b''

    def task_service(self,service,path,data,limit):
        if path.symbols or path.program_instance is not None or path.instance is None:
            raise CIPError(4,'Task metadata requires a controller-scoped instance path')
        if service==0x4B:return self.instance_list(path,data,limit)
        if path.instance==0:
            # Layout selection is independent of partial field availability.
            # Counts describe only source-bound, exposed ordinary tasks.
            revision=controller_schemas.object_revision(0x70,native_compatibility=self.endpoint.native_read_only,legacy_revision=2)
            attributes={1:struct.pack('<H',revision)}
            try:
                rows=self.tasks()
                attributes.update({2:struct.pack('<I',max((row['id'] for row in rows),default=0)),
                                   3:struct.pack('<I',len(rows))})
            except CIPError as error:
                if error.status!=0x0C:raise
        else:
            task=next((row for row in self.tasks() if row['id']==path.instance),None)
            if task is None:raise CIPError(5,'Unknown or unexposed Task instance')
            attributes=self.app.engine.project.task_configuration.attributes(
                task['name'],source_sha256=self.app.engine.project.sha256)
            attributes.update(self.app.engine.project.task_configuration.memory_attributes(
                task['name'],source_sha256=self.app.engine.project.sha256))
            attributes.update(self.app.engine.project.task_timing.attributes(
                task['name'],source_sha256=self.app.engine.project.sha256))
            measured=self.app.engine.task_measurement_attributes(task['name'],source_sha256=self.app.engine.project.sha256)
            attributes.update(measured)
            attributes.update(self.app.engine.task_status_attributes(task['name'],source_sha256=self.app.engine.project.sha256))
            attributes.update(self.app.engine.task_stack_attributes(task['name'],source_sha256=self.app.engine.project.sha256))
            identity=getattr(self.app,'native_project_identity',None);source=self.app.engine.project.sha256
            if (measured and identity is not None and identity.source_l5x_sha256==source
                    and identity.source_acd_sha256==self.app.native_tasks.source_acd_sha256
                    and not self.endpoint.programming_lease.scan_inhibited(self.app.generation,source)):
                attributes.update(self.app.engine.runtime_references.task_attributes(self.app.engine.project,task['name']))
            programs=getattr(self.app,'native_symbols',None)
            if programs is not None:
                attributes.update(self.app.native_tasks.configuration_attributes(
                    self.app.engine.project,task['name'],identity,programs))
                attributes.update(self.app.engine.project.task_configuration.scheduled_attributes(
                    task['name'],source_sha256=self.app.engine.project.sha256,
                    source_acd_sha256=self.app.native_tasks.source_acd_sha256,program_ids=programs.programs,
                    program_source_l5x_sha256=programs.source_l5x_sha256,
                    program_source_acd_sha256=programs.source_acd_sha256))
        return self.attribute_read(service,path,data,attributes)

    def aoi_definitions(self):
        project=self.app.engine.project;catalog=project.aoi_catalog
        if catalog.empty:return []
        binding=getattr(self.app,'native_aois',None);identity=self.app.native_project_identity
        if (catalog.metadata is None or binding is None or binding.source_l5x_sha256!=project.sha256
                or identity is None or identity.source_l5x_sha256!=project.sha256
                or binding.source_acd_sha256!=identity.source_acd_sha256
                or set(binding.definitions)!={row.name.casefold() for row in catalog.metadata}):
            raise CIPError(0x0C,'AOI inventory requires complete matching source identities')
        return sorted(({'id':binding.definitions[row.name.casefold()][1],'metadata':row}
                       for row in catalog.metadata),key=lambda row:row['id'])

    def aoi_service(self,service,path,data,limit):
        if path.symbols or path.program_instance is not None or path.instance is None:
            raise CIPError(4,'AOI definitions require a controller-scoped numeric instance')
        if service==0x4B:return self.instance_list(path,data,limit)
        if path.instance==0:
            # Installed v35 revision 6 and captured original AOI state reads.
            # This revision does not declare max/count or compiled addresses.
            attributes={1:struct.pack('<H',6)}
        else:
            row=next((row for row in self.aoi_definitions() if row['id']==path.instance),None)
            if row is None:raise CIPError(5,'Unknown source AOI definition')
            attributes=row['metadata'].attributes()
        return self.attribute_read(service,path,data,attributes)

    def aoi_description(self):
        result=self.app.engine.project.aoi_catalog.description()
        try:rows=self.aoi_definitions()
        except CIPError:
            return {**result,'instance_list':False,'instance_count':None,'identity_binding_available':False}
        return {**result,'instance_list':True,'instance_count':len(rows),
                'identity_binding_available':getattr(self.app,'native_aois',None) is not None}

    def catalog_class_attributes(self,instances,class_id=None):
        # The generic model keeps revision 1. Native layout selection never
        # changes these backed IDs/counts or supplies compiler signatures.
        revision=1 if class_id is None else controller_schemas.object_revision(class_id,native_compatibility=self.endpoint.native_read_only)
        return {1:struct.pack('<H',revision),2:struct.pack('<I',max(instances,default=0)),
                3:struct.pack('<I',len(instances))}

    def exposed_templates(self):
        scopes=['']+[n for n,p in self.app.engine.project.programs.items() if p['class']=='Standard']
        instances={s['type']&0xFFF for scope in scopes for s in self.symbols(scope) if s['type']&0x8000}
        return self.templates().closure(instances)

    def data_tables(self,scope=''):
        # Alias symbols refer to another tag's storage and do not create a new
        # Data Table instance. Reuse discovery's type/access/source checks.
        from .installed_memory import table_ids
        try:installed=table_ids(self.app,self)
        except ImageError as error:raise CIPError(0x0C,error.reason) from error
        return self._data_tables(scope,installed)

    def _data_tables(self,scope,installed):
        """One already verified Table map shared by this storage construction."""
        tags=self.app.engine.project.tags
        rows=[]
        for symbol in self.symbols(scope):
            if symbol.get('object_reference') is not None or tags[symbol['ref'].lower()].alias:continue
            if installed is not None:
                instance=installed.get(symbol['ref'].casefold())
                if instance is None:raise CIPError(0x0C,'installed_table_symbol_binding_unavailable')
                symbol={**symbol,'id':instance,'symbol_id':symbol['id']}
            rows.append(symbol)
        return sorted(rows,key=lambda row:row['id'])

    def data_table_service(self,service,path,data,limit):
        scope=self.symbol_scope(path)
        if service==0x4B:return self.instance_list(path,data,limit)
        if path.instance is None:raise CIPError(4,'Data Table path requires an instance')
        tables=self.data_tables(scope)
        if path.instance==0:
            attributes=self.catalog_class_attributes([s['id'] for s in tables],0x6A)
        else:
            table=next((s for s in tables if s['id']==path.instance),None)
            if table is None:raise CIPError(5,'Unknown modeled Data Table instance')
            storage=self.scalar_storage().by_ref.get(table['ref'].lower())
            if storage is not None and self.app.engine.project.tags[table['ref'].lower()].constant:
                from .installed_memory import read_constant
                try:read_constant(self.app,self,table['ref'].lower())
                except ImageError as error:raise CIPError(0x0C,error.reason) from error
            attributes=data_table.attributes(table,storage)
            if service==0x4F:
                if path.attribute is not None:raise CIPError(4,'Data Table reads do not take an attribute')
                exact(data,6);selector,count=struct.unpack('<IH',data)
                if storage is None:raise CIPError(8,'No supported model storage for this table')
                if selector!=0 or count!=storage.size:raise CIPError(3,'Only zero-selector full storage reads are supported')
                if count>limit-4:raise CIPError(0x1B,'Response cannot hold the full Data Table value')
                def read(ref):
                    self.access(ref)
                    return self.app.engine.memory.read(ref)
                return 0,storage.value(read)
        # Only this model's backed addresses are exposed. Formal types,
        # native physical memory and programming services remain unavailable.
        return self.attribute_read(service,path,data,attributes)

    def scalar_storage(self,*,_verified_installation=None):
        rows=[];project=self.app.engine.project
        from .installed_memory import constant_keys,table_ids,_table_ids
        try:
            installed=(table_ids(self.app,self) if _verified_installation is None
                       else _table_ids(self.app,*_verified_installation))
        except ImageError as error:raise CIPError(0x0C,error.reason) from error
        constants=constant_keys(self.app,self)
        scopes=['']+[name for name,p in project.programs.items() if p['class']=='Standard']
        for scope in scopes:
            for symbol in self._data_tables(scope,installed):
                tag=project.tags[symbol['ref'].lower()]
                if tag.constant and tag.key.casefold() not in constants:continue
                dtype=self.access(symbol['ref'])[2]
                if dtype in TYPES:rows.append((symbol,'<'+TYPES[dtype][1]))
                else:
                    catalog=self.templates();template=catalog.for_type(dtype)
                    if template:rows.append((symbol,data_table.StructureLayout(catalog,template)))
        key=(project,tuple((s['ref'],s['id'],s.get('symbol_id'),s['type'],tuple(s['dimensions']),fmt) for s,fmt in rows))
        if key!=self._storage_key:
            self._storage=data_table.AddressSpace(rows);self._storage_key=key
        return self._storage

    def enumerate_symbols(self,path,data,limit=REPLY_LIMIT):
        scope=self.symbol_scope(path)
        if path.attribute is not None:raise CIPError(4,'Enumeration path does not take an attribute')
        need(data,2);n=struct.unpack_from('<H',data)[0];exact(data,2+2*n)
        attrs=struct.unpack_from('<'+'H'*n,data,2)
        if not n or n>16 or any(a not in symbol_metadata.ATTRIBUTES for a in attrs):raise CIPError(0x14,'Unsupported Symbol attribute')
        out=b''
        for symbol in self.symbols(scope):
            if symbol['id']<(path.instance or 0):continue
            values=self.symbol_attributes(symbol)
            if any(a not in values for a in attrs):raise CIPError(0x14,'Symbol storage attribute unavailable for this tag kind')
            row=struct.pack('<I',symbol['id'])+b''.join(values[a] for a in attrs)
            if len(out)+len(row)>limit-4:
                if not out:raise CIPError(0x1B,'One symbol row exceeds negotiated response size')
                return 6,out
            out+=row
        return 0,out

    def diagnostics(self):
        catalog=getattr(self.app,'native_diagnostics',None);identity=getattr(self.app,'native_project_identity',None)
        source=self.app.engine.project.sha256
        if (catalog is None or identity is None or catalog.source_l5x_sha256!=source or
                identity.source_l5x_sha256!=source or catalog.source_acd_sha256!=identity.source_acd_sha256):
            raise CIPError(0x0C,'Original diagnostic definition binding is unavailable or stale')
        return catalog

    def diagnostic_profiles(self):
        catalog=getattr(self.app,'native_diagnostic_profiles',None);identity=getattr(self.app,'native_project_identity',None)
        source=self.app.engine.project.sha256
        if (catalog is None or identity is None or catalog.source_l5x_sha256!=source or
                identity.source_l5x_sha256!=source or catalog.source_acd_sha256!=identity.source_acd_sha256):
            raise CIPError(0x0C,'Original empty diagnostic profile binding is unavailable or stale')
        return catalog

    def diagnostic_objects(self):
        catalog=getattr(self.app,'native_diagnostic_objects',None);identity=getattr(self.app,'native_project_identity',None)
        source=self.app.engine.project.sha256
        if (catalog is None or identity is None or catalog.source_l5x_sha256!=source or
                identity.source_l5x_sha256!=source or catalog.source_acd_sha256!=identity.source_acd_sha256):
            raise CIPError(0x0C,'Original empty diagnostic object binding is unavailable or stale')
        return catalog

    def security_bindings(self):
        catalog=getattr(self.app,'native_security_bindings',None);identity=getattr(self.app,'native_project_identity',None)
        source=self.app.engine.project.sha256
        if (catalog is None or identity is None or catalog.source_l5x_sha256!=source or
                identity.source_l5x_sha256!=source or catalog.source_acd_sha256!=identity.source_acd_sha256):
            raise CIPError(0x0C,'Original empty security authority binding is unavailable or stale')
        return catalog

    def metadata_definitions(self):
        catalog=getattr(self.app,'native_metadata_definitions',None);identity=getattr(self.app,'native_project_identity',None)
        source=self.app.engine.project.sha256
        if (catalog is None or identity is None or catalog.source_l5x_sha256!=source or
                identity.source_l5x_sha256!=source or catalog.source_acd_sha256!=identity.source_acd_sha256):
            raise CIPError(0x0C,'Original Metadata Definition binding is unavailable or stale')
        return catalog

    def read_metadata_values(self,payload,native,limit):
        catalog=self.app.native_metadata_values;definitions=self.metadata_definitions()
        if (catalog.source_acd_sha256!=definitions.source_acd_sha256 or
                catalog.source_l5x_sha256!=definitions.source_l5x_sha256 or catalog.definitions!=definitions):
            native.metadata_query=None
            raise CIPError(0x0C,'Original Metadata Value binding is unavailable or stale')
        try:query=metadata_query.parse_query(payload)
        except ValueError as error:raise CIPError(3,'Unsupported metadata value query') from error
        if getattr(self.app.engine.project,'runtime_revision',0) and query.selection!='controller-attribute-26':
            native.metadata_query=None
            raise CIPError(0x0C,'Original metadata values do not describe edited runtime logic')
        installed=getattr(self.app.engine,'installed_download',None);provider=installed or catalog
        try:
            data=(catalog.body(query.selection) if installed is None else
                installed.metadata_body(self.app.native_project_identity,self.app.engine.project,catalog,query.selection))
        except ImageError as error:
            native.metadata_query=None
            raise CIPError(0x0C,error.reason) from error
        cursor=native.metadata_query
        if query.format==1 and (cursor is None or cursor[0] is not provider or cursor[1]!=self.app.generation
                or cursor[2:]!=(query.selection,query.position)):
            native.metadata_query=None
            raise CIPError(0x0C,'Metadata value cursor does not match this session and source')
        available=min(limit,REPLY_LIMIT)-12
        if available<0 or (query.position<len(data) and available==0):raise CIPError(0x1B,'Metadata value reply cannot fit')
        chunk=data[query.position:query.position+available];position=query.position+len(chunk);final=position==len(data)
        fmt=(0x301 if final else 0x101) if query.format==0x101 else (0x201 if final else 1)
        native.metadata_query=None if final else (provider,self.app.generation,query.selection,position)
        self.endpoint.counts['native_metadata_value_chunks']+=1
        return reply(0x53,0,struct.pack('<II',fmt,query.position)+chunk)

    def instance_list(self,path,data,limit):
        """Get Instance List: cursor in the path, packed UDINT IDs in reply."""
        if path.instance is None or path.attribute is not None:
            raise CIPError(4,'Instance list requires a starting instance and no attribute')
        exact(data,0)
        if path.class_id in (0x6A,0x6B):
            if path.class_id==0x6A:ids=[table['id'] for table in self.data_tables(self.symbol_scope(path))]
            else:ids=[symbol['id'] for symbol in self.symbols(self.symbol_scope(path))]
        elif path.class_id==0x68:
            if path.symbols or path.program_instance is not None:raise CIPError(4,'Program discovery must be controller scoped')
            ids=[program['id'] for program in self.programs()]
        elif path.class_id==0x70:
            if path.symbols or path.program_instance is not None:raise CIPError(4,'Task discovery must be controller scoped')
            ids=[task['id'] for task in self.tasks()]
        elif path.class_id==0x6D:
            if path.symbols or path.program_instance is None and path.aoi_instance is None:
                raise CIPError(4,'Executable discovery requires a Program or AOI parent')
            ids=[routine['id'] for routine in (self.aoi_routines(path.aoi_instance) if path.aoi_instance is not None
                                              else self.routines(path.program_instance))]
        elif path.class_id==0x338:
            if path.symbols or path.program_instance is not None:raise CIPError(4,'AOI discovery must be controller scoped')
            ids=[row['id'] for row in self.aoi_definitions()]
        elif path.class_id==0x3B2:
            if path.symbols or path.program_instance is not None:raise CIPError(4,'Diagnostic definitions require a controller scope')
            ids=[row.instance for row in self.diagnostics().rows]
        elif path.class_id==0x3B1:
            if path.symbols or path.program_instance is not None:raise CIPError(4,'Diagnostic profiles require a controller scope')
            self.diagnostic_profiles();ids=[]
        elif path.class_id==0x3B0:
            if path.symbols or path.program_instance is not None:raise CIPError(4,'Diagnostic objects require a controller scope')
            self.diagnostic_objects();ids=[]
        elif path.class_id==0x349 and getattr(self.app,'native_metadata_definitions',None) is not None:
            if path.symbols or any(value is not None for value in (path.program_instance,path.io_map_instance,path.controller_instance,path.aoi_instance)):
                raise CIPError(4,'Metadata Definition discovery requires a global class path')
            ids=[row.instance for row in self.metadata_definitions().rows]
        elif path.class_id==0x36A:
            if (path.symbols or any(value is not None for value in (path.program_instance,
                    path.io_map_instance,path.controller_instance,path.aoi_instance))):
                raise CIPError(4,'Security authority binding discovery requires a controller scope')
            self.security_bindings();ids=[]
        elif path.class_id in (*alarm_catalog.PROGRAM_CLASSES,0x8D,0x36E) and path.program_instance is not None:
            if path.symbols:raise CIPError(4,'Inventory discovery requires a numeric Program parent')
            program=self.source_bound_program(path.program_instance)
            project=self.app.engine.project;configuration=project.program_configuration
            catalog=(project.alarm_catalog if path.class_id in alarm_catalog.PROGRAM_CLASSES else
                     project.message_catalog if path.class_id==0x8D else project.hmi_button_catalog)
            if (not catalog.empty or
                    not configuration.type_attributes(program['name'],source_sha256=project.sha256) or
                    configuration.flag_attributes(program['name'],source_sha256=project.sha256).get(31)!=b'\1'):
                raise CIPError(0x0C,'Program inventory is nonempty or unavailable from this source')
            ids=[]
        else:
            if path.symbols or path.program_instance is not None:
                raise CIPError(4,'This instance list requires a global class path')
            if path.class_id in (0xB0,0xB1,0x32B) and not self.app.engine.project.motion_catalog.empty:
                raise CIPError(0x0C,'Motion catalog is nonempty or unavailable from this source')
            if path.class_id in alarm_catalog.CLASSES and not self.app.engine.project.alarm_catalog.empty:
                raise CIPError(0x0C,'Alarm catalog is nonempty or unavailable from this source')
            if path.class_id==0x69 and not self.app.engine.project.io_map.empty:
                raise CIPError(0x0C,'I/O Map catalog is nonempty or unavailable from this source')
            if path.class_id==0x71 and not self.app.engine.project.data_log_catalog.empty:
                raise CIPError(0x0C,'Data Logging catalog is nonempty or unavailable from this source')
            if path.class_id==0x36E and not self.app.engine.project.hmi_button_catalog.empty:
                raise CIPError(0x0C,'HMI Button Control catalog is nonempty or unavailable from this source')
            if path.class_id in energy_catalog.CLASSES and not self.app.engine.project.energy_catalog.empty:
                raise CIPError(0x0C,'Energy inventory is unavailable for this source configuration')
            if path.class_id==0x8D and not self.app.engine.project.message_catalog.empty:
                raise CIPError(0x0C,'Message catalog is nonempty or unavailable from this source')
            ids=sorted(self.exposed_templates()) if path.class_id==0x6C else []
        ids=[instance for instance in ids if instance>=path.instance]
        capacity=max(0,(limit-4)//4)
        if ids and not capacity:raise CIPError(0x1B,'One instance ID exceeds negotiated response size')
        return (6 if len(ids)>capacity else 0),b''.join(struct.pack('<I',instance) for instance in ids[:capacity])

    def forward_open(self,data,session,large=False):
        fixed=40 if large else 36;need(data,fixed)
        path_size=data[fixed-1]*2;exact(data,fixed+path_size);route_ok(data[fixed:],True)
        if data[fixed-2]!=0xA3:raise CIPError(8,'Only point-to-point Class 3 explicit connections are modeled')
        params=[struct.unpack_from('<I' if large else '<H',data,i)[0] for i in ((26,34) if large else (26,32))]
        for param in params:
            flags=param>>16 if large else param
            size=param&(0xFFFF if large else 0x1FF)
            if flags&0x6000!=0x4000 or not 16<=size<=4000:raise CIPError(1,'Only bounded point-to-point explicit connection sizes are supported')
        if len(session.connections)>=8:raise CIPError(2,'Connection limit reached')
        # Originator identity is retained verbatim for Forward Close matching.
        ident=data[10:18]
        if any(c.identity==ident for c in session.connections.values()):raise CIPError(1,'Duplicate connection serial/originator')
        incoming=secrets.randbits(32) or 1;outgoing=struct.unpack_from('<I',data,6)[0] or (secrets.randbits(32) or 2)
        while incoming in session.connections:incoming=secrets.randbits(32) or 1
        sizes=[p&(0xFFFF if large else 0x1FF) for p in params]
        session.connections[incoming]=Connection(incoming,outgoing,ident,*sizes)
        rpi1=data[22:26];rpi2=data[30:34] if large else data[28:32]
        return 0,struct.pack('<II',incoming,outgoing)+ident+rpi1+rpi2+b'\x00\x00'

    def forward_close(self,data,session):
        need(data,12);exact(data,12+data[10]*2)
        if data[11]:raise CIPError(4,'Nonzero close-path padding')
        route_ok(data[12:],True);ident=data[2:10]
        key=next((k for k,c in session.connections.items() if c.identity==ident),None)
        if key is None:raise CIPError(1,'Unknown connection identity')
        del session.connections[key];return 0,ident+b'\x00\x00'

    def dispatch(self,raw,session,depth=0,limit=REPLY_LIMIT,budget=None):
        if depth>4:raise CIPError(8,'Nested message depth limit')
        need(raw,2);service=raw[0];end=2+raw[1]*2;need(raw,end)
        path=decode_path(raw[2:end]);data=raw[end:]
        if path.routine_instance is not None or path.class_id==0x8C:
            return self.routine_labels_service(service,path,data)
        if path.class_id==0x64 and (path.symbols or path.program_instance is not None):
            raise CIPError(4,'Extended Device paths must be controller scoped')
        if self.endpoint.native_read_only:
            if path.class_id==0x64 and path.instance==1 and not path.symbols and path.attribute is None and service in (0x4B,0x4C):
                if not session.handle:raise CIPError(0x0F,'Native compatibility requires a registered TCP session')
                try:
                    if service==0x4B:
                        self.endpoint.clear_native(session)
                        if limit<134:raise CIPError(0x1B,'Challenge exceeds connection size')
                        session.native=native_session.NativeSession()
                        with self.endpoint.lock:self.endpoint.native_sessions[id(session)]=session.native
                        return 0,session.native.begin(data)
                    if not getattr(session,'native',None):raise CIPError(0x0F,'Native challenge required')
                    return 0,session.native.acknowledge(data)
                except (native_session.NativeError,key_exchange.OfferError) as error:raise CIPError(error.status,str(error)) from error
            if path.class_id==2 and path.instance==1 and not path.symbols and path.attribute is None and service in (0x36,0x37,0x38,0x39,0x3A):
                native=getattr(session,'native',None)
                if native is None:raise CIPError(0x0F,'Native compatibility session required')
                try:envelope=native.consume(raw)
                except native_session.NativeError as error:
                    with self.endpoint.lock:self.endpoint.programming_lease.discard(native)
                    raise CIPError(error.status,str(error)) from error
                self.endpoint.record('native_verified',sequence=envelope.sequence,stage=native.stage)
                if isinstance(envelope,read_transport.ReadRequest):
                    try:
                        if native.stage!='bound':raise CIPError(0x0F,'Bound native context required')
                        with self.endpoint.lock:
                            lease=self.endpoint.programming_lease
                            if lease.live(self.app.generation,self.app.engine.project.sha256):
                                raise CIPError(0x0C,'Finish programming before reading installed Routine source')
                            if envelope.container_format==0x101:
                                if native.read_stream is not None:raise CIPError(0x0C,'Routine source read already pending')
                                inner=envelope.inner;n=2+2*inner[1];target=decode_path(inner[2:n])
                                if (inner[0]!=0x5D or target.class_id!=0x6D or not target.program_instance or not target.instance
                                        or target.attribute is not None or target.symbols or target.io_map_instance is not None
                                        or target.controller_instance is not None or target.aoi_instance is not None):
                                    raise CIPError(0x0F,'Only scoped Routine source reads are supported')
                                if inner[n:] not in tuple(struct.pack('<II',1,s) for s in (3,4,9)):
                                    raise CIPError(0x0F,'Unsupported Routine read selector')
                                selector=struct.unpack_from('<I',inner,n+4)[0]
                                stream=routine_read.Stream.begin(self.app,target.program_instance,target.instance,selector)
                            else:
                                stream=native.read_stream
                                if stream is None:raise CIPError(0x0C,'Routine source read start required')
                            encoded,complete=stream.reply(self.app,envelope,native.key,limit)
                            native.read_stream=None if complete else stream
                            self.endpoint.record('native_routine_source_read',bytes_returned=len(encoded)-36,
                                selector=stream.selector,total_bytes=len(stream.data),complete=complete,frames=stream.frames)
                    except ImageError as error:
                        native.read_stream=None
                        raise CIPError(0x1B if error.reason=='routine_read_reply_budget' else 0x0C,error.reason) from error
                    except CIPError:
                        native.read_stream=None;raise
                elif isinstance(envelope,signed_messages.FragmentEnvelope):
                    if limit<36:raise CIPError(0x1B,'Fragment acknowledgement exceeds negotiated size')
                    if native.stage!='bound':raise CIPError(0x0F,'Bound native context required')
                    identity=self.app.native_project_identity
                    if identity is None or identity.source_l5x_sha256!=self.app.engine.project.sha256:
                        raise CIPError(0x0C,'Source correlation unavailable')
                    with self.endpoint.lock:
                        lease=self.endpoint.programming_lease
                        try:
                            if lease.selector==1:
                                if isinstance(envelope,signed_messages.CompactTransferEnvelope):
                                    raise CIPError(0x0F,'Compact device transfer requires a prepared download')
                                # Check ownership before any error can discard
                                # this owner's assembly for a different client.
                                lease.require_edit_owner(native,self.app.generation,self.app.engine.project.sha256)
                                try:edit_state=self.receive_edit_fragment(envelope,native,lease)
                                except CIPError:
                                    lease.edit_transfer.clear();raise
                                # A fragment ACK confirms bounded temporary
                                # storage only. Unsupported source is denied by
                                # the following signed post-source operation;
                                # it never becomes an attachable/active edit.
                            else:
                                lease.require_prepared(native,self.app.generation,self.app.engine.project.sha256)
                                if lease.download_namespace is not None:self.require_download_namespace(lease,identity)
                                lease.transport.accept(envelope)
                                stage=lease.transport.description()
                                self.endpoint.record('native_transport_fragment',container_format=envelope.container_format,
                                    position=envelope.position,received_bytes=stage['received_bytes'],total_bytes=stage['total_bytes'],
                                    fragments=stage['fragments'],complete=stage['complete'])
                        except (programming_lease.LeaseError,resilient_transport.TransportError,edit_transfer.EditTransferError) as error:
                            raise CIPError(error.status,error.reason) from error
                        except ImageError as error:raise CIPError(0x0C,error.reason) from error
                    encoded=signed_messages.encode_fragment_ack(envelope,native.key)
                elif isinstance(envelope,signed_messages.BatchEnvelope):
                    count=len(envelope.children);available=limit-30-2*count
                    if available<4*count:raise CIPError(0x1B,'Batch reply headers exceed negotiated size')
                    children=[]
                    for index,inner in enumerate(envelope.children):
                        child_limit=available-4*(count-index-1)
                        result=self.native_read(inner,session,native,depth,child_limit,budget,registration=False)
                        if len(result)>child_limit:result=reply(inner[0],0x1B)
                        children.append(result);available-=len(result)
                    encoded=signed_messages.encode_batch_response(envelope,tuple(children),native.key)
                else:
                    inner_limit=max(4,limit-(36 if envelope.service in (0x37,0x39) else 28))
                    result=self.native_read(envelope.inner,session,native,depth,inner_limit,budget,
                                            registration=envelope.service!=0x39,
                                            transfer_control=envelope.container_control if isinstance(envelope,signed_messages.TransferEnvelope) else None)
                    if len(result)>inner_limit:result=reply(envelope.inner[0],0x1B)
                    encoded=signed_messages.encode_response(envelope,result,native.key)
                return encoded[2],encoded[4:]
        if path.class_id==6 and path.instance==1 and not path.symbols and path.attribute is None:
            if service in (0x54,0x5B):return self.forward_open(data,session,service==0x5B)
            if service==0x4E:return self.forward_close(data,session)
            if service==0x52:
                need(data,4);size=struct.unpack_from('<H',data,2)[0];need(data,4+size+size%2+2)
                pos=4+size+size%2
                if size%2 and data[4+size]:raise CIPError(4,'Nonzero message padding')
                if data[pos+1]:raise CIPError(4,'Nonzero route padding')
                exact(data,pos+2+data[pos]*2);route_ok(data[pos+2:])
                # Successful UCMM replies contain the embedded service response.
                return self.handle(data[4:4+size],session,depth+1,limit,budget),None
        if path.class_id==1 and not path.symbols:
            if path.instance==1:
                if service==0x4B:
                    if path.attribute is not None:raise CIPError(4,'Flash LEDs does not take an attribute')
                    exact(data,1)
                    self.endpoint.flash_leds(data[0])
                    return 0,b''
                if service==1 and path.attribute is None:exact(data,0);return 0,self.identity()
                return self.attribute_read(service,path,data,self.identity_attributes())
            elif path.instance in (None,0):
                return self.attribute_read(service,path,data,{1:b'\1\0',2:b'\1\0',3:b'\1\0',6:b'\7\0',7:struct.pack('<H',102)})
            raise CIPError(5,'Unknown Identity object instance')
        if path.class_id==2 and path.instance==1 and not path.symbols and service in (1,3,0x0E):
            ids=(1,2,6,0x43,*energy_catalog.CLASSES,0x64,0x67,0x68,0x69,0x6A,0x6B,0x6C,0x6D,0x70,0x71,0x74,wall_clock.CLASS_ID,0x8D,0x8E,0xAC,0xB0,0xB1,0xF4,0xF5,0xF6,0x31A,0x32B,*alarm_catalog.CLASSES,0x338,0x349,0x36A,0x36E,0x3B0,0x3B1,0x3B2)+( (0x6E,*controller_schemas.SCHEMA_REVISIONS,0x378) if self.endpoint.native_read_only else () )
            classes=struct.pack('<'+'H'*(len(ids)+1),len(ids),*ids)
            if service==1 and path.attribute is None:exact(data,0);return 0,classes
            return self.attribute_read(service,path,data,{1:classes})
        if path.class_id in (0xF4,0xF5,0xF6):
            if path.symbols:raise CIPError(4,'Network object paths do not take symbols')
            instance=path.instance
            if instance is None:raise CIPError(4,'Network object path requires an instance')
            if path.class_id==0xF4:
                try:attributes=port_attributes(instance,self.endpoint.bind_address)
                except KeyError:raise CIPError(5,'Unknown Port object instance')
                if service==1 and path.attribute is None:
                    exact(data,0);return 0,b''.join(attributes.values())
            elif instance==0:
                attributes={1:b'\1\0',2:b'\1\0',3:b'\1\0'}
                if path.class_id==0xF5:
                    # No embedded HTTP service on the PLC interface. The
                    # separate local management UI is not this service.
                    attributes.update({101:b'\0',102:b'\0'})
                if service==1 and path.attribute is None:
                    exact(data,0);return 0,b''.join(attributes[n] for n in (1,2,3))
            elif instance==1 and path.class_id==0xF6:
                attributes={}
                if service==0x4C and path.attribute in (4,5):
                    exact(data,0)
                    raise CIPError(0x0F,'Clearing Ethernet diagnostics is not authorized')
                if service==0x0E:exact(data,0)
                selected={path.attribute} if service==0x0E else set()
                if service==3 and path.attribute is None:
                    need(data,2);count=struct.unpack_from('<H',data)[0];exact(data,2+2*count)
                    if not 1<=count<=32:raise CIPError(3,'Attribute count must be 1..32')
                    selected=set(struct.unpack_from('<'+'H'*count,data,2))
                if {1,2,3,4,5,6,7,8,9,10}.intersection(selected):
                    snapshot=self.network_interface()
                    if snapshot is not None:
                        if snapshot.mac is not None:attributes[3]=snapshot.mac
                        label=snapshot.interface_label()
                        if label is not None:attributes[10]=label
                        if snapshot.link is not None:attributes.update(snapshot.link.attributes())
                        if {4,5}.intersection(selected):
                            attributes.update(self.endpoint.ethernet_counters.read(snapshot.name))
                    if service==0x0E and path.attribute not in attributes and path.attribute not in (4,5):
                        raise CIPError(0x0C,'Ethernet link attribute is unavailable on this interface')
            elif instance==1:
                if service==0x0E:exact(data,0)
                attributes={6:cip_string(socket.gethostname())}
                # Query the local OS only when the caller needs this attribute.
                # Unknown interface data is an error, never a guessed /24 or MAC.
                requested=service==0x0E and path.attribute in (1,2,3,4,5)
                if service==3 and path.attribute is None:
                    need(data,2);count=struct.unpack_from('<H',data)[0];exact(data,2+2*count)
                    if not 1<=count<=32:raise CIPError(3,'Attribute count must be 1..32')
                    requested=bool({1,2,3,4,5}.intersection(struct.unpack_from('<'+'H'*count,data,2)))
                if requested:
                    snapshot=self.network_interface()
                    attributes[4]=b'\2\0\x20\xF6\x24\1' if snapshot is not None and snapshot.mac else b'\0\0'
                    if snapshot is not None:
                        attributes[1]=struct.pack('<I',1)
                        attributes[5]=snapshot.configuration()
                        if snapshot.tcpip is not None:attributes.update(snapshot.tcpip.attributes())
                    elif path.attribute==5 or service==3:raise CIPError(0x0C,'Local IPv4 configuration is unavailable')
                    if service==0x0E and path.attribute not in attributes:
                        raise CIPError(0x0C,'TCP/IP configuration attribute is unavailable on this interface')
            else:raise CIPError(5,'Unknown TCP/IP Interface object instance')
            return self.attribute_read(service,path,data,attributes)
        if path.class_id==0x69:
            if path.symbols or path.program_instance is not None or path.instance is None:
                raise CIPError(4,'I/O Map status requires a controller-scoped instance path')
            if service==0x4B:return self.instance_list(path,data,limit)
            if path.instance==1 and self.app.engine.project.io_map.root_link_address is not None:
                return self.attribute_read(service,path,data,self.app.engine.runtime_references.io_map_attributes(self.app.engine.project,self.endpoint.identity))
            if path.instance!=0:raise CIPError(5,'I/O Map module instances are not implemented')
            attributes=self.app.engine.project.io_map.class_attributes()
            attributes[1]=struct.pack('<H',controller_schemas.object_revision(0x69,native_compatibility=self.endpoint.native_read_only))
            return self.attribute_read(service,path,data,attributes)
        if path.class_id==0x7E:
            if path.symbols or path.program_instance is not None or path.instance is None:
                raise CIPError(4,'I/O Connection metadata requires a nested class path')
            if path.io_map_instance!=1 or path.instance!=0:
                raise CIPError(5,'Only the root I/O Connection class namespace is modeled')
            attributes=self.app.engine.project.io_map.connection_class_attributes()
            if attributes is None:raise CIPError(0x0C,'I/O Connection source inventory is unavailable')
            return self.attribute_read(service,path,data,attributes)
        if path.class_id==0x74:
            if path.symbols or path.instance is None:raise CIPError(4,'Semaphore paths require a logical instance')
            if path.program_instance is not None:
                if not any(row['id']==path.program_instance for row in self.programs()):raise CIPError(5,'Unknown Semaphore Program parent')
                if path.instance==0:return self.attribute_read(service,path,data,{1:b'\1\0'})
                if path.instance!=1:raise CIPError(5,'Unknown Program Semaphore instance')
                raise CIPError(0x0F,'Program reservation requires a bound signed edit context')
            if path.controller_instance not in (None,1):raise CIPError(5,'Unknown Semaphore parent')
            if path.instance==0:return self.attribute_read(service,path,data,{1:b'\1\0'})
            if path.controller_instance!=1 or path.instance!=1:raise CIPError(5,'Unknown Semaphore instance')
            raise CIPError(0x0F,'Semaphore coordination requires a bound signed native context')
        if path.class_id in energy_catalog.CLASSES:
            if service==0x4B:return self.instance_list(path,data,limit)
            raise CIPError(8,'Only bounded empty energy inventory discovery is supported')
        if path.class_id==0x8D:
            if service==0x4B:return self.instance_list(path,data,limit)
            raise CIPError(8,'Only source-checked empty Message discovery is supported')
        if path.class_id==0x31A:
            if path.symbols:raise CIPError(4,'File Manager paths do not take symbols')
            if path.instance!=0:raise CIPError(5,'No File Manager storage instances are modeled')
            return self.attribute_read(service,path,data,file_manager.class_attributes())
        if path.class_id in controller_schemas.SCHEMA_REVISIONS and self.endpoint.native_read_only:
            if (path.symbols or path.program_instance is not None or path.io_map_instance is not None or
                    path.controller_instance is not None or path.aoi_instance is not None or path.instance is None):
                raise CIPError(4,'Schema discovery requires a controller-scoped class path')
            if path.instance!=0:raise CIPError(5,'Schema instance operations are unavailable')
            return self.attribute_read(service,path,data,controller_schemas.class_attributes(path.class_id))
        if path.class_id in (0xB0,0xB1,0x32B):
            if service==0x4B:return self.instance_list(path,data,limit)
            raise CIPError(8,'Only source-checked empty motion discovery is supported')
        if path.class_id in alarm_catalog.CLASSES:
            if service==0x4B:return self.instance_list(path,data,limit)
            raise CIPError(8,'Only source-checked empty alarm discovery is supported')
        if path.class_id==0x338:
            return self.aoi_service(service,path,data,limit)
        if path.class_id==0x71:
            if path.symbols or path.program_instance is not None:
                raise CIPError(4,'Data Logging discovery must be controller scoped')
            if service==0x4B:return self.instance_list(path,data,limit)
            if path.instance!=0:raise CIPError(5,'Data Logging instances are not implemented')
            return self.attribute_read(service,path,data,self.app.engine.project.data_log_catalog.class_attributes())
        if path.class_id==0x36A:
            if (path.symbols or any(value is not None for value in (path.program_instance,
                    path.io_map_instance,path.controller_instance,path.aoi_instance)) or path.instance is None):
                raise CIPError(4,'Security authority bindings require a controller-scoped instance')
            if service==0x4B:return self.instance_list(path,data,limit)
            self.security_bindings()
            if path.instance!=0:raise CIPError(5,'No security authority binding instance is bound')
            return self.attribute_read(service,path,data,{1:struct.pack('<H',1)})
        if path.class_id==0x36E:
            if service==0x4B:return self.instance_list(path,data,limit)
            raise CIPError(8,'Only source-checked empty HMI Button Control discovery is supported')
        if path.class_id==0x3B0:
            if (path.symbols or path.program_instance is not None or path.io_map_instance is not None or
                    path.controller_instance is not None or path.aoi_instance is not None or path.instance is None):
                raise CIPError(4,'Diagnostic objects require a controller-scoped instance')
            if service==0x4B:return self.instance_list(path,data,limit)
            self.diagnostic_objects()
            if path.instance!=0:raise CIPError(5,'No diagnostic object instance is bound')
            return self.attribute_read(service,path,data,{2:bytes(4),3:bytes(4)})
        if path.class_id==0x3B1:
            if (path.symbols or path.program_instance is not None or path.io_map_instance is not None or
                    path.controller_instance is not None or path.aoi_instance is not None or path.instance is None):
                raise CIPError(4,'Diagnostic profiles require a controller-scoped instance')
            if service==0x4B:return self.instance_list(path,data,limit)
            self.diagnostic_profiles()
            if path.instance!=0:raise CIPError(5,'No diagnostic profile instance is bound')
            # Source proves maximum/count zero. Class revision is not inferred
            # from a storage-format version or a vendor description filename.
            return self.attribute_read(service,path,data,{2:bytes(4),3:bytes(4)})
        if path.class_id==0x3B2:
            if (path.symbols or path.program_instance is not None or path.io_map_instance is not None or
                    path.controller_instance is not None or path.aoi_instance is not None or path.instance is None):
                raise CIPError(4,'Diagnostic definitions require a controller-scoped instance')
            if service==0x4B:return self.instance_list(path,data,limit)
            catalog=self.diagnostics()
            if path.instance==0:attributes=self.catalog_class_attributes([row.instance for row in catalog.rows])
            else:
                row=catalog.by_instance.get(path.instance)
                if row is None:raise CIPError(5,'Unknown diagnostic definition')
                attributes=row.attributes()
            return self.attribute_read(service,path,data,attributes)
        if path.class_id==wall_clock.CLASS_ID:
            if (path.symbols or path.program_instance is not None or path.io_map_instance is not None or
                    path.controller_instance is not None or path.aoi_instance is not None):
                raise CIPError(4,'Wall Clock Time paths must be controller scoped')
            if path.instance==0:attributes=wall_clock.class_attributes()
            elif path.instance==1:
                requested=False
                if service==0x0E:
                    exact(data,0);requested=path.attribute in wall_clock.TIME_ATTRIBUTES
                if service==3 and path.attribute is None:
                    need(data,2);count=struct.unpack_from('<H',data)[0];exact(data,2+2*count)
                    if not 1<=count<=32:raise CIPError(3,'Attribute count must be 1..32')
                    requested=bool(set(wall_clock.TIME_ATTRIBUTES).intersection(struct.unpack_from('<'+'H'*count,data,2)))
                attributes=self.app.engine.project.wall_clock.attributes(read_time=requested,
                            coordinated_clock=self.app.coordinated_clock)
            elif path.instance is None:raise CIPError(4,'Wall Clock Time requires an instance')
            else:raise CIPError(5,'Unknown Wall Clock Time instance')
            return self.attribute_read(service,path,data,attributes)
        if path.class_id==0x43:
            if path.symbols or any(getattr(path,key) is not None for key in
                    ('program_instance','io_map_instance','controller_instance','aoi_instance')):
                raise CIPError(4,'Time Sync paths must be controller scoped')
            if path.instance==0:
                revision=controller_schemas.object_revision(0x43,native_compatibility=self.endpoint.native_read_only)
                attributes={1:struct.pack('<H',revision),2:b'\1\0',3:b'\1\0'}
            elif path.instance==1:
                requested=False
                if service==0x0E:
                    exact(data,0);requested=path.attribute in software_clock.TIME_ATTRIBUTES
                if service==3 and path.attribute is None:
                    need(data,2);count=struct.unpack_from('<H',data)[0];exact(data,2+2*count)
                    if not 1<=count<=32:raise CIPError(3,'Attribute count must be 1..32')
                    requested=bool(set(software_clock.TIME_ATTRIBUTES).intersection(struct.unpack_from('<'+'H'*count,data,2)))
                attributes={**self.app.engine.project.time_sync.attributes(),
                            **software_clock.attributes(read_time=requested,instance_id=self.app.instance_id,
                                                        ptp_enabled=self.app.engine.project.time_sync.ptp_enabled)}
            elif path.instance is None:raise CIPError(4,'Time Sync requires an instance')
            else:raise CIPError(5,'Unknown Time Sync instance')
            return self.attribute_read(service,path,data,attributes,limit=limit)
        if path.class_id==0x6E:
            if not self.endpoint.native_read_only:raise CIPError(8,'PLC file mapping discovery requires native compatibility')
            if path.symbols or path.attribute is not None or any(getattr(path,key) is not None for key in
                    ('program_instance','io_map_instance','controller_instance','aoi_instance')):
                raise CIPError(4,'PLC file mapping discovery requires a global class path')
            if path.instance is None:raise CIPError(4,'PLC file mapping discovery requires an instance cursor')
            if path.instance!=0:raise CIPError(5,'No PLC file mapping instance is available')
            if service!=0x4B:raise CIPError(8,'Only empty PLC file mapping discovery is supported')
            exact(data,0)
            project=self.app.engine.project;identity=self.app.native_project_identity
            body=project.pccc_mapping.discovery_body()
            if identity is None or identity.source_l5x_sha256!=project.sha256 or body is None:
                raise CIPError(0x0C,'Source-bound empty PLC file mappings are unavailable')
            return 0,body
        if path.class_id==0x67:
            if path.symbols or path.program_instance is not None:
                raise CIPError(4,'PLC message mapping paths must be controller scoped')
            if path.instance==0:attributes={1:b'\1\0',2:b'\1\0',3:b'\1\0'}
            elif path.instance==1:attributes=self.app.engine.project.pccc_mapping.attributes()
            elif path.instance is None:raise CIPError(4,'PLC message mapping requires an instance')
            else:raise CIPError(5,'Unknown PLC message mapping instance')
            return self.attribute_read(service,path,data,attributes)
        if path.class_id==0x349:
            if path.symbols or any(value is not None for value in (path.program_instance,path.io_map_instance,path.controller_instance,path.aoi_instance)):
                raise CIPError(4,'Metadata Definition paths require a global class scope')
            if service==0x4B:
                return self.instance_list(path,data,limit)
            if getattr(self.app,'native_metadata_definitions',None) is not None:
                catalog=self.metadata_definitions()
                if path.instance==0:attributes=catalog.class_attributes()
                else:
                    row=next((row for row in catalog.rows if row.instance==path.instance),None)
                    if row is None:raise CIPError(5,'Unknown source Metadata Definition')
                    attributes=row.attributes()
                return self.attribute_read(service,path,data,attributes)
            if path.instance!=0:raise CIPError(5,'No Metadata Definition instances are modeled')
            return self.attribute_read(service,path,data,controller_configuration.metadata_class_attributes())
        if path.class_id==0x334 and self.app.engine.project.processor=='1756-L85E':
            raise CIPError(5,'Standard L85E model has no Safety Controller object')
        if path.class_id==0x8E:
            if path.symbols or any(getattr(path,key) is not None for key in
                    ('program_instance','io_map_instance','controller_instance','aoi_instance')):
                raise CIPError(4,'Controller configuration paths must be controller scoped')
            if path.instance==0:
                revision=controller_schemas.object_revision(0x8E,native_compatibility=self.endpoint.native_read_only)
                attributes={1:struct.pack('<H',revision)}
            elif path.instance==1:
                configuration=self.app.engine.project.controller_configuration
                attributes=configuration.compatibility_attributes() if self.endpoint.native_read_only else configuration.attributes()
                attributes.update(self.app.engine.change_detection.attributes(self.app.engine.project.sha256))
                if self.endpoint.native_read_only:
                    with self.endpoint.lock:
                        identity=self.app.native_project_identity
                        if identity is not None and identity.source_l5x_sha256==self.app.engine.project.sha256:
                            attributes.update(self.app.engine.component_tracking_attributes(idle=
                                not self.endpoint.programming_lease.scan_inhibited(
                                    self.app.generation,self.app.engine.project.sha256)))
                        attributes[7]=struct.pack('<H',self.endpoint.programming_lease.inhibit(
                            self.app.generation,self.app.engine.project.sha256))
                        attributes[26]=struct.pack('<I',self.endpoint.programming_lease.preparation_status(
                            self.app.generation,self.app.engine.project.sha256))
                        if service==1 and path.attribute is None:
                            exact(data,0);aggregate=configuration.compatibility_get_all(attributes)
                            if aggregate is None:raise CIPError(0x14,'Controller aggregate source is unavailable')
                            return 0,aggregate
            else:raise CIPError(5,'Unknown Controller configuration instance')
            return self.attribute_read(service,path,data,attributes)
        if path.class_id==0xAC:
            if path.symbols:raise CIPError(4,'Controller metadata paths do not take symbols')
            if path.instance==0:
                # Common class metadata describes this implementation's revision
                # and its one modeled instance, not native firmware signatures.
                attributes={1:struct.pack('<H',5 if self.endpoint.native_read_only else 1),2:b'\1\0',3:b'\1\0'}
            elif path.instance==1:
                revision=CatalogRevision.from_source(self.app.engine.project.sha256)
                attributes=revision.compatibility_attributes() if self.endpoint.native_read_only else revision.attributes()
                native_identity=getattr(self.app,'native_project_identity',None)
                installed=getattr(self.app.engine,'installed_download',None)
                if self.endpoint.native_read_only and installed is not None:
                    try:attributes=installed.attributes(native_identity,self.app.engine.project)
                    except ImageError:raise CIPError(0x0C,'Installed download source changed') from None
                    native_identity=installed.identity
                if self.endpoint.native_read_only and native_identity is not None:
                    if native_identity.source_l5x_sha256!=self.app.engine.project.sha256:raise CIPError(0x0C,'Native correlation source changed')
                    if installed is None:attributes=native_identity.attributes()
                if self.endpoint.native_read_only and service==0x4F:
                    if path.attribute is not None:raise CIPError(4,'Change Log search requires an instance path')
                    exact(data,4)
                    if native_identity is None:raise CIPError(0x0C,'Change Log search requires source-bound ACD correlation')
                    cursor=native_identity.empty_log_search(data,
                        runtime_revision=getattr(self.app.engine.project,'runtime_revision',0))
                    if cursor is None:raise CIPError(0x0C,'Change Log history outside the supported empty source profile is unavailable')
                    return 0,cursor
                if self.endpoint.native_read_only and service==1 and path.attribute is None:
                    exact(data,0);return 0,b''.join(attributes[n] for n in range(1,11))
            else:raise CIPError(5,'Unknown controller metadata instance')
            return self.attribute_read(service,path,data,attributes)
        if path.class_id==0x64 and path.instance==1 and not path.symbols and path.attribute is None and service==1:
            exact(data,0);name=self.app.engine.project.name.encode('ascii')
            if len(name)>255:raise CIPError(0x1B,'Controller project name exceeds supported size')
            return 0,struct.pack('<H',len(name))+name
        if path.class_id==0x64 and path.instance==0 and not path.symbols:
            return self.attribute_read(service,path,data,{1:struct.pack('<H',controller_schemas.object_revision(0x64,native_compatibility=self.endpoint.native_read_only))})
        if path.class_id==0x64 and path.instance==1 and not path.symbols and service in (3,0x0E):
            attributes={**device_metadata.attributes(),**self.app.engine.project.controller_configuration.extended_device_attributes()}
            return self.attribute_read(service,path,data,attributes)
        if path.class_id==0x64 and path.instance==1 and service==0x4B:
            if path.symbols or path.attribute is not None:raise CIPError(4,'Key challenge requires an object instance path')
            try:return 0,key_exchange.challenge(data)
            except key_exchange.OfferError as error:raise CIPError(error.status,str(error)) from error
        if path.class_id==2 and path.instance==1 and service==0x0A and not path.symbols and path.attribute is None:
            need(data,2);count=struct.unpack_from('<H',data)[0]
            if not 1<=count<=16:raise CIPError(3,'Multiple Service Packet limit is 16')
            need(data,2+2*count);offsets=list(struct.unpack_from('<'+'H'*count,data,2))
            if offsets[0]!=2+2*count or offsets!=sorted(set(offsets)) or offsets[-1]>=len(data):raise CIPError(0x13,'Invalid multiple-service offsets')
            results=[self.handle(data[a:b],session,depth+1,limit,budget) for a,b in zip(offsets,offsets[1:]+[len(data)])]
            base=2+2*count;positions=[]
            for r in results:positions.append(base);base+=len(r)
            if base>limit-4:raise CIPError(0x1B,'Multiple-service response exceeds model limit')
            return (0x1E if any(r[2] for r in results) else 0),struct.pack('<H'+'H'*count,count,*positions)+b''.join(results)
        if path.class_id==0x68:return self.program_service(service,path,data,limit)
        if path.class_id==0x70:return self.task_service(service,path,data,limit)
        if path.class_id==0x6D:return self.routine_service(service,path,data,limit)
        if path.class_id==0x6A:return self.data_table_service(service,path,data,limit)
        if path.class_id in (0x6B,0x6C) and service==0x4B:return self.instance_list(path,data,limit)
        if path.class_id==0x6B and service==0x55:return self.enumerate_symbols(path,data,limit)
        if path.class_id==0x6C:return self.template_service(service,path,data,limit)
        if path.class_id==0x6B and service in (3,0x0E):
            scope=self.symbol_scope(path)
            if path.instance is None:raise CIPError(4,'Symbol path requires an instance')
            symbols=self.symbols(scope)
            if path.instance==0:
                return self.attribute_read(service,path,data,self.catalog_class_attributes([s['id'] for s in symbols],0x6B))
            symbol=next((s for s in symbols if s['id']==path.instance),None)
            if symbol is None:raise CIPError(5,'Unknown symbol instance')
            return self.attribute_read(service,path,data,self.symbol_attributes(symbol))
        if service in (0x4C,0x52,0x4D,0x53,0x4E) and path.class_id in (None,0x6B):
            if service in (0x4D,0x53):return self.write_tag(path,data,service==0x53)
            if service==0x4E:return self.read_modify_write(path,data)
            return self.read_tag(path,data,service==0x52,limit)
        raise CIPError(8,f'Unsupported service 0x{service:02X} class {path.class_id}')

    def handle(self,raw,session,depth=0,limit=REPLY_LIMIT,budget=None):
        service=raw[0] if raw else 0;detail='';path=''
        try:
            if budget is None:budget=[128]
            budget[0]-=1
            if budget[0]<0:raise CIPError(2,'CIP dispatch budget exceeded')
            if len(raw)>=2:path=repr(decode_path(raw[2:2+raw[1]*2]))
            with self.app.lock:
                if session.handle and session.generation!=self.app.generation:raise CIPError(0x10,'Project generation changed; reconnect')
                if self.app.busy:raise CIPError(0x10,'Project import is in progress')
                if self.app.engine is None:raise CIPError(0x10,'No project loaded')
                status,data=self.dispatch(raw,session,depth,limit,budget)
            result=status if isinstance(status,bytes) and data is None else reply(service,status,data)
            if len(result)>limit:raise CIPError(0x1B,'Response exceeds negotiated connection size')
        except CIPError as e:result=reply(service,e.status);detail=str(e)
        except ModelError as e:result=reply(service,0x0C);detail=str(e)
        except (ValueError,TypeError,IndexError,KeyError,struct.error,OverflowError) as e:result=reply(service,0x13);detail=str(e)
        self.endpoint.record('cip',request=raw,response=result,service=f'0x{service:02X}',path=path,status=result[2],detail=detail,
                             peer=session.peer,session=session.handle,generation=session.generation)
        return result


def cpf(items):return struct.pack('<IHH',0,0,len(items))+b''.join(struct.pack('<HH',kind,len(data))+data for kind,data in items)


def decode_cpf(data):
    need(data,8);interface,_,count=struct.unpack_from('<IHH',data)
    if interface or count!=2:raise CIPError(0x13,'Only two-item CIP CPF is supported')
    result=[];pos=8
    for _ in range(count):
        need(data[pos:],4);kind,size=struct.unpack_from('<HH',data,pos);pos+=4;need(data[pos:],size)
        result.append((kind,data[pos:pos+size]));pos+=size
    exact(data,pos);return result


class Endpoint:
    def __init__(self,app,port=44818,allow_writes=False,profile='research',bind_address='127.0.0.1',native_read_only=False):
        from ipaddress import IPv4Address
        try:
            if not isinstance(bind_address,str):raise ValueError('Expected IPv4 text')
            address=IPv4Address(bind_address)
            if address.packed[0]==0 or address.is_multicast or address.is_reserved:
                raise ValueError('Expected a specific unicast address')
        except ValueError as error:
            raise ModelError('Bind IP must be a specific unicast IPv4 address assigned to this PC') from error
        if isinstance(port,bool) or not isinstance(port,int) or not 0<=port<=65535:raise ModelError('EtherNet/IP port must be 0..65535')
        if not isinstance(allow_writes,bool):raise ModelError('allow_writes must be boolean')
        if not isinstance(native_read_only,bool):raise ModelError('native_read_only must be boolean')
        if native_read_only and (allow_writes or profile!='logix-v35-l85e'):
            raise ModelError('Native compatibility requires the experimental L85E profile and disabled tag writes')
        self.native_read_only=native_read_only
        self.bind_address=str(address)
        self.app=app;self.allow_writes=allow_writes;self.port=port;self.router=Router(app,self)
        if app.engine is None:raise ModelError('Load a project before selecting an identity')
        self.profile=profile;self.identity=Identity.from_project(profile,app.engine.project)
        self.source_sha256=app.engine.project.sha256
        self.lock=threading.RLock();self.events=deque(maxlen=TRACE_EVENT_LIMIT);self.counts=Counter();self.unsupported=Counter()
        self.trace_payload_bytes=0;self.trace_dropped_events=0
        self.trace_id=secrets.token_hex(16);self.trace_sequence=0
        self.attribute_gaps=attribute_gaps.AttributeGaps()
        self.native_rejections=native_rejections.NativeRejections()
        self.ethernet_counters=ethernet_counters.CounterCache()
        self.native_sessions={}
        self.programming_lease=programming_lease.ProgrammingLease()
        self.connections=set();self.threads=[];self.tcp=None;self.udp=None;self.enabled=False;self.slots=threading.BoundedSemaphore(16)
        self._locator_clock=time.monotonic;self._locator_until=0.0;self._locator_started=0.0;self._locator_request=None
        self.interface=None;self.interface_error=None;self.interface_queried=False
        self.broadcast_servers=[]
        self.discovery_status={'broadcast_enabled':False,'broadcast_addresses':[],'interface':None,'reason':'Endpoint is stopped'}

    def flash_leds(self,seconds):
        # Identification is independent of application tag-write permission.
        if isinstance(seconds,bool) or not isinstance(seconds,int) or not (seconds==0 or 9<=seconds<=255):
            raise CIPError(3,'Flash LEDs time must be zero or 9..255 seconds')
        with self.lock:
            if not self.enabled:raise CIPError(0x10,'Endpoint is stopped')
            now=self._locator_clock();self._locator_started=now
            self._locator_until=now+seconds if seconds else 0.0
            self._locator_request=secrets.token_hex(8)
            self.record('locator',duration_seconds=seconds)

    def locator_state(self):
        # Caller holds endpoint.lock; no app lock or wall-clock dependency.
        now=self._locator_clock();remaining=max(0.0,self._locator_until-now) if self.enabled else 0.0
        return {'active':remaining>0,'remaining_ms':math.ceil(remaining*1000),
                'elapsed_ms':max(0,int((now-self._locator_started)*1000)) if remaining else 0,
                'request_id':self._locator_request}

    def record(self,kind,request=b'',response=b'',**fields):
        with self.lock:
            self.counts[kind]+=1
            if kind=='cip' and fields.get('status') in (8,0x0A,0x14):
                key=fields.get('service','')+' '+fields.get('path','')
                self.unsupported[key if key in self.unsupported or len(self.unsupported)<128 else 'Other unsupported requests']+=1
            captured_request=request[:TRACE_PACKET_LIMIT];captured_response=response[:TRACE_PACKET_LIMIT]
            size=len(captured_request)+len(captured_response)
            # Retain complete protocol-sized packets, including native download
            # fragments. Bound the whole ring as well as each individual packet.
            while self.events and (len(self.events)>=TRACE_EVENT_LIMIT or self.trace_payload_bytes+size>TRACE_BYTE_LIMIT):
                old=self.events.popleft()
                self.trace_payload_bytes-=(len(old['request_hex'])+len(old['response_hex']))//2
                self.trace_dropped_events+=1
            self.trace_sequence+=1
            self.events.append({'time':time.time(),'kind':kind,**fields,'event_id':self.trace_sequence,'request_hex':captured_request.hex(),
                                'response_hex':captured_response.hex(),'request_bytes':len(request),'response_bytes':len(response),
                                'truncated':len(request)>TRACE_PACKET_LIMIT or len(response)>TRACE_PACKET_LIMIT})
            self.trace_payload_bytes+=size

    def trace_page(self,after_event=None,trace_id=None,limit=256):
        """Read a bounded suffix without copying the full controller status."""
        if type(limit) is not int or not 1<=limit<=256:
            raise ModelError('Trace page limit must be 1..256')
        with self.lock:
            if after_event is None:
                if trace_id is not None:raise ModelError('Initial trace cursor must omit the trace identity')
                after_event=self.trace_sequence
            elif (type(after_event) is not int or not 0<=after_event<=self.trace_sequence
                    or trace_id!=self.trace_id):
                raise ModelError('Trace cursor does not belong to the current endpoint')
            oldest=self.events[0]['event_id'] if self.events else self.trace_sequence+1
            events=[]
            for row in self.events:
                if row['event_id']>after_event:
                    events.append(dict(row))
                    if len(events)==limit:break
            next_event=events[-1]['event_id'] if events else after_event
            return dict(trace_id=self.trace_id,instance_id=self.app.instance_id,
                source_l5x_sha256=self.source_sha256,after_event=after_event,next_event=next_event,
                last_event=self.trace_sequence,oldest_event=oldest,
                missing_events=max(0,oldest-after_event-1),has_more=next_event<self.trace_sequence,events=events)

    def state(self,trace=False):
        with self.lock:
            result={'enabled':self.enabled,'address':f'{self.bind_address}:{self.port}','bind_address':self.bind_address,'allow_writes':self.allow_writes,
                    'identity':self.identity.description(),'profile':self.profile,'source_l5x_sha256':self.source_sha256,
                    'catalog_revision':CatalogRevision.from_source(self.source_sha256).description() if self.enabled else None,
                    'file_manager':file_manager.description() if self.enabled else None,
                    'controller_schemas':controller_schemas.description() if self.enabled and self.native_read_only else None,
                    'controller_configuration':self.app.engine.project.controller_configuration.description(native_compatibility=self.native_read_only) if self.enabled else None,
                    'controller_change_detection':self.app.engine.change_detection.description() if self.enabled else None,
                    'program_configuration':self.app.engine.project.program_configuration.description() if self.enabled else None,
                    'program_upload_query':program_query.description() if self.native_read_only else None,
                    'runtime_references':self.app.engine.runtime_references.description() if self.enabled else None,
                    'program_hierarchy':self.app.engine.project.program_hierarchy.description() if self.enabled else None,
                    'program_timing':self.app.engine.program_timing_description() if self.enabled else None,
                    'program_faults':self.app.engine.program_fault_description() if self.enabled else None,
                    'program_diagnostics':self.app.engine.project.program_diagnostics.description() if self.enabled else None,
                    'task_configuration':self.app.engine.project.task_configuration.description() if self.enabled else None,
                    'task_timing':self.app.engine.project.task_timing.description() if self.enabled else None,
                    'task_measurements':self.app.engine.task_measurement_description() if self.enabled else None,
                    'task_execution_status':self.app.engine.task_status_description() if self.enabled else None,
                    'task_aoi_stack':self.app.engine.task_stack_description() if self.enabled else None,
                    'controller_component_tracking':{**self.app.engine.project.component_tracking.description(),
                        'reads_available':bool(self.native_read_only and self.app.native_project_identity is not None
                            and self.app.native_project_identity.source_l5x_sha256==self.app.engine.project.sha256
                            and self.app.engine.component_tracking_attributes(idle=not self.programming_lease.scan_inhibited(
                                self.app.generation,self.app.engine.project.sha256)))} if self.enabled else None,
                    'executable_configuration':self.app.engine.project.executable_configuration.description() if self.enabled else None,
                    'routine_state':routine_state.description() if self.enabled else None,
                    'device_metadata':device_metadata.description() if self.enabled else None,
                    'metadata_definition':({**self.app.native_metadata_definitions.description(),
                        'metadata_values':getattr(self.app,'native_metadata_values',None) is not None,
                        'metadata_services':getattr(self.app,'native_metadata_values',None) is not None} if getattr(self.app,'native_metadata_definitions',None)
                        else controller_configuration.metadata_description()) if self.enabled else None,
                    'metadata_values':self.app.native_metadata_values.description() if self.enabled and getattr(self.app,'native_metadata_values',None) else None,
                    'data_table':data_table.description(native_compatibility=self.native_read_only) if self.enabled else None,
                    'symbol_metadata':symbol_metadata.description() if self.enabled else None,
                    'motion_catalog':self.app.engine.project.motion_catalog.description() if self.enabled else None,
                    'alarm_catalog':self.app.engine.project.alarm_catalog.description() if self.enabled else None,
                    'aoi_catalog':self.router.aoi_description() if self.enabled else None,
                    'data_log_catalog':self.app.engine.project.data_log_catalog.description() if self.enabled else None,
                    'hmi_button_control':self.app.engine.project.hmi_button_catalog.description() if self.enabled else None,
                    'energy_catalog':self.app.engine.project.energy_catalog.description() if self.enabled else None,
                    'message_catalog':self.app.engine.project.message_catalog.description() if self.enabled else None,
                    'pccc_mapping':self.app.engine.project.pccc_mapping.description() if self.enabled else None,
                    'time_sync':self.app.engine.project.time_sync.description(instance_id=self.app.instance_id,native_compatibility=self.native_read_only) if self.enabled else None,
                    'wall_clock_time':self.app.engine.project.wall_clock.description(
                        coordinated_clock=self.app.coordinated_clock) if self.enabled else None,
                    'program_forces':self.app.engine.project.program_forces.description() if self.enabled else None,
                    'io_map':self.app.engine.project.io_map.description() if self.enabled else None,
                    'key_exchange':{**key_exchange.description(self.native_read_only),'session_secret_retained':any(n.key is not None for n in self.native_sessions.values())} if self.enabled else None,
                    'native_session':{**native_session.description(self.enabled and self.native_read_only),
                        'controller_mode':self.app.controller_state()['mode'] if self.enabled and self.native_read_only else None,
                        'keyswitch':'Remote' if self.enabled and self.native_read_only else None,
                        'controller_mode_requests':self.enabled and self.native_read_only},
                    'native_programming_lease':{**self.programming_lease.description(self.app.generation,self.source_sha256),
                        'online_edits':self.app.allow_routine_edits,'online_edit_scope':'standard_rll_program_mode',
                        'available':bool(self.app.native_project_identity and self.app.native_project_identity.source_l5x_sha256==self.source_sha256)} if self.enabled and self.native_read_only else None,
                    'native_correlation':self.app.native_project_identity.description() if self.enabled and self.app.native_project_identity else None,
                    'native_download':self.app.engine.installed_download.description() if self.enabled and getattr(self.app.engine,'installed_download',None) else None,
                    'native_symbols':self.app.native_symbols.description() if self.enabled and self.app.native_symbols else None,
                    'native_types':self.app.native_types.description() if self.enabled and getattr(self.app,'native_types',None) else None,
                    'native_templates':self.app.native_templates.description() if self.enabled and getattr(self.app,'native_templates',None) else None,
                    'native_tasks':self.app.native_tasks.description() if self.enabled and getattr(self.app,'native_tasks',None) else None,
                    'native_routines':self.app.native_routines.description() if self.enabled and getattr(self.app,'native_routines',None) else None,
                    'native_tables':self.app.native_tables.description() if self.enabled and getattr(self.app,'native_tables',None) else None,
                    'native_diagnostics':self.app.native_diagnostics.description() if self.enabled and getattr(self.app,'native_diagnostics',None) else None,
                    'native_diagnostic_profiles':self.app.native_diagnostic_profiles.description() if self.enabled and getattr(self.app,'native_diagnostic_profiles',None) else None,
                    'native_diagnostic_objects':self.app.native_diagnostic_objects.description() if self.enabled and getattr(self.app,'native_diagnostic_objects',None) else None,
                    'native_security_bindings':self.app.native_security_bindings.description() if self.enabled and getattr(self.app,'native_security_bindings',None) else None,
                    'native_auxiliary_symbols':self.app.native_auxiliary_symbols.description() if self.enabled and getattr(self.app,'native_auxiliary_symbols',None) else None,
                    'native_reference_symbols':self.app.native_reference_symbols.description() if self.enabled and getattr(self.app,'native_reference_symbols',None) else None,
                    'native_routine_reference_symbols':self.app.native_routine_reference_symbols.description() if self.enabled and getattr(self.app,'native_routine_reference_symbols',None) else None,
                    'native_aois':self.app.native_aois.description() if self.enabled and getattr(self.app,'native_aois',None) else None,
                    'native_aoi_routines':self.app.native_aoi_routines.description() if self.enabled and getattr(self.app,'native_aoi_routines',None) else None,
                    'locator':self.locator_state(),
                    'network_interface':self.interface.description() if self.interface else None,
                    'ethernet_counters':self.ethernet_counters.description() if self.enabled else None,
                    'network_interface_error':self.interface_error,'network_interface_queried':self.interface_queried,
                    'discovery':{**self.discovery_status,'broadcast_enabled':self.enabled and bool(self.broadcast_servers)},
                    'active_tcp_clients':len(self.connections),'counts':dict(self.counts),
                    'unsupported':[{'request':k,'count':v} for k,v in self.unsupported.most_common(20)],
                    'attribute_gaps':self.attribute_gaps.snapshot(self.app.generation),
                    'native_rejections':self.native_rejections.snapshot(self.app.generation),
                    'studio_go_online':'EXPERIMENTAL NATIVE SDK CONNECTION; GUI MONITORING UNVERIFIED' if self.native_read_only else 'NOT IMPLEMENTED OR VERIFIED','trace_events':len(self.events),
                    'trace_capture':{'event_limit':TRACE_EVENT_LIMIT,'packet_byte_limit':TRACE_PACKET_LIMIT,
                        'trace_id':self.trace_id,'last_event':self.trace_sequence,
                        'retained_byte_limit':TRACE_BYTE_LIMIT,'retained_bytes':self.trace_payload_bytes,
                        'dropped_events':self.trace_dropped_events}}
            if trace:result['events']=list(self.events)
            return result

    def record_attribute_gap(self,path,missing,service):
        # Store IDs and scope only, never field values, requests or session keys.
        missing=[number for number in missing if isinstance(number,int)]
        scope=path.symbols[0] if path.symbols else ''
        with self.lock:
            self.attribute_gaps.record(path.class_id,path.instance,path.program_instance,
                                       scope,missing,self.app.generation,service,io_map_instance=path.io_map_instance,
                                       controller_instance=path.controller_instance,aoi_instance=path.aoi_instance)

    def record_native_rejection(self,service,path,status,reason):
        with self.lock:
            self.counts['native_rejected']+=1
            self.native_rejections.record(self.app.generation,service,path,status,reason)

    def discovery(self,command):
        if command==0x63:
            addr=struct.pack('>HH4s8s',2,self.port,socket.inet_aton(self.bind_address),b'\0'*8)
            with self.lock:identity=self.identity
            item=struct.pack('<H',1)+addr+self.router.identity()+identity.attributes()[8]
            return struct.pack('<HHH',1,0x0C,len(item))+item
        if command==4:
            item=struct.pack('<HH',1,0x20)+b'Communications'.ljust(16,b'\0')
            return struct.pack('<HHH',1,0x100,len(item))+item
        if command==0x64:return b'\x00\x00'
        raise CIPError(8,'Unknown discovery command')

    def packet(self,raw,session,udp=False):
        if len(raw)<24:return None
        command,size,handle,status,context,options=HEADER.unpack_from(raw)
        # A nonzero status is an encapsulation error reply from the peer.
        # Reflecting another error can make two implementations reply forever.
        if status:
            self.record('peer_error',request=raw,command=f'0x{command:04X}',status=status,
                        transport='udp' if udp else 'tcp',peer=session.peer,session=handle)
            return None
        result=b'';error=0;out_handle=handle
        if size!=len(raw)-24 or options:error=3
        elif command in (4,0x63,0x64):
            if size:error=3
            else:result=self.discovery(command)
        elif udp:error=1
        elif command==0x65:
            if raw[24:]!=b'\x01\x00\x00\x00' or handle:error=0x69
            elif session.handle:error=3
            else:
                session.handle=secrets.randbits(32) or 1;session.generation=self.app.generation
                out_handle=session.handle;result=raw[24:]
        elif command in (0x66,0x6F,0x70):
            if session.generation!=self.app.generation:self.clear_native(session)
            if not session.handle or handle!=session.handle or session.generation!=self.app.generation:error=0x64
            elif command==0x66:
                if size:error=3
                else:self.clear_native(session);session.handle=0;session.connections.clear();return None
            else:
                try:
                    items=decode_cpf(raw[24:])
                    if command==0x6F:
                        if items[0]!=(0,b'') or items[1][0]!=0xB2:raise CIPError(0x13,'Invalid unconnected CPF')
                        result=cpf([(0,b''),(0xB2,self.router.handle(items[1][1],session))])
                    else:
                        if items[0][0]!=0xA1 or len(items[0][1])!=4 or items[1][0]!=0xB1:raise CIPError(0x13,'Invalid connected CPF')
                        conn=session.connections.get(struct.unpack('<I',items[0][1])[0]);data=items[1][1];need(data,4)
                        if conn is None:raise CIPError(1,'Unknown connected address')
                        if len(data)>conn.incoming_size:raise CIPError(0x13,'Request exceeds negotiated connection size')
                        seq=struct.unpack_from('<H',data)[0]
                        if conn.last_sequence==seq:
                            if conn.last_request!=data:raise CIPError(1,'Sequence reused with different message')
                            response=conn.last_reply
                        else:
                            if conn.last_sequence is not None and not 0<(seq-conn.last_sequence)&0xFFFF<0x8000:raise CIPError(1,'Stale connected sequence')
                            # Connected replies use the negotiated T->O size;
                            # the two-byte transport sequence shares that budget.
                            response=data[:2]+self.router.handle(data[2:],session,limit=conn.outgoing_size-2)
                            conn.last_sequence,conn.last_request,conn.last_reply=seq,data,response
                        result=cpf([(0xA1,struct.pack('<I',conn.outgoing)),(0xB1,response)])
                except CIPError as e:error=3;self.record('cpf_error',request=raw,status=e.status,detail=str(e))
        elif command==0:return None
        else:error=1
        response=HEADER.pack(command,len(result),out_handle,error,context,0)+result
        self.record('encapsulation',request=raw,response=response,command=f'0x{command:04X}',status=error,transport='udp' if udp else 'tcp',peer=session.peer,session=out_handle)
        return response

    def start(self):
        endpoint=self
        class TCP(socketserver.ThreadingTCPServer):
            daemon_threads=True;block_on_close=False
            # Linux requires this on both old and new sockets to restart after
            # a server-closed connection enters TIME_WAIT. SO_REUSEPORT is not
            # enabled: another active listener must still make startup fail.
            allow_reuse_address=sys.platform=='linux'
            def process_request(self,request,address):
                if not endpoint.slots.acquire(False):request.close();return
                try:super().process_request(request,address)
                except Exception:endpoint.slots.release();raise
            def process_request_thread(self,request,address):
                try:super().process_request_thread(request,address)
                finally:endpoint.slots.release()
        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                conn=self.request;conn.settimeout(30);session=Session(peer=str(self.client_address))
                with endpoint.lock:endpoint.connections.add(conn)
                endpoint.record('client_open',peer=str(self.client_address))
                def read(size):
                    data=b''
                    while len(data)<size:
                        chunk=conn.recv(size-len(data))
                        if not chunk:return None
                        data+=chunk
                    return data
                try:
                    while endpoint.enabled:
                        header=read(24)
                        if header is None:break
                        size=HEADER.unpack(header)[1]
                        if size>32768:endpoint.record('frame_rejected',detail='Frame exceeds 32768 bytes');break
                        body=read(size)
                        if body is None:break
                        response=endpoint.packet(header+body,session)
                        if response is not None:conn.sendall(response)
                except (OSError,ValueError) as e:endpoint.record('client_closed',detail=str(e))
                finally:
                    endpoint.clear_native(session)
                    with endpoint.lock:endpoint.connections.discard(conn)
        class UDPHandler(socketserver.BaseRequestHandler):
            def handle(self):
                raw,sock=self.request
                if len(raw)>32792:return
                response=endpoint.packet(raw,Session(peer=str(self.client_address)),True)
                if response is not None:sock.sendto(response,self.client_address)
        requested_port=self.port;attempts=8 if requested_port==0 else 1
        for attempt in range(attempts):
            try:
                transport='TCP'
                self.tcp=TCP((self.bind_address,requested_port),Handler);self.port=self.tcp.server_address[1]
                transport='UDP'
                self.udp=socketserver.UDPServer((self.bind_address,self.port),UDPHandler)
                break
            except OSError as e:
                failed_port=self.port
                for server in (self.tcp,self.udp):
                    if server:server.server_close()
                self.tcp=self.udp=None;self.port=requested_port
                if attempt+1==attempts:
                    raise ModelError(f'Cannot bind EtherNet/IP {transport} at {self.bind_address}:{failed_port}: {e}. '
                        'Use an IP assigned to this PC and a free TCP/UDP port. A listener on 0.0.0.0 may also reserve this port.') from e
        self.broadcast_servers,self.discovery_status=prepare_broadcasts(self.bind_address,self.port,
            lambda raw,peer:self.packet(raw,Session(peer=str(peer)),True),self.record)
        self.enabled=True
        for server in (self.tcp,self.udp,*self.broadcast_servers):
            thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':0.05},daemon=True);thread.start();self.threads.append(thread)
        self.record('started',detail='Local research endpoint; Studio Go Online is unverified')
        return self

    def clear_native(self,session):
        with self.lock:
            self.programming_lease.discard(getattr(session,'native',None))
            self.native_sessions.pop(id(session),None)
        native_session.clear(session)

    def close_native_sessions(self):
        with self.lock:
            for native in self.native_sessions.values():native.close()
            self.native_sessions.clear()
            self.programming_lease.clear()

    def stop(self):
        self.close_native_sessions()
        with self.lock:self.enabled=False;self._locator_until=0.0
        with self.lock:clients=list(self.connections)
        for conn in clients:
            try:conn.shutdown(socket.SHUT_RDWR);conn.close()
            except OSError:pass
        for server in (self.tcp,self.udp,*self.broadcast_servers):
            if server:server.shutdown();server.server_close()
        self.record('stopped')
