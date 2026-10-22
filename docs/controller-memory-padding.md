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
denial, reset and existing Controller/mode/edit behavior. Native upload and
connection acceptance are recorded separately from these software checks.
