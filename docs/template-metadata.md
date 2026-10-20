# Template metadata and aligned reads

Version `.101` exposes Template attribute 6, Family Type, as a two-byte zero
for an explicit, unambiguous `Family="NoFamily"` source declaration. The wire
catalog supports explicit user structures in that family. A missing declaration
or a conflicting case/namespace variant does not gain a source value.

Individual reads and ordered attribute lists use the same value. Duplicates
retain their positions and byte widths. Multiply Code (attribute 7) and Recon
Data (attribute 8) remain unavailable; an attribute list containing them retains
partial status and their individual errors. Setters remain denied.

## Backed definition extent

For the model's advertised Template word count `W`, compact definition reads
cover `4*W-23` bytes. The aligned allocation covers `4*W-20` bytes: the same
definition followed by three reserved zero bytes. A captured native diagnostic
requested that aligned extent; the previous model stopped at the compact end.

Both extents are now backed. Compact reads preserve their existing bytes and
type handles. Larger reads may include the reserved bytes, subject to the
requested range and reply budget. Pagination can finish inside those bytes;
reads starting beyond the allocation remain errors. The allocation retains
the 32 KiB limit and does not expose another Template's storage.

## Evidence and limits

Focused tests cover declaration ambiguity, widths, ordered partial lists,
compact/aligned reads, pagination, bounds, access controls and unchanged tag
state. An independent client verifies the real TCP challenge/MAC exchange
and signed Template reads without the Logix Designer SDK. A separate appliance
read verifies the demo's 61-byte compact and 64-byte aligned definitions,
including the zero family value and unavailable attributes 7 and 8.

A private experiment supplying hypothetical values for attributes 7 and 8
advanced to a native Template-definition read, then faulted the SDK. Native
Offline was not confirmed. The source and active model were preserved through
explicit emulator endpoint cleanup. Those overrides are excluded from the app.
The aligned-storage change has independent protocol validation; neither the
cause nor resolution of that SDK fault is established. SDK retesting is held
pending service recovery. Full native type upload and address-cache population
remain unfinished.
