# Empty Security Authority Binding discovery

Version `.141` adds read-only class `0x36A` (Security Authority Binding) discovery
when the original ACD explicitly contains an empty collection. Plain L5X absence
and the legacy `Security@Code` are not evidence for this catalog.

## Source evidence

The bounded Comps.Dat reader requires one active format-0, 74-byte collection
with the controller-scoped class path, the checked empty tail profile and no
active binding definitions. Missing, nonempty, duplicate, scoped, malformed and
unknown profiles are unavailable. Deleted records and bytes outside the active
database do not become definitions. Original pointer words are never used.

An immutable optional `native_security_bindings` manifest carries the original
ACD/L5X hashes and an explicit empty `bindings` list. Conversion retains the L5X
and a separate diagnostic when this supplemental reader cannot establish its
profile. The appliance forwards supported evidence to the shared application
loader. Loading requires matching original Project and all other supplied native
bindings; failed loads preserve the active engine. Plain imports clear old
evidence, while reset and supported Routine replacement retain the current
source binding.

## Wire and state

Get Instance List (`0x4B`) returns an empty success for numeric controller-scoped
cursors after checking the bound source. Class attribute 1 supplies the known
revision 1; instance fields, authority identifiers and URIs are not exposed.
Invalid scopes and payloads are rejected. Signed native write policy stays in
force. Endpoint state reports the source hashes, explicit empty evidence and
unsupported configuration/authentication capabilities.

The installed v35 class schema names this object and its GUID/URI fields. A
saved reference exchange supplies an empty list and revision 1. These establish
framing; the original project's checked empty record establishes this instance
collection. Neither source evidence nor a successful list authorizes controller
operations. FactoryTalk authorities secure project access as described in
[Rockwell's security configuration help](https://www.rockwellautomation.com/en-hu/docs/studio-5000-logix-designer/37-00/contents-ditamap/studio-5000-logix-designer/controller-security/configure-security-for-the-controller.html).
Authority administration, authentication, authorization and nonempty binding
emulation remain unsupported.

## Verification

Focused tests cover source record/container bounds, compression, the exact empty
profile, deleted/allocation records, immutable manifests, conversion/appliance
forwarding, atomic load failures, stale/foreign bindings, reset and clearing,
class revision, list cursors, invalid scopes, signed TCP reads and write denial.
Native upload acceptance and full native transfer remain separate checks.

All 182 affected tests pass without a full suite run. Three own ACDs contain
the checked empty collection. The native SDK upload comparison
uses the same empty-Program project and private clock/schema/repository/Task
stack assumptions as the preceding trial. It now reads revision 1, accepts
Security Authority Binding discovery, passes empty Data Logging discovery and
reaches a later Controller attribute list. That list requests 21 attributes;
fields 10, 11, 12, 27, 28, 33, 34 and 35 remain unavailable, and upload fails
with `RxCsE_ASA_ATTRIBUTE_LIST_ERROR` across 360 verified requests and 363
expanded leaves. The private substitutes remain unshipped.

The normal-protocol SDK Program-mode NOP insertion and reconnect preserve this
source binding, Task settings, status, slot and measurements across 182 verified
requests. A second scan executes the changed model. The independent download
reaches the existing result-response gap across 175 verified requests and 909
temporary records, with no active commit. All three cases confirm actual
Offline/cleanup, preserved original files and no fatal SDK fault. Full native
upload/download and Test/Untest/Assemble remain unfinished.

The restarted normal demo passes SDK Go Online/Go Offline across 74 verified
requests. All 24 deployment checks pass, including live source-bound authority
discovery/revision and the executable-contained strict reader. All 97 deployed
app modules match the build, and webpage/app/executable versions agree on
`.141`. The model and edit configuration survive restart, actual Offline/cleanup
succeeds and no fatal SDK fault occurs.
