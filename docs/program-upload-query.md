# Program upload query diagnostics

The offline capture and [native transfer checkpoint reader](native-transfer-diagnostics.md)
describe the observed v35 Program service `0x50` exchange. This is an inspection
profile; the live emulator continues to reject that service.

## Observed framing

The request targets one unscoped numeric Program instance. Its eight-byte
payload contains a two-byte `0x0101` word, a two-byte selector (`31`, `32` or `33`),
and a four-byte zero position. The successful reply has a `0x0301` four-byte
container word, a four-byte byte count of eight, an opaque four-byte word and
a four-byte selector matching the request.

All 60 matching exchanges in a saved successful upload consume exactly with
this shape. That observation does not establish what the opaque word means,
how to calculate it, or how it binds to source. The selectors are not assigned
Program attribute names by this reader. Captured values are never replayed.

Reports retain the selector, status, byte count, record count and opaque-word
hash. They do not expose the word itself. Invalid paths, unsupported selectors
or positions, truncated data, mismatched selectors and unexpected successful
reply shapes are rejected. A normal error reply retains its status without
inventing returned records. Checkpoint query/error counts continue after the
64-row retention limit; a shape error makes `analysis_complete` false.

## Native investigation

An isolated upload experiment with private Controller field placeholders got
past the Controller list and reached this Program query. The normal app still
withholds those Controller fields because their value contracts are unresolved.
A further private empty Program reply experiment faulted the SDK. Its original
source and model were preserved, but native Offline could not be confirmed.
The private endpoint was stopped and the main demo endpoint restored. The empty
reply is not part of this decoder's successful profile and is not a live response.
After SDK service recovery, the established `.146` demo Go Online/Offline check
passes across 74 verified requests with native Offline and endpoint cleanup
confirmed, source/model preservation and no reported fault. The experimental
response trials remain retired.

Neither experiment establishes a complete upload. No live routing, source
metadata, checksum algorithm or download result encoding is added here. MAC,
source binding and native acceptance remain separate from framing checks.
