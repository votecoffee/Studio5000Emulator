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
