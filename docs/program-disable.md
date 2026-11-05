# Program DisableFlag

Ladder and Structured Text can suspend an ordinary scheduled Program with
`SSV(Program,Name,DisableFlag,Command)`. The command is a scalar SINT tag.
Zero enables the Program and any nonzero SINT disables it. GSV reports the
effective flag as 0 or 1 in a scalar SINT or DINT tag.

```text
SSV(Program,FastProgram,DisableFlag,FastProgramDisable);
GSV(Program,FastProgram,DisableFlag,LiveFastProgramDisabled);
SSV(Program,THIS,DisableFlag,SelfDisable);
```

## Execution and rollback

The flag takes effect at the instruction. The active Program invocation can
finish. Every subsequent Program entry checks the current flag, even when
multiple releases share an advance or an Event is dispatched synchronously.
The Task still releases and runs any other scheduled Programs. Skipped Programs
retain their values and last measurements. Their missed invocations are
discarded. The first execution after an enable transition asserts S:FS once.
This transition uses the existing Program state and does not run a new prescan.

Skipped instructions avoid live operand reads. A reached invalid index or
unknown source faults. A later fault rolls back changes to flags, first-scan
history, values, measurements and scheduling for the entire advance.
Run entry retains the flag and applies normal Run-entry prescan. Detached
routine replacement carries the committed flag into its new runtime.
Reset and project reload restore the imported enabled state.

## Scope and readback

This v35 5580 profile requires an ordinary scheduled Standard caller and
target. A target must have a main routine and explicit `Disabled="false"` in
the imported L5X. THIS selects the calling Program. Imported disabled Programs,
folders, unscheduled Programs, Safety, AOIs and isolated routine harnesses
remain outside this control profile.

The existing source-bound, read-only Program protocol byte 19 reflects a
committed runtime flag. The L5X declaration stays the same. Native write
services and Studio 5000 acceptance remain separate.

## System Lab

Open **System lab** and step 25 ms. Set `ControlFastProgram` for the ladder
control and `ControlSlowProgram` for the ST control. ST also needs `ReadConfig`,
which starts enabled. The commands `FastProgramDisable` and
`SlowProgramDisable` start at 1. After the controls run, their GSV readbacks
`LiveFastProgramDisabled` and `LiveSlowProgramDisabled` show 1. On later steps,
`FastCount` and `SlowCount` stay put while their Tasks keep releasing.

Set both commands to zero, step to apply the change, then step again.
`FastFirst` and `SlowFirst` each increment once when their Programs resume.
Use `TaskStartIndex=1`, `ReadTaskStarts=true` and `TaskStartDivisor=0` to
force a later fault and observe rollback. Restore the divisor to 1 to retry.

The operand types follow the installed v35 Program object help (14638).
See Rockwell's [program enable/disable example](https://www.rockwellautomation.com/en-id/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/input-output-instructions/gsv-ssv-programming-example.html)
and [Logix Design Considerations](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm094_-en-p.pdf)
for the Program first-scan behavior.
