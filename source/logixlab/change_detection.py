"""Source-bound simulator audit epoch, separate from native project signatures.

Each installed execution model starts a random 64-bit epoch. Selected modeled
events advance it without reusing a value within that epoch. The sequence is a
simulator contract, not a reconstruction of Rockwell's value generator.
Callers serialize access with the application lock.
"""
import re
import secrets
import struct

UINT64_MAX=(1<<64)-1
EVENT_MASKS={'remote_mode':1<<13,'routine_transaction':(1<<2)|(1<<32)}


class ChangeDetection:
    def __init__(self,source_sha256,mask):
        if not isinstance(source_sha256,str) or not re.fullmatch(r'[0-9a-f]{64}',source_sha256):
            raise ValueError('Change detection requires an original source digest')
        if mask is not None and (type(mask) is not int or not 0<=mask<=UINT64_MAX):
            raise ValueError('Change detection mask must be an explicit unsigned 64-bit value')
        self._source_sha256=source_sha256
        self._mask=mask
        self._value=secrets.randbits(64) if mask is not None else None
        self._updates=0
        self._invalidated=False

    def attributes(self,source_sha256):
        if source_sha256!=self._source_sha256 or self._value is None or self._invalidated:return {}
        return {27:struct.pack('<Q',self._value)}

    def record(self,event):
        """One committed event updates at most once, even for overlapping bits."""
        if not isinstance(event,str) or event not in EVENT_MASKS:raise ValueError('Unsupported simulator change event')
        if self._value is None or self._invalidated or not self._mask&EVENT_MASKS[event]:return False
        if self._updates==UINT64_MAX:
            self.invalidate()
            return False
        self._value=(self._value+1)&UINT64_MAX
        self._updates+=1
        return True

    def invalidate(self):
        # Interpreter errors have no established native major/minor mapping.
        # Withhold the audit value rather than classifying them as event 15.
        self._invalidated=True

    def prepare_download_epoch(self,previous):
        """A download starts a distinct epoch independently of monitored bits."""
        if (not isinstance(previous,ChangeDetection) or self is previous or self._updates
                or self._invalidated or self._source_sha256!=previous._source_sha256 or self._mask!=previous._mask):
            raise ValueError('Download audit epoch requires a fresh source-equivalent model')
        if self._value is not None and self._value==previous._value:
            self._value=(self._value+1)&UINT64_MAX

    def description(self):
        return dict(audit_value_available=self._value is not None and not self._invalidated,
            origin='simulator_execution_model_epoch',persistence='memory_only',updates=self._updates,
            mask_available=self._mask is not None,invalidated=self._invalidated,
            supported_event_bits={name:[bit for bit in range(64) if mask&(1<<bit)] for name,mask in EVENT_MASKS.items()},
            unclassified_fault_withholds_value=True,native_value_generator=False,
            archived_audit_value_imported=False,controller_log=False,state_detection_signatures=False)
