# Ladder MSG

LogixLab models CIP Data Table Read and Write over the unconnected `THIS`
path in whole-project v35 ControlLogix 5580 ladder execution. It transfers
values between tags in the current project. The `MSG` faceplate shows the
message control and its `EN`, `DN` and `ER` bits.

## Try it

1. Open **Examples → Message lab** and set `SendRead` to `1` in Tag Watch.
2. Step once to queue the read. `ReadControl.EW` and `ReadControl.EN` are set.
3. Step again to start it. `ReadControl.ST` is set and `EW` clears.
4. Step a third time. `ReadValue` changes to `17` and `ReadControl.DN` is set.
5. Set `SendWrite` to `1` and step three times. The write changes `VirtualValue`
   to `42`. Step with `SendRead` false, then set it true and step three times to
   read the new value.

To cancel a read, set `CancelRead` for the scan that queues or starts it. The
sample's latch sets `ReadControl.TO`. At the next step the message completes
with `ER` set, `ERR` equal to `16#00FE`, and the destination retains its value.
Clear `CancelRead` and scan `SendRead` false before issuing another read.

## Supported configuration and timing

- Use a scalar Standard controller base tag with `DataType="MESSAGE"` and
  `Data Format="Message"` containing `MessageParameters`. The model reads
  `MessageType`, `ConnectionPath`, `RequestedLength`, `LocalElement`,
  `RemoteElement`, and optional decimal `LocalIndex` and `RemoteIndex`. Use
  CIP communications, with the connected, cache and large packet options off.
- Both endpoints must name direct Standard controller `DINT` tags or spans of
  1 to 64 elements in one-dimensional `DINT` arrays. A literal subscript and
  the corresponding index attribute are added to get the start. Local writes
  require a writable tag. Remote reads and writes respect External Access.
- The controller advance after the trigger starts the transfer. The following
  advance completes it before task logic runs, sampling the source then. A
  held true rung does not repeat a completed message. A false rung clears
  `EN` once the request is no longer busy, and the next trigger clears the
  previous `DN` or `ER`. Prescan and Reset clear modeled pending requests.
- Up to 32 requests may be pending. Completion uses submission order and
  snapshots the source span before changing the destination. Status and data
  roll back together if a later rung faults in the same controller advance.
  `REQ_LEN` and `DN_LEN` report 16-bit words in this model. A DINT uses two.

This profile is an in-process simulation. External routing, network packet
timing, native MESSAGE layouts, dynamic configuration, and Studio 5000 runtime
qualification remain open. Decorated-only MESSAGE fields remain readable as
saved data. The native Message object inventory is separate.

- [Rockwell message instruction](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-03/contents-ditamap/instruction-set/input-output-instructions/message--msg-.html)
- [Rockwell communication paths](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-03/contents-ditamap/instruction-set/input-output-instructions/specify-the-communication-details.html)
- [Rockwell L5X import/export reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm014_-en-p.pdf)
