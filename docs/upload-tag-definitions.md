# Native uploaded controller tag definitions

The Windows SDK probe can independently export and check the complete controller
tag set after upload. This complements Offline byte reads and complete Program
exports, which separately check Program-local declarations and values.

```powershell
py -3.13 -X utf8 source/tools/probe_native_sdk.py --project .local/Controller.ACD --upload-target .local/MatchingController.ACD --url http://127.0.0.1:8786 --path 'Emulator\192.0.2.8\Backplane\0' --operation upload --verify-uploaded-content .local/Controller.L5X --verify-uploaded-tag-definitions --snapshot-uploaded-acd --retain-transfer-trace --output .local/checked-tag-snapshot
```

Use the owned emulator's endpoint and an unchanged matching saved-download ACD
for the snapshot workflow. The additional tag check requires an existing-project
upload with `--verify-uploaded-content` and at least one controller root. It is
optional; older upload receipts remain usable without it.

The helper calls `PartialExportToXmlFileAsync` for `Controller/Tags/Tag`, writing
a new private `uploaded-controller-tags.L5X`. Independent validation requires:

- The actual export hash, pinned source, v35 Tag target and Controller context.
- Every expected controller root exactly once, marked `Use="Target"`.
- Matching type references, declared dimensions, constant and external-access flags.
- Complete decorated values encoding to the expected current bytes using the
  source-bound type layouts, including supported structures and packed arrays.

Context-only tags, missing/extra/duplicate roots, changed declarations or values,
and malformed XML fail the check. BOOL declarations count logical bits while
their Table values count packed words; those dimensions are checked separately.
Matching bytes cannot hide an altered array declaration.

The summary includes `uploaded_tag_definitions_verification`. A requested check
must pass for the probe to succeed. The Offline ACD rebuild also revalidates the
actual export when its upload request enabled this check; a summary flag alone
is insufficient. Retained older requests keep their existing validation path.

This is a partial tag export, not a complete Controller export or an ACD save.
It does not reconstruct unknown type schemas or enable direct general Studio
upload/save. The commands do not change Windows services or retry native calls.

## Validation

Ninety focused checks pass. Independent checks also accept actual native SDK
exports from the demo's fourteen controller roots (45 bytes) and a saved UDT
fixture's twenty-two controller roots (172 bytes). The latter is an Offline
export check, separate from a new upload trial. This Windows tools increment
does not change the running app version, `26.1026.153720`.

A fresh native snapshot upload also passes the new check across 1,137 verified
requests. Three temporary runtime changes survive the complete tag export,
snapshot ACD save/reopen and all twelve typed Online scalar reads. Both
routine exports, the complete Program package and all fourteen value roots
match. Actual SDK Offline cleanup succeeds without a fault, and the original
runtime values and edit setting are restored afterward.

The Offline rebuild consumes that new receipt and revalidates its controller
tag export before any native import. Its saved/reopened ACD preserves all
fourteen roots, 45 bytes, two routines, ten rungs and source configuration;
its cleared correlation correctly requires a download before Online. Five
managed preflight cases validate option decoding without opening an SDK project.

A separate ordinary upload stopped at its 120-second deadline before reaching
the export step. Its final SDK outcome remains unknown. A fresh read-only
connection subsequently goes Online, reads the live value and returns Offline
without a fault. The timed-out call is not retried or relabeled as successful;
ordinary upload reliability and direct general ACD saving remain unfinished.

## Ordinary upload with a checked Online baseline

For an unchanged matching saved-download target, the probe can verify Online
and then Offline before starting an ordinary upload:

```powershell
py -3.13 -X utf8 source/tools/probe_native_sdk.py --project .local/Controller.ACD --upload-target .local/MatchingController.ACD --url http://127.0.0.1:8786 --path 'Emulator\192.0.2.8\Backplane\0' --operation upload --verify-uploaded-content .local/Controller.L5X --verify-uploaded-tag-definitions --verify-upload-baseline-online --retain-transfer-trace --output .local/checked-baseline-upload
```

This uses the same source/correlation admission as the snapshot workflow. A
missing, edited, uninstalled or incompatible baseline is rejected. The option
does not save an ACD, retry an upload or extend the ordinary 120-second native
helper limit. It is unsuitable for an arbitrary merge target whose offline
changes need to be replaced by upload.

The native report must confirm the actual ordered Online and Offline checks;
setting the option or a receipt flag alone cannot prove them. The summary
records `upload_baseline_online_verified` separately from upload success.

The checked-baseline demo completes across 1,052 verified requests, including
all fourteen controller definitions/current values and both routines. Native
Offline cleanup succeeds without a fault, and runtime state remains unchanged.
The controller response at the earlier stalled boundary is identical in the
successful and timed-out traces; a differing response at that boundary is not
established as the cause. This demonstrates the checked-baseline workflow,
not general upload reliability or direct Studio ACD saving.
