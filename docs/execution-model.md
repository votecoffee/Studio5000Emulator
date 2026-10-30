# Execution model

LogixLab is a bounded software model for supported Logix v35 forms. Coverage
reports describe the loaded project and selected scope; they are not a
percentage of native controller compatibility.

## Scope and state

[ST OSRI/OSFI](st-oneshot.md) use logical FBD_ONESHOT records and per-record
sampled input history. Reached calls produce rising/falling pulses; skipped
calls retain outputs and history. Run entry reprimes history. Values and edges
share scan/prescan rollback and supported detached routine replacement.

Whole-project execution supports one to 32 Standard Continuous/Periodic and
qualified [instruction-only Event tasks](event-tasks.md),
with at most one Continuous task. Periodic releases follow integral-millisecond
rates and priority ordering at coincident times; each task executes serially.
Continuous logic runs once per simulation step after due Periodic work. An
isolated routine harness bypasses scheduling. See the exact
[release and rollback rules](task-scheduling.md); CPU preemption, event and Safety
tasks remain unfinished.

Import restores represented saved values. Unknown values omitted by an export
remain unknown. Prescan and scan behavior use explicit modeled rules. Runtime
faults stop and roll back the current modeled scan, including parameter copies
and AOI state; native controller fault handling can differ.

The application retains imported values in Program and validates prescan with
a rollback preview. [Run entry](run-entry.md) commits initialization once and
rearms `S:FS` independently for each Program's first actual execution; the first
manual Step also initializes once. Repeated Run requests
do not repeat prescan. A failed prescan restores values and execution context,
keeps the controller stopped and reports a fault.

Scans and prescan have instruction budgets. Traces and tag-change histories are
bounded. The UI logic monitor displays execution evidence from this model, not
native Studio debugger state.

## Ladder and calls

Supported ladder forms include bit logic, comparisons, typed math, timers and
counters, copies/fills, expressions, strings, jumps and routine calls. The
project's Coverage view is authoritative for implemented operand forms.

The [integer ladder profile](integer-execution.md) adds homogeneous LINT and
unsigned arithmetic, comparisons and bitwise operations for v35 ControlLogix
5580 identifiers. Integer DIV truncates toward zero without floating-point
conversion. Mixed-type wide operations and native math flags remain blocked;
overflow and divide faults retain modeled scan rollback.

[String conversions](string-conversions.md) add ASCII-only LOWER/UPPER, decimal
STOR and a documented fixed-decimal RTOS software format. Source reads precede
writes; active data must be known and capacities enforced. RLL false calls and
skipped ST branches retain outputs. New ST calls track destination writes in
FOR dependency checks and share existing AOI string/REAL bindings.

[File arithmetic](file-arithmetic.md) adds ladder FAL ALL and numeric modes
using the existing CPT expressions. Destination subscripts resolve at each
CONTROL.POS; later iterations read earlier writes. Numeric work continues on
false rungs. Each iteration consumes the instruction budget; errors retain
whole-advance rollback rather than native partial-write/overflow semantics.
[INC mode](file-incremental.md) adds one iteration per observed enable edge for
idle-source controls. Separate canonical CONTROL progress shares rollback and
RES, survives Run entry and is copied during routine replacement.

[File search](file-search.md) adds ladder FSC ALL and numeric modes. Matches
set FD/IN and hold the current index until IN is cleared; numeric work can
continue while rung input is false. Each comparison consumes the instruction
budget. Unknown data and later failures retain whole-advance rollback. INC
uses the same internal progress profile, with explicit false-edge rearming after
FSC inhibit. Native saved hidden state and mixed CONTROL consumers remain open.

[File sorting](array-sort.md) supports ladder enable edges and three-operand ST
calls. Each executed ST call performs false then true. Integer sorting retains
exact values; selected dimensions and member boundaries constrain the writes.
FOR validation protects the whole selected array member when checking bound/step
dependencies. Native internal sort-position and partial-fault behavior stay open.

[Array statistics](array-statistics.md) add ladder AVE and sample STD with
logical CONTROL. A complete qualified operation varies one declared array
dimension, retains other subscripts, and completes within one advance. Held
EN/DN retains results. AVE and STD have distinct prescan/false-rung rules.
Partial POS/resume and native precision/error side effects remain unqualified.

[Common REAL math](math-operations.md) provides standalone ladder square roots,
power, logs, angle conversion and trigonometry. SINT/INT/DINT/REAL sources and
results use the finite float32 software profile with REAL destinations.
Square roots take the source absolute value, including existing CPT/ST functions.
Domain/overflow failures retain advance rollback; native NaN/infinity, precision
and math-status behavior remain separate work.

[Numeric conversions](numeric-conversions.md) provide ladder DINT FRD/TOD and
ladder/ST INT/DINT SWPB. FRD weights all eight hex nibbles, including A–F;
TOD packs qualified decimal values into a signed DINT bit pattern. SWPB uses
explicit byte-order selectors and sign-extends swapped INT results to DINT.
Native TOD saturation/math flags remain separate from modeled rollback.

[Masked moves and bit fields](bit-transfer.md) use declared SINT/INT/DINT
widths, zero-fill, snapshot overlap and preserved destination bits. BTD positions
and length are immediate; its excess bits never wrap to another array element.
Native math/status flags and ST/FBD variants remain unfinished.

[String search/editing](string-operations.md) supports FIND, INSERT and DELETE
in RLL/ST with one-based byte positions, represented user-string capacities
and captured source text for aliasing. Result writes preserve unused backing
bytes. Unqualified edge cases and native minor faults remain explicit.

[CONTROL operations](control-operations.md) add bounded DINT bit shifts and
matching numeric FIFO/LIFO pairs with separate edge latches, saved LEN/POS and
explicit reset/prescan. The logical members are accessible separately; native
CONTROL layouts and whole-record wire transfers remain unsupported.

[DINT sequencers](sequencer-operations.md) qualify v35 5580 ladder SQO/SQI/SQL.
SQO and SQL advance on an edge and apply the current row while held true.
SQI compares without advancing; cyclic rows 1..LEN follow startup row zero.
Selected-member bounds, mask widths, unknown values and rollback remain explicit.

[EVENT execution](event-tasks.md) synchronously runs a higher-priority task before
the caller's next instruction. Lower/equal-priority requests wait for task returns
and drain by priority, with FIFO Event ties and base releases first at equal
priority. There is one pending execution per Event task; repeated pending requests
coalesce with a diagnostic separate from active overlaps. Queues drain before the
simulation clock advances. Event first scans, diagnostics and writes share the
advance's transaction and budgets. Native time slicing/pending-duplicate semantics,
general CPU timing and external event sources remain open.

[Controller GSV reads](controller-gsv.md) expose the simulator AuditValue and
source ChangesToDetect mask in RLL and ST. They share the CIP values and preserve
all bits in LINT or two DINT elements. [Configuration GSV](gsv-configuration.md)
adds explicit Task/Controller settings with exact INT/DINT/string destinations.
Unqualified values, runtime attributes and broader SSV remain unsupported;
[Task InhibitTask](task-inhibition.md) has a separate runtime profile.

JSR/SBR/RET require exact parameter counts, compatible types and dimensions,
static references and bounded call nesting. Calls cannot target a main routine;
RET in a main routine is blocked. Parameterized subroutines require their caller
when selecting a routine harness.

RLL/ST AOIs support bounded nested instances, copied Input/Output values, InOut
references, Prescan and EnableInFalse behavior. Optional parameters use saved
instance members. Hidden saved locals omitted by an export remain unknown;
definition defaults do not substitute for missing instance state. Unsupported
AOI forms and Safety AOIs are blocked.

## Integer expression division

[Narrow integer expressions](integer-expressions.md) now use exact truncated
quotients in ST/CPT/CMP, with the same evaluator behavior in FAL/FSC. Existing
REAL promotion rules remain distinct: CPT includes its destination type, while
ST evaluates its expression before destination conversion. Per-node bounds,
eager evaluation, whole-advance rollback and INC retry preserve existing limits.

## Typed ST integer constants

[Decimal L/U/UL literals](st-integer-literals.md) retain their declared type in
the ST syntax tree. They select the existing wide profile even without numeric
tag operands. Signs and ranges are checked together; matching type, per-node
arithmetic bounds, eager evaluation and whole-advance rollback remain explicit.
Other literal formats, instruction arguments and mixed conversions stay open.

## Wide ST integers

[Wide ST](wide-st.md) uses exact homogeneous LINT/unsigned operands and
destination-aware typing for assignments. Every numeric intermediate is bounded;
division/remainder use exact integers and bitwise operations retain width. BOOL
conditions, WHILE/REPEAT and matching AOI/routine bindings share existing control
flow and rollback. Mixed types, wide loop/CASE/index forms and native parity
remain unqualified.

## File bit diagnostics

[FBC/DDT](file-bit-compare.md) compare DINT array bits and record relative
offsets using separate compare/result controls. One mode resumes on enable
edges; all mode completes the range. Full result lists wrap on the next
mismatch. DDT changes only mismatching reference bits; FBC retains reference
data. False/prescan rearms comparison and resets completed cursors without
learning data. Budgets and later faults retain whole-advance rollback.

## Data transition

[DTR](data-transition.md) compares a masked DINT source with the complete prior
reference. A true comparison pulses on change and replaces the reference; false
execution and prescan also refresh it. Disabled MCR bodies therefore update
references while suppressing pulses. Aliases and existing AOI bindings use
ordinary scan order; later faults roll back reference and downstream writes.
Required unknowns fault and native operand/status parity stays unqualified.

## Paired MCR zones

[Master control reset](master-control.md) plans paired ladder zones and forces
every disabled body instruction to receive false power. The ending restores
normal execution. Each routine/AOI invocation has local state; prescan remains
lexical and existing instruction false paths apply. Cross-boundary jumps and
unsupported endings block execution. Budget/fault rollback and detached routine
replacement retain their existing contracts; native override/CPU parity stays open.

## Runtime task inhibition

[SSV Task InhibitTask](task-inhibition.md) changes a separate runtime flag. Each
base release checks it before starting; the current body completes. Periodic
phase continues while inhibited, with missed releases discarded. GSV and exposed
Task read attribute 19 follow the live flag. Later faults roll it back with all
advance progress. Run entry retains flags; reset/reload restores source settings.
Inhibited tasks are still validated and prescanned. Native phase/abort parity
remains unqualified.

## Structured Text counter

[CTUD](st-counter.md) adds a logical FBD_COUNTER record and per-record sampled
edge history. The first reached call primes inputs; later up/down edges count
in that order. Reset consumes held inputs. Run entry primes again, while
skipped calls retain history. Values and edges share advance/prescan rollback
and detached routine-replacement preservation. Native flag/layout parity stays
unqualified; FBD graph and ladder forms remain blocked.

## Structured Text timers

[TONR/TOFR/RTOR](st-timers.md) add three ST-only calls and logical FBD_TIMER
records. Per-record history uses the simulated task-release clock; repeated
calls at one timestamp add no duplicate elapsed time. Reset/retention, skipped
calls and bounded instruction status are explicit. Values and clocks roll back
together, including on prescan failure. FBD graph and native clock/layout parity
remain unqualified.

## Structured Text

Supported forms include assignments, non-retentive `[:=]`, IF/ELSIF/ELSE,
[integer/REAL CASE](st-case-selection.md) selectors/ranges, FOR/BY, WHILE,
REPEAT/UNTIL, nearest-loop EXIT, supported
instruction/AOI calls and mixed ST/RLL subroutine calls. ST is case-insensitive.
Supported comments include `//`, `(* ... *)` and `/* ... */`; unsupported syntax
is checked even in unreachable branches.

CASE evaluates its expression once and executes only the first matching body.
Integer labels retain DINT bounds. REAL expressions and labels use float32
comparison with no added tolerance; labels do not promote an integer expression.
Invalid labels block execution; unknown/faulting selectors roll back an advance.

Typed numeric expressions currently focus on SINT/INT/DINT/REAL, BOOL and
single-byte strings. REAL operations use modeled float32 rules; conversions,
overflow and operand restrictions are explicit. [Homogeneous wide ST](wide-st.md)
has a separate v35 5580 profile. Mixed conversions, remaining wide forms and
whole-array/UDT assignment remain unfinished.

All expression operands are evaluated eagerly. Unknown data or faults cannot be
hidden by an assumed short-circuit path. Loop bounds, static/indirect references,
counter updates and instruction budgets are checked conservatively.

Ordinary `:=` assignments retain imported values until execution. `[:=]`
destinations clear during modeled prescan, including inside conditional code.
Prescan walks lexical ST sites rather than executing normal loop iterations.
Native prescan-order and iteration parity have not been established.

## Aggregate queue payloads

[String and explicit UDT FIFO/LIFO](record-queues.md) move exact matching logical
elements, preserving represented fields and unknown backing data. Unloads clear
typed zero elements. Copies are detached, bounds/overlap restrictions are checked
and later faults retain whole-advance rollback. Establishing an unknown record
now records per-leaf changes without assuming an earlier dictionary shape.
Native byte layouts, mixed conversions and operational/AOI records stay open.

## Data and imports

COP/CPS operate on matching declared element types within modeled array/member
regions. Raw byte layouts and cross-type reinterpretation are blocked. Strings
retain represented LEN/DATA values, including unknown backing bytes.

L5X files must contain the required project context and saved data. ACD conversion
uses a separately configured converter against a private copy. Source bytes are
preserved and private provenance records identify the import. Native files,
converter logs and project-specific reports are local inputs, not public fixtures.

## Boundaries

FBD/SFC, general CPU preemption, external Event sources, Safety tasks, motion, physical I/O, produced/consumed
behavior, full native fault/status behavior and Safety execution are not complete.
Offline model results do not establish commissioning, safety approval or native
runtime equivalence. Local explicit messaging has a separate
[protocol contract](connectivity.md).
