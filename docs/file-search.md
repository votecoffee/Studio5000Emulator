# File search and compare

The explicit v35 ControlLogix 5580 ladder profile supports:

```text
FSC(Control,?,?,ALL,Array[Control.POS]>=Limit);
FSC(Control,?,?,2,Array[Control.POS]>=Limit);
```

LEN/POS use saved CONTROL members; pseudo-operands do not initialize them on
each scan. ALL searches the remaining region in one execution. A positive DINT
immediate selects comparisons per scan for numeric mode. Each comparison also
consumes the global instruction budget. LEN is bounded to 4096.
See [implementation](../source/logixlab/file_search.py).

## Search state

Prescan does not initialize state. A fresh enabled search starts at saved POS;
with EN already set, the next pass resumes after the last compared element.
A true comparison sets FD/IN and leaves POS at the matching element. IN pauses
further work; clear it to resume while enabled. The last element also sets DN.
ER inhibits execution and is not modified by this profile.

This software profile retains the last compared POS after exhaustion, rather
than inventing a universal end-cursor contract. Vendor prose and flowcharts
differ in their cursor presentation; native final-position parity remains
unverified. A supplied POS already equal to LEN completes without comparing.

Numeric mode starts on an enabled scan, then keeps processing its per-scan
budget even if the rung goes false. Completion retains EN when the input is
true and clears EN when it is false. On the next false call with IN clear,
DN/EN/POS reset; FD is retained. In ALL mode, a false incomplete call clears EN
without restarting work. IN or ER inhibits these false-rung changes.

FSC's rung output follows incoming power, independently of a match. Examine
FD/IN/POS in logic to act on a result. Zero LEN completes without reading data.
Negative or excessive lengths/positions and invalid accesses stop and roll back
the modeled advance, including previous comparisons, other writes and scheduler
state. Native major/minor fault records and partial effects remain unfinished.

## Expressions and limits

FSC reuses the bounded CMP grammar: SINT/INT/DINT/REAL arithmetic/comparisons,
BOOL logic and supported STRING/user-string comparisons. CONTROL.POS can index
arrays, including paired arrays in the same expression. Type-checking uses a
structural cursor, so unknown saved data is consumed only when actually compared.
No short-circuit assumption hides a required unknown value or invalid access.

Existing CMP expression limits still apply. Wider/unsigned/LREAL types, BCD
expression functions and additional native conversion forms remain unfinished.
[INC mode](file-incremental.md) now supports one comparison per enable edge for
idle-source controls, with explicit inhibit/rearming and transactional progress.
Saved active INC controls remain blocked; native internal state stays unqualified.
FSC inside AOIs and ST/FBD instruction calls remain unsupported. CONTROL aliases
and constant source arrays are supported; CONTROL must be writable.

## Stats Lab

Set Search on and step. SearchControl finds Values[2]=6 above SearchLimit=5,
setting FD/IN. Step again to observe the pause. Clear SearchControl.IN and step
to find Values[3]=8, setting DN as well. Clear IN and set Search off, then step
to reset the cursor; Reset also clears control state while retaining LEN/data.

Set BatchSearch on and step to compare positions 0 and 1 against BatchLimit=9.
Set BatchSearch off and step: the active numeric search still checks positions
2 and 3, completing without a match. The next false scan clears DN/POS.
Values[4]=999 is outside the configured search and remains untouched.
See [StatsLab.L5X](../source/samples/StatsLab.L5X).

The baseline uses installed v35 help 14515 and its true/false/common flowcharts,
plus 14509/14519/14521 mode diagrams. Rockwell's published
[FSC reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/37-01/contents-ditamap/instruction-set/array-file-misc-instructions/file-search-and-compare-fsc.html)
provides context. Bounded software checks do not establish native controller or
Studio acceptance.
