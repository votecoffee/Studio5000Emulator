# Controller change-detection GSV

Version `.145` adds bounded `GSV` reads in ladder and Structured Text. Logic reads
the same [simulator Audit Value](simulator-audit-value.md) and explicit
[ChangesToDetect source mask](controller-change-detection.md) used by Controller
CIP attributes 27 and 28. No native controller is contacted during execution.

The supported form is `GSV(Controller,,attribute,destination)`: the Controller
instance operand is empty, and the attribute is `AuditValue` or `ChangesToDetect`.
Class and attribute names are case insensitive. Additional
[Task/Controller configuration reads](gsv-configuration.md) have their own typed
profile. Other classes/attributes and `SSV` remain unfinished. The Controller values and their GSV access are described
in [1756-PM015, Change detection](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm015_-en-p.pdf).

## Destinations and execution

Use a writable scalar `LINT` or two contiguous `DINT` array elements:

```text
GSV(Controller,,AuditValue,AuditValue);
GSV(Controller,,ChangesToDetect,ChangeMaskWords[0]);
```

Declare `AuditValue` as `LINT` and `ChangeMaskWords` as `DINT[2]`. A DINT array
reference without an index starts at its first element. Indexed destinations,
ordinary alias resolution and Program-local scope retain the memory model's
existing rules. Writes preserve all 64 bits: the low DINT is first, followed by
the high DINT. Negative signed values retain the original bit pattern.

Prescan and false ladder paths leave destinations unchanged. A Structured Text
call executes only when its containing statement is reached. Each executed read
uses the current simulator epoch or configuration; it does not advance the Audit
Value. A stopped controller's tag retains its last scanned value until execution
reads the newer epoch, just like other modeled logic destinations.

The complete destination span is validated before writing. Scalar DINTs, short
arrays, bits, constants and other element types are rejected. Indirect bounds
are rechecked at execution. A failed read or later instruction fault rolls back
the scan's writes. Structured Text FOR validation checks both written DINTs so
the second word cannot overwrite a bound or step dependency.

The historical native checkpoint below applies to the audit-value profile.
Configuration GSV reads have separate software-model checks.

## Availability and validation

Both reads require the existing explicit, supported source-mask profile. Unknown
or missing settings block coverage before execution, including unreachable
instructions. An invalidated runtime audit epoch remains unavailable. Unsupported
profiles never become a zero value.

Eighty-nine focused checks pass, covering both languages, bit preservation,
prescan, false paths, current-epoch reads, CIP agreement, aliases/local scope,
destination bounds, rollback and FOR dependencies. An owned four-GSV fixture
also passes native v35 offline import/save/reopen/export and reloads into the
execution model with all four instructions preserved. The rebuilt executable's
frozen modules execute that fixture successfully. All 99 app modules match
source/build/appliance, and the executable resources, packaged assets and served
webpage version agree on `.145`.

The live fixture's two LINT and two DINT-pair destinations match Controller
attributes 27/28 and symbolic CIP tag reads after a scan. Twenty-four repeated
web Run requests preserve the epoch and do not repeat the mode event. A Program
step refreshes the last scanned values without advancing the audit sequence.

The SDK mode trial passes Go Online/Offline and both SDK/web control directions
across 109 verified requests, with six updates for six transitions. Supported
Program-mode NOP import and reconnect pass across 182 requests, preserving the
four GSV instructions and audit epoch. The next scan reads the updated epoch.
An initial mode trial had one prematurely ended HTTP response; it retained
confirmed Offline/cleanup and no reported SDK fault. Its evidence is kept
separately from the successful fresh trial.

The independent fixture download still stops at its preparation-result encoding
boundary across 176 verified requests. It preserves the active model and audit
value. The SDK trials confirm actual Offline, endpoint cleanup, unchanged
originals and no reported SDK server fault. No Studio GUI monitoring acceptance
or completed native transfer is implied by these checks.

This adds instruction reads to the existing simulator model. It does not supply
physical memory statistics, State Detection signatures, complete native
upload/download or the full Test/Untest/Assemble lifecycle.
