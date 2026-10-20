from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import sys
import threading
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .importers import convert_acd, default_converter
from .native_project import NativeProjectIdentity
from .native_symbols import NativeSymbols
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

    def connectivity(self,trace=False):
        return self.endpoint.state(trace) if self.endpoint else {'enabled':False,'address':'127.0.0.1:44818','bind_address':'127.0.0.1',
            'allow_writes':False,'profile':'research','catalog_revision':None,'file_manager':None,
            'controller_configuration':None,'device_metadata':None,'metadata_definition':None,'data_table':None,'pccc_mapping':None,'time_sync':None,'program_forces':None,'io_map':None,'ethernet_counters':None,'aoi_catalog':None,'data_log_catalog':None,
            'native_session':{'enabled':False},'native_correlation':None,
            'locator':{'active':False,'remaining_ms':0,'elapsed_ms':0,'request_id':None},
            'counts':{},'unsupported':[],'attribute_gaps':[],'native_rejections':[],'trace_events':0,'studio_go_online':'NOT IMPLEMENTED OR VERIFIED'}

    def close(self):
        with self.connectivity_lock:
            if self.endpoint and self.endpoint.enabled:self.endpoint.stop()

    def state(self):
        metadata = {'app_version': __version__, 'desktop': dict(self.desktop),
                    'instance_id': self.instance_id, 'execution_environment': self.execution_environment,
                    'device_io':self.device_io.description()}
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
                    self.close()
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
                engine = Engine(project)
                with self.lock:
                    if self.endpoint and self.endpoint.enabled:
                        from .identity import Identity
                        identity=Identity.from_project(self.endpoint.profile,project)
                        with self.endpoint.lock:
                            self.endpoint.identity=identity;self.endpoint.source_sha256=project.sha256
                    self.engine, self.provenance = engine, provenance
                    self.native_project_identity = native_identity
                    self.native_symbols = native_symbols
                    self.generation += 1
                    self.device_io.bind(self.generation)
                    self._io_dirty = True
                    if self.endpoint:self.endpoint.close_native_sessions()
                    return self.state()
            finally:
                with self.lock: self.busy = False
        with self.lock:
            if self.busy: raise ModelError("Import in progress")
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
                self.engine = Engine(e.project, data.get("mode", "project"), data.get("routine", ""))
                self.generation += 1
                self.device_io.bind(self.generation); self._io_dirty = True
                if self.endpoint:self.endpoint.close_native_sessions()
            elif action == "step":
                if self.endpoint and self.endpoint.native_read_only:
                    with self.endpoint.lock:
                        if self.endpoint.programming_lease.inhibit(self.generation,e.project.sha256):
                            raise ModelError('Native programming preparation inhibits scans; release or disconnect the owning client')
                count, dt = int(data.get("count", 1)), int(data.get("dt", 10))
                if not 1 <= count <= 1000: raise ModelError("Scan count must be 1..1000")
                self.engine.validate_interval(dt)
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
                self.engine = Engine(e.project, e.mode, e.selected)
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
                        "scan": e.scan_count, "ms": e.time_ms, "tags": e.memory.leaves(), "changes": e.changes}
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
