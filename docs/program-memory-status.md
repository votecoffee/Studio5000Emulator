# Standard memory and normal Program status

Version `.121` adds read-only metadata for the supported Standard execution model:

| Object / attribute | Value | Conditions |
| --- | --- | --- |
| Program `26`, Data Use | Two-byte `0`, Standard user memory | Complete canonical ordinary v35 Program source |
| Task `20`, Data Use | Two-byte `0`, Standard user memory | Canonical Standard Continuous/Periodic Task source |
| Program `1`, Status | Two-byte normal `0` | Supported scheduled whole-project RLL, matching original native Task owner, idle untested edits and known-clean fault history |

Single and list reads share the same values. Native setters remain denied.
Memory classification does not change with Run/Program mode or a simulator
fault. Unknown, opaque, Safety and unsupported kind declarations do not become
Standard memory. Ordinary native exports can omit `Class`; they must still
pass the complete canonical Standard-source checks. The emulator does not add
Safety execution or Safety memory by recognizing its separate wire code.

Normal status is narrower than memory classification. Missing or foreign Task
bindings, unscheduled/disabled/blocked execution, a routine harness, unknown
fault history or active native edit preparation withhold this status read.
After an unclassified emulator fault, normal status stays unavailable until
engine reset, even if a subsequent scan succeeds. No fault or unscheduled
status bits are invented. Program status does not replace the controller's
separate Run/Program state or timing measurements.

## Reference checks

The saved successful upload contains two Tasks with memory codes `0` and `6`.
All 19 scheduled Programs match their owning Task's memory code. The one
unscheduled Program uses memory code `0` and status `0x0110`; the scheduled
Programs use status `0`. This separates the unscheduled status observation
from the Safety-memory distinction. The individual bits in `0x0110` remain
uninterpreted and are not served by the model.

The installed v35 Program and Task attribute definitions distinguish Standard
and Safety Data Use fields. Source class declarations follow Rockwell's
[Import/Export reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm014_-en-p.pdf).
These bounded reads describe the custom model; they do not establish physical
controller equivalence or complete native programming support.

## Task collection diagnostics

The shared [collection decoder](native-transfer-diagnostics.md#collection-attribute-lists)
also frames Task `0x70` lists at nonzero instances in offline captures and saved
native transfer reports. It handles the established fixed field widths,
ordered Program lists up to 1028 entries, counted trigger bytes with a 4096-byte
decoder limit, and DWORD-counted names up to 40 bytes. Trigger limits here bound
the analysis tool and do not claim a device's maximum trigger size.

Partial replies, unavailable fields, duplicates, suffixes and malformed layouts
remain distinct. Unknown successful fields stop decoding rather than being
skipped. Default reports contain lengths/hashes and no raw names or values;
payload inspection remains an explicit private-analysis option. Framing does
not infer memory semantics, authenticate a recorded exchange or prove upload
acceptance.
