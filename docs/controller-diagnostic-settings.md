# Controller retention and automatic diagnostic settings

Version `.142` adds two read-only source settings to the v35 Controller object:

| Attribute | Source | Wire value |
| --- | --- | --- |
| 10, Continue Test Edits | `Controller/RedundancyInfo@KeepTestEditsOnSwitchOver` | One byte, 0 or 1 |
| 35, ADDA Enable | `Controller@AutoDiagsEnabled` | One byte, 0 or 1 |

The settings require a complete, unambiguous Controller export and explicit
canonical `true` or `false` values. Missing fields remain unavailable. Shadow,
case, namespace and UId variants cannot supply a canonical value. The retention
setting additionally requires one canonical RedundancyInfo declaration with a
valid Enabled value and no unknown attributes, children or text. Each setting
can remain available independently when the other is unsupported.

These reads describe saved configuration. They do not run a redundant partner,
perform a switchover, deliver diagnostics or grant authority to change settings.
Reset and supported Routine replacement retain the declared settings. Writes
remain denied. Endpoint Controller configuration state distinguishes the source
flags from unsupported redundant execution and diagnostic delivery.

The installed v35 Controller schema specifies the two byte fields. Its
attribute numbers are sequential with `.NUMBER` overrides; the numbers following
`END` describe storage indices. Separate offline SDK imports, saves, reopens and
exports preserve a disabled Automatic Diagnostics setting and an enabled
KeepTestEditsOnSwitchOver setting. These tests use new private ACD copies and
preserve the original source. Native controller behavior is not inferred from
offline acceptance.

## Controller response framing

The offline collection decoder now recognizes the observed 21-field Controller
instance-1 upload profile. It frames byte/word/dword settings, eight-byte CCUID
fields and 32-byte signature arrays. Values stay lengths and hashes unless
explicit payload output is requested. The decoder preserves order, duplicate
fields, attribute errors and unreturned partial-response suffixes, rejecting
unknown successful layouts, truncation and trailing data.

This decoder inspects existing responses. It does not supply missing CCUIDs,
signatures or physical memory percentages. One saved reference list confirms
the profile widths; its framing does not establish value semantics, a matching
offline source or controller equivalence.

## Validation scope

All 101 affected tests pass without a full suite run. Checks cover strict source
declarations, independent byte values, incomplete/ambiguous metadata, signed
mixed reads and write denial, reset retention and offline response boundaries.
An older source-flag test now checks the already-supported null-handler and
legacy Get Attributes All profile, rather than its obsolete unsupported result.

The isolated native SDK upload uses the same private clock, schema, repository
and Task-stack assumptions as the preceding trial. The new settings succeed;
Controller fields 11/12/27/28/33/34 remain unavailable. Full native upload/download
and the complete edit lifecycle remain unfinished, and the private substitutes
are excluded from the release.
