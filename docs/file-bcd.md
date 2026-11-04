# BCD expressions in FAL and FSC

App `26.1104.123302` adds FRD/TOD to ladder FAL transforms and FSC searches in
Standard v35 ControlLogix 5580 projects (`1756-L81E` through `1756-L85E`).
These instructions opt into the existing narrow [CPT](cpt-bcd.md) and
[CMP](cmp-bcd.md) conversion profiles. Numeric inputs/results are SINT, INT or
DINT with checked DINT intermediates. FSC retains its existing eager Boolean
composition. Wider/REAL/string BCD mixtures and ST forms remain separate.

```text
FAL(Calc,?,?,ALL,Decoded[Calc.POS],FRD(Packed[Calc.POS]));
FAL(Calc,?,?,2,Packed[Calc.POS],TOD(Decimal[Calc.POS]));
FAL(Calc,?,?,INC,Output[Calc.POS],FRD(TOD(Input[Calc.POS]))+1);
FSC(Find,?,?,ALL,FRD(Packed[Find.POS])=Expected);
```

FRD decodes eight weighted nibbles after promoting a signed narrow argument:
FRD(16#1A)=20, FRD(-1)=166666665 and its low byte is 169. TOD accepts
0..99999999 and returns a signed DINT pattern, including
TOD(99999999)=-1717986919. FRD(TOD(99999999)) returns 99999999. Standalone
conversion widths remain separate. FAL destination results must fit their
declared numeric range; TOD(99)=153 cannot be stored in SINT. Every required
intermediate must fit DINT. Native numerical/status equivalence is unverified.

## Modes and progress

The existing file algorithms and CONTROL contracts are retained:

- ALL handles the remaining work in the current advance. FAL writes sequentially,
  so source/destination overlap can propagate. FSC stops at its first match,
  setting FD/IN and retaining the matched position; clear IN to resume after it.
- Numeric modes handle the specified number of elements per scan. Once active,
  work can continue while the rung is false. A false rung does not hide missing
  data in an active operation. Existing completion and following-scan cleanup
  rules remain.
- INC handles one element per observed false-to-true enable edge. A held true
  call does not reevaluate its expression. Failed work restores the pending
  edge so corrected input can retry the same element. Search inhibit must be
  cleared and a false enable observed before the next edge can advance.

LEN/POS use saved CONTROL members; neutral-text operands remain `?,?`. The
existing 4096-element work bound, last-processed cursor policy and idle-source
INC restriction remain. Hidden progress uses canonical CONTROL identities and
participates in rollback. RES clears that progress; Run entry retains it.
Saved active INC controls, native hidden state and native cursor/flag parity
remain unqualified.

Structural preflight checks expression types, references and shapes without
reading saved values or dynamic indices. False idle, held INC, completed,
error-inhibited, search-inhibited and zero-length paths retain their existing
lazy reads. Reached iterations require all arguments, including under true OR,
false AND or zero masks. Full FAL writes establish unknown selected results;
outside elements and member guards remain unchanged. Aliases, UDT member arrays,
function indices and existing AOI exact InOut/local arrays share these rules.
Numeric continuation in AOI EnableInFalse uses the same expression profile.

Unknown data, conversion ranges, indices, destination overflow and later faults
restore the entire advance, including earlier iterations, CONTROL state, hidden
INC progress, task timing and warm AOI bindings. Prior successful advances stay
committed. Completed prescan remains a separate lifecycle boundary. The parser
options are explicit; generic expressions, direct conditions and ST retain their
existing function sets. No mnemonic, language form or native alias is added.

## Control lab

Select **BcdFiles** and Step once while its three mode gates are false. The
input arrays hold four data elements and an outside guard; output data starts
unknown. BcdFindValue starts at 21. To reset between examples, turn all three
mode gates off, enable BcdFileReset for one Step, then turn Reset off. Reset
retains array data and LEN while clearing all six controls and hidden progress.

Enable BcdFileAll and Step. BcdDecoded becomes 12,21,20,99 with guard 901.
BcdAllCalc is done at position 3; BcdAllFind stops at position 1 with FD/IN.
Set FindValue=99, clear BcdAllFind.IN and Step to find position 3. To demonstrate
rollback after earlier writes, reset the controls, set Packed[0]=34 and
LateDivisor=0, then enable All and Step. Restore the divisor to 1 and retry;
Decoded[0] becomes 22. Restore Packed[0]=18 before the next example.

After reset, enable BcdFileNumeric and Step. Repacked[0..1] become 18 and 33.
Disable Numeric and Step again: active work completes Repacked[2..3] as 32 and
153, with guard 902. NumericCalc has DN true and EN false. Another false scan
clears its completed cursor. NumericFind's match/inhibit state is independent.
A negative Decimal[2] before continuation demonstrates a required-range fault;
restore it to 20 to finish the pending work.

After reset, enable BcdFileIncrement and Step. Incremented[0] becomes 13. Held
true does not advance; Decimal[0]=-1 can remain while held. Disable/Step and
enable/Step to process row 1 as 22 and find the packed value 21. A bad Decimal[1]
on this edge rolls back; correcting it lets the same pending edge retry. Clear
IncFind.IN, set FindValue=99, and pulse through rows 2 and 3: results become 21
and 100, and the search finds position 3. Guard 903 remains. Restore valid input
values before reset/reuse. Monitoring does not advance the stopped simulation.

Source basis: installed v35 FAL (14504), FSC (14515), CPT (14597) and CMP (14592).
The current published
[FSC reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/array-file-misc-instructions/file-search-and-compare-fsc.html)
uses newer BCD_TO/TO_BCD spellings; this increment targets installed v35 FRD/TOD.
Native sampling, faults, partial effects, packed layout, lifecycle and Studio
acceptance remain unverified. See [FAL](../source/logixlab/file_arithmetic.py),
[FSC](../source/logixlab/file_search.py),
[focused cases](../source/tests/test_file_bcd.py),
[ControlLab.L5X](../source/samples/ControlLab.L5X) and
[existing incremental rules](file-incremental.md).
