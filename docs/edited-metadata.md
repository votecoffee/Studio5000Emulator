# Current metadata after native RLL edits

The supported native Program-mode RLL transaction now retains its exact Comment
removal packets at commit. It creates a detached current all-object metadata
view, leaving the original ACD catalog and committed download snapshot intact.
Only an invariant `Comment` removal for an old region absent from the replacement
source can clear a matching property. A missing removal never silently prunes
stale metadata. Unknown affected properties and references keep this view guarded.

Metadata addresses use the observed 23-bit RLL region encoding, separate from
the numeric XML `RegionId`. Both scope and canonical encoding are checked. A
removal for a region still present in the new source is rejected before commit.
The previous complete native source is also checked before applying the change.

Unrelated definitions, localized diagnostics, template metadata and surviving
Comments retain their exact typed values and local record IDs. IDs are not
renumbered to fill a removed record's gap. Original catalogs remain immutable.
Each fragment rechecks current source for every installed routine, tag layout,
native catalog fingerprints, serial/profile configuration and the view's bytes.
The metadata path validates declarations and catalogs without rescanning the
legacy transfer RAM image for each fragment. Storage reads retain that separate
full effect validation. Routine source validation shares one catalog check
within a locked fragment and still checks every retained source against current
logic. No catalog validation result is reused across requests. Canonical type
encoding is reused only after a freshly rebuilt immutable snapshot compares
every source, type ID, type and member field; mutable or subclass values retain
full serialization. Type manifests retain the same
canonical bytes and binding fingerprints while avoiding recursive copies of
immutable member fields.

A later edit revokes an existing continuation. An internal or unrecorded edit
does not acquire native metadata authority.

## Native content diagnostic

The native SDK probe can explicitly compare an edited upload with current
interpreter logic using the unchanged source L5X as its declaration context:

```powershell
py -3.13 -X utf8 source/tools/probe_native_sdk.py --operation upload --project .local/Source.ACD --upload-target .local/Downloaded.ACD --verify-uploaded-content .local/Source.L5X --allow-edited-upload-content --verify-uploaded-tag-definitions --retain-transfer-trace --url http://127.0.0.1:8786 --path 'Emulator\192.0.2.8\Backplane\0' --output .local/edited-upload-check
```

Use the owned endpoint's actual address and a new output directory. This requires
stopped Program mode, complete retained native edit sources, unchanged tag and
Program declarations, and matching parsed current rung text. The plan pins the
runtime revision and full logic fingerprint before SDK calls. Native Offline
routine exports independently check current instructions and Comments; value,
Program-package and controller-tag definition checks remain separate receipts.
This option does not enable reconstructed-upload saving, snapshots, factory
upload or native Test/Untest/Assemble. The default content check still requires
unchanged logic unless this explicit edited-content option is supplied.

## Native validation boundary

For the two-routine conveyor demo, native download/save/reopen/Go Online and a
Program-mode RLL edit with reconnect succeed. Independent signed reads verify
both current routine sources, all fourteen tag roots, and all 1,670 current
metadata records. Exactly the accepted old-rung Comment is removed from the
1,671-record downloaded view; other typed values and local record IDs remain.

The native edited-project upload now receives both routine sources and the
complete current all-object metadata stream. Offline reconstruction of its
complete journal matches the independently verified bytes. The next request,
Change Log instance 1 service `0x4F`, receives the guard for unsupported edited
history. The original empty-log shortcut requires runtime revision zero and
must not stand in for actual edit history.

That trial reached the diagnostic deadline, so its harness outcome remains
unknown. A later SDK receipt reports a CIP error and Offline without a server
fault; a separate fresh Go Online/read/Offline check confirms recovery. The
trial is not an edited-upload success, does not verify the exported edited
content, and saves no reconstructed ACD. Implementing the current Change Log
search/history format is the next upload target.
