# Ethernet counter model

Version `.56` adds read-only Ethernet Link (`0xF6`, instance 1) counter
attributes `4` and `5` on Linux interfaces using the `e1000e` driver. This is the
driver used by the tested VMware appliance. Other drivers and platforms retain
unsupported-attribute replies for these optional fields.

The reader uses `ETHTOOL_GDRVINFO`, `ETHTOOL_GSTRINGS` and `ETHTOOL_GSTATS` through
read-only ioctls, plus sysfs `rx_dropped`. It requires no `ethtool` executable,
adapter changes or elevated privileges. Table lengths, names, duplicate entries,
counter types and derived packet counts are validated before publishing a sample.
No kernel source is included in the application.

## Coverage and semantics

Attribute `4` is an ordered structure of eleven UDINTs. Broadcast and multicast
driver counts form the non-unicast count; subtracting that count from the
driver's good-packet total forms the unicast count. Receive discards combine
sysfs drops and driver missed packets. Byte, error and transmit-discard fields
use the corresponding driver counters.

Attribute `5` is an ordered structure of twelve UDINTs. Supported fields include
alignment/FCS errors, single/multiple/excessive/late collisions, deferred
transmissions, carrier errors and oversize frames.

These fields describe the host driver. In particular, its good-packet totals
do not establish all RFC MIB delivery/request semantics or native controller
counter equivalence. The driver table is defined in the Linux
[e1000e counter implementation](https://github.com/torvalds/linux/blob/master/drivers/net/ethernet/intel/e1000e/ethtool.c).
The CIP field order follows the installed v35 attribute definitions and can be
compared with the interface/media fields in
[RFC 1213](https://www.rfc-editor.org/rfc/rfc1213.html) and
[RFC 1643](https://www.rfc-editor.org/rfc/rfc1643.html).

The following fields have no unambiguous provider and use **zero on the wire**:

| Structure | Unimplemented fields |
| --- | --- |
| Interface counters | InUnknownProtos |
| Media counters | SQETestErrors, MACTransmitErrors, MACReceiveErrors |

The trace/API `ethernet_counters` object lists these names and uses JSON `null`
for their values. A zero in these wire positions is a model placeholder. Linux
`rx_nohandler`, FIFO errors and missed packets are not substituted for unrelated
unknown-protocol or internal MAC errors. Implementing the wire structures does
not establish complete Ethernet/CIP conformance.

## Sampling and access

Only reads requesting attribute `4` or `5` invoke the counter provider. One
sample supplies the entire attribute list, including repeated fields. A
one-second cache limits driver calls; the API describes the last sample, its
age and whether it is stale without querying the driver again. Driver and sysfs
reads are close in time but do not form an atomic hardware snapshot.

Wire counters use the low 32 bits of observed 64-bit values. Inconsistent samples,
unsupported drivers and provider failures leave the attributes unavailable;
an expired failed sample is not replaced with healthy-looking zeros. Other
network metadata and the PLC execution model remain available.

Get-and-Clear (`0x4C`) for these attributes returns permission denied. The endpoint
does not authorize clearing host diagnostics, including when ordinary tag writes
are enabled. Native anonymous sessions also deny counter clears and setters.
This model neither starts packet capture nor changes host counter baselines.

## Validation

The `.56` suite passes 797 tests on Windows and Linux with their expected
platform skips. The rebuilt appliance passes 190 wire checks, including live
counter refresh and denied clears. Its native SDK connection/Offline cleanup
sequence succeeds with 82 verified signed requests.

A deployed upload verifies 197 signed requests, retains 12 scalar reads and
12 Symbol descriptors, accepts the full Ethernet counter/status list, then
reaches the Time Sync list with 18 unsupported fields. Upload still fails with
`RxCsE_UPLOAD_OF_CONTROLLER_COLLECTION_FAILED`. Generic BOOL/DINT tag reads
remain `RxDA_E_NO_ONLINE_ADDRESS`, without sending a tag-read packet. Original
ACD bytes, modeled values and zero scan count were preserved by these checks.
