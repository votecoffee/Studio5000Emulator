# Controller change-detection configuration

Source revision `.143` adds read-only Controller attribute 28 (CCUID
Configuration / ChangesToDetect). Native SDK acceptance has not been run for
this revision. The most recent native-validated build remains `.142`.
Source revision `.144` separately adds a [simulator-owned Audit Value](simulator-audit-value.md)
for selected modeled events; the source setting itself remains read-only.

The value comes from an explicit `Controller/Security@ChangesToDetect`
declaration in a complete Controller L5X export. The supported source profile
uses a radix-16 unsigned mask with up to 16 hexadecimal digits, ungrouped or
separated into groups of four. Both zero and the full 64-bit mask are retained;
unknown event bits are preserved without assigning meanings to them. The wire
value is eight bytes, little endian.

Missing, overflowed, malformed and unsupported representations remain
unavailable. The parser requires one canonical Security declaration, rejects
context, namespace, case, UId and shadow variants, and withholds the mask for
unknown attributes, nested elements or meaningful text. The legacy Security Code
does not grant authority to read or change configuration. Source reads do not
modify the original XML. Existing write restrictions remain in place.

Rockwell describes ChangesToDetect as a 64-bit configuration mask, separate
from the live Audit Value that changes when monitored events occur.
See [Change Detection Mask Low](https://www.rockwellautomation.com/en-ie/docs/diagnostics-counter-monitor/1-08/ftdcm-ditamap/diagnostics-counters/ftlx-dc/logix-data-provider-dc/changelog-node/change-detection-mask-low.html)
and [Change Detection High](https://www.rockwellautomation.com/en-ie/docs/diagnostics-counter-monitor/1-08/ftdcm-ditamap/diagnostics-counters/ftlx-dc/logix-data-provider-dc/changelog-node/change-detection-high.html).
The installed v35 Controller schema identifies the eight-byte configuration
field. Reading the configuration does not generate an Audit Value, record
change-detection events or calculate State Detection signatures.

## Diagnostics and remaining fields

Controller attribute-gap reports now name the retention, diagnostic, memory,
CCUID and signature fields. Reports retain their original IDs and unsupported
statuses, preserve unknown IDs and remain value-free. A named gap is still an
unsupported response; its name does not establish the cause of a client failure.

With a supported source mask, source revision `.143` can supply field 28. Controller
fields 11/12/27/33/34 remain unavailable in that revision. This is a model result, not a new native
upload result. Task fields 22/23, nonempty Routine source retrieval, full native
transfer and the complete edit lifecycle retain their existing limitations.

## Verification

Thirty pure unit and in-memory stub checks pass. They cover mask boundaries,
reserved-bit retention, strict parsing, complete source context, XML preservation,
single and ordered mixed reads, duplicate fields, write rejection, named gaps,
collection framing and existing Controller metadata behavior. The checks prohibit
process, worker and network starts and record zero resource-start attempts.

No native SDK test, application restart or executable rebuild accompanies this
source revision. `.142` remains the last build with demonstrated native SDK
Go Online/Go Offline and supported Program-mode import/reconnect acceptance.
