"""Inspect an existing capture with optional TShark; never capture or connect.

Reports outer CIP messages and only pairs unambiguous, same-stream exchanges
using TShark's explicit response-to frame references. Payloads are hashed by
default. This tool does not infer vendor-service meanings or online success.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from logixlab.ethernetip import CIPError, decode_path

MAX_CAPTURE = 64 * 1024 * 1024
MAX_JSON = 128 * 1024 * 1024
PACKET_LIMIT = 50_000


def values(node, name):
    result = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == name:
                result.extend(value if isinstance(value, list) else [value])
            else:
                result.extend(values(value, name))
    elif isinstance(node, list):
        for value in node:
            result.extend(values(value, name))
    return result


def number(node, name):
    found = values(node, name)
    if len(found) != 1:
        raise ValueError(f'Expected one {name}')
    return int(found[0], 0)


def describe(raw, include_payloads=False):
    if len(raw) < 2:
        raise ValueError('Truncated CIP header')
    service = raw[0]
    message = {'service': service & 0x7f, 'response': bool(service & 0x80),
               'message_bytes': len(raw), 'message_sha256': hashlib.sha256(raw).hexdigest()}
    if message['response']:
        if len(raw) < 4 or len(raw) < 4 + 2 * raw[3]:
            raise ValueError('Truncated CIP status')
        if raw[1] != 0:
            raise ValueError('Nonzero reserved response byte')
        start = 4 + 2 * raw[3]
        message.update(status=raw[2], additional_status=[int.from_bytes(raw[i:i+2], 'little')
                       for i in range(4, start, 2)])
    else:
        start = 2 + 2 * raw[1]
        if len(raw) < start:
            raise ValueError('Truncated CIP request path')
        try:
            path = decode_path(raw[2:start])
        except CIPError as error:
            raise ValueError('Unsupported or malformed request path') from error
        message.update(class_id=path.class_id, instance=path.instance,
                       attribute=path.attribute, symbolic_path=bool(path.symbols))
    payload = raw[start:]
    message.update(payload_bytes=len(payload), payload_sha256=hashlib.sha256(payload).hexdigest())
    if include_payloads:
        message['message_hex'] = raw.hex()
    return message


def summarize(packets, include_payloads=False):
    messages, skipped, duplicate_frames = {}, [], set()
    for packet in packets:
        layers = packet.get('_source', {}).get('layers', {})
        frame = None
        try:
            frame = number(layers.get('frame', {}), 'frame.number')
            stream = number(layers.get('tcp', {}), 'tcp.stream')
            raw = layers.get('cip_raw')
            # Multiple PDUs or nested-only decodes cannot be paired by frame alone.
            if not isinstance(raw, list) or not raw or not isinstance(raw[0], str):
                raise ValueError('Expected one outer CIP message')
            message = describe(bytes.fromhex(raw[0]), include_payloads)
            message.update(frame=frame, stream=stream)
            references = values(layers.get('enip', {}), 'enip.response_to')
            if references:
                if len(references) != 1:
                    raise ValueError('Ambiguous response frame reference')
                message['request_frame'] = int(references[0], 0)
            if frame in messages or frame in duplicate_frames:
                messages.pop(frame, None)
                duplicate_frames.add(frame)
                raise ValueError('Duplicate frame')
            messages[frame] = message
        except (ValueError, TypeError) as error:
            skipped.append({'frame': frame, 'reason': str(error)})
    exchanges, paired_requests, paired_responses = [], set(), set()
    for response in messages.values():
        if not response['response']:
            continue
        request = messages.get(response.get('request_frame'))
        if (request is None or request['response'] or request['frame'] >= response['frame'] or
                request['stream'] != response['stream'] or request['service'] != response['service']):
            continue
        exchanges.append({'request': request, 'response': response})
        paired_requests.add(request['frame']); paired_responses.add(response['frame'])
    counts = Counter(f"0x{value['service']:02X}" for value in messages.values() if not value['response'])
    return {'format_version': 1, 'scope': 'outer CIP messages only',
            'vendor_semantics': 'NOT INFERRED', 'studio_go_online': 'NOT ASSESSED',
            'cip_packets': len(packets), 'decoded_messages': len(messages),
            'request_services': dict(sorted(counts.items())), 'exchanges': exchanges,
            'unpaired_requests': [m for f, m in messages.items() if not m['response'] and f not in paired_requests],
            'unpaired_responses': [m for f, m in messages.items() if m['response'] and f not in paired_responses],
            'skipped_packets': skipped}


def find_tshark(explicit=None):
    candidates = [explicit] if explicit else [shutil.which('tshark'),
                  Path(r'C:\Program Files\Wireshark\tshark.exe')]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    raise ValueError('TShark is required; install Wireshark or pass --tshark')


def decode_capture(capture, tshark):
    # -r and -n keep this offline, including name resolution. Bound packets,
    # output size and execution time independently of the capture's file size.
    command = [tshark, '-n', '-2', '-r', str(capture), '-c', str(PACKET_LIMIT),
               '-Y', 'cip', '-T', 'json', '-x', '--no-duplicate-keys']
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(command, stdout=output, stderr=errors)
        try:
            deadline = time.monotonic() + 60
            while process.poll() is None:
                if os.fstat(output.fileno()).st_size > MAX_JSON or time.monotonic() > deadline:
                    raise ValueError('TShark output or time limit exceeded')
                time.sleep(0.1)
            if output.seek(0, 2) > MAX_JSON:
                raise ValueError('TShark output limit exceeded')
            if process.returncode:
                errors.seek(0)
                raise ValueError('TShark failed: ' + errors.read(2000).decode('utf-8', errors='replace'))
            output.seek(0)
            return json.load(output)
        finally:
            if process.poll() is None:
                process.kill(); process.wait()


def inspect(capture, tshark, include_payloads=False):
    capture = Path(capture).resolve()
    with capture.open('rb') as source:
        original = source.read(MAX_CAPTURE + 1)
    if len(original) > MAX_CAPTURE:
        raise ValueError('Capture exceeds the 64 MiB limit; trim it offline first')
    digest = hashlib.sha256(original).hexdigest()
    result = summarize(decode_capture(capture, tshark), include_payloads)
    with capture.open('rb') as source:
        after = source.read(MAX_CAPTURE + 1)
    if hashlib.sha256(after).hexdigest() != digest:
        raise ValueError('Capture changed during analysis; use a completed capture')
    result.update(capture_sha256=digest, capture_bytes=len(original),
                  limits={'input_packets': PACKET_LIMIT, 'capture_completeness': 'NOT ASSESSED'},
                  input_unchanged=True, payloads_included=include_payloads)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path, help='Private JSON report; normally under .local/')
    parser.add_argument('--tshark', type=Path)
    parser.add_argument('--include-payloads', action='store_true', help='Include full CIP bytes in the private report')
    args = parser.parse_args()
    try:
        if (args.out.resolve() == args.capture.resolve() or
                args.out.exists() and args.out.samefile(args.capture)):
            raise ValueError('Output must not overwrite the capture')
        result = inspect(args.capture, find_tshark(args.tshark), args.include_payloads)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    except (ValueError, OSError, json.JSONDecodeError) as error:
        parser.exit(1, f'{error}\n')
    print(json.dumps({key: result[key] for key in ('cip_packets', 'decoded_messages', 'request_services')}))
    print(f"Paired exchanges: {len(result['exchanges'])}; skipped packets: {len(result['skipped_packets'])}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
