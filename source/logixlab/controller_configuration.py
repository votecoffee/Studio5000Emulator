"""Read-only source configuration, distinct from security enforcement.

The v35 Controller attribute definition identifies attribute 13 as a BITS32
SecurityCode. L5X Security@Code is the legacy RSI Security Server setting;
it neither authenticates a peer nor grants permission to run an operation.
"""
from dataclasses import dataclass
import re
import struct
from .tag_catalog import complete_tag_source
from . import controller_schemas


PASS_THROUGH = {'Disabled': 0, 'Enabled': 1, 'EnabledWithAppend': 3}
MEMORY_PAD_FIELDS = ('IOMemoryPadPercentage','DataTablePadPercentage')
REDUNDANCY_FIELDS = {'Enabled','KeepTestEditsOnSwitchOver','Use',*MEMORY_PAD_FIELDS}


def memory_padding(root,controller):
    """Static spare-memory settings, never percentages of live free RAM.

    Explicit disabled redundancy selects this emulator's zero-reservation
    policy for omitted settings. Enabled/unknown redundancy has no defaults.
    Malformed explicit values never fall back to the omission policy.
    """
    unavailable=((None,None),(False,False))
    if (root is None or not complete_tag_source(root,controller) or controller.get('MajorRev')!='35'
            or root.get('SchemaRevision')!='1.0' or not re.fullmatch(r'35\.[0-9]{2}',root.get('SoftwareRevision',''))):
        return unavailable
    nodes=controller.findall('RedundancyInfo')
    if len(nodes)!=1:return unavailable
    node=nodes[0]
    if (node.attrib.keys()-REDUNDANCY_FIELDS or node.get('Use') not in (None,'Target')
            or node.get('Enabled') not in ('true','false') or len(node) or (node.text or '').strip()):
        return unavailable
    # Reject aliases and shadows even when the canonical setting is omitted.
    names=('redundancyinfo',*(name.casefold() for name in MEMORY_PAD_FIELDS))
    for item in controller.iter():
        local=item.tag.rsplit('}',1)[-1].casefold()
        if any(local.startswith(name) for name in names) and item is not node:return unavailable
        for key in item.attrib:
            if any(key.rsplit('}',1)[-1].casefold().startswith(name) for name in names):
                if item is not node or key not in MEMORY_PAD_FIELDS:return unavailable
    values=[];defaulted=[]
    for name in MEMORY_PAD_FIELDS:
        text=node.get(name)
        use_default=text is None and node.get('Enabled')=='false'
        value=(0 if use_default else int(text) if isinstance(text,str)
               and re.fullmatch(r'(?:0|[1-9][0-9]{0,2})',text) and int(text)<=100 else None)
        values.append(value);defaulted.append(use_default)
    return tuple(values),tuple(defaulted)


def change_detection_mask(root,controller):
    """Read the explicit unsigned 64-bit hex mask, independently of audit history."""
    if root is None or not complete_tag_source(root,controller):return None
    related=[node for node in controller if
             node.tag.rsplit('}',1)[-1].casefold().startswith('security')]
    nodes=controller.findall('Security')
    if len(nodes)!=1 or related!=nodes:return None
    node=nodes[0]
    if (node.attrib.keys()-{'Code','ChangesToDetect','Use'} or
            node.get('Use') not in (None,'Target') or len(node) or (node.text or '').strip()):return None
    text=node.get('ChangesToDetect')
    if not isinstance(text,str) or len(text)>22:return None
    # Support the observed L5X radix-16 form, either ungrouped or groups of
    # four hex digits. Missing/other representations never become zero.
    if not re.fullmatch(r'16#(?:[0-9A-Fa-f]{1,16}|[0-9A-Fa-f]{1,4}(?:_[0-9A-Fa-f]{4}){1,3})',text):return None
    return int(text[3:].replace('_',''),16)


@dataclass(frozen=True)
class ControllerConfiguration:
    security_code: int | None
    project_name: str
    project_description: str | None
    redundancy_configured: bool | None = None
    time_slice: int | None = 20
    share_unused_time_slice: int | None = 1
    time_slice_defaulted: bool = True
    share_unused_defaulted: bool = True
    empty_power_loss_handler: bool = False
    empty_fault_handler: bool = False
    pass_through_configuration: str | None = None
    match_project_to_controller: bool | None = None
    automatic_firmware_update_inhibit: int | None = None
    can_use_rpi_from_producer: bool | None = None
    report_minor_overflow: bool | None = None
    continue_test_edits: bool | None = None
    automatic_diagnostics_enabled: bool | None = None
    changes_to_detect: int | None = None
    io_memory_pad_percentage: int | None = None
    data_table_pad_percentage: int | None = None
    memory_pad_defaulted: tuple[bool,bool] = (False,False)

    @classmethod
    def from_controller(cls, controller, root=None):
        elements = controller.findall('Security')
        code = elements[0].get('Code', '') if len(elements) == 1 else ''
        value = int(code) if re.fullmatch(r'[0-9]{1,10}', code) else None
        descriptions = controller.findall('Description')
        description = '' if not descriptions else None
        if len(descriptions) == 1 and not len(descriptions[0]):
            description = descriptions[0].text or ''
        redundancy=controller.findall('RedundancyInfo')
        enabled=redundancy[0].get('Enabled') if len(redundancy)==1 else None
        slice_text=controller.get('TimeSlice')
        share_text=controller.get('ShareUnusedTimeSlice')
        time_slice=(20 if slice_text is None else int(slice_text)
                    if re.fullmatch(r'[0-9]{1,2}',slice_text) and 10<=int(slice_text)<=90 else None)
        share=(1 if share_text is None else {'0':0,'1':1}.get(share_text))
        complete=root is not None and complete_tag_source(root,controller)
        def source_setting(name):
            # A source flag is available only in a complete, unambiguous
            # controller export. Case, namespace and UId variants cannot
            # silently supply or override the canonical declaration.
            related=[key for key in controller.attrib
                     if key.rsplit('}',1)[-1].casefold().startswith(name.casefold())]
            return controller.get(name) if complete and related==[name] else None
        match_project={'true':True,'false':False}.get(source_setting('MatchProjectToController'))
        producer_rpi={'true':True,'false':False}.get(source_setting('CanUseRPIFromProducer'))
        report_overflow={'true':True,'false':False}.get(source_setting('ReportMinorOverflow'))
        diagnostics={'true':True,'false':False}.get(source_setting('AutoDiagsEnabled'))
        related_redundancy=[node for node in controller if
            node.tag.rsplit('}',1)[-1].casefold().startswith('redundancyinfo')]
        retain=None
        if (complete and len(redundancy)==1 and related_redundancy==redundancy):
            node=redundancy[0]
            if (not node.attrib.keys()-REDUNDANCY_FIELDS and
                    node.get('Use') in (None,'Target') and node.get('Enabled') in ('true','false') and
                    not len(node) and not (node.text or '').strip()):
                retain={'true':True,'false':False}.get(node.get('KeepTestEditsOnSwitchOver'))
        firmware_text=source_setting('InhibitAutomaticFirmwareUpdate')
        firmware=(int(firmware_text) if firmware_text is not None
                  and re.fullmatch(r'[0-9]{1,3}',firmware_text) and int(firmware_text)<=255 else None)
        pass_fields=[name for name in controller.attrib
                     if name.rsplit('}',1)[-1].casefold()=='passthroughconfiguration']
        pass_mode=controller.get('PassThroughConfiguration')
        if pass_fields!=['PassThroughConfiguration'] or pass_mode not in PASS_THROUGH:
            pass_mode=None
        def empty_handler(*names):
            # A missing name is meaningful only in a complete source. UId-only
            # or namespaced handler declarations must not be replaced by null.
            names=set(names)
            related={n.lower() for n in names}|{(n+'uid').lower() for n in names}
            for name,value in controller.attrib.items():
                local=name.rsplit('}',1)[-1]
                if local.lower() in related:
                    if name not in names or value:return False
            return complete
        padding,defaulted=memory_padding(root,controller)
        return cls(value if value is not None and value <= 0xFFFFFFFF else None,
                   controller.get('Name', 'Controller'), description,
                   {'true':True,'false':False}.get(enabled),time_slice,share,
                   slice_text is None,share_text is None,
                   empty_handler('PowerLossProgram','PowerUpHandlerProgram'),
                   empty_handler('MajorFaultProgram'),pass_mode,
                   match_project,firmware,producer_rpi,report_overflow,retain,diagnostics,
                   change_detection_mask(root,controller),*padding,defaulted)

    def attributes(self):
        values={13: struct.pack('<I', self.security_code)} if self.security_code is not None else {}
        # v35 Controller attributes 10, 15, 17, 23, 31 and 35 are BITS8 settings.
        # These are source configuration reads, not hardware behavior or
        # permission to match/download a project, update firmware or use I/O.
        for number,value in ((10,self.continue_test_edits),(15,self.match_project_to_controller),
                             (17,self.automatic_firmware_update_inhibit),
                             (23,self.can_use_rpi_from_producer),
                             (31,self.report_minor_overflow),(35,self.automatic_diagnostics_enabled)):
            if value is not None:values[number]=bytes((value,))
        if self.changes_to_detect is not None:values[28]=struct.pack('<Q',self.changes_to_detect)
        for number,value in ((11,self.io_memory_pad_percentage),(12,self.data_table_pad_percentage)):
            if value is not None:values[number]=struct.pack('<H',value)
        return values

    def compatibility_attributes(self):
        # No hardware run-inhibit input or project transfer is implemented.
        # The router overlays the native lease's inhibit and preparation state.
        values={**self.attributes(),7:b'\0\0',26:bytes(4)}
        if self.time_slice is not None:values[3]=struct.pack('<H',self.time_slice)
        if self.share_unused_time_slice is not None:values[16]=struct.pack('<H',self.share_unused_time_slice)
        # Anonymous model sessions do not own a multi-workstation edit slot.
        values[8]=bytes(2)
        # Source configuration only: the endpoint does not forward traffic to
        # other controllers. v35 offline round trips establish the 0/1/3 mask.
        if self.pass_through_configuration in PASS_THROUGH:
            values[25]=struct.pack('<I',PASS_THROUGH[self.pass_through_configuration])
        # A successful v35 reference upload establishes four-byte POINTER
        # values and the all-zero null. Configured handler references remain
        # unavailable; never copy a physical controller's nonzero reference.
        if self.empty_power_loss_handler:values[1]=bytes(4)
        if self.empty_fault_handler:values[6]=bytes(4)
        if self.redundancy_configured is not None:values[9]=bytes((self.redundancy_configured,))
        return values

    def extended_device_attributes(self):
        values = {}
        for number, text, maximum in ((1, self.project_name, 40), (2, self.project_description, 128)):
            if text is None:
                continue
            try:
                data = text.encode('ascii')
            except UnicodeEncodeError:
                continue
            if len(data) <= maximum:
                values[number] = struct.pack('<H', len(data)) + data
        return values

    def compatibility_get_all(self,attributes):
        """Observed 16-byte legacy profile, restricted to proven null handlers.

        The final two zero bytes are an observed opaque trailer. They confer
        no extra controller state or handler/address interpretation.
        """
        if not self.empty_power_loss_handler or not self.empty_fault_handler:return None
        if attributes.get(1)!=bytes(4) or attributes.get(6)!=bytes(4):return None
        fields=((3,2),(6,4),(1,4),(7,2),(8,2))
        if any(not isinstance(attributes.get(n),bytes) or len(attributes[n])!=size for n,size in fields):return None
        return b''.join(attributes[n] for n,_ in fields)+bytes(2)

    def description(self, *, native_compatibility=False):
        return {'object_revision': controller_schemas.object_revision(0x8E,native_compatibility=native_compatibility),
                'security_code_available': self.security_code is not None,
                'legacy_security_configured': self.security_code != 0 if self.security_code is not None else None,
                'source': 'Controller/Security@Code', 'security_enforcement': 'NOT IMPLEMENTED',
                'time_slice':self.time_slice,'share_unused_time_slice':self.share_unused_time_slice,
                'time_slice_defaulted':self.time_slice_defaulted,'share_unused_defaulted':self.share_unused_defaulted,
                'compatibility_defaults':{'time_slice':20,'share_unused_time_slice':1},
                'native_time_slice_scheduling':False,
                'pass_through_configuration':self.pass_through_configuration,
                'pass_through_configuration_code':PASS_THROUGH.get(self.pass_through_configuration),
                'pass_through_source':'Controller@PassThroughConfiguration',
                'pass_through_routing':False,
                'match_project_to_controller':self.match_project_to_controller,
                'automatic_firmware_update_inhibit':self.automatic_firmware_update_inhibit,
                'can_use_rpi_from_producer':self.can_use_rpi_from_producer,
                'report_minor_overflow':self.report_minor_overflow,
                'continue_test_edits':self.continue_test_edits,
                'automatic_diagnostics_enabled':self.automatic_diagnostics_enabled,
                'changes_to_detect_available':self.changes_to_detect is not None,
                'changes_to_detect_source':'Controller/Security@ChangesToDetect; explicit radix-16 mask',
                'changes_to_detect_bits':64,'change_detection_audit_value':False,
                'memory_padding':{'read_attributes':[11,12],
                    'io_memory_pad_percentage':self.io_memory_pad_percentage,
                    'data_table_pad_percentage':self.data_table_pad_percentage,
                    'defaulted':dict(zip(MEMORY_PAD_FIELDS,self.memory_pad_defaulted)),
                    'source':'Controller/RedundancyInfo; explicit percentage or disabled-redundancy omission policy',
                    'omission_policy':'Zero reservation only with explicit disabled redundancy in complete v35 source',
                    'live_free_memory_measurement':False,'native_reservation_enforcement':False},
                'change_detection_events_recorded':False,'state_detection_signatures':False,
                'source_read_attributes':sorted(self.attributes()),
                'source_flag_attributes':{'10':'Controller/RedundancyInfo@KeepTestEditsOnSwitchOver',
                                          '15':'Controller@MatchProjectToController',
                                          '17':'Controller@InhibitAutomaticFirmwareUpdate',
                                          '23':'Controller@CanUseRPIFromProducer',
                                          '31':'Controller@ReportMinorOverflow',
                                          '35':'Controller@AutoDiagsEnabled'},
                'redundant_switchover_execution':False,'automatic_diagnostics_delivery':False,
                'project_serial_matching_enforced':False,'firmware_update_services':False,
                'producer_rpi_negotiation':False,'source_settings_writable':False,
                'native_minor_overflow_fault_reporting':False,
                'empty_power_loss_handler':self.empty_power_loss_handler,'empty_fault_handler':self.empty_fault_handler,
                'handler_reference_encoding':'null_uint32_only','handler_reference_bytes':4,
                'configured_handler_references':False,
                'null_handler_get_all_profile':self.empty_power_loss_handler and self.empty_fault_handler and self.time_slice is not None,
                'handler_execution':False,'multi_workstation_edit_slot':False,
                'operator_registration': False, 'authority_services': False}


def metadata_class_attributes():
    """Metadata Definition class with UINT revision and no UDINT instances."""
    return {1: struct.pack('<H', 1), 2: struct.pack('<I', 0), 3: struct.pack('<I', 0)}


def metadata_description():
    return {'object_revision': 1, 'maximum_instance': 0, 'instance_count': 0,
            'instance_list': True, 'metadata_services': False}


def empty_metadata_query(payload):
    """Recognize bounded read queries for the model's empty definition set.

    The native connection query selects controller attribute 26; project upload
    requests all controller definitions. Unknown selectors/targets and mutation
    opcodes must not receive a successful empty response.
    """
    prefix=struct.pack('<II',0x101,0)
    target=(0xFFFF,0x8E,1,0,0,0,0)
    return payload in (prefix+struct.pack('<8H',1,*target),
                       prefix+struct.pack('<9H',9,*target,26))
