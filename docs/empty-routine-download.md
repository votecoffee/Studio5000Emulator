# Empty ladder routine downloads

Version `26.1024.013050` accepts the observed v35 download shape for a routine
whose original, source-bound L5X explicitly contains an empty `RLLContent`.
The routine remains present in the native inventory and interpreter.

## Transfer profile

The native SDK sends the empty routine's source container without a preceding
compiled-code component. Its compressed XML retains the ordinary v35 target
header but omits `RLLContent`. A following attachment has the exact DWORDs
`2, 5, 0, 0`, with a four-byte declared payload. No code marker, ELF or NOP is
invented. Reads of the absent code component remain unavailable.

Source framing, compression extents, padding, target name, Program reservation
and complete batch coverage retain their existing checks. The source and
attachment each have their own ordered effect and byte-for-byte readback.
Nonempty routines still require code, matching source and their counted
attachment with the original code marker.

The omitted-content form is accepted only when the loaded routine has no
problems and explicitly contains zero rungs. The download decoder cannot turn a
nonempty, missing or protected source declaration into an empty routine. The
ordinary edit/import decoder continues to require `RLLContent` and rungs;
the separate upload decoder is unchanged.

## Source preservation

The native Offline import/save/reopen control accepts an explicit empty
`RLLContent`, but its re-export omits that element. Such an export remains
blocked as missing or protected content. The tested source association retains
the exact explicitly empty XML imported into the native ACD. It does not repair
an arbitrary export or infer empty logic from absence.

An installed download serves the original accepted source bytes. Changed source,
logic, native catalogs or download installation revoke readback as before.
The interpreter executes its independently validated source model; native code
execution and controller equivalence are not established.

## Native checkpoint

An owned two-routine fixture, with an empty Main routine and a retained ordinary
Reporting routine, completes native SDK download/save/close/reopen/Go Online
across 433 verified signed requests. Original files and modeled values remain
unchanged, with zero scans, actual Offline cleanup and no reported SDK fault.
The complete 1,748-event journal replays identically offline; that replay checks
framing and does not reverify message authentication.

The preceding runtime rejects the same fixture after 277 verified requests at
the source-component sequence. Its complete retained batch establishes the
omitted code, omitted XML content and zero-count attachment handled here.

A separate SDK process reopens the saved ACD and goes Online across 74 verified
requests. Upload into that saved baseline still fails Program collection after
348 requests. The first bulk reply describes the nonempty Reporting routine:
all 22 fields succeed, with no subsequent source-read request. These outcomes
preserve source/model and installation, confirm Offline cleanup and report no
SDK fault. They do not establish general Routine upload support.

A second fixture contains only the explicit empty Main routine and preserves
the same 14 saved tag values. Native download/save/reopen/Online succeeds across
433 requests with a complete 1,751-event recording. Upload into its saved ACD
fails after 349 requests at that empty routine's first bulk reply: all 22 fields
succeed, but source retrieval is not requested. Its complete 1,427-event
recording replays identically offline. This reproduces the unresolved metadata
boundary without a nonempty routine preceding it; it does not identify the
native client's rejection cause. Source/model/installation and Offline cleanup
remain checked, with no reported SDK fault.
