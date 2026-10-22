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
