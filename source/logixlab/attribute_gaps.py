"""Bounded diagnostics for unsupported attribute reads, without attribute values.

An unsupported field is evidence about a protocol response, not a conclusion
about the cause of a native client's higher-level failure.
"""
from collections import OrderedDict
import time


MAX_GAPS = 64
CLASSES = {1: 'Identity', 0x6A: 'Data Table', 0x6B: 'Symbol',
           0x8E: 'Controller', 0xF5: 'TCP/IP Interface', 0xF6: 'Ethernet Link'}
NAMES = {
    0x8E: {1: 'Power-loss handler reference', 3: 'Communication time slice',
           6: 'Fault handler reference', 8: 'Connection ID', 16: 'Share unused time slice'},
    0xF6: {1: 'Interface speed', 2: 'Interface flags', 3: 'MAC address',
           4: 'Interface counters', 5: 'Media counters', 6: 'Interface control',
           7: 'Interface type', 8: 'Interface state', 9: 'Administrative state'},
    0xF5: {1: 'Configuration status', 2: 'Configuration capability',
           3: 'Configuration control', 4: 'Physical link', 5: 'IPv4 configuration', 6: 'Host name'},
    0x6B: {1: 'Name', 2: 'Type', 3: 'Value address', 4: 'Formal type',
           5: 'Symbol address', 6: 'Control', 7: 'Element size', 8: 'Dimensions',
           9: 'Safety flag', 10: 'External access', 11: 'Constant',
           12: 'Data Table link', 13: 'Logical reference', 14: 'Signature types'},
}


class AttributeGaps:
    """Endpoint-owned collector; its caller serializes access with its lock."""
    def __init__(self):
        self.rows = OrderedDict()

    def record(self, class_id, instance, program_instance, scope, missing, generation, service):
        missing = tuple(sorted(set(missing)))
        if not missing:
            return
        key = (generation, class_id, instance, program_instance, scope, missing, service)
        previous = self.rows.pop(key, None)
        self.rows[key] = {'generation': generation, 'class_id': class_id,
                         'instance': instance, 'program_instance': program_instance,
                         'scope': scope, 'missing': missing, 'service': service,
                         'count': previous['count'] + 1 if previous else 1,
                         'last_seen': time.time()}
        while len(self.rows) > MAX_GAPS:
            self.rows.popitem(last=False)

    def snapshot(self, generation):
        result = []
        for row in reversed(self.rows.values()):
            if row['generation'] != generation:
                continue
            class_id = row['class_id']
            result.append({**{key: value for key, value in row.items() if key != 'missing'},
                           'class_name': CLASSES.get(class_id, 'CIP object'),
                           'attributes': [{'id': number, 'status': 0x14,
                                           'name': NAMES.get(class_id, {}).get(number, 'Attribute ' + str(number))}
                                          for number in row['missing']]})
        return result
