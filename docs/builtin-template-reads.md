# Source-checked TIMER and COUNTER reads

Version `26.1024.111516` can expose TIMER and COUNTER tags using the exact
Template definitions retained by a completed source-equivalent download.
The native compatibility catalog verifies the original ACD/L5X pair, Template
identities and every saved member layout before binding these structures.
An explicitly supplied, source-checked native Template snapshot can also bind
them. Ordinary model-mode catalogs keep their existing behavior.

## Values and layout

Both supported structures occupy 12 bytes: the hidden control word, then
signed DINT `PRE` and `ACC` at offsets 4 and 8. TIMER exposes `EN`, `TT`, `DN`;
COUNTER exposes `CU`, `CD`, `DN`, `OV`, `UN`. Their original declared bit
locations must match the interpreter's existing download encoder exactly.
Other predefined structures and alternative layouts remain unavailable.

Template definitions, handles, allocation sizes, family and reconstruction
bytes are preserved. The latter two fields remain opaque. Hidden control
storage has no independent application value; visible flags are packed from
the current interpreter state and unused bits are zero.

Symbol discovery, structured symbolic reads and linked Data Table reads share
one checked layout. Supported arrays retain distinct element values and
bounded fragment reads. Reads do not scan the PLC or change its mode, values
or audit state. Native endpoint tag writes remain disabled.

## Lifecycle and validation

The installed catalog disappears on reset, reload or restart with the
memory-only download. Changed source layouts, IDs or retained definitions
revoke reads. A saved snapshot does not enable native code execution.

Five focused software tests cover source definitions, live values and flags,
arrays/fragments, hidden-member denial, mode/snapshot boundaries and source
or definition changes. Native SDK upload acceptance is recorded separately in
the [Routine upload checkpoint](routine-upload.md).

On this version, native SDK upload of the two-routine conveyor demo succeeds
across 981 verified requests, including both complete Routine source streams.
Download/save/reopen/Go Online succeeds across 430. Independent CIP checks
match the saved source's original controls, type identities and all 24 value
bytes through both symbolic and Table reads. No SDK fault is reported, and
actual Offline cleanup passes. Uploaded ACD saving remains unverified.
