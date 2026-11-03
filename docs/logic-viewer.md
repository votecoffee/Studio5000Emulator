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
selection. The monitor is read-only; tag writes use the existing watch.

Green wiring describes the last recorded scan. The value labels show the
current tag snapshot, which can change between scans. Unvisited instructions
have no invented power state. Missing values remain `?`; expressions are not
executed by the browser. Wide integers remain decimal strings. Program scope,
represented integer bits, simple indirect tag indices and AOI instance bindings
are resolved from snapshot metadata. More complex address expressions can remain
unavailable in the viewer even when the runtime supports them.

## Separation of responsibilities

The viewer uses plain JavaScript and SVG, with no browser framework or graph
library required at runtime.

| Layer | Responsibility |
| --- | --- |
| [ladder-graph.js](../source/web/ladder-graph.js) | Adapt imported rung nodes into an explicit graph, compute layout, associate last-scan power |
| [logic-view.js](../source/web/logic-view.js) | Render symbols, wires, text, values, selection and instruction details |
| [logic-view.css](../source/web/logic-view.css) | Document colors, typography and selection/monitor styles |
| [server.py](../source/logixlab/server.py) | Existing authenticated snapshots, plus canonical read-only AOI binding references |

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
const geometry = LadderGraph.layout(graph, 1000);
const monitoring = LadderGraph.power(graph, lastTrace);
```

These operations leave imported source and graph data unchanged. The renderer's
`graphs()` method returns copies. A `logic-node-selected` DOM event carries the
node and graph identity for inspector integration. Imported identities are
deterministic source-path IDs, stable across scans and value updates; they are
not durable identities across source reordering.

## Planned node and wire editor

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

Insertion, dragging/wiring, undo/redo, graph compilation and authoring saves are
future work. The current viewer does not change the loaded routine or offer
editing gestures that discard changes on the next scan.

## Verification

With Node.js installed for development, run the dependency-free graph and ST
token tests from the project root:

```powershell
node --test source/tests/web/logic-view.test.cjs
```

The focused tests cover branch topology, stable monitoring identities, source
preservation, port geometry, nested branch spacing, output alignment, missing
and partial traces, and exact ST token reconstruction. HTTP checks cover asset
delivery, module order and read-only AOI binding metadata. Browser checks cover
selection, values, navigation, scope, zoom and the rendered documents.

Visual similarity does not establish native Studio instruction, transfer or
controller equivalence. Runtime qualification remains tracked separately in
the [capability checklist](emulation-coverage.md).
