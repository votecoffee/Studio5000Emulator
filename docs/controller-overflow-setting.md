# Controller overflow-reporting setting

Version `.83` reads the explicit `Controller@ReportMinorOverflow` flag from a
complete, unambiguous L5X controller export. Controller object `0x8E/1`
attribute `31` returns one byte: `0` for `false`, `1` for `true`. Both ordinary
and anonymous native read paths use that same imported value.

The installed v35 Controller attribute descriptions r12 through r15 identify
attribute 31 as the BITS8 Minor Fault Overflow setting. Rockwell's
[Controller Properties Advanced tab documentation](https://www.rockwellautomation.com/en-au/docs/studio-5000-logix-designer/37-02/contents-ditamap/studio-5000-logix-designer/controller-properties/editing-controller-properties/advanced-tab.html)
describes Report Overflow Faults as a project setting retained in ACD, L5K and
L5X and transferred to the controller. The source counterpart is
`ReportMinorOverflow`; this read does not report a fault queue's overflow state.

Missing, malformed, context-only, case-variant, namespaced or conflicting source
declarations remain unavailable. There is no default value or inferred runtime
status. Attribute-list reads preserve order, duplicates and individual missing
field statuses. Unknown fields and writes retain their existing rejection.

This is a source-configuration read. Native arithmetic fault logging, math
status-flag parity, fault handlers and editing that setting online remain
unfinished. Reading the setting grants no programming or edit authority.

An isolated native SDK import reads attribute 31 successfully and advances from
the prior attribute-list error to a denied, empty-payload Controller service
`0x55`. The import reports `RxCsE_ASA_NO_PERMISSION` across 99 verified signed
requests and confirms native Offline plus endpoint cleanup. The meaning and
response contract of that Controller service remain unresolved; Symbol class
`0x6B` service `0x55` enumeration does not establish the contract for class
`0x8E`. No edit is accepted or committed.
