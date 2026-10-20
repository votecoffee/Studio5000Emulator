"""Bounded summaries of native requests rejected before ordinary dispatch.

Keep structural IDs only. Symbols, payloads, operator identities, context
tokens, Timeline UID proposals and session keys never enter this collector.
"""
from collections import OrderedDict
import time


MAX_REJECTIONS = 64


class NativeRejections:
    def __init__(self):
        self.rows = OrderedDict()

    def record(self, generation, service, path, status, reason):
        fields = (getattr(path,'class_id',None), getattr(path,'instance',None),
                  getattr(path,'attribute',None), getattr(path,'program_instance',None),
                  getattr(path,'io_map_instance',None),
                  bool(getattr(path,'symbols',())))
        key = (generation,service,*fields,status,reason)
        previous = self.rows.pop(key,None)
        self.rows[key] = {'generation':generation, 'service':service,
                         **dict(zip(('class_id','instance','attribute','program_instance','io_map_instance','symbolic'),fields)),
                         'status':status, 'reason':reason,
                         'count':previous['count']+1 if previous else 1, 'last_seen':time.time()}
        while len(self.rows) > MAX_REJECTIONS:
            self.rows.popitem(last=False)

    def snapshot(self, generation):
        return [dict(row) for row in reversed(self.rows.values()) if row['generation']==generation]
