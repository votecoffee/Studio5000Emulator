"""Optional diskless Alpine appliance on an existing VMware host-only network.

Generated images, keys, session receipts and logs stay in ignored .local storage.
This tool does not configure host interfaces, Linx, NAT or firewall rules.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import ipaddress
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
ROOT = SOURCE.parent
sys.path.insert(0, str(SOURCE))
from logixlab import __version__

ALPINE = '3.24.2'
BRANCH = 'v3.24'
ISO_NAME = f'alpine-virt-{ALPINE}-x86_64.iso'
ISO_SHA256 = '3ab424762af704b2c2a9e57df1dc37f982af260071504d977f2fb96822e7130b'
CDN = 'https://dl-cdn.alpinelinux.org/alpine'
WORLD = ('alpine-base', 'openssl', 'python3', 'python3-pycache-pyc0',
         'openssh-server', 'openssh-server-common-openrc', 'open-vm-tools',
         'open-vm-tools-openrc', 'open-vm-tools-guestinfo', 'open-vm-tools-vix')
UI_PORT = 8786


def background_options(**options):
    """Keep CLI children from opening console windows under pythonw on Windows."""
    options['creationflags'] = options.get('creationflags', 0) | getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    return options


def run(args, timeout=30, check=True, **kwargs):
    result = subprocess.run([str(a) for a in args], capture_output=True, text=True,
                            timeout=timeout, **background_options(**kwargs))
    if check and result.returncode:
        raise RuntimeError(f'{Path(str(args[0])).name} failed: {result.stderr or result.stdout}')
    return result.stdout.strip()


def vmrun():
    options = [shutil.which('vmrun')]
    for variable in ('ProgramFiles(x86)', 'ProgramFiles'):
        if os.environ.get(variable):
            options.append(str(Path(os.environ[variable]) / 'VMware/VMware Workstation/vmrun.exe'))
    return next((p for p in options if p and Path(p).is_file()), None)


def download(url, path, expected=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file() or (expected and hashlib.sha256(path.read_bytes()).hexdigest() != expected):
        print(f'Download {path.name}', flush=True)
        temporary = path.with_suffix(path.suffix + '.partial')
        with urllib.request.urlopen(url, timeout=60) as response, temporary.open('wb') as output:
            shutil.copyfileobj(response, output)
        if expected and hashlib.sha256(temporary.read_bytes()).hexdigest() != expected:
            raise ValueError(f'Checksum mismatch for {path.name}')
        temporary.replace(path)
    return path


def package_index(path, repository):
    with tarfile.open(path) as archive:
        text = archive.extractfile('APKINDEX').read().decode('utf-8')
    records = []
    for block in text.strip().split('\n\n'):
        record = dict(line.split(':', 1) for line in block.splitlines() if ':' in line)
        if 'P' in record:
            record['repository'] = repository
            records.append(record)
    return records


def dependency_name(value):
    return re.split(r'[<>=~]', value, maxsplit=1)[0]


def resolve_packages(records, requested):
    named = {record['P']: record for record in records}
    providers = {}
    for record in records:
        for value in record.get('p', '').split():
            providers.setdefault(dependency_name(value), record)
    result = {}

    def visit(requirement):
        if requirement.startswith('!'):
            return
        name = dependency_name(requirement)
        record = named.get(name) or providers.get(name)
        if record is None:
            raise ValueError(f'No package provides {requirement}')
        if record['P'] in result:
            return
        result[record['P']] = record
        for dependency in record.get('D', '').split():
            visit(dependency)

    for name in requested:
        visit(name)
    return sorted(result.values(), key=lambda r: r['P'])


def tar_bytes(files, links=()):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w:gz') as archive:
        for name, content, mode in files:
            content = content.encode() if isinstance(content, str) else content
            entry = tarfile.TarInfo(name)
            entry.uid = entry.gid = 0
            entry.uname = entry.gname = 'root'
            entry.mode, entry.size = mode, len(content)
            archive.addfile(entry, io.BytesIO(content))
        for name, target in links:
            entry = tarfile.TarInfo(name)
            entry.type, entry.linkname, entry.mode = tarfile.SYMTYPE, target, 0o777
            archive.addfile(entry)
    return output.getvalue()


def overlay(directory):
    key = (directory / 'client-key.pub').read_text().strip()
    startup = '''#!/bin/sh
set -eu
ip=$(ip -4 -o addr show dev eth0 scope global | awk '{split($4,a,"/"); print a[1]; exit}')
test -n "$ip"
# ICMP echo is answered by the guest network stack, independently of CIP ports.
sysctl -w net.ipv4.icmp_echo_ignore_all=0 >/dev/null
id logixlab >/dev/null 2>&1 || adduser -D -h /var/lib/logixlab -s /sbin/nologin logixlab
mkdir -p /var/lib/logixlab
chown logixlab:logixlab /var/lib/logixlab
su logixlab -s /bin/sh -c "exec env LOGIXLAB_ENVIRONMENT=vmware-host-only /usr/bin/python3 /opt/logixlab/launch.py --port 8786 --no-browser --no-tray --data-dir /var/lib/logixlab --sample ConveyorDemo --eip-port 44818 --eip-bind $ip --eip-profile logix-v35-l85e --eip-native-read-only" >/var/log/logixlab.log 2>&1 &
echo $! >/run/logixlab.pid
'''
    ssh_config = '''Port 22
HostKey /etc/ssh/ssh_host_ed25519_key
PermitRootLogin prohibit-password
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitEmptyPasswords no
AuthenticationMethods publickey
AllowUsers root
AllowAgentForwarding no
X11Forwarding no
PermitTTY no
AllowTcpForwarding local
PermitOpen 127.0.0.1:8786
'''
    files = [('etc/hostname', 'logixlab-vm\n', 0o644),
             ('etc/.default_boot_services', '', 0o644),
             ('etc/apk/world', '\n'.join(WORLD) + '\n', 0o644),
             ('etc/network/interfaces', 'auto lo\niface lo inet loopback\nauto eth0\niface eth0 inet dhcp\n', 0o644),
             ('etc/local.d/logixlab.start', startup, 0o755),
             ('etc/ssh/sshd_config', ssh_config, 0o600),
             ('etc/ssh/ssh_host_ed25519_key', (directory / 'host-key').read_bytes(), 0o600),
             ('etc/ssh/ssh_host_ed25519_key.pub', (directory / 'host-key.pub').read_bytes(), 0o644),
             ('root/.ssh/authorized_keys', key + '\n', 0o600)]
    for pattern in ('logixlab/*.py', 'web/*', 'web/icons/*', 'samples/*.L5X', 'tests/*.py', 'launch.py'):
        for path in sorted(SOURCE.glob(pattern)):
            if path.is_file():
                files.append(('opt/logixlab/' + path.relative_to(SOURCE).as_posix(), path.read_bytes(), 0o644))
    files.append(('opt/logixlab/LICENSE', (ROOT / 'LICENSE').read_bytes(), 0o644))
    links = [(f'etc/runlevels/{level}/{name}', f'/etc/init.d/{name}') for level, name in
             (('boot', 'networking'), ('default', 'sshd'), ('default', 'local'), ('default', 'open-vm-tools'))]
    return tar_bytes(files, links)


def host_network(name):
    if not re.fullmatch(r'VMnet\d+', name):
        raise ValueError('Use an existing VMware VMnet name')
    networks = run([vmrun(), '-T', 'ws', 'listHostNetworks'])
    if not re.search(rf'^\s*\d+\s+{re.escape(name)}\s+hostOnly\s', networks, re.I | re.M):
        raise ValueError('The selected VMware network must already be host-only')
    script = ("Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias "
              f"'VMware Network Adapter {name}' | Select-Object IPAddress,PrefixLength | ConvertTo-Json -Compress")
    value = json.loads(run(['powershell', '-NoProfile', '-Command', script]))
    if not isinstance(value, dict):
        raise ValueError('Expected one IPv4 address on the host-only adapter')
    return str(ipaddress.ip_network(f"{value['IPAddress']}/{value['PrefixLength']}", strict=False)), value['IPAddress']


def prepare(directory, network, rebuild=False):
    if not vmrun():
        raise RuntimeError('VMware Workstation vmrun is required')
    config = directory / 'appliance.json'
    old_config = None
    if config.exists():
        if not rebuild:
            raise ValueError('Appliance already prepared; stop it before using prepare --rebuild')
        old_config = load_config(directory)
        if old_config['vmx'].lower() in run([vmrun(), '-T', 'ws', 'list']).lower():
            raise ValueError('Stop this appliance before rebuilding its boot image')
    deps = ROOT / '.local/vmware/build-deps'
    if deps.is_dir():
        sys.path.insert(0, str(deps))
    try:
        import pycdlib
    except ImportError as error:
        raise RuntimeError('The optional builder requires pycdlib==1.14.0') from error
    subnet, host_ip = host_network(network)
    directory.mkdir(parents=True, exist_ok=True)
    cache = directory.parent / 'downloads'
    original = download(f'{CDN}/{BRANCH}/releases/x86_64/{ISO_NAME}', cache / ISO_NAME, ISO_SHA256)
    records, indexes = [], {}
    for repository in ('main', 'community'):
        index = cache / ('APKINDEX.tar.gz' if repository == 'main' else 'APKINDEX-community.tar.gz')
        download(f'{CDN}/{BRANCH}/{repository}/x86_64/APKINDEX.tar.gz', index)
        indexes[repository] = index
        records.extend(package_index(index, repository))
    packages = resolve_packages(records, WORLD)
    for key_name in ('client-key', 'host-key'):
        key_file = directory / key_name
        if not key_file.exists():
            run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-C', 'LogixLab appliance', '-f', key_file])
    archive = pycdlib.PyCdlib()
    archive.open(str(original))
    buffers = []

    def replace(path, content):
        try:
            old = archive.get_record(rr_path=path)
        except (pycdlib.pycdlibexception.PyCdlibInvalidInput, IndexError):
            old = None
        if old:
            iso_path = archive.full_path_from_dirrecord(old, rockridge=False)
            archive.rm_file(iso_path=iso_path)
        else:
            parent = path.rsplit('/', 1)[0]
            parent_record = archive.get_record(rr_path=parent or '/')
            parent_iso = archive.full_path_from_dirrecord(parent_record, rockridge=False).rstrip('/')
            iso_path = parent_iso + '/F' + str(len(buffers)).zfill(7) + '.DAT;1'
        data = io.BytesIO(content)
        buffers.append(data)
        archive.add_fp(data, len(content), iso_path=iso_path, rr_name=path.rsplit('/', 1)[-1], joliet_path=path)

    # Separate signed repository indexes retain Alpine's normal verification.
    archive.add_directory('/COMMUNITY', rr_name='community', joliet_path='/community')
    archive.add_directory('/COMMUNITY/X86_64', rr_name='x86_64', joliet_path='/community/x86_64')
    replace('/community/.boot_repository', b'')
    replace('/apks/x86_64/APKINDEX.tar.gz', indexes['main'].read_bytes())
    replace('/community/x86_64/APKINDEX.tar.gz', indexes['community'].read_bytes())
    manifests = []
    for package in packages:
        name = f"{package['P']}-{package['V']}.apk"
        url = f"{CDN}/{BRANCH}/{package['repository']}/x86_64/{name}"
        path = download(url, cache / name)
        prefix = 'apks' if package['repository'] == 'main' else 'community'
        replace(f'/{prefix}/x86_64/{name}', path.read_bytes())
        manifests.append({'name': package['P'], 'version': package['V'], 'url': url,
                          'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    replace('/logixlab.apkovl.tar.gz', overlay(directory))
    boot = io.BytesIO()
    archive.get_file_from_iso_fp(boot, rr_path='/boot/syslinux/syslinux.cfg')
    replace('/boot/syslinux/syslinux.cfg', boot.getvalue().replace(
        b'quiet ', b'console=tty0 console=ttyS0,115200 apkovl=/media/sr0/logixlab.apkovl.tar.gz '))
    image = directory / 'logixlab.iso'
    archive.write(str(image))
    archive.close()
    mac = old_config['mac'] if old_config else '00:50:56:3a:' + ':'.join(f'{x:02x}' for x in secrets.token_bytes(2))
    vmx = directory / 'LogixLab.vmx'
    values = {'.encoding': 'UTF-8', 'config.version': '8', 'virtualHW.version': '20',
              'displayName': 'LogixLab isolated emulator', 'guestOS': 'other5xlinux-64',
              'memsize': '768', 'numvcpus': '2', 'firmware': 'bios', 'uuid.action': 'create',
              'pciBridge0.present': 'TRUE', 'pciBridge4.present': 'TRUE',
              'pciBridge4.virtualDev': 'pcieRootPort', 'pciBridge4.functions': '8',
              'ide1:0.present': 'TRUE', 'ide1:0.deviceType': 'cdrom-image', 'ide1:0.fileName': str(image),
              'ethernet0.present': 'TRUE', 'ethernet0.connectionType': 'custom', 'ethernet0.vnet': network,
              'ethernet0.virtualDev': 'e1000e', 'ethernet0.addressType': 'static', 'ethernet0.address': mac,
              'usb.present': 'FALSE', 'sound.present': 'FALSE', 'floppy0.present': 'FALSE',
              'serial0.present': 'TRUE', 'serial0.fileType': 'file', 'serial0.fileName': str(directory / 'serial.log'),
              'serial0.yieldOnMsrRead': 'TRUE', 'tools.syncTime': 'TRUE', 'msg.autoAnswer': 'TRUE'}
    vmx.write_text('\n'.join(f'{key} = "{value.replace(chr(92), "/")}"' for key, value in values.items()) + '\n', encoding='utf-8')
    receipt = {'app_version': __version__, 'alpine_version': ALPINE, 'vmx': str(vmx), 'mac': mac,
               'network': network, 'subnet': subnet, 'host_ip': host_ip, 'ui_port': UI_PORT,
               'base_iso_sha256': ISO_SHA256, 'image_sha256': hashlib.sha256(image.read_bytes()).hexdigest(),
               'packages': manifests}
    config.write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    print(json.dumps({'prepared': str(vmx), 'app_version': __version__, 'network': network,
                      'subnet': subnet, 'packages': len(packages)}, indent=2), flush=True)


def ssh_args(directory, ip):
    ip = str(ipaddress.IPv4Address(ip))
    public_key = (directory / 'host-key.pub').read_text().split()
    known = directory / 'known_hosts'
    known.write_text(f'{ip} {public_key[0]} {public_key[1]}\n', encoding='ascii')
    return ['ssh', '-i', str(directory / 'client-key'), '-o', 'IdentitiesOnly=yes',
            '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', f'UserKnownHostsFile={known}',
            '-o', 'ConnectTimeout=4', '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=3',
            f'root@{ip}']


def lease_address(config, text):
    candidates = []
    for address, body in re.findall(r'lease\s+([0-9.]+)\s*\{([^}]+)\}', text):
        if re.search(r'hardware ethernet\s+' + re.escape(config['mac']) + r'\s*;', body, re.I):
            value = ipaddress.IPv4Address(address)
            if value in ipaddress.ip_network(config['subnet']) and address != config['host_ip']:
                candidates.append(address)
    return candidates[-1] if candidates else None


def api(url, action, body=None):
    script = urllib.request.urlopen(url + '/session.js', timeout=3).read().decode()
    token = json.loads(re.search(r'LOGIX_TOKEN = (".*?")', script)[1])
    request = urllib.request.Request(url + '/api/' + action,
        json.dumps(body).encode() if body is not None else None,
        {'Content-Type': 'application/json', 'X-Logix-Token': token})
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response)


def load_config(directory):
    value = json.loads((directory / 'appliance.json').read_text(encoding='utf-8'))
    if Path(value['vmx']).resolve() != (directory / 'LogixLab.vmx').resolve():
        raise ValueError('Appliance manifest does not identify this VM directory')
    return value


def validated_state(directory):
    config = load_config(directory)
    session = json.loads((directory / 'session.json').read_text(encoding='utf-8'))
    if session.get('url') != f'http://127.0.0.1:{UI_PORT}':
        raise ValueError('Unexpected appliance UI address')
    guest = ipaddress.IPv4Address(session['guest_ip'])
    if guest not in ipaddress.ip_network(config['subnet']) or str(guest) == config['host_ip']:
        raise ValueError('Unexpected guest address')
    state = api(session['url'], 'state')
    if state.get('instance_id') != session.get('instance_id') or not session.get('instance_id'):
        raise ValueError('Appliance session changed; refusing to control a different process')
    return session, state


def import_project(directory, project, converter=None):
    from logixlab.importers import convert_acd, default_converter, digest
    session, _ = validated_state(directory)
    source = Path(project).resolve()
    if source.suffix.lower() not in ('.acd', '.l5x') or not source.is_file():
        raise ValueError('Choose an existing ACD or L5X project')
    if source.stat().st_size > 100_000_000:
        raise ValueError('100 MB project limit')
    job = directory / 'imports' / secrets.token_hex(8)
    job.mkdir(parents=True)
    original_hash = digest(source)
    if source.suffix.lower() == '.acd':
        settings = directory / 'settings.json'
        if not settings.is_file():
            settings = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'LogixLab/settings.json'
        configured = json.loads(settings.read_text()).get('converter') if settings.is_file() else ''
        exported = job / 'converted.L5X'
        provenance = convert_acd(source, exported, converter or configured or default_converter())
    else:
        exported = job / source.name
        shutil.copyfile(source, exported)
        provenance = {'method': 'Complete L5X upload', 'source_sha256': original_hash}
    # Recheck identity after potentially long native conversion.
    validated_state(directory)
    result = api(session['url'], 'load', {'name': source.stem + '.L5X',
                                         'content': base64.b64encode(exported.read_bytes()).decode(),
                                         **({'native_project_identity':provenance['native_project_identity']}
                                            if 'native_project_identity' in provenance else {}),
                                         **({'native_symbols':provenance['native_symbols']}
                                            if 'native_symbols' in provenance else {})})
    if digest(source) != original_hash:
        raise ValueError('Source project changed during import')
    receipt = {'app_version': result['app_version'], 'project': result['name'],
               'source_unchanged': True, 'source_sha256': original_hash, 'provenance': provenance}
    (job / 'import-receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    if converter and source.suffix.lower() == '.acd':
        (directory / 'settings.json').write_text(json.dumps({'converter': str(Path(converter).resolve())}), encoding='utf-8')
    return receipt


def import_dialog(directory):
    import tkinter as tk
    from tkinter import filedialog, messagebox
    root = tk.Tk()
    root.withdraw()
    try:
        project = filedialog.askopenfilename(parent=root, title='Import into LogixLab VM',
            filetypes=[('Logix projects', '*.ACD *.acd *.L5X *.l5x')])
        if project:
            import_project(directory, project)
            session, _ = validated_state(directory)
            webbrowser.open(session['url'])
    except Exception as error:
        messagebox.showerror('LogixLab VM import', str(error), parent=root)
    finally:
        root.destroy()


def stop(directory):
    config = load_config(directory)
    session_file = directory / 'session.json'
    session = json.loads(session_file.read_text()) if session_file.exists() else {}
    if session.get('guest_ip'):
        try:
            validated_state(directory)
            snapshot = api(session['url'], 'snapshot', {})
            (directory / 'last-snapshot.json').write_text(json.dumps(snapshot, indent=2), encoding='utf-8')
            api(session['url'], 'quit', {})
        except (OSError, ValueError):
            pass
        run(ssh_args(directory, session['guest_ip']) + ['poweroff'], check=False, timeout=8)
    else:
        run([vmrun(), '-T', 'ws', 'stop', config['vmx'], 'soft'], timeout=20)


def start(directory, open_browser=True, tray=True):
    config = load_config(directory)
    if config['app_version'] != __version__:
        raise ValueError('Appliance version differs from source; rebuild it in a new directory')
    existing = directory / 'session.json'
    if existing.exists():
        session = json.loads(existing.read_text())
        try:
            _, state = validated_state(directory)
        except OSError:
            pass
        else:
            if state.get('app_version') != __version__:
                raise ValueError('Another application is using the appliance UI port')
            if open_browser:
                webbrowser.open(session['url'])
            print(json.dumps(session, indent=2), flush=True)
            return
    running = run([vmrun(), '-T', 'ws', 'list'])
    if config['vmx'].lower() not in running.lower():
        print('Starting isolated emulator VM', flush=True)
        run([vmrun(), '-T', 'ws', 'start', config['vmx'], 'nogui'], timeout=45)
    deadline = time.monotonic() + 180
    ip = None
    while time.monotonic() < deadline:
        candidate = run([vmrun(), '-T', 'ws', 'getGuestIPAddress', config['vmx']], check=False, timeout=8)
        try:
            address = ipaddress.ip_address(candidate)
        except ValueError:
            leases = Path(os.environ.get('PROGRAMDATA', 'C:/ProgramData')) / 'VMware/vmnetdhcp.leases'
            candidate = lease_address(config, leases.read_text(encoding='utf-8')) if leases.is_file() else None
            if candidate:
                try:
                    run(ssh_args(directory, candidate) + ['true'], timeout=6)
                except (RuntimeError, subprocess.TimeoutExpired):
                    candidate = None
            if not candidate:
                time.sleep(2)
                continue
            address = ipaddress.IPv4Address(candidate)
        if address not in ipaddress.ip_network(config['subnet']) or str(address) == config['host_ip']:
            raise ValueError('Guest is not on the expected host-only subnet')
        ip = str(address)
        break
    if not ip:
        raise RuntimeError('Guest IP not available; inspect the private serial.log and vmware.log')
    print(f'Guest address: {ip}', flush=True)
    command = ssh_args(directory, ip)
    # Matching tunnel and guest ports preserve the HTTP Host/session boundary.
    tunnel_args = command[:-1] + ['-N', '-o', 'ExitOnForwardFailure=yes', '-L',
        f'127.0.0.1:{UI_PORT}:127.0.0.1:{UI_PORT}', command[-1]]
    tunnel = None
    icon = None
    url = f'http://127.0.0.1:{UI_PORT}'
    try:
        with (directory / 'ssh.log').open('a', encoding='utf-8') as log:
            tunnel = subprocess.Popen(tunnel_args, stdin=subprocess.DEVNULL,
                                      stdout=subprocess.DEVNULL, stderr=log, **background_options())
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if tunnel.poll() is not None:
                raise RuntimeError('SSH tunnel exited; inspect the private ssh.log')
            try:
                state = api(url, 'state')
                break
            except OSError:
                time.sleep(1)
        else:
            raise RuntimeError('Guest browser service did not become ready')
        expected = f'{ip}:44818'
        if state.get('app_version') != __version__ or state['connectivity']['address'] != expected:
            raise ValueError('Guest version or EtherNet/IP address does not match the appliance')
        session = {'app_version': __version__, 'instance_id': state['instance_id'], 'manager_pid': os.getpid(), 'guest_ip': ip,
                   'endpoint': expected, 'url': url, 'tunnel_pid': tunnel.pid, 'vmx': config['vmx']}
        existing.write_text(json.dumps(session, indent=2), encoding='utf-8')
        if tray:
            from logixlab.desktop import TrayIcon
            def quit_vm():
                threading.Thread(target=stop, args=(directory,), daemon=True).start()
            icon = TrayIcon(url, quit_vm, lambda: import_dialog(directory))
            icon.start()
        print(json.dumps(session, indent=2), flush=True)
        if open_browser:
            webbrowser.open(url)
        failures = 0
        while tunnel.poll() is None:
            time.sleep(2)
            try:
                state = api(url, 'state')
                (directory / 'last-state.json').write_text(json.dumps(state), encoding='utf-8')
                failures = 0
            except OSError:
                failures += 1
                if failures >= 2:
                    break
    except KeyboardInterrupt:
        pass
    finally:
        if icon:
            icon.stop()
        if ip:
            run(ssh_args(directory, ip) + ['poweroff'], check=False, timeout=8)
        if tunnel:
            tunnel.terminate()
            tunnel.wait(timeout=8)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'start', 'status', 'stop', 'import'))
    parser.add_argument('--directory', type=Path, default=ROOT / '.local/vmware/appliance')
    parser.add_argument('--network', default='VMnet1')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--no-tray', action='store_true')
    parser.add_argument('--rebuild', action='store_true', help='Replace this stopped appliance image, retaining its keys and MAC')
    parser.add_argument('--project', type=Path, help='ACD or L5X to import from Windows')
    parser.add_argument('--converter', help='Optional Windows l5xgit converter for ACD imports')
    args = parser.parse_args()
    directory = args.directory.resolve()
    if args.action == 'start' and sys.stdout is None:
        directory.mkdir(parents=True, exist_ok=True)
        log = (directory / 'manager.log').open('a', encoding='utf-8', buffering=1)
        sys.stdout = sys.stderr = log
    if args.action == 'prepare':
        prepare(directory, args.network, args.rebuild)
    elif args.action == 'start':
        start(directory, not args.no_browser, not args.no_tray)
    elif args.action == 'stop':
        stop(directory)
    elif args.action == 'import':
        if not args.project:
            parser.error('import requires --project')
        print(json.dumps(import_project(directory, args.project, args.converter), indent=2))
    else:
        config = load_config(directory)
        session = directory / 'session.json'
        print(json.dumps({'app_version': config['app_version'], 'network': config['network'],
                          'running': config['vmx'].lower() in run([vmrun(), '-T', 'ws', 'list']).lower(),
                          'session': json.loads(session.read_text()) if session.exists() else None}, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        if sys.stderr:
            import traceback
            traceback.print_exc()
        if sys.platform == 'win32' and Path(sys.executable).name.lower() == 'pythonw.exe':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, str(error), 'LogixLab VM could not complete the operation', 0x10)
        raise SystemExit(1)
