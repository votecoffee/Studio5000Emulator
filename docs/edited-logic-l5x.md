# Saving edited logic as L5X

Version `.91` adds **Save edited L5X** next to **Export snapshot**. After supported
native routine edits have finished, stop the emulator and select this control.
The browser downloads a separate `<controller>-edited-r<revision>.L5X` working
copy. The control is enabled only after an edit and while stopped with no active
native programming reservation.

The copy contains the active neutral source and model comments of edited
Standard RLL routines. Other project XML, routine attributes, unedited routines,
tag definitions, imported tag initial values and scheduling are retained from
the original complete L5X. The source file is read and checked against its
original SHA-256; a changed or missing source prevents export. Original ACD/L5X
files are never overwritten. Live values and scan history remain available in
the separate JSON snapshot feature.

Use **Open L5X** to reload the working copy in the emulator. It has a new source
hash, its own revision-0 baseline, and no inherited native ACD correlation
manifests. Changes persist in the saved L5X; there is no automatic save. This is
an emulator working-copy path. Native Studio L5X import, edited ACD generation
and firmware upload/download round trips remain unverified.

The session-authenticated `export-edited-l5x` action returns UTF-8 XML content,
a safe suggested filename, output/base hashes, runtime revision/digest and the
edited routine list. It reports `tag_values: original_import` and
`native_acd_correlation: false`. It does not write a server-side output file or
change the active model. A busy import, running emulator or active programming
reservation prevents saving.

The isolated native test replaces rungs in `MainRoutine` and `Reporting`, saves
the resulting revision-2 project, and reloads it into a separate emulator.
Both routines retain their edited instruction ASTs. The reloaded initial values
are 50 and 5; one scan again produces 123 and 456. XML comparison confirms that
tag data and Task/Module/DataType sections are preserved. The original ACD and
separate main demo remain unchanged.
