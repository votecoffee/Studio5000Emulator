"""Bounded private trace recording while one native probe process runs.

The endpoint ring stays bounded. Cursor gaps, replaced endpoints, diagnostic
errors and storage limits are explicit; recording never retries a native call.
"""
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import time

MAX_EVENTS=32768
MAX_BYTES=64*1024*1024
MAX_LINE=1024*1024
FORMAT='logixlab-trace-journal-v1'


class TraceJournal:
    def __init__(self,path,read_page,instance,source):
        self.path=Path(path);self.read_page=read_page;self.instance=instance;self.source=source
        self.cursor=None;self.trace_id=None;self.events=0;self.bytes=0;self.error=None;self.caught_up=False
        self.stream=gzip.open(self.path,'xb')
        try:
            page=self.read_page({});self._identity(page)
            self.trace_id=page['trace_id'];self.cursor=page['next_event']
            if (page['events'] or type(self.cursor) is not int or self.cursor<0
                    or self.cursor!=page['last_event'] or page['missing_events'] or page['has_more']):
                raise ValueError('Invalid initial trace cursor')
            self._write(dict(format=FORMAT,instance_id=instance,source_l5x_sha256=source,
                             trace_id=self.trace_id,after_event=self.cursor))
        except Exception:
            self.stream.close();raise

    def _identity(self,page):
        if (page.get('instance_id')!=self.instance or page.get('source_l5x_sha256')!=self.source
                or not isinstance(page.get('trace_id'),str) or len(page['trace_id'])!=32
                or any(c not in '0123456789abcdef' for c in page['trace_id'])
                or self.trace_id is not None and page['trace_id']!=self.trace_id):
            raise ValueError('Trace endpoint identity changed')

    def _write(self,row):
        data=(json.dumps(row,separators=(',',':'))+'\n').encode('utf8')
        if len(data)>MAX_LINE or self.bytes+len(data)>MAX_BYTES:raise ValueError('Trace journal storage limit')
        self.stream.write(data);self.bytes+=len(data)

    def drain(self):
        if self.error:return
        try:
            for _ in range(8):
                page=self.read_page(dict(trace_id=self.trace_id,after_event=self.cursor,limit=256));self._identity(page)
                events=page['events'];last=page['last_event'];next_event=page['next_event']
                if (page['after_event']!=self.cursor or type(last) is not int or last<self.cursor
                        or type(next_event) is not int or type(page['missing_events']) is not int
                        or page['missing_events']!=0 or not isinstance(events,list) or len(events)>256
                        or type(page['has_more']) is not bool):raise ValueError('Trace cursor gap or invalid page')
                for row in events:
                    if (not isinstance(row,dict) or type(row.get('event_id')) is not int
                            or row['event_id']!=self.cursor+1 or self.events>=MAX_EVENTS):
                        raise ValueError('Trace event sequence or count limit')
                    self._write(dict(event=row));self.cursor=row['event_id'];self.events+=1
                if next_event!=self.cursor or self.cursor>last or page['has_more']!=(self.cursor<last):
                    raise ValueError('Trace page extent mismatch')
                self.caught_up=not page['has_more']
                if self.caught_up:break
        except Exception:
            self.error='trace_collection_failed';self.caught_up=False

    def close(self):
        self.drain()
        complete=self.error is None and self.caught_up
        footer=dict(complete=complete,events=self.events,last_event=self.cursor,error=self.error)
        try:self._write(dict(result=footer))
        except (OSError,ValueError):complete=False;footer['complete']=False;footer['error']='trace_storage_failed'
        finally:self.stream.close()
        return dict(**footer,path=self.path.name,sha256=hashlib.sha256(self.path.read_bytes()).hexdigest(),
                    expanded_bytes=self.bytes)


def run_recorded(command,*,journal,stdout,timeout,background):
    """Keep diagnostic polling outside the native SDK process and its threads."""
    deadline=time.monotonic()+timeout
    with subprocess.Popen(command,stdout=stdout,stderr=subprocess.STDOUT,**background) as process:
        while True:
            remaining=deadline-time.monotonic()
            if remaining<=0:
                process.kill();process.wait()
                raise subprocess.TimeoutExpired(command,timeout)
            try:
                code=process.wait(timeout=min(.25,remaining))
                return subprocess.CompletedProcess(command,code)
            except subprocess.TimeoutExpired:
                journal.drain()


def read_interval(path,before,after):
    """Recover exactly the SDK checkpoint interval, never a retained suffix."""
    start=before.get('trace_capture',{});end=after.get('trace_capture',{})
    first=start.get('last_event');last=end.get('last_event');trace=start.get('trace_id')
    if (type(first) is not int or type(last) is not int or not 0<=first<=last
            or not trace or end.get('trace_id')!=trace):raise ValueError('Trace checkpoint identities unavailable')
    count=total=0;cursor=None;header=None;result=None;events=[]
    path=Path(path)
    if not 1<=path.stat().st_size<=MAX_BYTES:raise ValueError('Trace journal file limit')
    with gzip.open(path,'rb') as stream:
        while True:
            data=stream.readline(MAX_LINE+1)
            if not data:break
            total+=len(data)
            if len(data)>MAX_LINE or total>MAX_BYTES:raise ValueError('Trace journal expanded limit')
            row=json.loads(data)
            if not isinstance(row,dict) or result is not None:raise ValueError('Invalid trace journal row')
            if header is None:
                if row.get('format')!=FORMAT or row.get('trace_id')!=trace:raise ValueError('Trace journal identity mismatch')
                cursor=row.get('after_event')
                if type(cursor) is not int or not 0<=cursor<=first:raise ValueError('Trace journal starts after the checkpoint')
                header=row
            elif set(row)=={'event'}:
                event=row['event'];count+=1
                if (not isinstance(event,dict) or type(event.get('event_id')) is not int
                        or event['event_id']!=cursor+1 or count>MAX_EVENTS):raise ValueError('Trace journal event gap or limit')
                cursor=event['event_id']
                if first<cursor<=last:events.append(event)
            elif set(row)=={'result'}:result=row['result']
            else:raise ValueError('Invalid trace journal structure')
    if (not isinstance(result,dict) or result.get('complete') is not True or result.get('error') is not None
            or result.get('last_event')!=cursor or result.get('events')!=count or cursor<last
            or len(events)!=last-first):raise ValueError('Trace journal is incomplete')
    return events
