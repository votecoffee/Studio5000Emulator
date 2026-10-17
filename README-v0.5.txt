LogixLab 0.5.0 - custom offline Logix v35 execution model
October 16, 2026

START
Double-click LogixLab.exe or START.cmd. Python is not required.
Choose Text lab for the new Structured Text features. End session stops the
local server. Earlier deliveries remain separately preserved.

NEW IN 0.5
A bounded Structured Text engine for Standard program routines and AOIs:
  := and non-retentive [:=] assignments
  IF / ELSIF / ELSE, integer CASE selectors/lists/ranges
  FOR / BY, WHILE, REPEAT / UNTIL, nearest-loop EXIT
  Typed numeric, BOOL and string expressions, comments and string literals
  Supported data/string instruction calls, AOI calls and mixed ST/RLL JSRs
  Dynamic integer-bit references such as Packed.[BitIndex]
The Logic monitor displays ST source, executed statements and their last
recorded detail this scan. AOI views retain instance selection. Click the
arrow beside a JSR line to inspect its called routine. The original ladder
monitor remains available automatically for RLL routines.

TEXT LAB WALKTHROUGH
1. Choose Text lab. Before scanning, ClearedOnRun and Accumulator.Count are
   0 after modeled prescan, while ScanTotal remains 0.
2. Step three times. ScanTotal = 3, ClearedOnRun = 17 and Sum = 30.
   Values = [0,3,6,9,12], CaseResult = 20, WhileCount = 3, RepeatCount = 2,
   SearchResult = 3, Packed = 15 and AOITotal = 6.
3. Scaled = 61 demonstrates a call chain from ST MainRoutine into ladder
   LadderScale, then ST TextAdjust, with typed values returned to the caller.
4. Message and Shadow both read SCAN 3. Watch their string values or filter
   .DATA to inspect backing bytes.
5. Select AOI:LabSTAccumulator / Logic to inspect its Count/Total assignments.
6. Set Enable to 0 and Step to 9; step. State becomes -1, while AOITotal stays
   6 and Accumulator.Step stays 2: the skipped ST call is not false-scanned.
7. Reset restores imported values and repeats modeled prescan.
Conveyor, Data, AOI and Call labs remain available. All five labs have
source-authored L5X and native v35 ACD files under source/samples.

STRUCTURED TEXT CONTRACT
ST is case-insensitive. //, (* ... *) and /* ... */ comments are supported;
nested comments and raw multiline string literals are blocked. Statements
and constructs require terminators. Unsupported instructions and syntax are
checked even in unreachable branches.
Native XML formatting newlines around numbered ST lines are removed from
the modeled view. Embedded multiple source lines in one numbered Line are blocked.

Expression precedence follows the ST reference, separately from CMP/CPT:
functions, power, unary negate, NOT, multiplication/division/MOD, addition,
ordered relations, equality/inequality, AND, XOR, OR. Equal precedence is
evaluated left to right. Supported numeric types are SINT/INT/DINT/REAL;
BOOL and single-byte string expressions are also supported. REAL source
operands/functions promote numeric computation to float32. Assignment
conversion uses the existing typed memory rules, including ties-to-even
REAL-to-integer rounding and blocked overflow. Integer division is blocked;
use an explicit REAL operand. Integer power permits nonnegative exponents
0..31 subject to DINT bounds. Wide/unsigned ST arithmetic is not implemented.
Numeric bitwise expressions currently require DINT operands.

BOOL destinations require BOOL expressions or integer literal 0/1. String
literals use the supported Rockwell dollar escapes; implementation-dependent
$N is blocked. String-tag assignment requires identical declared types and
copies the represented LEN/DATA, including unknown tail bytes. Literal
assignment writes LEN/active bytes and preserves unused backing data.
Whole-array/UDT assignment is blocked; use supported COP forms instead.
All expression operands are evaluated eagerly. Unknown data or faults cannot
be concealed by an assumed short-circuit path. This is an explicit model
policy; native short-circuit parity has not been verified.

FOR counters must be static scalar SINT/INT/DINT references. Bounds and step
must be integer expressions. Dynamic references in bounds/step, dependence
on the counter, body writes to bounds/step, and JSR inside tag-bounded FOR
loops are conservatively blocked. Zero step faults. The counter retains its
exit value, including the final increment when the terminal value is passed.
WHILE tests before the body; REPEAT tests afterward and executes at least
once. EXIT leaves the nearest loop. Empty infinite loops also consume the
instruction budget. CASE currently supports integer values/selectors and
executes only the first matching branch. REAL CASE is not implemented.

ST instructions execute only when their statements are reached. Skipping
an IF branch does not false-scan its instructions or AOIs. The supported
standalone built-ins are COP/CPS/FLL/SIZE, CONCAT/MID/DTOS/STOD and JSR/SBR/RET.
Ladder-only calls such as OTE, TON, CMP and MOV are blocked in ST; use ST
expressions/assignments where appropriate. AOI calls use the existing typed
parameter rules. JSR/SBR/RET inside AOIs remain blocked.

Ordinary := assignments retain imported values until execution. [:=]
destinations clear during modeled prescan even inside conditional code.
Prescan walks lexical ST sites once; it does not perform normal assignments
or loop iterations. Configured AOI Prescan routines execute normally after
their primary Logic prescan. Required AOI parameter transfers occur during
prescan. Indirect prescan references use imported index values; invalid
indices block execution. Native prescan-order/iteration parity is unverified.

Preflight checks syntax, types and references using structural placeholders.
Dynamic array/bit addresses are checked for their actual values at runtime.
These placeholders never become simulator values. Hidden AOI saved locals
omitted by the export remain unknown; definition defaults are never assumed
to be saved instance state. Actual unknown reads, bounds errors and arithmetic
faults stop and roll back the scan, including AOI state and parameter copies.

INHERITED FEATURES
54 built-in RLL mnemonics have bounded supported forms: bit logic,
comparisons, math, timers/counters, typed copies/fills, expressions, strings,
jumps and routine calls. RLL/ST AOIs support nested instances, copied
Input/Output values, InOut references, Prescan and EnableInFalse. Optional
parameters use stored instance members. Alias/constant/nullable AOI parameter
forms and safety AOIs remain blocked.
JSR/SBR/RET support exact parameter counts/types/dimensions, by-value copies,
up to 40 parameters each direction and 25 nested calls. Parameter references
must be static; overlapping transfers are restricted. Calls cannot target
a main routine; RET in a main routine blocks execution. Parameterized
subroutines need their caller when using an isolated harness.
COP/CPS require matching declared element types and stay within modeled
array/member regions. Raw byte layouts and cross-type reinterpretation are
blocked. Wide integer storage/display and exact copies remain supported;
their arithmetic is restricted. Strings retain represented LEN/DATA values.

SCOPE / REMAINING WORK
Whole project requires one Standard Continuous/Periodic task. An isolated
harness runs its selected routine, called routines and AOIs, excluding
unrelated programs/tasks. Periodic tasks require the exported integral
millisecond rate. Program prescan uses sorted routine order. Each scan and
prescan has a 100,000 instruction budget; trace retains 5,000 visits and
change history retains 2,000 changes. Green ST lines show executed statement
starts, with the last visit shown when loops or same-line statements repeat.
This is a trace viewer, not a Studio 5000 online editor or debugger.

Remaining work includes broader ST forms, FBD/SFC, BTDT/FBC and other
instructions, CONTROL/raw layouts, multiple/event tasks, GSV/SSV services,
native status/fault handling, motion, CIP/network, produced/consumed behavior,
physical I/O and safety execution. The app has no controller connection or
download capability. Native runtime equivalence remains unverified. Model
rollback differs from native controller fault handling.

IMPORT / SOURCE PRESERVATION
Open ACD / L5X reads into a private workspace. ACD conversion uses installed
Studio 5000/Logix Designer SDK through l5xgit.exe from the supplied archive,
working on a second private copy and recording SHA-256 provenance. Original
files are unchanged. Matching Studio/SDK and required activation must be
available. No Rockwell binaries or archive source are bundled. L5X execution
does not require the SDK. Import settings changes the converter path.
Default converter:
C:\~LocalWork\Repos\Programming\PLCCodeGenerator\Archive\ra-logix-designer-vcs-custom-tools-main\artifacts\bin\Debug\l5xgit.exe
Private imports/settings/logs remain in %LOCALAPPDATA%\LogixLab or --data-dir.
The server binds only to 127.0.0.1.

VALIDATION
191 behavioral tests pass, including all previous feature regressions and
new ST control flow, prescan, source metadata, string escapes/copies, indirect
indexes/bits, unknown values, unsupported forms, budgets and rollback tests.
Text Lab imported through installed v35 SDK with zero warnings and zero
errors, saved as ACD, exported to L5X and passed the modeled scenarios.
No native controller instruction execution comparison was performed.
The same hash-checked 60-routine / 3,951-program-instruction sample retains
12 runnable routine harnesses, each completing 25 scans at 10 simulated ms.
Whole-project execution remains blocked by 428 findings and 6 tag problems.
These fixture counts are not a completeness percentage. See validation/.

REFERENCES / DEVELOPMENT
The supplied installed v35 help is the primary reference:
C:\Program Files (x86)\Rockwell Software\Studio 5000\Logix Designer\ENU\v35\Bin\Help\ENU\RS5000\17691.htm
ST pages include 14760, 14761, 14763, 14766, 14757, 14759, 14762, 14754,
14755, 348204, 267909 and 271126..271129. Original paths and SHA-256 values
are in validation/reference-sources.json. Help pages are not redistributed.
Supplementary Rockwell Structured Text programming manual:
https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm007_-en-p.pdf
Source uses Python's standard library. From source/:
  py -3.13 -X utf8 launch.py
  py -3.13 -X utf8 -m unittest discover -s tests -v
  py -3.13 -X utf8 verify_delivery.py
Build with source/build.ps1 (PyInstaller is a build-time dependency).
Coverage and snapshots download in the UI; --report FILE emits coverage JSON.
Optional native_*_scenario.py scripts check SDK-exported fixtures.
SHA256-MANIFEST.json binds the delivery files.
