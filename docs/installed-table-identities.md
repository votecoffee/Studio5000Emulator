# Installed Symbol and Data Table identities

Version `26.1026.143655` keeps a tag's Symbol ID separate from its Data Table ID
after a verified source-equivalent download. Native Program import can preserve
one identity while allocating a different storage-table identity. Equal numeric
IDs are not a general invariant.

For example, a Symbol with ID `14` can refer to Data Table `25`. Symbol attribute
`12`, the Table catalog, descriptor bytes and Table reads must all use `25`;
the Symbol catalog and Symbol descriptor retain `14`. Program-scoped identities
retain their original numeric parent, including repeated IDs in other Programs.

The committed view derives these links from the validated downloaded object
graph and complete prepared values. Every read rechecks source identity,
catalogs, typed headers and retained effects. Missing or altered links fail;
the view does not substitute a Symbol ID for an unavailable Table ID. An
uninstalled or edited project retains the prior model discovery behavior.

Addresses remain model-owned and backed by current interpreter values. This
does not expose firmware/host memory, add setters or execute compiled code.
Constants retain their value and member-access checks and write restrictions.

The same revision recognizes the captured download-header access byte `02`
for explicitly read-only Program-local constants. It replaces the earlier `01`
expectation only for that source profile; both encodings are not accepted.
The constant flag and all other source fields still have to match. Runtime
access permissions and constant values do not change.

Focused checks cover admitted bindings, changed-effect rejection, independent
Symbol/Table IDs through actual wire consumers, storage-cache invalidation,
missing-root rejection and strict read-only local-constant headers. Native
transfer acceptance is recorded separately from these software checks.

## Native checkpoint

Both actually rebuilt source profiles complete native download/save/reopen/
Online on this revision. Independent full exports verify the demo's fourteen
roots and ten rungs (431 requests), and the two-Program profile's twenty-nine
roots and thirteen rungs (435 requests). The latter retains ten constants,
nested UDTs, arrays and explicitly read-only local constants. Native Offline
cleanup succeeds without an SDK fault.

The rebuilt demo's upload now passes tag collection, all fourteen value reads,
both routine exports and its complete Program export. Its snapshot saves,
reopens and goes Online. All three DINT getters and the first BOOL getter pass;
`MotorRunning` then returns a no-data result. A separate fresh download/read
check also passes all three DINTs. Another complete snapshot trial passes
`MotorRunning` and more BOOLs before failing at `SensorMemory`. Both trials
confirm Offline cleanup without SDK faults; neither complete case passes.

The rebuilt two-Program trial saves a snapshot, but its 300-second client
deadline expires during native reopen. Its final native outcome and Offline
cleanup are unknown. That operation is not repeated. A separate read-only
session using the previously verified downloaded file subsequently goes Online,
reads the live value and returns Offline without a fault.

These changes pass 398 focused checks and the full 2,163-test milestone, with
two platform skips. All 372 Python sources parse. Direct reconstructed-project
saving, general project replacement and Studio GUI acceptance remain unfinished.

## Read-path validation cost

Version `26.1026.153720` verifies a committed installation once per scalar
read and reuses that result while constructing its current storage view.
Standalone storage construction also shares one Table identity map across
all Program scopes. These are local call results, not a cache retained across
requests. Changed headers, source, identities, effects and access still revoke
the next read. The application lock serializes construction with project edits.

This removes redundant project-wide validation as native polling grows to more
tags. It does not increase native timeouts or retry a failed SDK getter.
159 affected checks pass, including validation counts and corruption detected
on the following read. Native transfer acceptance is checked separately.
