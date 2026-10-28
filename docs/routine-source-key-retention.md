# Source Key metadata through plain RLL edits

Version `26.1028.121233` retains the original opaque Executable Source Key
attribute `22` after a supported plain Standard RLL replacement. Earlier builds
withheld it whenever a routine changed, leaving its ordered bulk metadata reply
incomplete even when current source and interpreter state verified.

An offline native SDK check edits the first rung of two separate routines on a
private copy of the original demo. Each edit is saved to a separate ACD, reopened
Offline and exported for independent logic checks. Both routines keep their exact
native scoped IDs, unprotected Type words and original 66-byte Source Key values
through both changes. The original input stays unchanged, no controller
connection is initiated, and the SDK reports no fault.

The emulator's supported replacement changes plain RLL source and interpreted
logic. It does not implement a Source Key or source-protection configuration
setter. The unchanged opaque field therefore remains available with a matching
original installation catalog. No bytes are decrypted, inferred or generated.
This behavior is limited to the supported unprotected Standard RLL profile.

Every edited-model read first verifies current source, idle native edits,
ordinary type, source identity and clean interpreter state. The Source Key also
requires the installation's original source snapshot and matching complete
Symbol/Routine/type catalog fingerprint. A replaced catalog or missing snapshot
withholds the field; an invalid edit source still revokes the guarded state.
This prevents an arbitrary replacement key from inheriting the original source
association. Earlier immutable source snapshots remain intact.

The change restores the complete observed 22-field bulk reply for an eligible
edited routine. It does not supply edited Routine components or change-log
records, establish full SDK upload after edits, or add protection configuration
changes. See [current source/state readback](accepted-routine-source.md) and
[tag readback after edits](edited-tag-readback.md) for the neighboring profiles.
