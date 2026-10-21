# Program synchronization model default

Version `.123` adds a narrowly scoped initialization rule for Program `0x68`
attribute `29`, Synchronize Data. Its one-byte model value is enabled (`1`) when
the source omits the setting and all of these conditions hold:

- Complete, canonical v35 controller source identifies `1756-L85E`.
- Exactly one direct, canonical `RedundancyInfo` explicitly disables redundancy.
- The Program is an ordinary Standard Program with explicit `UseAsFolder="false"`.
- The synchronization attribute is absent, rather than malformed or opaque.

The rule initializes the emulator's own setting. It does not extract a hidden
checkbox value from the original ACD or implement redundant execution.
Explicit canonical `true`/`false` source values retain precedence. Other processor
profiles, enabled or unknown redundancy, folders, Safety Programs, context,
shadow declarations and malformed settings do not acquire this default.
Single and list reads agree; native setters remain denied.

## Basis and diagnostics

Rockwell's installed v35 help and public
[New Program settings](https://www.rockwellautomation.com/en-gb/docs/studio-5000-logix-designer/38-00/contents-ditamap/studio-5000-logix-designer/tasks--programs--and-routines/programs/create-a-program/new-program-dialog-box-settings.html)
describe enabled synchronization as the new-Program default and identify the
control as disabled when redundancy is disabled. The
[Import/Export reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm014_-en-p.pdf)
specifies `true`/`false` for L5X boolean attributes; numeric L5K spelling must not
be assumed valid in L5X.

Two disposable, nonredundant v35 SDK controls import explicit true/false values,
save separate ACDs, close/reopen and export successfully. Both exports omit the
setting. Their complete Program records agree apart from the new logical IDs.
This establishes the omission in the tested profile; it does not identify a
stored field or establish a universal missing-value rule. Redundancy-enabled
control imports were rejected without a reported fatal SDK fault and provide no
evidence for enabled-redundancy behavior.

API diagnostics distinguish `synchronize_source_values` from
`synchronize_model_defaults`. `missing_values_defaulted` becomes true when this
rule applies, and `synchronize_default_recovers_original_acd_setting` remains
false. Original source bytes and hashes stay unchanged.

## Native scope

The isolated `.123` SDK upload reads all 22 requested Program fields
successfully, including attribute `29`. The previous `.122` comparison had one
unavailable field. The upload still reports `RxCsE_UPLOAD_OF_PROGRAMS_FAILED`;
no rejected subsequent request identifies its cause. Complete field framing and
successful replies do not establish successful Program reconstruction.

The attempt records 204 verified signed requests, confirmed Offline/cleanup,
unchanged source/model and no reported fatal SDK fault. It uses an isolated
owned project, a matching Template snapshot and unshipped clock/revision
hypotheses. The public clock profile remains unchanged; its unchanged upload
failure is not rerun in this iteration. Released connection acceptance is
checked separately. Full upload/download, the complete online-edit lifecycle
and Studio GUI monitoring remain unfinished.
