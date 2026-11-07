# Ladder MSG

LogixLab models CIP Data Table Read and Write for numeric tags, matching
strings and user-defined records, plus bounded CIP Generic Identity and
Wall Clock Time reads to the simulated controller in whole-project v35 ControlLogix 5580 ladder
execution. It transfers
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
sample latches `ReadControl.FLAGS.8`, which is the same bit as `ReadControl.TO`.
At the next step the message completes
with `ER` set, `ERR` equal to `16#00FE`, and the destination retains its value.
Clear `CancelRead` and scan `SendRead` false before issuing another read.

Set `SendConnectedRead` to 1 and step four scans. CachedReadControl opens
a modeled connection and reads 17 into ConnectedValue. Scan the trigger
false, then set it true again. The repeated request takes three scans
because it reuses the cached connection.

After that read completes, clear SendConnectedRead and set
ReleaseConnectedCache for one scan. Rung 23 unlatches
CachedReadControl.EN_CC and releases the retained connection. Clear
ReleaseConnectedCache and set EnableConnectedCache for one scan. Rung 24
latches the bit again. The next read opens a new connection in four scans
and retains it for subsequent reads.

On a fresh Message Lab, set ApplyConnectedTiming and step once. Rung 22
writes a ConnectionRate of 2,500 microseconds and a TimeoutMultiplier of
zero, then reads both settings back into ConnectedRateEcho and
ConnectedMultiplierEcho. Clear ApplyConnectedTiming, trigger the connected
read and step four times at the default 10 ms. The response expires with
ERR 16#00FE. To let the next request finish, clear SendConnectedRead, set
ConnectedMultiplier to 1, apply the settings for one scan and trigger again.
A request that was already queued retains the settings it captured.

On a fresh Message Lab, enable ApplyMessageRoute for one scan. Rung 25
copies LocalMessageRoute into CachedReadControl.Path. Its two bytes select
port 1 and the project controller's slot 0. Clear ApplyMessageRoute and
trigger a read to use this route. Set LocalMessageRoute.DATA[1] to 1 and
apply the route again to select an unsupported slot. The next request
returns ERR 16#0005 and keeps the previous destination value.

ApplyPathBuffer runs the same route change through the Message object on
rung 26. SSV consumes the count and path in MessagePathBuffer. GSV then
writes the live route into MessagePathEcho. The first four bytes are
`[2, 0, 1, 0]` for slot 0 and the rest of the output buffer is zero.
Change MessagePathBuffer[0] to 0 to select THIS on the next request.

Set `CaptureReadFlags` and `SendRead` on a fresh Message Lab and step three
times. The ladder MOV copies the current `ReadControl.FLAGS` into
`ReadFlagsSnapshot` each scan. The INT word is 132 (EN and EW), then 192
(EN and ST), then 160 (EN and DN).

For the typed examples, set SendTyped to 1 and step three times. The read
copies 2.5 and -7.25 from the program-scoped Samples array into RealReadback.
The write copies the exact LINT value 9007199254740993 into the program-scoped
WideTarget tag. Look for RealReadControl.DN and WideWriteControl.DN in Tag Watch.

Set SendGridRead to 1 and step three times to read three DINTs across a
row boundary. GridReadback[0,2], GridReadback[1,0] and GridReadback[1,1]
receive 30, 40 and 50 from the program-scoped Grid. The adjacent -1
sentinels stay in place and GridReadControl.DN_LEN reports six words.

Set SendLocalMessages to 1 in a fresh Message Lab and step three scans.
The program-local LocalReadControl reads VirtualValue into
Program:MainProgram.LocalInbox[1]. LocalWriteControl sends the program's
LocalOutbox value of 73 to the controller tag LocalEcho. Both local
buffers have External Access set to None.

Set SendRecord to 1 and step three scans to send the complete MessageRecord
to the program-local RecordInbox and to RecordEcho. Inspect their Batch,
Lot, Ready, Samples and Quality fields in Tag Watch. The bundled record
uses a 32-byte modeled layout, so both controls report 16 words.

Set SendText to 1 and step three scans. TextSource starts at READY.
The two messages copy it to the program-local TextInbox and to TextEcho.
Each control reports 44 words for the full standard STRING record.

Set SendMembers to 1 and step three scans. The read copies
RecordSource.Samples into the program-local RecordInbox.Samples array.
The write uses QualitySource and QualityTarget aliases to copy
RecordSource.Quality.Value into RecordEcho.Quality.Value. Other record
members retain their values.

For a runtime index change, scan SendTyped false, then set SetReadIndices
to 1, ReadLocalIndex to 1, and ReadRemoteIndex to 0. Set SendTyped to 1 and
step three times. Ladder MOV writes the MESSAGE index fields before MSG
queues the read. RealReadback[1] and RealReadback[2] receive 100.0 and 2.5.
If you change either index after the first step, the new index takes effect
on the next request.

To retarget a read, start with a fresh Message Lab and queue a read with
SendRead. Set UseAlternateRead to 1 while the request is pending. Ladder MOV
changes ReadControl.RemoteElement to AlternateValue, and the queued request
still reads VirtualValue. Scan SendRead false before triggering again. The
next read returns 64 from AlternateValue. To edit the STRING directly in
Tag Watch, clear UseAlternateRead first.

For a timeout and retry, use the default 10 ms scan interval and start
with a fresh Message Lab. Set ApplyReadTimeout to 1 and step once with
SendRead off. SSV sets UnconnectedTimeout to ReadTimeoutUs (10,000), and
GSV reads it back into the TIME32 tag ReadTimeoutEcho. Set SendRead to 1
and step three times. The read sets ER and leaves ReadValue
untouched. Set ReadTimeoutUs to 20,000 and step with SendRead off. Turn
SendRead on and step three times to retry. ReadValue receives 17 and DN sets.

## CIP Generic Identity read

On a v35 1756-L85E project, ladder MSG can issue Get Attribute Single
(service 16#0E) or Get Attributes All (service 16#01) to Identity class
16#01, instance 1, on THIS. It reads the emulator's L85E identity profile.
The standard reply contains Vendor ID (1), Device Type (2), Product Code
(3), Revision (4), Status (5), Serial Number (6) and Product Name (7).
Status uses the simulated controller mode at the advance that completes
the reply. The modeled Program and Run values are 16#3070 and 16#3060.

Configure MessageType as CIP Generic with ServiceCode, ObjectType and
TargetObject. Get Attribute Single also requires AttributeNumber. Get
Attributes All ignores a valid hexadecimal placeholder in that field.
Use zero RequestedLength and a direct, writable local SINT, INT or DINT
DestinationTag. A one-dimensional array can start at a literal index such
as IdentityReply[1]. The reply starts in the low byte of the selected
element and fills consecutive elements in little-endian order. A partial
final element retains its untouched high bytes. A complete element can
replace an unknown value. DN_LEN reports reply bytes. A short destination
reports 16#0011. An unknown partial element reports 16#0003. Both errors
preserve the entire destination. The usual queue, cancel and simulated
timeout rules apply.

Get Attribute List (service 16#03) uses LocalElement as a direct SINT,
INT or DINT source or fixed one-dimensional array start. RequestedLength
is 4 through 66 bytes and must match the request. The request consists of
a little-endian 16-bit count followed by 1 through 32 unsigned 16-bit
attribute IDs. The instruction captures the list at admission. REQ_LEN
reports bytes. The reply contains a 16-bit count and, in request order,
each 16-bit ID, its 16-bit status and the value when supported. An
unsupported ID returns item status 16#0014. The emulator stores the reply
and sets ER with ERR 16#000A and the returned DN_LEN in this case. A
malformed request reports 16#0003 and leaves the destination untouched.

The Generic control exposes Class (INT), Instance (DINT) and Attribute
(INT) as writable members. A queued request keeps the values captured at
trigger time. Later writes affect the next request. An Identity read uses
class 1 and instance 1. An unsupported class or instance completes
with 16#0005. An unsupported single attribute completes with 16#0014.
Neither error changes the reply buffer. Get Attributes All and Get
Attribute List ignore Attribute.
Prescan preserves the live members and Reset reloads the authored values.

In Message Lab, set SendIdentityRead to 1 and step three times. IdentityReply
changes from [-9, 0, 0, -9] to [-9, 35, 11, -9]. The middle bytes are the
major and minor revision. Enable SendIdentityAll to read all seven
attributes. After three steps IdentityAllReply contains the 26-byte reply,
including the two Program status bytes at indices 9 and 10 when stepping
from Program mode. Enable SendIdentityWord to read the revision into a
DINT. IdentityWordReply changes from 16#11223344 to 16#11220B23 and
IdentityWordControl.DN_LEN reports 2. Enable SendIdentityList to request
Revision and Serial Number together. IdentityListReply begins with
`[2, 4, 0, 16#0B23, 6, 0, 1, 16#4C4C]` and keeps its last element at 91.
To exercise the item error, rearm the rung and put 65535 in the request
as the signed INT value -1.

To change the selected attribute while a request is queued, start with a
fresh Message Lab, set SendIdentityRead to 1 and step once. Set
ApplyIdentityAttribute to 1 and step twice more. The first request still
returns Revision. Scan SendIdentityRead false and then re-trigger it.
The next request reads Product Code and writes -88 and 0 to the middle
two SINT elements. Those bytes encode product code 168.

## CIP Generic Wall Clock Time

On Message Lab, set SendClockRead and step three times. Rung 29 reads
class 16#8B, instance 1, attribute 7 into ClockReply. The seven DINTs
contain the UTC year, month, day, hour, minute, second and microsecond.
Set ClockReadControl.Attribute to 6 and trigger a new request to read
the 64-bit UTC microsecond counter into the first two DINTs. Attribute 11
returns the same counter. DN_LEN reports 28 bytes for the calendar and
8 bytes for either counter.

Get Attribute Single and Get Attribute List use the emulator's existing
[Wall Clock Time model](wall-clock-policy.md). A list uses one sample of
the host UTC clock at completion for all requested time attributes.
Legacy attributes and UTC policy fields require the existing source
qualification. An unavailable single attribute returns ERR 16#0014 and
preserves the destination. A list records the error per item.

Class and Instance are captured at admission along with the single
attribute or list payload. Ladder can retarget a supported single or list
read between Identity and Wall Clock Time on qualified projects.
Get Attributes All remains specific to Identity. Changing its Class to
16#8B reports ERR 16#0008. The clock is read-only and reflects the emulator
host's UTC time.

## Supported configuration and timing

- Use a scalar Standard controller or Program Local base tag with
  `DataType="MESSAGE"` and `Data Format="Message"` containing
  `MessageParameters`. Each program resolves its own named control before
  looking in controller scope. The model reads
  `MessageType`, `ConnectionPath`, `RequestedLength`, `LocalElement`,
  `RemoteElement`, and optional decimal `LocalIndex` and `RemoteIndex`. Use
  standard CIP communications on THIS or a one-hop backplane route to the
  declared local controller, such as `1,0`. An explicit route requires a
  unique matching Local module with an ICP port 1, a valid slot and a
  chassis size. Connected THIS is supported by the emulator. Cache requires
  ConnectedFlag. Large packets remain outside this profile.
- MESSAGE.Path is a writable STRING containing raw path bytes. An empty
  string represents THIS in the emulator. Two bytes such as the ladder
  literal `'$01$00'` represent port 1 and slot 0. Writes through MOV or
  the LEN and DATA members affect the next admitted request. A request
  with invalid bytes, invalid LEN, unknown active DATA or an unsupported
  route reports ERR 16#0005 and leaves its destination untouched. Prescan
  retains the live path and Reset restores the authored path.
- Ladder GSV and SSV access Message ConnectionPath through an 82-element
  contiguous SINT window in a one-dimensional array. The first two bytes
  form an unsigned little-endian count of 0 through 80. The active path
  follows the header. SSV ignores trailing bytes, while GSV writes all 82
  elements and zeroes the unused output. Unknown header or active bytes,
  excessive counts and short windows fault the scan. SSV can store an
  unsupported route for readback. MSG reports its path error if triggered.
- Numeric Data Table endpoints must use matching SINT, INT, DINT, LINT, or finite REAL types.
  They can name scalar tags or spans of 1 to 64 elements in arrays of up to
  three dimensions. A two- or three-dimensional start must specify every
  coordinate, for example `Grid[0,2]` or `Cube[0,1,0]`, with no additional
  authored index offset. The last dimension varies fastest, so a span can
  cross rows and planes within the tag. A `[*]` selector in a one-dimensional
  array takes its starting position from the corresponding
  writable DINT member, LocalIndex or RemoteIndex. The exported index supplies
  the initial value. A literal subscript keeps its authored start and offset.
  Runtime writes to the index members affect only `[*]` selectors. A new
  fully indexed multidimensional RemoteElement is captured when queued.
- Numeric endpoints can select members of explicit UDTs, including paths
  such as `Records[2].Quality.Value` and `Record.Samples[*]`. Every
  array before the final member requires literal coordinates. The final
  numeric array uses the same start and span rules as a direct tag. A
  transfer stays inside that array. Remote access checks the root and
  each member on the selected path, so an unrelated restricted sibling
  does not block access to an allowed member.
- A numeric endpoint can use a static alias to a scalar, an array, or a
  numeric UDT member. An alias to a whole array accepts a final subscript
  or `[*]`. An alias to a fixed array element selects just that element.
  Alias targets resolve in the alias declaration's scope. Remote access
  checks each alias, the base tag and the selected member path. Cycles,
  chains longer than eight aliases, and wildcard targets in AliasFor
  report an invalid path. Specify any UDT member in AliasFor itself.
- Data Table endpoints can also use the same explicit UDT type. The
  emulator uses its [structured tag layout](connectivity.md#structured-transfers) to size complete
  records and qualify nested numeric members, member arrays, and explicitly
  packed BOOLs. The 64-element limit applies to records, and the complete
  span may use up to 32,768 modeled bytes. A remote write requires every
  visible member to allow Read/Write. Unknown or invalid source members
  reject the entire span before any destination changes. Operational
  records and layouts with unmodeled members remain outside this profile.
- Matching standard STRING or explicit `StringFamily` tags also support
  scalar and array transfers. A string transfers its LEN and all DATA,
  including any known bytes beyond LEN. Omitted inactive bytes in
  Decorated data stay unknown. Invalid LEN or unknown active bytes return
  ERR 16#0003 before any write. The modeled size includes the four-byte
  LEN, declared DATA capacity and padding to a four-byte boundary.
  Standard STRING uses 88 bytes. Custom capacities are bounded to
  4,096 bytes and must match by declared type. Scalar L5X tags can use
  the `Data Format="String"` form with a decimal Length and quoted data.
  This form supplies zero padding when only the active bytes are present.
- Local endpoints name direct Standard controller tags or data in the
  calling Standard program. For a Program Local control, a bare local data
  name resolves in its own program before looking in controller scope.
  For a controller control, a bare name keeps its controller binding.
  Use `Program:<program>.<tag>` in the emulator to explicitly select data
  in the calling program. The same rules apply to the Generic DestinationTag.
  Remote endpoints can also name direct tags in ordinary Standard Programs using
  `Program:<program>.<tag>`. Local writes require a writable tag. Remote reads
  and writes respect External Access. Type mismatches and unknown source
  values set an error before the destination is changed.
- The writable RemoteElement STRING accepts an ASCII symbol of up to 82
  bytes. Queuing captures the symbol and its resolved start together.
  A new literal subscript uses its own start. A new `[*]` selector uses the
  live RemoteIndex. The unchanged exported symbol keeps its saved
  addressing rules. Unreadable or invalid text completes with ERR 16#0005.
  Prescan preserves edited text and Reset reloads the export. Existing
  exported addresses longer than 82 bytes continue to use the saved endpoint.
- The controller advance after the trigger starts the transfer. The following
  advance completes it before task logic runs, sampling the source then. A
  held true rung does not repeat a completed message. A false rung clears
  `EN` once the request is no longer busy, and the next trigger clears the
  previous `DN` or `ER`. Queuing captures both starts. Out-of-range captures,
  including negative indices, set `ER` and `ERR` `16#0005` when the transfer is
  serviced. The destination is preserved. Prescan clears pending requests
  and status while preserving live index values. Reset restores authored indices.
- The INT `FLAGS` word and the named status members share one value. Its
  bit positions are EW (2), ER (4), DN (5), ST (6), EN (7), TO (8) and
  EN_CC (9). EN_CC starts from the saved CacheConnections setting. A write
  through the named bit, FLAGS.9 or the whole word can change EN_CC on a
  connected control. Writes to an unconnected control leave EN_CC clear.
  TO remains writable. The emulator preserves managed status and reserved
  bits. A cancellation clears TO on completion.
- UnconnectedTimeout is a positive DINT in microseconds. Its default is
  30,000,000. The request captures a deadline when queued. Service checks
  the deadline at the beginning of each advance using committed simulated
  time. At or after the deadline, ER sets with ERR 16#00FE and the request
  performs no transfer. A zero or negative setting reports 16#0003 when
  triggered. Prescan retains the live timeout and Reset restores the default.
  A false scan rearms the instruction for a ladder-controlled retry.
- Ladder GSV and SSV support the named Message instance's UnconnectedTimeout
  with a single DINT or TIME32 tag operand. SSV requires a known positive
  value. A later GSV in the same scan reads the setting immediately. A
  pending MSG keeps its captured deadline. A later scan fault rolls back
  the SSV setting and GSV destination together.
- A connected request without a cached connection spends one extra advance
  opening it. UnconnectedTimeout governs setup. When ST sets, the response
  gets a new deadline from `ConnectionRate × 2^(TimeoutMultiplier + 2)`.
  The positive DINT ConnectionRate is in microseconds and defaults to
  7,500,000. The SINT multiplier ranges from 0 through 7 and defaults to
  zero. The request captures both settings at admission. Expiry and
  cancellation use ERR 16#00FE and preserve the destination.
- Ladder GSV and SSV can read and change ConnectionRate (DINT or TIME32
  in microseconds) and TimeoutMultiplier (SINT) on named connected MESSAGE
  controls. The emulator accepts the modeled multiplier range of 0 through
  7. An invalid or unknown source faults the scan. The same scan can read
  accepted values back. Prescan keeps the values and Reset restores the
  defaults. Changes to a setting and its readback roll back with the scan.
- The emulator retains up to 32 successful cached connections, one per
  control tag. A cached request skips setup when it captures the same raw
  path bytes. Admission with a different path discards the old entry and
  requires a new setup, including a switch between THIS and the explicit
  self route. Clearing EN_CC releases its cache entry immediately. A queued or started request can still finish.
  The bit at successful completion determines whether to retain the
  connection. Setting EN_CC after an idle release still requires a new open.
  Errors and cancellation discard that control's entry. Prescan clears
  retained connections and preserves the live setting. Reset also restores
  the saved setting. A full cache leaves newly completed requests uncached.
  Cache, bit and transfer changes commit together with the scan. Physical
  connection establishment and network sharing remain open.
- The simulated throttle admits up to 16 requests per controller advance,
  with a ceiling of 48 admitted requests. A message that cannot enter
  stays enabled with EW, ST and ER clear. It retries on its next instruction
  scan even if the rung is now false. The advance that starts queued
  requests frees their throttle positions. Waiting requests capture their
  address and start their timeout on admission. TO cancels a waiting
  request on its next instruction scan, and prescan clears the wait.
- Completion uses submission order and snapshots the source span before
  changing the destination. Status and data roll back together if a later
  rung faults in the same controller advance.
  Data Table `REQ_LEN` and `DN_LEN` report 16-bit words. Odd byte counts
  round up to a whole word. A LINT uses four words. UDT lengths include
  alignment padding from the emulator's layout.

This profile is an in-process simulation. External routing, network packet
timing, native MESSAGE layouts and Studio 5000 runtime qualification
remain open. Decorated-only MESSAGE fields remain readable as
saved data. The native Message object inventory is separate.

- [Rockwell Wall Clock Time attributes](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm003_-en-p.pdf)
- [Rockwell Get Attribute List request and response example](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm020_-en-p.pdf)
- [Rockwell CIP Generic DINT destination example](https://literature.rockwellautomation.com/idc/groups/literature/documents/um/dnet-um004_-en-p.pdf)
- [ODVA Identity object reference](https://www.odva.org/wp-content/uploads/2020/06/PUB00123R1_Common-Industrial_Protocol_and_Family_of_CIP_Networks.pdf)
- [Rockwell message instruction](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-03/contents-ditamap/instruction-set/input-output-instructions/message--msg-.html)
- [Rockwell connected message timeout formula and units](https://www.rockwellautomation.com/content/dam/rockwell-automation/sites/downloads/pdf/developerguide.pdf)
- [Rockwell MESSAGE tag scope](https://www.rockwellautomation.com/en-ro/docs/studio-5000-logix-designer/37-02/contents-ditamap/studio-5000-logix-designer/tag-editor-and-data-monitor/work-with-tags/enter-an-msg-tag.html)
- [Rockwell Message timing attributes](https://www.rockwellautomation.com/en-pl/docs/studio-5000-logix-designer/38-01/contents-ditamap/instruction-set/input-output-instructions/access-the-message-object.html)
- [Rockwell communication paths](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-03/contents-ditamap/instruction-set/input-output-instructions/specify-the-communication-details.html)
- [Rockwell message configuration and program-scoped addressing](https://www.rockwellautomation.com/en-ua/docs/studio-5000-logix-designer/38-00/contents-ditamap/studio-5000-logix-designer/configuring-message-instructions.html)
- [Rockwell CIP data table types](https://literature.rockwellautomation.com/idc/groups/literature/documents/um/2080-um002_-en-e.pdf)
- [Rockwell CIP Read Tag and Write Tag services](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm020_-en-p.pdf)
- [Rockwell array index configuration](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm012_-en-p.pdf)
- [Rockwell L5X import/export reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm014_-en-p.pdf)
