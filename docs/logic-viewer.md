# Logic viewer and graph editor foundation

The logic monitor uses a Studio 5000 style document: a light drawing surface,
rung numbers and comments, rails, contact/coil symbols, instruction parameter
rows and green last-scan power. Structured Text has a line gutter and syntax
coloring. Existing FBD diagrams show named pins and orthogonal connections.

Open **Examples** to select a lab. Select an instruction to inspect its operand
references, current values and types. Left/right arrows move between ladder
instructions. JSR instructions provide **Open routine** in their details;
Structured Text JSR lines also have a navigation button. **Fit width**, zoom,
**Values** and **Comments** control presentation. Zoom and selection survive
monitor refreshes. Opening another routine or source resets the viewport and
selection. The monitor is read-only. Tag writes use the existing watch.

Green wiring describes the last recorded scan. Value labels normally show the
current tag snapshot, which can change between scans. Unvisited instructions
have no invented power state. Missing values remain `?`; expressions are not
executed by the browser. Wide integers remain decimal strings. Program scope,
represented integer bits, simple indirect tag indices and AOI instance bindings
are resolved from snapshot metadata. More complex address expressions can remain
unavailable in the viewer even when the runtime supports them.

## Call operand values

When a ladder JSR, SBR or RET completes a parameter transfer, its blue value
labels show the resolved addresses and scalar values captured for that
instruction. The authored expression stays visible. Select the instruction
to see the full address under **Last transfer**. This lets you see which
array element was used even when an index changes later in the scan.

JSR displays the input values and return destinations captured for the call.
SBR displays the destinations and copied inputs. RET displays the reached
return sources and their values. Aggregates show their address and type.
The monitor uses the last recorded visit to each rung in the committed scan.
A rolled-back scan preserves the previous trace. Skipped or unvisited calls
use the live tag snapshot.

## FOR loop operand values

Select a ladder FOR block to see how many times its routine was entered and
why the loop exited. The block shows the index cell selected at entry and its
value at exit. Initial, terminal and step rows show each operand's last
successful read. Those reads can come from different points in the loop.
The authored references stay visible.

After a cleared bounds fault, captured values describe the loop before the
fault handler ran. Operands that had no successful read show a dash and
**Not sampled** in the details. The latest committed rung visit controls the
display. A false rung uses the ordinary live value labels.

## Fault recovery in the ladder monitor

When a fault handler clears a fault and the rung resumes, the skipped
instruction is marked in amber with the fault code. Its details also
show the skip. The wires continue to show the recorded rung power.

The mark belongs to the last recorded visit to that rung and instruction.
A later visit without recovery removes it. Editing the rung also removes
the mark from the changed source.

## Instruction presentation

AOI calls use the imported definition name, an instance row and the visible
parameters in declaration order. Input, Output and InOut markers distinguish
argument roles; tooltips include data types, dimensions and descriptions.
Required arguments bind in declaration order even if their rows are hidden.
Optional parameters read from the instance. EnableIn/EnableOut are represented
as EN/ENO status indicators. Select a call to inspect hidden parameters as well
as visible ones. **Open AOI logic** opens an instantiated call's Logic routine
with the matching instance context.

Built-in ladder instructions use descriptive headers, opcode captions and named
operands. Timers/counters show live PRE/ACC values and status indicators.
CONTROL faceplates show live LEN/POS whether the rung supplied literals or
`?` placeholders. Routine calls distinguish input and return arguments. Routine
names, system attribute names and expressions are source references, not tag
values to evaluate in the browser. Unknown instructions retain all source
operands and remain marked unsupported.

Every visible parameter row participates in layout, including AOIs with more
than six parameters and parallel/nested branches. Long references are shortened
on the drawing; tooltips and the inspector retain the full reference. Faceplate
rows and status decorations are not additional executable graph nodes or wires.
The viewer remains read-only. This is a Studio-style presentation, not a claim
of pixel-for-pixel native UI or instruction execution equivalence.

JMP instructions offer **Go to label** in the inspector. Double-click the JMP
or press Ctrl+Enter while it has focus to select and reveal its unique LBL target.
Missing or duplicate labels have no invented destination. This navigation changes
only the viewport and selection, not program execution or the scan position.

Value lookup respects program-local shadowing, including arrays and structures.
An unavailable local member does not fall back to a same-named controller member.
AOI InOut structures/arrays resolve to their actual backing storage; aggregates
show **Members** in the inspector. Indirect indices require known integer snapshot
values. Address expressions remain unevaluated, and unknown values remain `?`.

## Separation of responsibilities

The viewer uses plain JavaScript and SVG, with no browser framework or graph
library required at runtime.

| Layer | Responsibility |
| --- | --- |
| [ladder-graph.js](../source/web/ladder-graph.js) | Adapt imported rung nodes into an explicit graph, compute layout, associate last-scan power |
| [instruction-view.js](../source/web/instruction-view.js) | Describe built-in/AOI faceplates, operand roles, visible rows and measured extents |
| [logic-values.js](../source/web/logic-values.js) | Resolve scoped snapshot references, AOI bindings, aggregates, indices and integer bits without evaluating logic |
| [logic-view.js](../source/web/logic-view.js) | Render symbols, wires, text, values, selection and instruction details |
| [logic-view.css](../source/web/logic-view.css) | Document colors, typography and selection/monitor styles |
| [server.py](../source/logixlab/server.py) | Existing authenticated snapshots, plus read-only AOI definitions and canonical binding references |

The graph has `schemaVersion: 1`, a routine/rung identity, source text and comment,
instruction/rail/junction nodes, typed directional power ports and explicit
port-to-port edges. Instructions keep their opcode, operand references, source
path and lexical trace ordinal. Parallel branches become split/join junctions;
an empty bypass is a connection without an invented instruction.

The source adapter also retains series/parallel grouping as `regions` for this
layout. Connectivity is represented by nodes, ports and edges. Grouping hints
can be maintained or derived by a future editor; DOM nesting is not the logic
model. Layout coordinates and snapshot values remain outside the graph.

```javascript
const graph = LadderGraph.compile(rung, routine.key);
const measure = node => LogixInstructionView.dimensions(node,
  LogixInstructionView.describe(node, snapshot.aoi_definitions));
const geometry = LadderGraph.layout(graph, 1000, measure);
const monitoring = LadderGraph.power(graph, lastTrace);
```

These operations leave imported source and graph data unchanged. The renderer's
`graphs()` method returns copies. A `logic-node-selected` DOM event carries the
node and graph identity for inspector integration. Imported identities are
deterministic source-path IDs, stable across scans and value updates; they are
not durable identities across source reordering.

## Offline ladder drafts

Open an ordinary ladder routine and select **Edit draft**. Choose an
instruction or **Branch** from **Insert**, then select a dot on a wire.
Each branch leg has its own insertion points. Drag an instruction to a wire
dot in the same rung, in a branch, or in another rung. For keyboard editing,
select the instruction, choose **Move instruction**, then focus a destination
dot and press Enter. Esc cancels the selection of a destination.

Choose **Insert rung above** on a rung or **Add rung at end** in the toolbar.
The new rung starts with an empty wire. Choose **Edit comment** to add, change
or clear its comment, or **Delete rung** to remove the rung and its contents.
The routine must retain at least one rung. Adding or deleting a rung renumbers
the draft in order. Undo restores the prior layout and numbers.

Drag the square on a branch's right rail to a highlighted wire dot. A dot
after the branch wraps the intervening instructions into the top leg. A dot
inside the top leg releases everything after it to the right of the branch.
For keyboard editing, select the square and choose **Resize branch**.
Nested branches move as a unit, and the other legs keep their instructions.

Select the square to add or delete a leg. Deleting a leg removes its
instructions. When one leg remains, its instructions return to the
surrounding rung or branch. **Undo** restores the whole edit, including
moves across two rungs and branch resizing. **Redo** repeats it. Ctrl+Z
and Ctrl+Y also work outside text fields.

**Monitor** restores the live view. Select **Resume draft** to return to
a changed draft for the same project generation and routine revision.
**Save draft JSON** downloads the current rung layout, text, comments and base
source identifiers. To reopen it after closing the browser, load the original project
and select the original routine. Choose **Edit draft**, then **Open draft
JSON**. LogixLab checks the project source, base logic revision and references
to retained rungs, then parses the draft text with its Python ladder parser.
Earlier saved files that identify rungs by number still open. A
successful open replaces the browser draft in one undoable step. It accepts
unfinished operand placeholders and keeps the loaded simulator logic active.

Drafts use the same SVG graph and faceplates as the monitor. Insertion and
operand editing affect the browser draft only. Scan traces and live values
are shown in Monitor, where the simulator continues to use the loaded
routine. A draft retains the original source text of each unchanged rung.
The operand field checks delimiters to keep each value within its own
argument. Use **Validate draft** to check the edited routine with the
loaded project's tag definitions, call targets and execution plan. The check
builds a temporary model with the project's initial tag values and previews
prescan. It includes the selected routine even when that routine is outside
the scheduled programs. Diagnostics name the routine and rung where the
runtime can locate the problem. An edit clears the previous result.

This preflight uses the original initial values. To run the draft with the
current tag values, switch the emulator to **Program** in whole-project mode
and choose **Apply draft**. Apply supports complete Standard RLL projects
within the existing edited L5X export profile. Close any Studio sessions or
native programming reservations on the emulator first.

Apply rechecks the project source and revision, validates the replacement,
and reimports a temporary L5X to check rung text, comments, operands and
imported initial values. A successful apply installs the routine in memory
and returns to **Monitor**. The emulator retains live tags and scan counters,
and clears the old trace for the replaced routine. The next scan uses the
edited routine. Use **Save edited L5X** to download a working copy. [Saving
edited logic](edited-logic-l5x.md)

## Node and wire editor roadmap

The next authoring stages build on these same instruction nodes and connections:

1. Give an editable document durable node/edge identities, with commands for
   inserting instructions, connecting ports, creating branches and changing
   typed operands. Preserve identities through undo/redo and layout changes.
2. Validate legal rail connectivity, branch grouping, power-port directions,
   acyclic flow and instruction/operand rules before accepting a transaction.
   Keep layout gestures separate from changes to executable logic.
3. Add a graph-to-neutral-text compiler and source mappings. Round-trip imported
   rungs, nested branches and supported instructions through the existing parser
   and execution checks. Keep ambiguous/unsupported source visible.
4. Add document revisions, change review and explicit save/export to new L5X
   working copies, followed by project editing and persistence. Reuse the graph
   in an editor rather than representing ladder as nested instruction cards.
5. Qualify native engineering transfers and online editing separately from
   offline authoring and simulation.

The draft tools cover wire insertion, drag moves, branch resizing and legs,
operand editing, rung layout and comments, deletion, history, reopening saved
drafts, execution preflight, applying a routine offline and exporting a
separate L5X copy.

## Verification

With Node.js installed for development, run the dependency-free graph and ST
token tests from the project root:

```powershell
node --test source/tests/web/logic-view.test.cjs source/tests/web/logic-values.test.cjs
```

The focused tests cover branch topology, stable monitoring identities, source
preservation, port geometry, nested branch spacing, output alignment, missing
and partial traces, AOI argument/visibility binding, full-row geometry, saved control members,
and exact ST token reconstruction. HTTP checks cover asset
delivery, module order and read-only AOI binding metadata. Browser checks cover
selection, values, navigation, scope, zoom and the rendered documents.

Visual similarity does not establish native Studio instruction, transfer or
controller equivalence. Runtime qualification remains tracked separately in
the [capability checklist](emulation-coverage.md).
