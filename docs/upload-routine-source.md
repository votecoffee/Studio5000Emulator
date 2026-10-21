# Routine upload source inspection

Version `.133` adds a read-only decoder for the Routine source streams carried
by the observed [signed read transport](read-transport.md). It preserves the
source class and edit state instead of treating every returned rung as ordinary
active ladder. It does not reconstruct or install a native Studio project.

## Separate profiles

The upload XML includes `TargetClass`, which the existing
[online-edit source decoder](routine-source.md) deliberately rejects. The new
`logixlab.upload_routine_source` module accepts these observed combinations:

| TargetClass | OnlineEditType | Rung types |
| --- | --- | --- |
| Standard | Original | `N` |
| Safety | Original | `N` |
| Standard | TestEdits | `N`, adjacent `IR`/`R` pairs |

Names, XML attributes, revision, content structure and rung fields are checked
against the bounded v35 RLL profile. Unknown class/edit combinations, protection
attributes, extra nodes, unsupported rung kinds and empty routines remain errors.
Recognizing Safety source is inspection only; no safety behavior, signature or
execution is verified.

Each record retains its original RegionId, rung kind, order and TextIOI. The
observed TestEdits profile repeats a RegionId in adjacent `IR` and `R` records.
The decoder keeps both records. It does not select an active record, interpret
the native edit lifecycle or substitute one record for the other. Other repeated
regions and incomplete or reversed pairs are rejected.

## Bounded containers and private content

The decoder shares the existing container framing and decompression checks:
exact offsets and extents, zero padding, bounded expansion, complete zlib streams
and no trailing compressed content. Upload inputs have an additional 4 MiB
container bound. XML expansion is limited to 2 MiB, auxiliary data to 64 KiB,
rungs to 4,096 and each TextIOI to 65,536 characters. XML entities and document
types are rejected. The observed UTF-8 bytes are decoded explicitly despite
their UTF-16 declaration.

`UploadSource.description()` reports class/edit state, counts and SHA-256 hashes.
It omits routine names, RegionIds, operands, source text and auxiliary bytes.
Default object representations also omit names and source records. Callers that
explicitly inspect the immutable records can access their original TextIOI;
keep such data and captures in ignored local storage. Auxiliary semantics,
operand bindings and source association remain unverified.

Upload inspection returns a separate immutable type with `records`. The edit
resolver and candidate planner require their existing `RoutineSource` type and
reject uploaded records. The online-edit decoder's accepted XML profile has not
expanded. This prevents accidental cross-use; it is not a Python security sandbox.

## Completed read streams

For a completed `logixlab.read_transport.Assembly`, call `routine_source()`.
It requires inner service `0x5D`, selector DWORDs `(1, 3)` and exactly one
Program- or AOI-scoped Routine path. Incomplete streams, unrelated selectors,
unscoped objects, attribute paths and write requests are rejected.

Alternatively, `upload_routine_source.decode(data)` inspects an already assembled
container without assigning it a request scope. Neither API authenticates a MAC
or binds the source to an emulator project. The caller owns session separation,
integrity checks and any later source association. The live endpoint still
rejects `0x3A`; this API adds no native read/write service.

## Validation and remaining work

The saved successful upload contains 809 Routine source streams. The decoder
reads 806: 730 Standard/Original, 63 Safety/Original and 13 Standard/TestEdits.
They retain 14,414 rung records, including 15 adjacent edit pairs. Three other
containers have an unsupported compression flag variant and remain errors;
their meaning is unverified. All data stays offline and outside the active demo.
The saved capture's MAC integrity remains unverified.

The most recent isolated SDK upload, on `.132`, fails Program upload after all 22
Routine metadata fields return status zero. It never requests these source
streams. This source-decoding work does not resolve that earlier failure or
establish native upload, download or complete online-edit acceptance.

All 145 affected tests pass, covering source profiles, edit/import separation,
container limits, completed read streams and the existing edit path. The full
behavioral suite was not rerun for this passive decoder change.

The restarted release passes 12 focused deployment checks, including execution
of the packaged decoder against synthetic Standard, Safety and TestEdits sources.
All 94 deployed app modules match the build. The webpage, packaged assets and
Windows executable report `.133`. Native SDK Go Online/Go Offline passes across
75 verified signed requests, with actual Offline/cleanup, unchanged source/model
and no reported fatal SDK fault. Inputs, logic and edit settings match across
restart. Full native upload was not rerun for this inspection-only change.
