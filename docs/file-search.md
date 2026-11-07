# File search and compare

The explicit v35 ControlLogix 5580 ladder profile supports:

```text
FSC(Control,?,?,ALL,Array[Control.POS]>=Limit);
FSC(Control,?,?,2,Array[Control.POS]>=Limit);
```

Scans use live CONTROL.LEN/POS, which can receive
[literal initializers](control-operations.md#literal-len-and-pos-on-import).
ALL searches the remaining region in one execution. A positive DINT
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
A handler can
[clear a reached array subscript fault](controller-handlers.md#recover-file-arithmetic-and-search-array-faults)
in a whole-project scan after the emulator restores the search CONTROL.
A reached negative LEN or POS can be
[cleared as Type 4 Code 21](controller-handlers.md#recover-a-negative-file-cursor).
Unrecovered faults and other errors roll back the advance, including other
writes and scheduler state. Native major/minor fault records and partial
effects remain unqualified.

## Expressions and limits

FSC reuses the bounded CMP grammar: SINT/INT/DINT/REAL arithmetic/comparisons,
BOOL logic and supported STRING/user-string comparisons. CONTROL.POS can index
arrays, including paired arrays in the same expression. Type-checking uses a
structural cursor, so unknown saved data is consumed only when actually compared.
No short-circuit assumption hides a required unknown value or invalid access.

Integer division now follows the [narrow expression profile](integer-expressions.md).
Existing CMP expression limits still apply. [LINT/unsigned searches](integer-files.md)
share the exact wide/mixed CMP profile. [Binary64 searches](#binary64-searches)
add an LREAL-selected profile. Narrow BCD forms are linked below.
[INC mode](file-incremental.md) now supports one comparison per enable edge for
idle-source controls, with explicit inhibit/rearming and transactional progress.
Saved active INC controls remain blocked; native internal state stays unqualified.
[RLL AOI execution](aoi-file-operations.md) now supports exact InOut/local
operands, frame-scoped expressions and canonical per-CONTROL progress.
ST/FBD instruction calls remain unsupported. CONTROL aliases
and constant source arrays are supported; CONTROL must be writable.

## Binary64 searches

App `26.1105.174720` adds LREAL comparisons to ladder FSC in ALL, positive
numeric and idle-source INC modes. An LREAL tag or floating L/l literal selects
the [binary64 evaluator](lreal-expressions.md) for all numeric subexpressions.
For example, a saved LREAL value of 1.0000000000000002 is greater than 1.0L.
REAL tags and unsuffixed floating literals retain float32 precision before
promotion. Decimal L/U/UL constants are checked at their declared widths before
conversion. Large integer inputs can round during binary64 conversion.

The expression must produce a BOOL result. The six numeric relations and
Boolean composition work with the same eager operand evaluation as CMP. An
unknown or arithmetic fault on one side still faults when the other side
already determines the Boolean result. Numeric bitwise and FRD/TOD forms
remain outside the binary64 profile. Existing narrow, wide integer, REAL and
string searches use their respective expression rules.

In **Stats lab**, enable `Binary64Find` and step. The search matches at
`Binary64FindControl.POS = 1` and sets FD/IN. Clear IN and step to resume at
position 2 and set DN. Set `Binary64Divisors[1]` to 0 before starting a fresh
search to see the advance roll back. Restore the divisor to 1 and retry.

Enable `Binary64FindBatch` for one comparison per scan. The search continues
after the rung goes false and finds 3.5 at position 2. Enable
`Binary64FindStep` to find the binary64 difference above 1.0 at position 0.
Clear IN, scan with the enable false, then enable it again to find position 1.
Native cursor, fault and Studio import behavior remain unverified.

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

[BCD file expressions](file-bcd.md) now qualify FRD/TOD in narrow FAL/FSC
operands for existing ALL/numeric/INC modes. Conversion and progress/rollback
rules are explicit; wider types, ST and native parity remain separate.
