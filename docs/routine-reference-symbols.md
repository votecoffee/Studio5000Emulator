# Scoped Routine reference Symbols

Version `26.1024.085425` adds Program-scoped `Routine:<name>` references to the
Symbol (`0x6B`) catalog. They supplement the existing
[root Program and Task references](reference-symbols.md). They describe current
interpreter objects and retain original Symbol IDs from the supplied ACD.

## Source and scope

The auxiliary-symbol reader already retains explicit Routine data names from
Program-scoped format-63 records. Promotion into discovery now requires matching
ACD/L5X hashes, native Project and Program bindings, original Routine identities,
the known ordinary RLL Type profile and complete readable source declarations.
Every eligible Routine must have its explicit reference. Missing legacy
bindings, incomplete inventories and unsupported kinds do not invent references.
Unknown targets, duplicate references and scoped tag-ID collisions reject the
candidate load before it replaces the active model.

Discovery preserves each numeric Program parent. The same child Symbol ID can
appear under different Programs without sharing an object or descriptor address.
Scoped reference IDs also remain distinct from root tag and reference IDs.
Safety, folder and unreadable Program profiles are not promoted by this feature.

## Descriptor and access behavior

| Attribute | Value |
| --- | --- |
| `1` | Original explicit `Routine:<name>` data name |
| `2` | `0x106D` object-reference type |
| `3` | Backed reference matching that Routine's Header Address (`0x6D`, attribute `8`) |
| `5` | Separate immutable scoped Symbol descriptor reference |
| `6`, `7`, `8` | Zero storage flags, size and dimensions |
| `9`, `10`, `11`, `14` | Standard class and null access/constant/signature metadata |
| `12` | DWORD `0xFFFF` no-Data-Table sentinel |

Instance lists, ordered attribute lists, individual reads and cursor-based
enumeration use the same descriptors. Runtime references resolve against the
current interpreter objects. Reset replaces the address registry; stale source
bindings or changed target kinds revoke discovery. Captured controller addresses
are never replayed, and these values expose no native process memory.

References create no tag values, Data Tables, storage buffers or Template
definitions. Tag-value reads and writes remain denied. The status API reports
bound counts under `native_routine_reference_symbols`.

## Evidence and limits

Offline analysis of a retained successful v35 upload finds 708 scoped Routine
reference Symbols across 20 Programs. Each is read before its matching Routine
bulk metadata and links to exactly one matching scoped Header Address. All use
the no-Data-Table sentinel. The 677 Standard-class descriptors have the null
storage/access profile implemented here; the other 31 report Safety class and
are outside this profile. Message MACs and association with an original ACD
are not independently established by that capture analysis.

Focused software checks cover duplicate child IDs across Programs and the root,
exact header linkage, scoped pagination, metadata widths, rejected value access,
incomplete or colliding source inventories, stale bindings and reset. Those
checks establish software behavior, not native upload completion, reconstructed
ACD validity or controller equivalence.
