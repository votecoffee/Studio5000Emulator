# Empty PLC file-mapping discovery

Version `.157` supports the observed native v35 PLC file-mapping catalog
request: service `0x4B`, class `0x6E`, instance cursor `0`, with no payload.
An empty response contains no instance IDs.

## Source and protocol bounds

This read requires the native compatibility profile, a native project identity
matching the loaded L5X hash, and complete source that proves no PLC message
mappings. It reuses the existing `PcccMapping` source check for controller
`ProduceInfo` declarations. Missing, malformed, context-only, ambiguous or
configured mappings remain unavailable; an unknown catalog never becomes empty.

The path must be global and numeric. Symbolic, Program/AOI/I/O/controller
parent paths, attribute selectors, nonzero cursors and trailing payloads are
rejected. No class revision, mapped instance, attribute layout or PLC file
contents are synthesized. The class is advertised only in native compatibility
mode. Signed reads preserve normal session checks and reply authentication.

This extends read-only discovery. It does not implement PCCC execution,
configured mapping upload, mapping writes or compiled tag addresses. The API
identifies the discovery class and its source-binding requirement separately
from whether the source proves an empty mapping set.

## Validation scope

Focused cases cover signed empty discovery, missing/mismatched identity,
configured or unknown mappings, exact paths/payloads, research-profile denial,
single class advertisement and retained write/attribute/file-service denials.
Source, memory, scan state and controller audit values remain unchanged.

The unmodified `.156` empty-routine fixture reached this request after passing
Program collection and returned a discovery denial, followed by
`RxCsE_FAILED_2_UPLOAD_PLC_FILE_MAPPING_INFO`. That identifies the request being
implemented; it does not establish support for populated mapping repositories
or a complete saved upload.

On the rebuilt `.157`, all 252 focused checks and live signed catalog reads
pass. SDK Go Online/Offline verifies 74 requests. The normal demo upload
retains its separate Program/Routine failure after 349 verified requests.
The empty-routine fixture receives the new empty mapping reply successfully,
then requests Task metadata and reports `RxCsE_UPLOAD_OF_TASKS_FAILED` after
358 verified requests. Task fields 13/22/23 remain unavailable. This advances
the tested fixture past file-mapping discovery; it does not complete upload.

The raw transfer intervals are retained and their inspected layouts report
no framing errors. The bounded collection summary retains only its first 64
lists, so the later Task request is checked in the separate final-request
view. Source/model preservation, actual Offline/cleanup and no reported SDK
fault are confirmed for all three cases. The original demo is restored to
stopped Program mode with zero scan/audit state; no upload-save trial is run.
