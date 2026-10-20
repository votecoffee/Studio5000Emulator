"""One software coordination lease; it grants no project-transfer authority.

Ownership belongs to a live anonymous native context, never an IP address,
operator name or reusable session number. The endpoint serializes access.
"""
import math
import time


class LeaseError(ValueError):
    def __init__(self, status, reason):
        self.status=status;self.reason=reason
        super().__init__(reason)


class ProgrammingLease:
    def __init__(self, clock=time.monotonic):
        self.clock=clock
        self.clear()

    def clear(self):
        self.owner=None;self.generation=None;self.source_sha256=None

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

    def description(self, generation, source_sha256):
        owned=self.live(generation,source_sha256)
        return {'owned':owned,'exclusive':True,'controller_instance':1,'semaphore_instance':1,
                'remaining_ms':max(0,math.ceil((self.owner.deadline-self.clock())*1000)) if owned else 0,
                'owner_identity_exposed':False,'project_transfer':False,'online_edits':False,
                'controller_mode_changes':False,'tag_write_authority':False}
