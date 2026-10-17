# Execution model

LogixLab is a bounded software model for supported Logix v35 forms. Coverage
reports describe the loaded project and selected scope; they are not a
percentage of native controller compatibility.

## Scope and state

Whole-project execution currently requires one Standard Continuous or Periodic
task. An isolated routine harness runs its selected routine, called routines and
AOIs, excluding unrelated tasks/programs. Periodic tasks require an integral
millisecond rate supported by the model.

Import restores represented saved values. Unknown values omitted by an export
remain unknown. Prescan and scan behavior use explicit modeled rules. Runtime
faults stop and roll back the current modeled scan, including parameter copies
and AOI state; native controller fault handling can differ.

Scans and prescan have instruction budgets. Traces and tag-change histories are
bounded. The UI logic monitor displays execution evidence from this model, not
native Studio debugger state.

## Ladder and calls

Supported ladder forms include bit logic, comparisons, typed math, timers and
counters, copies/fills, expressions, strings, jumps and routine calls. The
project's Coverage view is authoritative for implemented operand forms.

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

FBD/SFC, multiple/event-task execution, motion, physical I/O, produced/consumed
behavior, full native fault/status behavior and Safety execution are not complete.
Offline model results do not establish commissioning, safety approval or native
runtime equivalence. Local explicit messaging has a separate
[protocol contract](connectivity.md).
