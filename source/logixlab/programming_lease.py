"""One software coordination lease; it grants no project-transfer authority.

Ownership belongs to a live anonymous native context, never an IP address,
operator name or reusable session number. The endpoint serializes access.
"""
import math
import time
from .library_staging import LibraryStaging
from .metadata_staging import MetadataStaging


class LeaseError(ValueError):
    def __init__(self, status, reason):
        self.status=status;self.reason=reason
        super().__init__(reason)


class ProgrammingLease:
    def __init__(self, clock=time.monotonic):
        self.clock=clock
        self.libraries=LibraryStaging()
        self.metadata=MetadataStaging()
        self.clear()

    def clear(self):
        self.owner=None;self.generation=None;self.source_sha256=None
        self.run_inhibit=0;self.prepared=False
        self.clear_staging()

    def clear_staging(self):
        self.libraries.clear();self.metadata.clear()

    def discard(self, native):
        if self.owner is native:self.clear()

    def live(self, generation, source_sha256):
        owner=self.owner
        if owner is not None and (self.generation!=generation or self.source_sha256!=source_sha256
                or owner.stage!='bound' or owner.key is None or self.clock()>=owner.deadline):
            self.clear()
        return self.owner is not None

    def acquire(self, native, generation, source_sha256):
        if native.stage!='bound' or native.key is None or self.clock()>=native.deadline:
            raise LeaseError(0x0F,'unbound_context')
        if self.live(generation,source_sha256) and self.owner is not native:
            raise LeaseError(0x0C,'programming_lease_conflict')
        self.owner=native;self.generation=generation;self.source_sha256=source_sha256

    def release(self, native, generation, source_sha256):
        if native.stage!='bound' or native.key is None or self.clock()>=native.deadline:
            raise LeaseError(0x0F,'unbound_context')
        if self.live(generation,source_sha256) and self.owner is not native:
            raise LeaseError(0x0F,'programming_lease_owner_required')
        self.clear()

    def set_run_inhibit(self, native, generation, source_sha256, value):
        if type(value) is not int or value not in (0,1):
            raise LeaseError(3,'invalid_request')
        self.require_owner(native,generation,source_sha256)
        self.run_inhibit=value
        if not value:self.prepared=False;self.clear_staging()

    def require_owner(self, native, generation, source_sha256):
        if not self.live(generation,source_sha256) or self.owner is not native:
            raise LeaseError(0x0F,'programming_lease_owner_required')

    def inhibit(self, generation, source_sha256):
        return self.run_inhibit if self.live(generation,source_sha256) else 0

    def begin_preparation(self, native, generation, source_sha256):
        self.require_owner(native,generation,source_sha256)
        if self.run_inhibit!=1:
            raise LeaseError(0x0C,'run_mode_inhibit_required')
        self.prepared=True

    def end_preparation(self, native, generation, source_sha256):
        self.require_owner(native,generation,source_sha256)
        self.prepared=False
        self.clear_staging()

    def require_prepared(self, native, generation, source_sha256):
        self.require_owner(native,generation,source_sha256)
        if not self.prepared:
            raise LeaseError(0x0C,'programming_preparation_required')

    def preparation_status(self, generation, source_sha256):
        # The tested v35 SDK advances from preparation when attribute 26 is 2.
        # This software state grants no library-data transfer or commit.
        return 2 if self.live(generation,source_sha256) and self.prepared else 0

    def description(self, generation, source_sha256):
        owned=self.live(generation,source_sha256)
        return {'owned':owned,'exclusive':True,'controller_instance':1,'semaphore_instance':1,
                'run_mode_inhibit':self.run_inhibit if owned else 0,'scan_inhibited':owned and bool(self.run_inhibit),
                'preparation_state':'ready' if owned and self.prepared else 'idle',
                'preparation_status':2 if owned and self.prepared else 0,
                'library_staging':self.libraries.description(),
                'metadata_staging':self.metadata.description(),
                'remaining_ms':max(0,math.ceil((self.owner.deadline-self.clock())*1000)) if owned else 0,
                'owner_identity_exposed':False,'project_transfer':False,'online_edits':False,
                'controller_mode_changes':False,'tag_write_authority':False}
