"""Inspect an existing capture with optional TShark; never capture or connect.

Reports CIP messages and only pairs unambiguous, same-stream exchanges
using TShark's explicit response-to frame references. Payloads are hashed by
default. One observed signed layer can be decoded without asserting MAC validity,
vendor-service meanings or online success.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
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
from logixlab import signed_messages
from tools.collection_inventory import instance_supported as collection_instance, scope_supported as collection_scope, CollectionError, decode_attribute_list as decode_collection_list

MAX_CAPTURE = 64 * 1024 * 1024
MAX_OUTPUT = 128 * 1024 * 1024
MAX_LINE = 1024 * 1024
PACKET_LIMIT = 250_000


@dataclass(frozen=True)
class CaptureDecode:
    packets: list
    input_frames: int


def field_packets(source):
    """Read compact TShark fields, preserving ambiguous frames as skipped rows.

    All frames are counted, including non-CIP frames, so hitting the input
    bound cannot silently look like a complete capture. Raw protocol fields
    are accepted only when one outer CIP PDU exists in the frame.
    """
    packets = []
    frames = 0
    while line := source.readline(MAX_LINE + 1):
        if len(line) > MAX_LINE:
            raise ValueError('TShark field line exceeds the output bound')
        frames += 1
        if frames > PACKET_LIMIT:
            raise ValueError('TShark returned more than the packet bound')
        try:
            fields = line.rstrip(b'\r\n').decode('ascii').split('\t')
        except UnicodeDecodeError as error:
            raise ValueError('TShark fields are not ASCII') from error
        if len(fields) != 4:
            raise ValueError('Expected four TShark fields per frame')
        frame, stream, references, raw = fields
        if not frame.isdecimal() or int(frame) < 1:
            raise ValueError('Invalid TShark frame number')
        if not raw:
            continue
        layers = {'frame': {'frame.number': frame}, 'tcp': {'tcp.stream': stream}, 'enip': {}}
        if references:
            layers['enip']['enip.response_to'] = references.split(',')
        # A comma denotes more than one PDU. Never select an arbitrary one.
        if ',' not in raw:
            layers['cip_raw'] = [raw.replace(':', '')]
        packets.append({'_source': {'layers': layers}})
    return CaptureDecode(packets, frames)


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


def describe_path(raw):
    """Describe observed class/instance scopes without changing live routing.

    Every parent is exactly an object path. Symbols are validated by the live
    decoder but never returned here, including when their bytes resemble paths.
    """
    boundaries = [0]
    position = 0
    while position < len(raw):
        start = position
        code = raw[position]
        position += 1
        if code == 0x91:
            if position == len(raw):
                raise ValueError('Truncated symbolic segment')
            size = raw[position]
            position += 1 + size + size % 2
        elif code in (0x20, 0x21, 0x22, 0x24, 0x25, 0x26,
                      0x28, 0x29, 0x2A, 0x30, 0x31, 0x32):
            if code in (0x20, 0x21, 0x22) and start:
                boundaries.append(start)
            width = (1, 2, 4)[code & 3]
            position += width + (width > 1)
        else:
            raise ValueError('Unsupported request path segment')
        if position > len(raw):
            raise ValueError('Truncated request path segment')
    if len(boundaries) > 16:
        raise ValueError('Request object scope limit exceeded')
    try:
        scopes = [decode_path(raw[a:b]) for a, b in
                  zip(boundaries, boundaries[1:] + [len(raw)])]
    except CIPError as error:
        raise ValueError('Unsupported or malformed request path') from error
    if len(scopes) > 1:
        if any(p.class_id is None or p.instance is None or p.attribute is not None or p.symbols
               for p in scopes[:-1]) or scopes[-1].class_id is None or scopes[-1].instance is None:
            raise ValueError('Unsupported object scope path')
    fields = [dict(class_id=p.class_id, instance=p.instance, attribute=p.attribute,
                   symbolic_path=bool(p.symbols)) for p in scopes]
    if len(fields) == 1:
        return fields[0]
    # A scoped path must not look like a directly addressable leaf object.
    return dict(class_id=None, instance=None, attribute=None,
                symbolic_path=any(p.symbols for p in scopes), object_path=fields)


def envelope_description(envelope, include_payloads):
    result = {'structure': 'DECODED', 'integrity': 'NOT VERIFIED',
              'sequence': envelope.sequence}
    if isinstance(envelope,signed_messages.FragmentEnvelope):
        result.update(container_format=envelope.container_format,position=envelope.position,
                      fragment_bytes=len(envelope.fragment),fragment_sha256=hashlib.sha256(envelope.fragment).hexdigest())
        if envelope.container_format==0x101:result['first_request']=describe(envelope.fragment,include_payloads,unwrap=False)
        elif include_payloads:result['fragment_hex']=envelope.fragment.hex()
    elif isinstance(envelope,signed_messages.FragmentAck):
        result.update(container_format=0x301,container_control=0,acknowledgement=True)
    elif isinstance(envelope, signed_messages.BatchEnvelope):
        result.update(child_count=len(envelope.children),
                      children=[describe(child, include_payloads, unwrap=False)
                                for child in envelope.children])
    else:
        result.update(container_format=envelope.container_format,
                      inner=describe(envelope.inner, include_payloads, unwrap=False))
        if isinstance(envelope,signed_messages.TransferEnvelope):
            result['container_control']=envelope.container_control
    return result


def describe(raw, include_payloads=False, *, unwrap=True):
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
        message.update(describe_path(raw[2:start]))
    payload = raw[start:]
    message.update(payload_bytes=len(payload), payload_sha256=hashlib.sha256(payload).hexdigest())
    target = message.get('object_path', [message])[-1]
    if (not message['response'] and service == 3 and target.get('class_id') is not None and
            target['attribute'] is None and not message['symbolic_path']):
        count = int.from_bytes(payload[:2], 'little')
        if len(payload) >= 2 and count <= 256 and len(payload) == 2 + 2 * count:
            message['requested_attributes'] = [int.from_bytes(payload[i:i+2], 'little')
                                               for i in range(2, len(payload), 2)]
    if include_payloads:
        message['message_hex'] = raw.hex()
    if (unwrap and not message['response'] and message['class_id'] == 2 and message['instance'] == 1 and
            message['attribute'] is None and not message['symbolic_path'] and service in (0x36, 0x37, 0x38, 0x39)):
        try:
            message['signed_envelope'] = envelope_description(signed_messages.parse_request(raw), include_payloads)
        except (signed_messages.EnvelopeError, ValueError) as error:
            message['signed_envelope'] = {'structure': 'UNSUPPORTED OR MALFORMED',
                                          'integrity': 'NOT VERIFIED', 'reason': str(error)}
    return message


def time_sync_layout(request, response, raw, include_payloads):
    target=request;parents={};scopes=request.get('object_path')
    if scopes:
        if len(scopes)!=2 or scopes[0].get('class_id') not in (0x68,0x338) or scopes[0].get('attribute') is not None:return
        target=scopes[1]
        if target.get('class_id')!=0x6D:return
        parents['program_instance' if scopes[0]['class_id']==0x68 else 'aoi_instance']=scopes[0].get('instance')
    if (collection_instance(target.get('class_id'),target.get('instance')) and
            collection_scope(target.get('class_id'),**parents) and not request.get('symbolic_path') and
            request.get('service') == 3 and target.get('attribute') is None and
            request.get('requested_attributes') and response.get('status') in (0, 6, 0x0A)):
        key = 'time_sync_attribute_list' if target['class_id'] == 0x43 else 'collection_attribute_list'
        try:
            response[key] = decode_collection_list(raw, request['requested_attributes'], target['class_id'],
                                                    include_payloads=include_payloads)
        except CollectionError as error:
            response[key] = {'structure': 'UNSUPPORTED OR MALFORMED', 'reason': str(error)}


def summarize(packets, include_payloads=False):
    messages, raw_messages, skipped, duplicate_frames = {}, {}, [], set()
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
                raw_messages.pop(frame, None)
                duplicate_frames.add(frame)
                raise ValueError('Duplicate frame')
            messages[frame] = message
            raw_messages[frame] = bytes.fromhex(raw[0])
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
        if 'signed_envelope' in request:
            try:
                parsed = signed_messages.parse_request(raw_messages[request['frame']])
                decoded = signed_messages.parse_response(raw_messages[response['frame']], parsed)
                response['signed_envelope'] = envelope_description(decoded, include_payloads)
                left, right = request['signed_envelope'], response['signed_envelope']
                if 'inner' in left and 'inner' in right:
                    time_sync_layout(left['inner'], right['inner'], decoded.inner, include_payloads)
                elif 'children' in left and 'children' in right:
                    for child, reply, raw in zip(left['children'], right['children'], decoded.children, strict=True):
                        time_sync_layout(child, reply, raw, include_payloads)
            except (signed_messages.EnvelopeError, ValueError) as error:
                response['signed_envelope'] = {'structure': 'UNSUPPORTED OR MALFORMED',
                                               'integrity': 'NOT VERIFIED', 'reason': str(error)}
        time_sync_layout(request, response, raw_messages[response['frame']], include_payloads)
        exchanges.append({'request': request, 'response': response})
        paired_requests.add(request['frame']); paired_responses.add(response['frame'])
    counts = Counter(f"0x{value['service']:02X}" for value in messages.values() if not value['response'])
    return {'format_version': 4, 'scope': 'outer CIP messages and one observed signed layer',
            'signed_integrity': 'NOT VERIFIED',
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
    # Expanded JSON repeats every dissected field and raw byte many times.
    # @cip supplies the outer protocol bytes without a tree of byte fields.
    command = [tshark, '-n', '-2', '-r', str(capture), '-c', str(PACKET_LIMIT),
               '-T', 'fields', '-e', 'frame.number', '-e', 'tcp.stream',
               '-e', 'enip.response_to', '-e', '@cip']
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(command, stdout=output, stderr=errors,
                                   **({'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}))
        try:
            deadline = time.monotonic() + 60
            while process.poll() is None:
                if os.fstat(output.fileno()).st_size > MAX_OUTPUT or time.monotonic() > deadline:
                    raise ValueError('TShark output or time limit exceeded')
                time.sleep(0.1)
            if output.seek(0, 2) > MAX_OUTPUT:
                raise ValueError('TShark output limit exceeded')
            if process.returncode:
                errors.seek(0)
                raise ValueError('TShark failed: ' + errors.read(2000).decode('utf-8', errors='replace'))
            output.seek(0)
            return field_packets(output)
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
    decoded = decode_capture(capture, tshark)
    result = summarize(decoded.packets, include_payloads)
    with capture.open('rb') as source:
        after = source.read(MAX_CAPTURE + 1)
    if hashlib.sha256(after).hexdigest() != digest:
        raise ValueError('Capture changed during analysis; use a completed capture')
    result.update(capture_sha256=digest, capture_bytes=len(original),
                  limits={'input_packets': PACKET_LIMIT, 'input_frames_read': decoded.input_frames,
                          'packet_bound_reached': decoded.input_frames >= PACKET_LIMIT,
                          'capture_completeness': 'NOT ASSESSED'},
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
