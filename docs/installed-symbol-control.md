# Installed Symbol Control readback

Version `26.1024.104524` returns Symbol attribute `6`, named **Symbol Control**
by the installed v35 schema, from the validated headers of an unchanged,
source-equivalent installed download. Previously, ordinary backed tags always
returned the model descriptor's zero control word.

The value is the original four bytes received from that download. Its bits stay
opaque: they do not set simulator flags, permissions, constant state, addresses
or executable code. Symbol value/header addresses and Data Table links retain
their existing backed model definitions.

## Source checks

Readback requires the native compatibility endpoint, a committed installation,
the same original identity and Project, matching Symbol instance and Type, and
the complete unchanged incremental effect ledger. Each read checks the current
header bindings and retained effects. Contradicted or altered records fail
rather than supplying a guessed control value.

Version `26.1024.111516` compares native header Type with the backed Table
layout. For packed BOOL arrays the public Symbol remains `0x20C1` with logical
bit dimensions, while the downloaded header/Table uses `0x20D3` with word
dimensions. Both must still refer to the same current storage cell.

Before installation, outside native compatibility, or after routine editing,
the existing model descriptor behavior remains in use. Supported value writes
do not change source declarations or the retained control word.

## Evidence and validation

A saved successful upload contains nonzero controls in ordinary BOOL Symbol
descriptors while the two-BOOL emulator fixture reports zero. Both use Type
`0x00C1` and element size `1`. The extended v35 Symbol definition identifies the
field; it does not establish meanings for all its bits. Original control words
were already retained by the temporary download-header model.

Four signed TCP tests cover precommit versus installed readback, unchanged
values and links, later value writes, modified effects, changed source/Type and
edited-project fallback. Native upload acceptance is assessed separately from
these software checks; the [routine-upload checkpoint](routine-upload.md)
records the current reconstruction boundary.

With these original controls, the owned one-rung, two-BOOL `XIC`/`OTE` fixture
completes native SDK `UploadAsync` on `26.1024.104524` across 936 verified
requests. The complete source contains two IOI operands. Download, save,
reopen and Go Online also succeed; upload preserves source/model/audit state
and confirms Offline cleanup without an SDK fault. Saving an uploaded ACD
remains unverified.
