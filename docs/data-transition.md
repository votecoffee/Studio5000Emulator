# DINT ladder data transition

App `26.1030.081135` adds DTR to the bounded v35 ControlLogix 5580 profile.
Source and Mask are DINT scalar tags or bounded integer immediates. Reference
is a writable DINT scalar tag, array element or represented member. Existing
aliases, indirect element references, program locals and AOI bindings apply.

```text
XIC(TransitionEnable)DTR(TransitionSource,TransitionMask,TransitionReference)OTE(TransitionPulse);
XIC(TransitionPulse)ADD(TransitionCount,1,TransitionCount);
```

DTR compares the selected source bits with the entire previous reference. A
difference on a true rung produces true rung-out and saves the masked source
as the new reference. An unchanged comparison produces false rung-out. This
detects changes in either direction; it needs no separate one-shot bit.

## Prescan and false execution

During prescan and false execution, DTR refreshes the reference from Source
AND Mask and produces no pulse. A source change while the preceding condition
is false is therefore already recorded when the condition becomes true.
Run entry primes the reference again without advancing simulated time.
The model's deferred import preview preserves the saved values until Run entry.

A disabled MCR body still calls DTR with false power, so its reference refresh
still occurs. Skipping the instruction with JMP or an uncalled subroutine has
different behavior: normal execution never reaches that site. Existing lexical
prescan visits the routines included in the engine's execution plan.

Each site uses its explicit Reference operand. Separate references are independent;
sites sharing one reference observe earlier writes in scan order. Overlapping
source/mask/reference bindings are read before replacement. AOI prescan and
EnableInFalse routines use the existing parameter and reference bindings.

## Values, faults and qualification

Bit comparisons cover all 32 bits. Results with bit 31 set are stored as signed
DINT values. Decimal immediates must fit a signed DINT; hexadecimal, octal and
binary bit patterns can cover all 32 bits. Narrow, unsigned, LINT, REAL, BOOL,
whole-array and constant-reference operands are rejected in this profile.
Other controller profiles and ST/FBD calls remain unqualified.

Required unknown Source or Mask values fault even on a false rung or with a
zero mask. A true comparison also requires a known prior Reference. False
execution and prescan can establish an unknown reference. A later fault rolls
back reference changes, downstream outputs and other writes with the existing
whole-advance transaction. Prescan also rolls back as a unit if it fails.

Coverage reports include `data_transition`; traces show DTR's incoming and
outgoing rung conditions. Full native operand, status, fault and timing parity
has not been established.

## Try Bit Lab

Choose **Bit lab** and step once. Change TransitionSource to 1 and step:
TransitionPulse turns on and TransitionCount increments. A second unchanged
step clears the pulse. TransitionMask starts at 255; changes above bit 7 do
not trigger it. Change the mask to choose other bits.

Set TransitionEnable=false and change the source. Stepping updates
TransitionReference while the pulse stays false. Re-enabling with that same
source produces no stale pulse. Set FaultDivisor=0 to demonstrate a late scan
fault; correct it to 1 before retrying. The reference, transition count and
earlier packing writes all participate in rollback.

See [BitLab.L5X](../source/samples/BitLab.L5X),
[implementation](../source/logixlab/data_transition.py) and
[checks](../source/tests/test_data_transition.py). The installed v35 help and
Rockwell's [DTR reference](https://www.rockwellautomation.com/en-id/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/special-instructions/data-transition--dtr-.html)
document the instruction's comparison and prescan/false reference updates.
Software checks remain separate from native controller acceptance.
