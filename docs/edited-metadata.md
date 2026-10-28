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
