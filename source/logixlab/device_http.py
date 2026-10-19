"""Local device API; cached reads and queued writes never take app.lock."""
import json

from .device_io import DeviceIOError, IDENTIFIER, MAX_REQUEST_BYTES


def get(handler, io, path):
    if path == '/api/device-io/session': return handler.send(200, io.session())
    if not io.authorized(handler.headers.get('X-Logix-Device-Token')):
        return handler.send(403, {'error':'Device read token required'})
    if path == '/api/device-io/snapshot':
        etag, raw = io.snapshot()
        return handler.send(304 if handler.headers.get('If-None-Match') == etag else 200,
                            b'' if handler.headers.get('If-None-Match') == etag else raw,
                            headers={'ETag':etag})
    prefix = '/api/device-io/requests/'
    if path.startswith(prefix) and IDENTIFIER.fullmatch(path[len(prefix):]):
        try: return handler.send(200, io.receipt(path[len(prefix):]))
        except DeviceIOError as error: return handler.send(error.status, {'error':str(error)})
    return handler.send(404, {'error':'Device API path not found'})


def write(handler, io):
    if not io.authorized(handler.headers.get('X-Logix-Device-Token'), write=True):
        return handler.send(403, {'error':'External writes disabled or device write token required'})
    try:
        size = int(handler.headers.get('Content-Length','0'))
        if not 0 < size <= MAX_REQUEST_BYTES: raise DeviceIOError(413,'Device transaction size must be 1..65536 bytes')
        data = json.loads(handler.rfile.read(size))
        receipt = io.enqueue(data)
        return handler.send(202 if receipt['status'] == 'queued' else 200, receipt)
    except DeviceIOError as error: return handler.send(error.status, {'error':str(error)})
    except (ValueError, TypeError, UnicodeError, RecursionError): return handler.send(400, {'error':'Invalid device transaction JSON'})
