# Temporary native object graphs

Version `0.6.0-connectivity.73` models Symbol, Data Table, Program and Routine
Create records and Program-scoped coordination inside the
[decoded device batch](device-payload-inspection.md). Combined with
[Templates](template-staging.md) and [Diagnostics Messages](diagnostic-staging.md),
the tested batch's 904 records now have temporary models. No record executes
against the active project. Compiled definitions, device processing and project
commit remain unfinished, so service `0x06` still returns execution denial.

## Observed profile

This is a bounded model of an observed programming profile, not a general
controller programming specification. No vendor files or captured definitions
are bundled. Instance IDs are limited to `1..65534`; `65535` is reserved as an
unbound-reference marker in this profile. Attributes/symbolic qualifiers and
unexpected or deeper parents fail.

| Object/operation | Scope | Payload |
| --- | --- | --- |
| Symbol `0x6B`, Create `0x08` | Controller or one Program | Two attributes: 12 as UDINT reference; 9 as zero USINT |
| Data Table `0x6A`, Create `0x08` | Controller | Five attributes: 6 UINT, 2 UINT, 1 three UDINT dimensions, 8 UDINT reference, 9 zero UINT |
| Program `0x68`, Create `0x08` | Controller | Empty |
| Routine `0x6D`, Create `0x08` | One Program | One zero UINT, retained without assigning language/execution semantics |
| Coordination `0x74`, instance 1, acquire `0x4B` | One Program | One byte equal to 1 |
| Coordination `0x74`, instance 1, release `0x4C` | One Program | Empty |

Attribute lists permit any order but require each known attribute exactly once
with its exact width. Missing/duplicate/unknown attributes and trailing bytes
fail. Unknown services and unrelated classes are not dispatched and remain
outside the modeled-record total.

## References, scopes and bounds

Controller Symbols and Program-scoped Symbols have separate namespaces.
Programs must be created before their children. Scoped Symbol/Routine creation
requires a matching temporary acquire; duplicate acquires, unmatched releases
and an unclosed acquire at the end of the batch fail. This transcript never
operates the live programming lease.

Controller Symbol-to-Table links can be forward references within the atomic
batch, but must resolve reciprocally. A Data Table with flag value `0x6A`
requires a controller Symbol whose reference points back to that Table. The
observed flag-4 form instead requires the unbound marker. Other data-use flags
or nonzero extended flags fail. Program-scoped Symbols currently support only
the unbound marker. These checks provide no native online addresses.

Table type words use the documented structure flag, Template ID and array-rank
bits from Rockwell's [Logix 5000 Data Access manual](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm020_-en-p.pdf),
page 50. Structured types must refer to a staged Template. Atomic types support
BOOL, SINT, INT, DINT, LINT, USINT, UINT, UDINT, ULINT and REAL. System-type words
are rejected. Array rank must match positive leading dimensions and zero unused
dimensions, with at most 65,536 elements.

Limits are 1,024 Symbols, 1,024 Tables, 64 Programs and 512 Routines per batch.
Logical storage accounting uses atomic wire widths or the referenced Template's
declared structure size and is capped at 1 MiB, per Table and in total. It does
not allocate native memory or establish physical/firmware layouts. Object names,
routine bodies, instructions, compiled Template members and active tag values
are not supplied by this model.

## Atomicity, privacy and cleanup

The runtime builds all three model sets locally and publishes them together
only after validation. An object-reference or coordination error leaves all
sets empty, including otherwise completed Templates and Diagnostics Messages.
Structural inspection can still report `decoded`; `object_staging` reports
`invalid` with a fixed reason, and service `0x06` returns `0x03`. Errors are
cached until assembly cleanup. A successfully modeled batch still returns
`0x0F` with `device_batch_execution_unimplemented`.

The `object_staging` summary exposes counts, logical storage accounting, limits
and a reference-validation flag. It omits IDs, references, type words, names,
payloads and definitions. Completed descriptors are immutable.
`definitions_exposed`, `active_catalog_replaced` and `commit` remain false;
inspection still reports zero executed records. Per-type summaries retain their
earlier count meanings; the new object event reports the total across all models.

Assembly expiry and every transport/lease cleanup path clear all sets.
SDK probe admission and cleanup require an advertised object stage to be idle
and empty, with its reference-validation flag reset and installation disabled.

## Validation and remaining work

The normal-source SDK attempt models the remaining 41 records: 20 Symbols,
16 Tables, one Program, two Routines and two coordination operations. Two
Symbols and both Routines retain their Program parent. Reciprocal Table links
and structured-type references validate. Together with 727 Template records and
136 Diagnostics Message records, all 904 records have temporary models.

The SDK still receives execution denial and reports
`RxCsE_DOWNLOAD_OF_DEVICES_FAILED`, then returns Offline with unchanged source,
model and active catalogs and empty temporary stages. The 976-test suite passes
on Windows with two expected skips and Linux with one expected skip. Tests cover
malformed/reordered attributes, missing and mismatched references, scope collisions,
balanced coordination, types/ranks, exact capacity and excess, atomic rejection,
signed requests, owner/source guards, caching, privacy and lifecycle cleanup.

An isolated experiment with a substituted batch acknowledgement encountered a
further class `0x412` request (`0x4D`) with an empty payload. The substitution is absent from the app;
final preparation was denied in that experiment and its SDK attempt failed.
This identifies a later transfer boundary, not native download acceptance.

Next work requires compiled-definition validation, the full device-operation
contract, the further empty transport request, remaining transfer stages and atomic
active-model commit. Full native upload/download, online tag monitoring and
online edits remain unfinished; Studio GUI monitoring remains unverified.
