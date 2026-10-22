# Controller spare-memory configuration

Version `.159` adds read-only Controller attributes 11 and 12. The installed v35
schema calls them Percent Free IO Memory and Percent Free Table Memory. They
describe configured spare-memory percentages, separately from runtime free RAM.

| Attribute | L5X setting on `Controller/RedundancyInfo` | Encoding |
| --- | --- | --- |
| 11 | `IOMemoryPadPercentage` | UINT16 percentage |
| 12 | `DataTablePadPercentage` | UINT16 percentage |

Rockwell's [Import/Export reference, Controller attributes](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm014_-en-p.pdf)
defines both settings from 0 through 100 and places them on `RedundancyInfo`.
They configure spare I/O memory for redundancy and a data-table reservation.
The reference recommends a zero data-table reservation with redundancy disabled.
The [Controller object reference](https://www.rockwellautomation.com/en-mde/docs/studio-5000-logix-designer/38-02/contents-ditamap/instruction-set/input-output-instructions/access-the-controller-object.html)
also describes DataTablePadPercentage as a reservation percentage.

## Source and omission policy

Complete v35 Controller source with one canonical `RedundancyInfo` declaration
is required. Explicit bounded decimal percentages are preserved independently.
If the declaration explicitly disables redundancy and omits either percentage,
the emulator selects zero reservation for that omitted setting. This is an
explicit emulator policy, not recovery of an omitted saved property. The API's
`controller_configuration.memory_padding` reports each value and whether that
policy supplied it.

Enabled redundancy receives no missing-value default. Missing, duplicate,
context, opaque, nested, case, namespace and shadow declarations withhold the
settings. Invalid explicit percentages remain unavailable even with redundancy
disabled; they never fall back to zero. One malformed percentage does not hide
the other independent valid setting. The existing retention flag remains
readable when the two recognized percentage attributes are present.

These reads do not reserve host memory, enforce redundancy, report available
controller capacity, implement native allocation services or enable GSV/SSV.
Single, signed and ordered duplicate/mixed reads preserve source and execution
state. Writes retain the existing denial. State Detection signatures 33 and 34
remain unavailable; no placeholder signatures are added.

## Validation

All 181 affected checks pass, including strict parsing, omission versus invalid
values, independent fields, supported source context, signed framing, write
denial, reset and existing Controller/mode/edit behavior. Eight live signed
requests verify MACs, both initialized zero-reservation settings, duplicates,
single/mixed reads, signature gaps and write denial without changing source,
model or audit state.

The unmodified public runtime's empty-routine upload verifies 361 requests.
Both new fields return their two-byte zero reservations successfully, while
State Detection signatures 33/34 retain unavailable statuses in the final
Controller list. Task collection still accepts all 22 fields. The SDK diagnostic
remains `RxCsE_ASA_ATTRIBUTE_LIST_ERROR`; passing these fields does not complete
upload. The raw transfer interval is complete with no reported collection
framing errors. The bounded earlier collection summary truncates, while the
final-request view retains the full Controller and Task lists.

SDK Go Online/Offline verifies 74 requests. The supported Program-mode routine
import/reconnect verifies 192, preserves the settings across engine replacement,
and produces exactly one logic revision and audit update. The original demo is
restored afterward to stopped Program mode with zero scans and zero audit state.
This does not establish the complete Test/Untest/Assemble lifecycle.

The normal demo upload retains its Program/Routine failure after 349 verified
requests. Download verifies 175 and prepares 904 temporary records, including
242 Templates and 16 Tables, before stopping at the result query. No active
image is committed. All five native cases confirm actual Offline/cleanup,
preserved original files and no reported SDK fault. The connection and transfer cases
preserve the active model; the routine-import case changes its supported logic
intentionally before restoration. Webpage, executable and appliance versions
match `.159`. Full native upload/download and a valid saved uploaded ACD remain
unfinished. No uploaded-file save was attempted.
