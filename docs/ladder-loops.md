# Ladder FOR and BRK

App `26.1030.105135` adds a bounded v35 ControlLogix 5580 software model for
ladder indexed routine loops. Choose **Loop lab** in the web page, or launch
with `--sample LoopLab`. The initial example sums 0 through 4: Total is 10,
Iterations is 5, and Index finishes at 5. Enable BreakEnabled to stop at index
2 before adding it: Total becomes 1, Iterations becomes 3, and Index stays 2.

```text
XIC(Enabled)FOR(Accumulate,Index,Start,Finish,Increment)OTE(Completed);
```

The five operands are the routine name, index, initial value, terminal value
and step. The index must be a writable scalar DINT. Static members, array
elements and aliases work. Initial/terminal/step operands accept scalar SINT,
INT or DINT tags, or signed DINT literals. Indirect operand selections, wide
integers, floating values, bit selections and constant indices are blocked.
The called routine belongs to the same program, cannot be its main routine,
and has no SBR/RET parameters. Supported RLL and ST routines can be targets.
FOR and BRK instructions themselves are ladder only.

## Loop execution

On true rung input, FOR writes the initial value into the index. A nonnegative
step continues while index <= terminal; a negative step continues while index
>= terminal. The target runs once per matching index. After each normal return,
FOR adds the step to the current index. An empty range still assigns the initial
value. False rung input leaves the index and target untouched.

This model reads initial before assigning index, terminal and step before each
test, and index and step again after the routine returns. Thus a routine or
preempting Event may change the next iteration. Native live-operand sampling
and alias behavior have not been demonstrated on a controller.

BRK() on true rung input exits the nearest active FOR, including through nested
JSR calls. It skips the remaining routine instructions, return-value transfer
and that iteration's index increment. Execution resumes after FOR. A nested
FOR catches its own break; outer iterations continue. False BRK or BRK without
an active FOR has no action. RET()/TND() end only the current routine call;
FOR then increments and checks again.

The installed v35 flowchart treats zero step as nonnegative. A zero-step loop
therefore runs until BRK, a changing operand or the instruction budget stops it.
ST FOR/EXIT has a separate profile and rejects zero step.

## Scheduling, lifecycle and faults

FOR and JSR share the existing 25-level call limit. Each FOR test consumes
instruction budget, even for an empty target. DINT index overflow, unknown
required values, budget exhaustion or a later error rolls back the entire
advance: tag values, timer history, time, first-scan state and scheduler counts.
These are simulator faults; controller overflow flags and watchdog behavior
remain unimplemented.

Project prescan visits each active routine once without running loop iterations
or transferring parameters. Harness planning follows FOR targets as well as JSR
targets. Run entry and supported detached routine replacement rebuild the same
validated call graph. Repeated calls retain ordinary target instruction history.

Each task invocation has a separate call stack. A higher-priority Event task
cannot break the suspended caller's loop or consume its SBR/RET parameters.
Returning from the Event restores the caller's frames. Periodic and deferred
Event execution still uses the scheduler's shared transaction and budgets.

Disabled MCR bodies give FOR false rung input. BRK within an MCR zone remains
blocked. Recursive call graphs, FOR/BRK within AOIs, SFC targets, native postscan,
other controller profiles and native scheduling/fault parity remain unfinished.
No changes to Studio upload/download or native online-edit support are implied.

Operand and flow references are the installed Studio v35 help pages for FOR and
BRK, cross-checked with Rockwell's
[General Instructions reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm003_-en-p.pdf).
The public example is synthetic; vendor help assets are not distributed.
