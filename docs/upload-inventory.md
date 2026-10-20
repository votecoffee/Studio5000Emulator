# Upload inventory and remaining contracts

Native upload is still incomplete. A successful object read establishes only
that object's response; it does not establish a complete Studio 5000 upload.

The retained SDK upload traces reach scalar Data Table and Symbol reads, then
device and network inventory. The Time Sync attribute list returns known
software clock fields alongside unavailable PTP fields. The SDK subsequently
requests Controller attributes before reporting a controller-collection
failure. The last incomplete object in a trace is therefore not sufficient
evidence to assign the failure to that object.

| Object | Supported behavior | Remaining contract |
| --- | --- | --- |
| Data Table and Symbol | Bounded model descriptors and scalar values correlated to imported tag identifiers | Native compiled addresses, layouts and complete type upload |
| Network inventory | Actual selected interface information and supported host counters | Device-specific fields without a host or source counterpart |
| Time Sync | Imported PTP configuration, unsynchronized status, empty PTP port set, software descriptions and current host UTC | PTP master, parent, identity and synchronization measurements |
| Controller | Supported source settings, run mode and programming lease state | Native handler-reference encoding and complete upload collection |

Isolated prior diagnostic profiles supplied hypothetical PTP descriptions or
made the clock object unavailable; both still failed controller collection.
Those hypotheses are excluded from application behavior. New upload changes
should be tested separately against the same source before combining them
with download or online-edit changes.

A current-source handler matrix varied only the two absent Controller handler
references. Two-byte and twelve-byte null-reference hypotheses changed the
final attribute list from partial failure to success at the CIP response
level. All three cases still failed the SDK upload after the same two terminal
Controller requests, with no further native request after that list. These
private hypotheses establish neither the correct `POINTER` representation
nor a unique cause for the collection failure; they are excluded from the app.

## Software system time and offset

Time Sync instance 1, attribute 28 exposes the relationship between the
emulator's system time and local software clock. Both use the same host UTC
clock, so their offset is zero. The v35 `cip067r03v01.adf` and
`cip067r04v01.adf` layouts put the signed 64-bit system offset first, then the
signed 64-bit system time in microseconds. The values are little endian.

Attributes 3, 4 and 28 share one host time snapshot in an attribute-list read,
including duplicate attributes. Attribute 3 and attribute 28 use microseconds;
attribute 4 uses nanoseconds. A failed or unrepresentable host clock sample
returns attribute unavailable rather than a fabricated zero timestamp. Each
unit retains its own range check, so nanosecond overflow does not hide a
representable microsecond value.

The zero system-to-local offset is not an offset-to-master measurement. The
emulator remains unsynchronized, exposes no PTP ports, does not set or
discipline the host clock, and makes no accuracy claim. Host clock adjustments
remain visible; deterministic PLC scan time remains independent.

Protocol tests cover field order, units, duplicate-list coherence, clock
failure, integer limits, denied setters and unchanged simulation values.
Native SDK upload and Studio GUI acceptance require separate checks.
