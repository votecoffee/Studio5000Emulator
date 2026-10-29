# Execution model

LogixLab is a bounded software model for supported Logix v35 forms. Coverage
reports describe the loaded project and selected scope; they are not a
percentage of native controller compatibility.

## Scope and state

Whole-project execution supports one to 32 Standard Continuous/Periodic tasks,
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

[Controller GSV reads](controller-gsv.md) expose the simulator AuditValue and
source ChangesToDetect mask in RLL and ST. They share the CIP values and preserve
all bits in LINT or two DINT elements; unavailable values and other GSV/SSV forms
remain unsupported.

JSR/SBR/RET require exact parameter counts, compatible types and dimensions,
static references and bounded call nesting. Calls cannot target a main routine;
RET in a main routine is blocked. Parameterized subroutines require their caller
when selecting a routine harness.

RLL/ST AOIs support bounded nested instances, copied Input/Output values, InOut
references, Prescan and EnableInFalse behavior. Optional parameters use saved
instance members. Hidden saved locals omitted by an export remain unknown;
definition defaults do not substitute for missing instance state. Unsupported
AOI forms and Safety AOIs are blocked.

## Structured Text

Supported forms include assignments, non-retentive `[:=]`, IF/ELSIF/ELSE, integer
CASE selectors/ranges, FOR/BY, WHILE, REPEAT/UNTIL, nearest-loop EXIT, supported
instruction/AOI calls and mixed ST/RLL subroutine calls. ST is case-insensitive.
Supported comments include `//`, `(* ... *)` and `/* ... */`; unsupported syntax
is checked even in unreachable branches.

Typed numeric expressions currently focus on SINT/INT/DINT/REAL, BOOL and
single-byte strings. REAL operations use modeled float32 rules; conversions,
overflow and operand restrictions are explicit. Wide/unsigned arithmetic and
whole-array/UDT assignment have narrower support than storage/copy operations.

All expression operands are evaluated eagerly. Unknown data or faults cannot be
hidden by an assumed short-circuit path. Loop bounds, static/indirect references,
counter updates and instruction budgets are checked conservatively.

Ordinary `:=` assignments retain imported values until execution. `[:=]`
destinations clear during modeled prescan, including inside conditional code.
Prescan walks lexical ST sites rather than executing normal loop iterations.
Native prescan-order and iteration parity have not been established.

## Data and imports

COP/CPS operate on matching declared element types within modeled array/member
regions. Raw byte layouts and cross-type reinterpretation are blocked. Strings
retain represented LEN/DATA values, including unknown backing bytes.

L5X files must contain the required project context and saved data. ACD conversion
uses a separately configured converter against a private copy. Source bytes are
preserved and private provenance records identify the import. Native files,
converter logs and project-specific reports are local inputs, not public fixtures.

## Boundaries

FBD/SFC, preemptive/event/Safety-task execution, motion, physical I/O, produced/consumed
behavior, full native fault/status behavior and Safety execution are not complete.
Offline model results do not establish commissioning, safety approval or native
runtime equivalence. Local explicit messaging has a separate
[protocol contract](connectivity.md).
