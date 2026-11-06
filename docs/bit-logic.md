# Ladder contacts, coils and one-shots

The v35 ControlLogix 5580 software profile validates XIC, XIO, OTE, OTL, OTU,
ONS, OSR and OSF using declared types, scalar shape and write permissions.
It does not require saved BOOL values or live indices during preflight.
Scalar BOOL members, logical BOOL array elements, aliases and existing integer
bit references are supported. Other controller profiles keep their legacy path.

| Instruction | Value selection |
| --- | --- |
| XIC / XIO | A false incoming rung skips the contact and its live index. A true rung requires a known contact value. |
| OTE | Always writes the rung condition, including false. A complete BOOL write can establish an unknown value. The destination index is still required. |
| OTL / OTU | False retains the stored value and skips the live destination. True establishes a complete BOOL value. |
| ONS / OSR | False clears storage without reading its previous value. A true rung requires known storage to determine the rising edge. |
| OSF | True establishes storage and clears the pulse without reading history. A false rung requires known storage to determine the falling edge. |

Existing prescan clears OTE outputs, initializes ONS/OSR storage true and OSF
storage false, and clears OSR/OSF pulse outputs. OTL/OTU values are retained.
Import preview preserves saved values; Run applies the actual initialization.
One-shot storage still has to be known whenever its prior state determines a
pulse. Unknown history is not inferred from a desired output.

Individual integer-bit writes require a known backing integer to preserve
neighboring bits. They do not establish an entire unknown packed integer.
Native packed BOOL layout remains unqualified. In a whole-project scan,
[XIC, XIO, OTE, OTL, OTU and ONS](controller-handlers.md#recover-contact-coil-ons-and-comparison-array-faults)
and [OSR and OSF](controller-handlers.md#recover-osr-and-osf-array-faults)
can recover out-of-bounds array subscripts when a fault handler clears Type 4
Code 20. OSR and OSF restore storage before a fault handler runs if the
pulse output subscript is out of bounds. Reached unknowns, unrecovered faults
and later errors roll back the complete advance, including established BOOLs,
edge storage, task/time state and existing AOI bindings.

Choose **Bit lab**, step once with `LogicInput` false, then toggle it. Inspect
`LogicOutput`, `LogicInverse`, `LogicLatched`, `OneShotPulse`, `RisePulse` and
`FallPulse`. `LogicReset` clears the latch. The existing packing, transition and
file-comparison examples remain available. The API report exposes `bit_logic`.

Reference basis: installed Studio 5000 v35 bit-instruction help 14573–14578,
14580 and 14583. Rockwell's published [OTE reference](https://www.rockwellautomation.com/en-be/docs/studio-5000-logix-designer/38-02/contents-ditamap/instruction-set/bit-instructions1/output-energize--ote-11.html)
also describes normal and prescan writes. Software-model/HTTP validation does
not establish native controller equivalence. Native fault/postscan/lifecycle
parity and broader profile qualification remain unfinished; no ST/FBD form is added.
