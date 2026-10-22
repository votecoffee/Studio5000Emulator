from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import sys
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .importers import convert_acd, default_converter
from .native_project import NativeProjectIdentity
from .native_symbols import NativeSymbols
from .native_types import NativeTypes
from .native_templates import NativeTemplates
from .native_tasks import NativeTasks
from .native_routines import NativeRoutines
from .native_aois import NativeAOIs
from .native_aoi_routines import NativeAOIRoutines
from .native_auxiliary_symbols import NativeAuxiliarySymbols
from .reference_symbols import ReferenceSymbols
from .native_tables import NativeTables
from .native_diagnostics import NativeDiagnostics
from .native_diagnostic_profiles import NativeDiagnosticProfiles
from .native_diagnostic_objects import NativeDiagnosticObjects
from .native_security_bindings import NativeSecurityBindings
from .device_io import DeviceIO
from .model import ModelError, Project, Branch
from .runtime import Engine
from . import __version__

BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
SAMPLES = ('ConveyorDemo', 'DataLab', 'AOILab', 'CallLab', 'TextLab', 'NetworkLab', 'StructureLab', 'LayoutLab', 'FlagLab')


def serialize_nodes(nodes):
    return [{"branch": [serialize_nodes(p) for p in n.paths]} if isinstance(n, Branch)
            else {"name": n.name, "args": n.args} for n in nodes]


class Application:
    def __init__(self, data_dir=None):
        self.data_dir = Path(data_dir or Path(os.environ.get("LOCALAPPDATA", str(Path.cwd()))) / "LogixLab")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.converter = default_converter()
        settings = self.data_dir / 'settings.json'
        if settings.is_file():
            try: self.converter = str(json.loads(settings.read_text(encoding='utf-8'))['converter'])
            except (ValueError, KeyError, OSError): pass
        self.engine = None
        self.provenance = {}
        self.native_project_identity = None
        self.native_symbols = None
        self.native_types = None
        self.native_templates = None
        self.native_tasks = None
        self.native_routines = None
        self.native_aois = None
        self.native_aoi_routines = None
        self.native_auxiliary_symbols = None
        self.native_reference_symbols = None
        self.native_tables = None
        self.native_diagnostics = None
        self.native_diagnostic_profiles = None
        self.native_diagnostic_objects = None
        self.native_security_bindings = None
        self.lock = threading.RLock()
        self.busy = False
        self.generation = 0
        self.endpoint = None
        self.connectivity_lock = threading.RLock()
        self.desktop = {'tray_available': False, 'tray_error': None}
        self.instance_id = uuid.uuid4().hex
        self.device_io = DeviceIO(self.instance_id)
        self._io_dirty = False
        self.execution_environment = os.environ.get('LOGIXLAB_ENVIRONMENT', 'desktop')
        self.running = False
        self.allow_routine_edits = False
        self.scan_interval_ms = 10
        self._scan_condition = threading.Condition(self.lock)
        self._scan_thread = None
        self._closed = False
        self._scan_epoch = 0

    def scan_inhibited(self):
        # Caller owns app.lock; protocol dispatch uses this same lock order.
        if self.endpoint and self.endpoint.native_read_only:
            with self.endpoint.lock:
                return self.endpoint.programming_lease.scan_inhibited(self.generation,self.engine.project.sha256)
        return False

    def controller_state(self):
        fault = bool(self.engine and self.engine.fault)
        return {'mode':'Faulted' if fault else 'Run' if self.running else 'Program',
                'running':self.running, 'keyswitch':'Remote', 'scan_interval_ms':self.scan_interval_ms,
                'prescan_count':self.engine.prescan_count if self.engine else 0,
                'first_scan_pending':self.engine.memory.first_scan if self.engine else False}

    def default_scan_interval(self):
        tasks=self.engine.project.tasks
        if self.engine.mode=='project' and tasks and tasks[0]['type']=='Periodic':
            try:
                rate=float(tasks[0]['rate'])
                if rate.is_integer() and 1<=rate<=60000:return int(rate)
            except (ValueError,TypeError,KeyError):pass
        return 10

    def set_controller_mode(self, mode, dt=None, *, remote_request=False):
        # Shared by HTTP controls and verified native requests. Caller owns app.lock.
        if mode not in ('Run','Program'):raise ModelError('Supported controller modes are Run and Program')
        if mode == 'Program':
            changed=self.running
            if self.running:self._scan_epoch+=1
            self.running = False
            if changed and remote_request:self.engine.change_detection.record('remote_mode')
            self._scan_condition.notify_all()
            return
        if self._closed:raise ModelError('Application is shutting down')
        if self.busy or self.engine is None:raise ModelError('Load a project before running')
        if self.engine.fault:raise ModelError('Reset the faulted project before running')
        if self.scan_inhibited():raise ModelError('Native programming preparation inhibits scans')
        interval = self.scan_interval_ms if dt is None else dt
        if type(interval) is not int:raise ModelError('Scan interval must be an integer in milliseconds')
        self.engine.validate_interval(interval)
        if self.running and interval == self.scan_interval_ms:return
        changed=not self.running
        if changed:
            self.engine.enter_run()
            self._io_dirty=True
        self.scan_interval_ms = interval
        self.running = True
        self._scan_epoch+=1
        if self._scan_thread is None:
            self._scan_thread = threading.Thread(target=self._scan_loop,name='LogixLab scans',daemon=True)
            self._scan_thread.start()
        if changed and remote_request:self.engine.change_detection.record('remote_mode')
        self._scan_condition.notify_all()

    def _scan_loop(self):
        with self._scan_condition:
            while not self._closed:
                if not self.running:
                    self._scan_condition.wait()
                    continue
                # Wait releases app.lock. No catch-up burst after a slow scan or import.
                deadline = time.monotonic()+self.scan_interval_ms/1000
                epoch=self._scan_epoch
                while self.running and not self._closed and epoch==self._scan_epoch:
                    remaining = deadline-time.monotonic()
                    if remaining <= 0:break
                    self._scan_condition.wait(remaining)
                if not self.running or self._closed or epoch!=self._scan_epoch:continue
                if self.busy or self.scan_inhibited():
                    self.set_controller_mode('Program')
                    continue
                try:
                    self.device_io.apply(self)
                    self._io_dirty = True
                    self.engine.step(self.scan_interval_ms)
                    if self.device_io.sample_due():self.publish_device_io()
                except Exception as error:
                    if not self.engine.fault:self.engine.fault = str(error) or type(error).__name__
                    self.set_controller_mode('Program')
                    self.publish_device_io()

    def stop_connectivity(self):
        with self.connectivity_lock:
            if self.endpoint and self.endpoint.enabled:self.endpoint.stop()

    def connectivity(self,trace=False):
        return self.endpoint.state(trace) if self.endpoint else {'enabled':False,'address':'127.0.0.1:44818','bind_address':'127.0.0.1',
            'native_reference_symbols':None,'native_diagnostics':None,'native_diagnostic_profiles':None,'native_diagnostic_objects':None,'native_security_bindings':None,'routine_state':None,
            'allow_writes':False,'profile':'research','catalog_revision':None,'file_manager':None,
            'controller_configuration':None,'controller_change_detection':None,'task_configuration':None,'task_timing':None,'native_tasks':None,'native_routines':None,'native_aois':None,'native_aoi_routines':None,'native_auxiliary_symbols':None,'native_tables':None,'executable_configuration':None,'runtime_references':None,'device_metadata':None,'metadata_definition':None,'data_table':None,'pccc_mapping':None,'time_sync':None,'program_forces':None,'io_map':None,'ethernet_counters':None,'aoi_catalog':None,'data_log_catalog':None,
            'native_session':{'enabled':False},'native_correlation':None,
            'locator':{'active':False,'remaining_ms':0,'elapsed_ms':0,'request_id':None},
            'counts':{},'unsupported':[],'attribute_gaps':[],'native_rejections':[],'trace_events':0,'studio_go_online':'NOT IMPLEMENTED OR VERIFIED'}

    def close(self):
        with self.lock:
            self.set_controller_mode('Program')
            self._closed = True
            self._scan_condition.notify_all()
        if self._scan_thread and self._scan_thread is not threading.current_thread():self._scan_thread.join(timeout=5)
        self.stop_connectivity()

    def state(self):
        from .routine_edits import description as routine_edit_description
        metadata = {'app_version': __version__, 'desktop': dict(self.desktop),
                    'routine_edits':routine_edit_description(self),
                    'instance_id': self.instance_id, 'execution_environment': self.execution_environment,
                    'device_io':self.device_io.description(), 'controller':self.controller_state()}
        if self.engine is None: return {**metadata, "loaded": False, "converter": self.converter,'connectivity':self.connectivity()}
        e = self.engine
        tags = e.memory.leaves()
        self.publish_device_io(tags)
        metadata['device_io'] = self.device_io.description()
        return {**metadata, "loaded": True, "name": e.project.name, "version": e.project.version,
                "processor": e.project.processor, "scan": e.scan_count, "ms": e.time_ms,
                "mode": e.mode, "selected": e.selected, "blockers": e.blockers,
                'entry_routines':e.entries,
                "fault": e.fault, "tags": tags, "trace": e.trace,'connectivity':self.connectivity(),
                "changes": e.changes, "provenance": self.provenance,
                "tasks": e.project.tasks, "converter": self.converter,
                'aoi_instances':e.addons.instances,
                "routines": [{"key": r.key, "kind": r.kind, "problems": r.problems,
                              "active": r.key.lower() in e.active or r.program[4:] in e.addons.active,
                              'harness':not r.program.startswith('AOI:'),
                              'lines':r.lines,
                              "rungs": [{"number": x["number"], "text": x["text"], "comment": x["comment"],
                                         "nodes": serialize_nodes(x["nodes"])} for x in r.rungs]}
                             for r in list(e.project.routines.values())+[r for a in e.project.aois.values() for r in a.routines.values()]]}

    def publish_device_io(self, tags=None):
        # Caller owns app.lock. No socket/JSON work, or consumer callback, here.
        if self.engine is not None and self._io_dirty:
            self.device_io.capture(self.engine,self.generation,tags if tags is not None else self.engine.memory.leaves())
            self._io_dirty = False

    def command(self, action, data):
        if action.startswith('connectivity-'):
            with self.connectivity_lock:
                if action=='connectivity-stop':
                    self.stop_connectivity()
                    with self.lock:return self.state()
                if action=='connectivity-trace':return self.connectivity(True)
                if action=='connectivity-start':
                    from .ethernetip import Endpoint
                    with self.lock:
                        if self.engine is None or self.busy:raise ModelError('Load a project before starting connectivity')
                        if self.endpoint and self.endpoint.enabled:raise ModelError('EtherNet/IP endpoint is already running')
                        endpoint=Endpoint(self,data.get('port',44818),data.get('allow_writes',False),data.get('profile','research'),data.get('bind_address','127.0.0.1'),data.get('native_read_only',False))
                        self.endpoint=endpoint.start()
                        return self.state()
                raise ModelError('Unknown connectivity action')
        if action in ("load", "demo"):
            with self.lock:
                if self.busy: raise ModelError("An import is already running")
                self.set_controller_mode('Program')
                self.busy = True
            try:
                if action == "demo":
                    sample=data.get('sample','ConveyorDemo')
                    if sample not in SAMPLES:raise ModelError('Unknown bundled demo')
                    source = BASE / "samples" / (sample+'.L5X')
                    provenance = {"method": "Bundled v35 L5X demo"}
                else:
                    name = Path(data.get("name", "project").replace("\\", "/")).name
                    suffix = Path(name).suffix.lower()
                    if suffix not in (".acd", ".l5x"): raise ModelError("Choose an ACD or L5X file")
                    if suffix == '.acd' and self.execution_environment == 'vmware-host-only':
                        raise ModelError('ACD conversion runs on Windows. Use the Windows VM tray menu Import ACD / L5X, or load a complete L5X export here.')
                    content = base64.b64decode(data["content"], validate=True)
                    if len(content) > 100_000_000: raise ModelError("100 MB upload limit")
                    folder = self.data_dir / "imports" / uuid.uuid4().hex
                    folder.mkdir(parents=True)
                    source = folder / ("source" + suffix)
                    source.write_bytes(content)
                    if suffix == ".acd":
                        converted = folder / "project.L5X"
                        provenance = convert_acd(source, converted, self.converter)
                        source = converted
                    else: provenance = {"method": "Complete L5X upload", "original_filename": name}
                project = Project(source)
                correlation = provenance.get('native_project_identity')
                if action == 'load' and Path(name).suffix.lower() == '.l5x' and 'native_project_identity' in data:
                    correlation = data['native_project_identity']
                native_identity = NativeProjectIdentity.from_manifest(correlation, project.sha256) if correlation is not None else None
                if native_identity: provenance['native_project_identity'] = native_identity.manifest()
                symbol_manifest = provenance.get('native_symbols')
                if action == 'load' and Path(name).suffix.lower() == '.l5x' and 'native_symbols' in data:
                    symbol_manifest = data['native_symbols']
                native_symbols = NativeSymbols.from_manifest(symbol_manifest, project.sha256) if symbol_manifest is not None else None
                if native_symbols:
                    if native_identity and native_symbols.source_acd_sha256 != native_identity.source_acd_sha256:
                        raise ModelError('Native symbol and correlation manifests refer to different ACD files')
                    provenance['native_symbols'] = native_symbols.manifest()
                type_manifest = provenance.get('native_types')
                if action == 'load' and Path(name).suffix.lower() == '.l5x' and 'native_types' in data:
                    type_manifest = data['native_types']
                native_types = NativeTypes.from_manifest(type_manifest, project.sha256) if type_manifest is not None else None
                if native_types:
                    if any(binding and binding.source_acd_sha256 != native_types.source_acd_sha256
                           for binding in (native_identity, native_symbols)):
                        raise ModelError('Native type and project manifests refer to different ACD files')
                    # Keep the full catalog in its own bound object. Polling and
                    # snapshot provenance must not repeat megabytes of members.
                    provenance['native_types'] = native_types.description()
                template_manifest = data.get('native_templates') if action == 'load' and Path(name).suffix.lower() == '.l5x' else None
                native_templates = NativeTemplates.from_manifest(template_manifest, native_types) if template_manifest is not None else None
                if native_templates:
                    native_templates.bind(project, native_types)
                    provenance['native_templates'] = native_templates.description()
                task_manifest = provenance.get('native_tasks')
                if action == 'load' and Path(name).suffix.lower() == '.l5x' and 'native_tasks' in data:
                    task_manifest = data['native_tasks']
                native_tasks = NativeTasks.from_manifest(task_manifest, project.sha256) if task_manifest is not None else None
                if native_tasks:
                    if any(binding and binding.source_acd_sha256 != native_tasks.source_acd_sha256
                           for binding in (native_identity, native_symbols, native_types)):
                        raise ModelError('Native Task and project manifests refer to different ACD files')
                    if (not project.task_configuration.source_complete or
                            set(native_tasks.tasks) != {name.casefold() for name in project.task_configuration.names}):
                        raise ModelError('Native Task identities do not match the complete ordinary Task source')
                    provenance['native_tasks'] = native_tasks.description()
                routine_manifest = provenance.get('native_routines')
                if action == 'load' and Path(name).suffix.lower() == '.l5x' and 'native_routines' in data:
                    routine_manifest = data['native_routines']
                native_routines = NativeRoutines.from_manifest(routine_manifest, project.sha256) if routine_manifest is not None else None
                if native_routines:
                    if any(binding and binding.source_acd_sha256 != native_routines.source_acd_sha256
                           for binding in (native_identity, native_symbols, native_types, native_tasks)):
                        raise ModelError('Native Executable and project manifests refer to different ACD files')
                    configuration = project.executable_configuration
                    expected = {(program.casefold(),name.casefold()) for program in configuration.program_names
                                for name in configuration.routine_names(program,source_sha256=project.sha256)}
                    if (not configuration.source_complete or native_symbols is None
                            or set(native_routines.by_key) != expected
                            or any(native_symbols.programs.get(row.program.casefold()) != row.program_instance
                                   for row in native_routines.rows)):
                        raise ModelError('Native Executable identities do not match the complete ordinary source and Program bindings')
                    provenance['native_routines'] = native_routines.description()
                aoi_manifest=provenance.get('native_aois')
                if action=='load' and Path(name).suffix.lower()=='.l5x' and 'native_aois' in data:
                    aoi_manifest=data['native_aois']
                native_aois=NativeAOIs.from_manifest(aoi_manifest,project.sha256) if aoi_manifest is not None else None
                if native_aois:
                    if any(binding and binding.source_acd_sha256!=native_aois.source_acd_sha256
                           for binding in (native_identity,native_symbols,native_types,native_tasks,native_routines)):
                        raise ModelError('Native AOI and project manifests refer to different ACD files')
                    metadata=project.aoi_catalog.metadata
                    if metadata is None or set(native_aois.definitions)!={row.name.casefold() for row in metadata}:
                        raise ModelError('Native AOI identities do not match the complete AOI source declarations')
                    provenance['native_aois']=native_aois.description()
                aoi_routine_manifest=provenance.get('native_aoi_routines')
                if action=='load' and Path(name).suffix.lower()=='.l5x' and 'native_aoi_routines' in data:
                    aoi_routine_manifest=data['native_aoi_routines']
                native_aoi_routines=NativeAOIRoutines.from_manifest(aoi_routine_manifest,project.sha256) if aoi_routine_manifest is not None else None
                if native_aoi_routines:
                    if native_aois is None or native_aoi_routines.source_acd_sha256!=native_aois.source_acd_sha256:
                        raise ModelError('AOI routine identities require matching AOI parent bindings')
                    expected={(row.name.casefold(),r.name.casefold()) for row in project.aoi_catalog.metadata
                              for r in row.routines or ()}
                    actual={(r.aoi.casefold(),r.name.casefold()) for r in native_aoi_routines.rows}
                    if actual!=expected or any(native_aois.definitions[r.aoi.casefold()][1]!=r.aoi_instance
                                              for r in native_aoi_routines.rows):
                        raise ModelError('AOI routine identities do not match readable source and AOI parents')
                    provenance['native_aoi_routines']=native_aoi_routines.description()
                auxiliary_manifest=provenance.get('native_auxiliary_symbols')
                if action=='load' and Path(name).suffix.lower()=='.l5x' and 'native_auxiliary_symbols' in data:
                    auxiliary_manifest=data['native_auxiliary_symbols']
                native_auxiliary_symbols=NativeAuxiliarySymbols.from_manifest(auxiliary_manifest,project.sha256) if auxiliary_manifest is not None else None
                if native_auxiliary_symbols:
                    native_auxiliary_symbols.require_parents(native_symbols)
                    if any(binding and binding.source_acd_sha256!=native_auxiliary_symbols.source_acd_sha256
                           for binding in (native_identity,native_types,native_tasks,native_routines,native_aois,native_aoi_routines)):
                        raise ModelError('Auxiliary Symbol and project manifests refer to different ACD files')
                    provenance['native_auxiliary_symbols']=native_auxiliary_symbols.description()
                table_manifest=provenance.get('native_tables')
                if action=='load' and Path(name).suffix.lower()=='.l5x' and 'native_tables' in data:
                    table_manifest=data['native_tables']
                native_tables=NativeTables.from_manifest(table_manifest,project.sha256) if table_manifest is not None else None
                if native_tables:
                    if any(binding and binding.source_acd_sha256!=native_tables.source_acd_sha256
                           for binding in (native_identity,native_symbols,native_types,native_tasks,native_routines,native_aois,native_aoi_routines,native_auxiliary_symbols)):
                        raise ModelError('Data Table and project manifests refer to different ACD files')
                    provenance['native_tables']=native_tables.description()
                diagnostic_manifest=provenance.get('native_diagnostics')
                if action=='load' and Path(name).suffix.lower()=='.l5x' and 'native_diagnostics' in data:
                    diagnostic_manifest=data['native_diagnostics']
                native_diagnostics=NativeDiagnostics.from_manifest(diagnostic_manifest,project.sha256) if diagnostic_manifest is not None else None
                if native_diagnostics:
                    if native_identity is None or any(binding and binding.source_acd_sha256!=native_diagnostics.source_acd_sha256
                            for binding in (native_identity,native_symbols,native_types,native_tasks,native_routines,native_aois,native_aoi_routines,native_auxiliary_symbols,native_tables)):
                        raise ModelError('Diagnostic definitions require matching original Project bindings')
                    provenance['native_diagnostics']=native_diagnostics.description()
                profile_manifest=provenance.get('native_diagnostic_profiles')
                if action=='load' and Path(name).suffix.lower()=='.l5x' and 'native_diagnostic_profiles' in data:
                    profile_manifest=data['native_diagnostic_profiles']
                native_diagnostic_profiles=NativeDiagnosticProfiles.from_manifest(profile_manifest,project.sha256) if profile_manifest is not None else None
                if native_diagnostic_profiles:
                    if native_identity is None or any(binding and binding.source_acd_sha256!=native_diagnostic_profiles.source_acd_sha256
                            for binding in (native_identity,native_symbols,native_types,native_tasks,native_routines,native_aois,native_aoi_routines,native_auxiliary_symbols,native_tables,native_diagnostics)):
                        raise ModelError('Diagnostic profiles require matching original Project bindings')
                    provenance['native_diagnostic_profiles']=native_diagnostic_profiles.description()
                object_manifest=provenance.get('native_diagnostic_objects')
                if action=='load' and Path(name).suffix.lower()=='.l5x' and 'native_diagnostic_objects' in data:
                    object_manifest=data['native_diagnostic_objects']
                native_diagnostic_objects=NativeDiagnosticObjects.from_manifest(object_manifest,project.sha256) if object_manifest is not None else None
                if native_diagnostic_objects:
                    if native_identity is None or any(binding and binding.source_acd_sha256!=native_diagnostic_objects.source_acd_sha256
                            for binding in (native_identity,native_symbols,native_types,native_tasks,native_routines,native_aois,native_aoi_routines,native_auxiliary_symbols,native_tables,native_diagnostics,native_diagnostic_profiles)):
                        raise ModelError('Diagnostic objects require matching original Project bindings')
                    provenance['native_diagnostic_objects']=native_diagnostic_objects.description()
                security_manifest=provenance.get('native_security_bindings')
                if action=='load' and Path(name).suffix.lower()=='.l5x' and 'native_security_bindings' in data:
                    security_manifest=data['native_security_bindings']
                native_security_bindings=NativeSecurityBindings.from_manifest(security_manifest,project.sha256) if security_manifest is not None else None
                if native_security_bindings:
                    if native_identity is None or any(binding and binding.source_acd_sha256!=native_security_bindings.source_acd_sha256
                            for binding in (native_identity,native_symbols,native_types,native_tasks,native_routines,native_aois,native_aoi_routines,native_auxiliary_symbols,native_tables,native_diagnostics,native_diagnostic_profiles,native_diagnostic_objects)):
                        raise ModelError('Security authority bindings require matching original Project bindings')
                    provenance['native_security_bindings']=native_security_bindings.description()
                native_reference_symbols=ReferenceSymbols.from_source(project,native_identity,native_symbols,native_tasks,native_auxiliary_symbols)
                if native_reference_symbols:provenance['native_reference_symbols']=native_reference_symbols.description()
                engine = Engine(project,defer_prescan=True)
                with self.lock:
                    if self.endpoint and self.endpoint.enabled:
                        from .identity import Identity
                        identity=Identity.from_project(self.endpoint.profile,project)
                        with self.endpoint.lock:
                            self.endpoint.identity=identity;self.endpoint.source_sha256=project.sha256
                    self.engine, self.provenance = engine, provenance
                    self.scan_interval_ms = self.default_scan_interval()
                    self.native_project_identity = native_identity
                    self.native_symbols = native_symbols
                    self.native_types = native_types
                    self.native_templates = native_templates
                    self.native_tasks = native_tasks
                    self.native_routines = native_routines
                    self.native_aois = native_aois
                    self.native_aoi_routines = native_aoi_routines
                    self.native_auxiliary_symbols = native_auxiliary_symbols
                    self.native_reference_symbols = native_reference_symbols
                    self.native_tables = native_tables
                    self.native_diagnostics = native_diagnostics
                    self.native_diagnostic_profiles = native_diagnostic_profiles
                    self.native_diagnostic_objects = native_diagnostic_objects
                    self.native_security_bindings = native_security_bindings
                    self.generation += 1
                    self.device_io.bind(self.generation)
                    self._io_dirty = True
                    if self.endpoint:self.endpoint.close_native_sessions()
                    return self.state()
            finally:
                with self.lock: self.busy = False
        with self.lock:
            if self.busy: raise ModelError("Import in progress")
            if action=='routine-edits-configure':
                enabled=data.get('allow_writes')
                if type(enabled) is not bool:raise ModelError('Supported Studio edits must be boolean')
                if enabled!=self.allow_routine_edits:
                    if self.running:raise ModelError('Switch to Program before changing Studio edit access')
                    if self.endpoint and self.endpoint.enabled:
                        with self.endpoint.lock:
                            lease=self.endpoint.programming_lease
                            if self.endpoint.state()['active_tcp_clients'] or lease.live(self.generation,self.engine.project.sha256):
                                raise ModelError('Disconnect native clients before changing Studio edit access')
                    self.allow_routine_edits=enabled
                return self.state()
            if action == 'device-io-configure':
                self.device_io.configure(data.get('allow_writes',False))
                return self.state()
            if action == "settings":
                self.converter = str(data["converter"])
                (self.data_dir / 'settings.json').write_text(json.dumps({'converter': self.converter}), encoding='utf-8')
                return self.state()
            if self.engine is None: raise ModelError("Load a project first")
            e = self.engine
            if action == "configure":
                engine = Engine(e.project, data.get("mode", "project"), data.get("routine", ""),defer_prescan=True)
                self.set_controller_mode('Program')
                self.engine = engine
                self.scan_interval_ms = self.default_scan_interval()
                self.generation += 1
                self.device_io.bind(self.generation); self._io_dirty = True
                if self.endpoint:self.endpoint.close_native_sessions()
            elif action == 'controller-mode':
                self.set_controller_mode(data.get('mode'),data.get('dt'),remote_request=True)
            elif action == "step":
                if self.running:raise ModelError('Switch to Program before stepping manually')
                if self.endpoint and self.endpoint.native_read_only:
                    with self.endpoint.lock:
                        if self.endpoint.programming_lease.inhibit(self.generation,e.project.sha256):
                            raise ModelError('Native programming preparation inhibits scans; release or disconnect the owning client')
                count, dt = int(data.get("count", 1)), int(data.get("dt", 10))
                if not 1 <= count <= 1000: raise ModelError("Scan count must be 1..1000")
                self.engine.prepare_step(dt)
                for _ in range(count):
                    self.device_io.apply(self)
                    self._io_dirty = True
                    try: self.engine.step(dt)
                    except Exception:
                        self.publish_device_io(); raise
                    if count > 1 and self.device_io.sample_due(): self.publish_device_io()
            elif action == "write":
                e.memory.write(data["tag"], data["value"])
                self._io_dirty = True
            elif action == "reset":
                self.set_controller_mode('Program')
                self.engine = Engine(e.project, e.mode, e.selected,defer_prescan=True)
                self.generation += 1
                self.device_io.bind(self.generation); self._io_dirty = True
                if self.endpoint:self.endpoint.close_native_sessions()
            elif action == 'observe':pass
            elif action == "report":
                report = e.report()
                report["import_provenance"] = self.provenance
                return report
            elif action == "snapshot":
                return {"report": e.report(), "import_provenance": self.provenance,
                        "scan": e.scan_count, "ms": e.time_ms, "tags": e.memory.leaves(), "changes": e.changes,
                        'controller':self.controller_state()}
            elif action=='export-edited-l5x':
                if self.running:raise ModelError('Switch to Program before saving edited logic')
                if self.endpoint and self.endpoint.enabled:
                    with self.endpoint.lock:
                        if self.endpoint.programming_lease.live(self.generation,e.project.sha256):raise ModelError('Wait for the native edit transaction to finish before saving logic')
                from .logic_export import export
                return export(e)
            else: raise ModelError(f"Unknown action {action}")
            return self.state()


def serve(port=0, open_browser=True, data_dir=None, eip_port=None, eip_writes=False, sample=None, eip_profile='research', tray=True, eip_bind='127.0.0.1',eip_native_read_only=False,device_writes=False):
    app = Application(data_dir)
    if sample:app.command('demo',{'sample':sample})
    if device_writes:app.command('device-io-configure',{'allow_writes':True})
    if eip_port is not None:app.command('connectivity-start',{'port':eip_port,'allow_writes':eip_writes,'profile':eip_profile,'bind_address':eip_bind,'native_read_only':eip_native_read_only})
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass

        def send(self, code, content, mime="application/json", headers=None):
            def safe(value):
                if isinstance(value,int) and abs(value)>9007199254740991:return str(value)
                if isinstance(value,dict):return {k:safe(v) for k,v in value.items()}
                if isinstance(value,list):return [safe(v) for v in value]
                return value
            if not isinstance(content, bytes): content = json.dumps(safe(content), allow_nan=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            for name,value in (headers or {}).items():self.send_header(name,value)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(content)

        def valid_host(self):
            return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

        def do_GET(self):
            if not self.valid_host(): return self.send(403, {"error": "Invalid host"})
            path = urlsplit(self.path).path
            if path.startswith('/api/device-io/'):
                from . import device_http
                return device_http.get(self,app.device_io,path)
            if path == "/session.js":
                return self.send(200, f"window.LOGIX_TOKEN = {json.dumps(token)};".encode(), "text/javascript")
            if path == "/api/state":
                if self.headers.get("X-Logix-Token") != token: return self.send(403, {"error": "Session token required"})
                with app.lock: return self.send(200, app.state())
            assets = {"/": ("index.html", "text/html; charset=utf-8"),
                      "/app.js": ("app.js", "text/javascript"), "/style.css": ("style.css", "text/css"),
                      "/favicon.ico": ("icons/plc-simulator.ico", "image/vnd.microsoft.icon"),
                      "/icons/plc-simulator-64.png": ("icons/plc-simulator-64.png", "image/png"),
                      "/icons/plc-simulator-128.png": ("icons/plc-simulator-128.png", "image/png")}
            if path not in assets: return self.send(404, {"error": "Not found"})
            name, mime = assets[path]
            content = (BASE / "web" / name).read_bytes()
            if name == 'index.html':
                content = content.replace(b'__LOGIXLAB_VERSION__', __version__.encode('ascii'))
            self.send(200, content, mime)

        def do_POST(self):
            origin = self.headers.get("Origin")
            expected_origin = f"http://127.0.0.1:{self.server.server_port}"
            if urlsplit(self.path).path == '/api/device-io/write':
                if not self.valid_host() or (origin and origin != expected_origin):return self.send(403,{'error':'Invalid device origin'})
                from . import device_http
                return device_http.write(self,app.device_io)
            if not self.valid_host() or self.headers.get("X-Logix-Token") != token or (origin and origin != expected_origin):
                return self.send(403, {"error": "Invalid session"})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 140_000_000: raise ModelError("Invalid request size")
                data = json.loads(self.rfile.read(size))
                action = urlsplit(self.path).path.removeprefix("/api/")
                if action == 'quit':
                    self.send(200, {'closed': True})
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                    return
                result = app.command(action, data)
                self.send(200, result)
            except Exception as e:
                self.send(400, {"error": str(e)})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{server.server_port}"
    tray_icon = None
    try:
        if tray:
            from .desktop import TrayIcon
            def quit_from_tray():
                threading.Thread(target=server.shutdown, daemon=True).start()
            tray_icon = TrayIcon(url, quit_from_tray)
            tray_icon.start()
            app.desktop = {'tray_available': tray_icon.available, 'tray_error': tray_icon.error}
        (app.data_dir / "last-session.json").write_text(json.dumps({"url": url, "pid": os.getpid(),
            'app_version': __version__, **app.desktop}), encoding="utf-8")
        if sys.stdout: print(f"LogixLab {__version__}: {url}", flush=True)
        if open_browser: webbrowser.open(url)
        server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        app.close()
        if tray_icon: tray_icon.stop()
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description="LogixLab offline v35 ladder simulator")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument('--no-tray', action='store_true', help='Disable the Windows notification-area icon')
    parser.add_argument("--data-dir")
    parser.add_argument('--sample',choices=SAMPLES)
    parser.add_argument('--eip-port',type=int,help='Start local research EtherNet/IP listener; requires --sample')
    parser.add_argument('--eip-bind',default='127.0.0.1',help='Bind EtherNet/IP to a specific local IPv4 address (default: loopback)')
    parser.add_argument('--eip-writes',action='store_true',help='Allow explicit atomic tag writes to the software model')
    parser.add_argument('--eip-profile',choices=('research','logix-v35-l85e'),default='research')
    parser.add_argument('--eip-native-read-only',action='store_true',help='Experimental anonymous Studio compatibility; requires L85E profile and disabled tag writes')
    parser.add_argument('--device-writes',action='store_true',help='Allow queued device-simulator input writes between scans')
    parser.add_argument("--report", help="Generate a JSON coverage report for an L5X, without starting the app")
    args = parser.parse_args()
    if args.report:
        print(json.dumps(Engine(Project(args.report)).report(), indent=2))
    else:
        if args.eip_port is not None and not args.sample:parser.error('--eip-port requires --sample')
        if args.eip_writes and args.eip_port is None:parser.error('--eip-writes requires --eip-port')
        if args.eip_bind!='127.0.0.1' and args.eip_port is None:parser.error('--eip-bind requires --eip-port')
        if args.eip_profile!='research' and args.eip_port is None:parser.error('--eip-profile requires --eip-port')
        if args.eip_native_read_only and args.eip_port is None:parser.error('--eip-native-read-only requires --eip-port')
        serve(args.port, not args.no_browser, args.data_dir,args.eip_port,args.eip_writes,args.sample,args.eip_profile,not args.no_tray,args.eip_bind,args.eip_native_read_only,args.device_writes)


if __name__ == "__main__": main()
