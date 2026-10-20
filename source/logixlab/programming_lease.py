"""One software coordination lease; it grants no project-transfer authority.

Ownership belongs to a live anonymous native context, never an IP address,
operator name or reusable session number. The endpoint serializes access.
"""
import math
import time
from .library_staging import LibraryStaging
from .metadata_staging import MetadataStaging
from .resilient_transport import ResilientTransport
from .edit_transfer import EditTransfer

MAX_PROGRAM_RESERVATIONS=128

class LeaseError(ValueError):
    def __init__(self, status, reason):
        self.status=status;self.reason=reason
        super().__init__(reason)


class ProgrammingLease:
    def __init__(self, clock=time.monotonic):
        self.clock=clock
        self.libraries=LibraryStaging()
        self.metadata=MetadataStaging()
        self.transport=ResilientTransport(clock)
        self.edit_transfer=EditTransfer(clock)
        self.clear()

    def clear(self):
        self.owner=None;self.generation=None;self.source_sha256=None
        self.selector=None
        self.run_inhibit=0;self.prepared=False
        self.clear_staging()

    def clear_staging(self):
        self.libraries.clear();self.metadata.clear();self.transport.clear()
        self.program_reservations=set()
        self.edit_phase_open=False;self.program_stack_preparations={}
        self.edit_transfer.clear()

    def discard(self, native):
        if self.owner is native:self.clear()

    def live(self, generation, source_sha256):
        owner=self.owner
        if owner is not None and (self.generation!=generation or self.source_sha256!=source_sha256
                or owner.stage!='bound' or owner.key is None or self.clock()>=owner.deadline):
            self.clear()
        return self.owner is not None

    def acquire(self, native, generation, source_sha256, *, selector=0):
        # Observed selector 0 coordinates programming; selector 1 reserves an
        # online import. Neither reservation installs or accepts controller edits.
        if type(selector) is not int or selector not in (0,1):
            raise LeaseError(3,'invalid_semaphore_selector')
        if native.stage!='bound' or native.key is None or self.clock()>=native.deadline:
            raise LeaseError(0x0F,'unbound_context')
        if self.live(generation,source_sha256) and self.owner is not native:
            raise LeaseError(0x0C,'programming_lease_conflict')
        if self.owner is native and self.selector!=selector:
            raise LeaseError(0x0C,'programming_lease_purpose_conflict')
        self.owner=native;self.generation=generation;self.source_sha256=source_sha256
        self.selector=selector

    def release(self, native, generation, source_sha256):
        if native.stage!='bound' or native.key is None or self.clock()>=native.deadline:
            raise LeaseError(0x0F,'unbound_context')
        if self.live(generation,source_sha256) and self.owner is not native:
            raise LeaseError(0x0F,'programming_lease_owner_required')
        self.clear()

    def set_run_inhibit(self, native, generation, source_sha256, value):
        if type(value) is not int or value not in (0,1):
            raise LeaseError(3,'invalid_request')
        self.require_programming_owner(native,generation,source_sha256)
        self.run_inhibit=value
        if not value:self.prepared=False;self.clear_staging()

    def require_owner(self, native, generation, source_sha256):
        if not self.live(generation,source_sha256) or self.owner is not native:
            raise LeaseError(0x0F,'programming_lease_owner_required')

    def require_programming_owner(self, native, generation, source_sha256):
        self.require_owner(native,generation,source_sha256)
        if self.selector!=0:
            raise LeaseError(0x0F,'programming_lease_purpose_required')

    def require_edit_owner(self, native, generation, source_sha256):
        self.require_owner(native,generation,source_sha256)
        if self.selector!=1:
            raise LeaseError(0x0F,'edit_reservation_required')

    def reserve_program(self,native,generation,source_sha256,program):
        self.require_edit_owner(native,generation,source_sha256)
        if type(program) is not int or not 1<=program<=0xFFFFFFFF:
            raise LeaseError(3,'invalid_program_reservation')
        if program not in self.program_reservations and len(self.program_reservations)>=MAX_PROGRAM_RESERVATIONS:
            raise LeaseError(2,'program_reservation_limit')
        self.program_reservations.add(program)

    def release_program(self,native,generation,source_sha256,program):
        self.require_edit_owner(native,generation,source_sha256)
        if type(program) is not int or not 1<=program<=0xFFFFFFFF:
            raise LeaseError(3,'invalid_program_reservation')
        self.program_reservations.discard(program)
        self.program_stack_preparations.pop(program,None)
        if self.edit_transfer.target and self.edit_transfer.target[0]==program:self.edit_transfer.clear()

    def open_edit_preparation(self,native,generation,source_sha256):
        self.require_edit_owner(native,generation,source_sha256)
        self.edit_phase_open=True

    def close_edit_preparation(self,native,generation,source_sha256):
        self.require_edit_owner(native,generation,source_sha256)
        if self.program_reservations:raise LeaseError(0x0C,'release_program_reservations_first')
        self.program_stack_preparations.clear();self.edit_transfer.clear();self.edit_phase_open=False

    def prepare_zero_program_stack(self,native,generation,source_sha256,program,value):
        self.require_edit_owner(native,generation,source_sha256)
        if not self.edit_phase_open:raise LeaseError(0x0C,'edit_preparation_phase_required')
        if type(program) is not int or program not in self.program_reservations:
            raise LeaseError(0x0C,'program_reservation_required')
        if type(value) is not int or value!=0:raise LeaseError(0x0C,'nonzero_udi_stack_unimplemented')
        self.program_stack_preparations[program]=0

    def scan_inhibited(self,generation,source_sha256):
        return self.live(generation,source_sha256) and bool(self.run_inhibit or self.program_reservations or self.edit_phase_open)

    def inhibit(self, generation, source_sha256):
        return self.run_inhibit if self.live(generation,source_sha256) else 0

    def begin_preparation(self, native, generation, source_sha256):
        self.require_programming_owner(native,generation,source_sha256)
        if self.run_inhibit!=1:
            raise LeaseError(0x0C,'run_mode_inhibit_required')
        self.prepared=True

    def end_preparation(self, native, generation, source_sha256):
        self.require_programming_owner(native,generation,source_sha256)
        self.prepared=False
        self.clear_staging()

    def require_prepared(self, native, generation, source_sha256):
        self.require_programming_owner(native,generation,source_sha256)
        if not self.prepared:
            raise LeaseError(0x0C,'programming_preparation_required')

    def preparation_status(self, generation, source_sha256):
        # The tested v35 SDK advances from preparation when attribute 26 is 2.
        # This software state grants no library-data transfer or commit.
        return 2 if self.live(generation,source_sha256) and self.prepared else 0

    def description(self, generation, source_sha256):
        owned=self.live(generation,source_sha256)
        return {'owned':owned,'exclusive':True,'controller_instance':1,'semaphore_instance':1,
                'request_selector':self.selector if owned else None,
                'edit_preparation':{'status':'open' if owned and self.edit_phase_open else 'reserved' if owned and self.selector==1 else 'idle',
                    'reserved':owned and self.selector==1,'source_bound':owned and self.selector==1,
                    'changes_staged':0,'active_changes':False,'accepted':False,'testing':False,
                    'assembled':False,'commit':False,'program_reservations':len(self.program_reservations) if owned else 0,
                    'phase_open':owned and self.edit_phase_open,
                    'program_stack_preparations':len(self.program_stack_preparations) if owned else 0,
                    'stack_bytes_allocated':0,'active_stack_changed':False},
                'edit_transfer':self.edit_transfer.description(),
                'run_mode_inhibit':self.run_inhibit if owned else 0,'scan_inhibited':self.scan_inhibited(generation,source_sha256),
                'preparation_state':'ready' if owned and self.prepared else 'idle',
                'preparation_status':2 if owned and self.prepared else 0,
                'library_staging':self.libraries.description(),
                'metadata_staging':self.metadata.description(),
                'resilient_transport':self.transport.description(),
                'remaining_ms':max(0,math.ceil((self.owner.deadline-self.clock())*1000)) if owned else 0,
                'owner_identity_exposed':False,'project_transfer':False,'online_edits':False,
                'controller_mode_changes':False,'tag_write_authority':False}
