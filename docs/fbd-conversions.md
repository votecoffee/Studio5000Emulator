# FBD remainder, truncation and BCD conversions

MOD, TRN, TOD and FRD execute as FBD Blocks in the bounded v35 ControlLogix 5580
profile. MOD extends the existing finite REAL math model. TRN adds a logical
FBD_TRUNCATE record. TOD/FRD share the existing ladder BCD calculations and use
FBD_CONVERT, also used by the supported NOT block. No RLL/ST record-call
overloads or implicit wire conversions are added.

| Block | Logical record | Inputs | Dest |
| --- | --- | --- | --- |
| MOD | FBD_MATH | SourceA, SourceB: REAL | REAL remainder, with the dividend's sign |
| TRN | FBD_TRUNCATE | Source: REAL | DINT, truncated toward zero |
| TOD | FBD_CONVERT | Source: DINT | Packed BCD as a signed DINT bit pattern |
| FRD | FBD_CONVERT | Source: DINT | DINT weighted-nibble decimal value |

Each record also contains BOOL EnableIn and EnableOut. MOD uses host fmod on
finite float32 inputs and rounds the result to float32. It preserves negative
zero and does not use Python's divisor-sign modulo rule. Zero divisors fail the
advance; the native zero-result/minor-fault path is not implemented.

TRN reads a finite float32 value and truncates toward zero. The result must fit
signed DINT; overflow fails rather than wrapping or substituting a value. REAL
representation matters: 2147483647 rounds to 2147483648 and is outside this
destination profile; 2147483520 and -2147483648 are representable and accepted.
Missing exported fields remain unknown rather than taking declaration defaults.

TOD accepts 0 through 99999999. Its eight packed digits may set the DINT sign bit;
80000000 becomes -2147483648. FRD decodes all eight weighted hexadecimal nibbles,
including A through F: 16#1234567E becomes 12345684, and all bits set becomes
166666665. Negative packed values are bit patterns. TOD's native out-of-range
saturation/minor-fault behavior is excluded; those inputs fail the advance.

Prescan retains enables/Dest for all four forms. Connected false EnableIn clears
enables and retains Dest without reading operands; unwired enable executes.
Skipped calls retain outputs. Direct Dest writes survive disabled/skipped calls
and enabled execution replaces them. There is no hidden conversion state. Run,
Continuous/Periodic/instruction-only Event tasks, routine harnesses and supported
detached RLL caller replacement use the existing lifecycle/transaction rules.
Required unknown/nonfinite/range failures and later errors roll back values,
enables, outputs, trace, time and scheduling for the whole advance.

Choose **FBD conversion lab** for `FBDConversionLab.L5X`: 20 roots, five blocks,
16 nodes and 17 wires. Value 17.75 and Divisor 5 produce Remainder 2.75 and
Truncated 2. DecimalInput 12345678 passes through TOD/FRD; RawBCD 16#1234567E
decodes separately. BlockEnable gates all five blocks; ExecuteGraph skips them.
FaultDivisor zero demonstrates a later ladder error; restore valid inputs to retry.

The graph inventory is 63 forms: 23 shared ST-call names, 34 common RLL names and
six FBD-only forms. RLL remains 101 and ST calls 29. The 222-entry type catalog
has 54 dedicated bounded models and 168 without one. FBD_CONVERT is classified
with conversion records; its existing NOT model remains available.

Schemas and execution tables were checked against installed v35 help 14620.htm,
14671.htm, 14674.htm and 14675.htm, with Rockwell's
[general-instruction reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm003_-en-p.pdf)
as corroboration. Wider/mixed types, LREAL, tagless Functions, additional aliases,
native precision/flags/fault/lifecycle/packed-layout parity and Studio import/Verify
or transfer/edit qualification remain unfinished or unverified.
