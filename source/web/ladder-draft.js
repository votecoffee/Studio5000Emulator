/* Browser-only draft commands over the ladder viewer's source nodes. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.LogixLadderDraft = api;
})(typeof globalThis === 'object' ? globalThis : this, function () {
  'use strict';

  function canEdit(routine) {
    return routine?.kind === 'RLL' && !routine.key.startsWith('AOI:') &&
      routine.problems.length === 0 && routine.rungs.length > 0 &&
      new Set(routine.rungs.map(rung => rung.number)).size === routine.rungs.length;
  }

  function serialize(nodes) {
    return nodes.map(node => node.branch
      ? '[' + node.branch.map(serialize).join(',') + ']'
      : node.name + '(' + node.args.join(',') + ')').join('');
  }

  function operandText(value) {
    const text = value.trim() || '?';
    const stack = [];
    for (let i = 0; i < text.length; i++) {
      const token = text[i];
      if (stack.at(-1) === "'") {
        if (token === '$') i++;
        else if (token === "'") stack.pop();
      } else if (token === "'" || token === '(' || token === '[') {
        stack.push(token);
      } else if (token === ')' || token === ']') {
        if (stack.pop() !== (token === ')' ? '(' : '[')) throw new Error('Unbalanced operand');
      } else if (token === ';' || (token === ',' && stack.length === 0)) {
        throw new Error('Enter one operand per field');
      }
    }
    if (stack.length) throw new Error('Unbalanced operand');
    return text;
  }

  function atGap(nodes, gap) {
    if (!Array.isArray(gap?.legs) || !Number.isInteger(gap.index)) return null;
    let series = nodes;
    for (const [branch, leg] of gap.legs) {
      series = series[branch]?.branch?.[leg];
      if (!series) return null;
    }
    return gap.index >= 0 && gap.index <= series.length ? series : null;
  }

  function locate(nodes, id) {
    for (const [index, node] of nodes.entries()) {
      if (node.draftId === id) return {series: nodes, index, node};
      for (const leg of node.branch || []) {
        const found = locate(leg, id);
        if (found) return found;
      }
    }
    return null;
  }

  function movePlacement(source, id, target, gap) {
    if (!source || !target) return null;
    const from = locate(source, id), to = atGap(target, gap);
    if (!from || from.node.branch || !to) return null;
    const index = gap.index;
    if (from.series === to && (index === from.index || index === from.index + 1)) return null;
    return {from, to, index: from.series === to && index > from.index ? index - 1 : index};
  }

  function resizePlacement(nodes, id, gap) {
    if (!nodes) return null;
    const branch = locate(nodes, id), top = branch?.node.branch?.[0];
    if (!top) return null;
    const destination = atGap(nodes, gap), after = branch.index + 1;
    if (destination === branch.series && gap.index > after) {
      return {from: branch.series, start: after, count: gap.index - after, to: top, index: top.length};
    }
    if (destination === top && gap.index < top.length) {
      return {from: top, start: gap.index, count: top.length - gap.index, to: branch.series, index: after};
    }
    return null;
  }

  function create(routine, instructionCatalog = {}) {
    if (!canEdit(routine)) throw new Error('This routine is read-only');
    function operandShape(name) {
      return Object.hasOwn(instructionCatalog, name) ? instructionCatalog[name] : null;
    }
    let nextId = 0;
    function identify(nodes) {
      for (const node of nodes) {
        node.draftId = ++nextId;
        if (node.source_args) {
          node.args = node.source_args;
          delete node.source_args;
        }
        for (const leg of node.branch || []) identify(leg);
      }
    }
    const base = structuredClone(routine.rungs);
    for (const [index, rung] of base.entries()) {
      rung.base_index = index;
      rung.draftRungId = ++nextId;
      identify(rung.nodes);
    }
    let rungs = base;
    const past = [], future = [];

    function commit(updates) {
      const next = rungs.slice();
      for (const [index, nodes] of updates) {
        const original = base[rungs[index].base_index];
        const logic = serialize(nodes);
        const text = original && logic === serialize(original.nodes) ? original.text : logic + ';';
        next[index] = {...rungs[index], nodes, text};
      }
      record(next);
    }
    function hasBaseLayout(rows) {
      return rows.length === base.length && rows.every((rung, i) => rung.base_index === i);
    }
    function numbers(rows) {
      const original = hasBaseLayout(rows);
      return rows.map((_, i) => original ? base[i].number : String(i));
    }
    function renumber(rows) {
      return numbers(rows).map((number, i) => rows[i].number === number ? rows[i] : {...rows[i], number});
    }
    function record(next) {
      past.push(rungs);
      if (past.length > 100) past.shift();
      future.length = 0;
      rungs = next;
    }
    function change(rungIndex, edit) {
      const before = rungs[rungIndex];
      if (!before) return null;
      const nodes = structuredClone(before.nodes), result = edit(nodes);
      if (result) commit([[rungIndex, nodes]]);
      return result;
    }
    function canMove(fromRung, id, toRung, gap) {
      return Number.isInteger(fromRung) && Number.isInteger(toRung) &&
        !!movePlacement(rungs[fromRung]?.nodes, id, rungs[toRung]?.nodes, gap);
    }
    function review() {
      const changes = [];
      const detail = ({number, text, comment}) => ({number, text, comment});
      const retained = new Set(rungs.map(rung => rung.base_index)), loadedOrder = new Map();
      for (const [index] of base.entries()) {
        if (retained.has(index)) loadedOrder.set(index, loadedOrder.size);
      }
      let draftPosition = 0;
      for (const [index, rung] of rungs.entries()) {
        if (rung.base_index === null) {
          changes.push({kind: 'added', after: detail(rung), index});
          continue;
        }
        const before = base[rung.base_index];
        const reordered = draftPosition++ !== loadedOrder.get(rung.base_index);
        const logic = before.text !== rung.text, comment = before.comment !== rung.comment;
        if (logic || comment) {
          changes.push({kind: 'edited', before: detail(before), after: detail(rung), logic, comment, reordered, index});
        } else if (reordered) {
          changes.push({kind: 'reordered', before: detail(before), after: detail(rung), index});
        } else if (before.number !== rung.number) {
          changes.push({kind: 'renumbered', from: before.number, to: rung.number});
        }
      }
      for (const [index, rung] of base.entries()) {
        if (!retained.has(index)) changes.push({kind: 'removed', before: detail(rung)});
      }
      return changes;
    }

    return {
      get rungs() {return rungs;},
      get changed() {return !hasBaseLayout(rungs) ||
        rungs.some((rung, i) => rung.text !== base[i].text || rung.comment !== base[i].comment);},
      get canUndo() {return past.length > 0;},
      get canRedo() {return future.length > 0;},
      operandShape,
      review,
      insertRung(index) {
        if (!Number.isInteger(index) || index < 0 || index > rungs.length) return false;
        const next = rungs.slice();
        next.splice(index, 0, {base_index: null, draftRungId: ++nextId, comment: '', text: ';', nodes: []});
        record(renumber(next));
        return true;
      },
      removeRung(index) {
        if (!Number.isInteger(index) || !rungs[index] || rungs.length === 1) return false;
        record(renumber(rungs.filter((_, i) => i !== index)));
        return true;
      },
      moveRung(from, to) {
        if (!Number.isInteger(from) || !Number.isInteger(to) || !rungs[from] || !rungs[to] || from === to) return false;
        const next = rungs.slice();
        const [rung] = next.splice(from, 1);
        next.splice(to, 0, rung);
        record(renumber(next));
        return true;
      },
      setComment(index, comment) {
        if (!Number.isInteger(index) || !rungs[index] || typeof comment !== 'string' || rungs[index].comment === comment) return false;
        const next = rungs.slice();
        next[index] = {...rungs[index], comment};
        record(next);
        return true;
      },
      insert(rung, gap, opcode) {
        const shape = operandShape(opcode);
        if (!shape && opcode !== 'Branch') return null;
        return change(rung, nodes => {
          const series = atGap(nodes, gap);
          if (!series) return null;
          const draftId = ++nextId;
          const node = opcode === 'Branch' ? {branch: [[], []], draftId}
            : {name: opcode, args: shape.defaults?.slice() ?? Array(shape.min_args).fill('?'), draftId};
          series.splice(gap.index, 0, node);
          return draftId;
        });
      },
      canMove,
      move(fromRung, id, toRung, gap) {
        if (!canMove(fromRung, id, toRung, gap)) return null;
        const source = structuredClone(rungs[fromRung].nodes);
        const target = fromRung === toRung ? source : structuredClone(rungs[toRung].nodes);
        const {from, to, index} = movePlacement(source, id, target, gap);
        from.series.splice(from.index, 1);
        to.splice(index, 0, from.node);
        commit(source === target ? [[fromRung, source]] : [[fromRung, source], [toRung, target]]);
        return id;
      },
      canResize(rung, id, gap) {
        return Number.isInteger(rung) && !!resizePlacement(rungs[rung]?.nodes, id, gap);
      },
      resize(rung, id, gap) {
        return change(rung, nodes => {
          const placement = resizePlacement(nodes, id, gap);
          if (!placement) return null;
          const {from, start, count, to, index} = placement;
          to.splice(index, 0, ...from.splice(start, count));
          return id;
        });
      },
      addLeg(rung, id) {
        return change(rung, nodes => {
          const branch = locate(nodes, id)?.node.branch;
          if (!branch) return null;
          branch.push([]);
          return id;
        });
      },
      removeLeg(rung, id, leg) {
        return change(rung, nodes => {
          const found = locate(nodes, id), branch = found?.node.branch;
          if (!branch || branch.length < 2 || !Number.isInteger(leg) || leg < 0 || leg >= branch.length) return null;
          branch.splice(leg, 1);
          if (branch.length === 1) found.series.splice(found.index, 1, ...branch[0]);
          return id;
        });
      },
      remove(rung, id) {
        return change(rung, nodes => {
          const found = locate(nodes, id);
          if (!found || found.node.branch) return null;
          found.series.splice(found.index, 1);
          return id;
        });
      },
      setOperands(rung, id, operands) {
        const args = operands.map(operandText);
        return change(rung, nodes => {
          const found = locate(nodes, id);
          const node = found?.node;
          if (!node || node.branch) return null;
          const shape = operandShape(node.name);
          if (shape ? args.length < shape.min_args || args.length > shape.max_args ||
              (args.length - shape.min_args) % shape.step !== 0 : args.length !== node.args.length) {
            throw new Error('This instruction does not accept that number of operands');
          }
          if (args.length === node.args.length && args.every((arg, i) => arg === node.args[i])) return null;
          node.args = args;
          delete node.literal_values;
          return id;
        });
      },
      restore(rows) {
        if (!Array.isArray(rows) || !rows.length || rows.some(row =>
          !row || typeof row.number !== 'string' || typeof row.text !== 'string' ||
          typeof row.comment !== 'string' || !Array.isArray(row.nodes))) {
          throw new Error('The opened draft does not match this routine');
        }
        const legacy = !Object.hasOwn(rows[0], 'base_index');
        const incoming = legacy ? rows.map((row, i) => ({...row, base_index: i})) : rows;
        const seen = new Set();
        const expected = numbers(incoming);
        if (incoming.some(({base_index: index, number}, i) => {
          if (number !== expected[i]) return true;
          if (index === null) return false;
          if (!Number.isInteger(index) || index < 0 || index >= base.length || seen.has(index)) return true;
          seen.add(index);
          return false;
        }) || (legacy && incoming.length !== base.length)) {
          throw new Error('The opened draft does not match this routine');
        }
        const retained = new Map(rungs.filter(row => row.base_index !== null).map(row => [row.base_index, row]));
        const next = incoming.map((row, i) => {
          const index = row.base_index;
          const before = index === null
            ? (rungs[i]?.base_index === null ? rungs[i] : null)
            : retained.get(index) || base[index];
          if (before && row.text === before.text) {
            return row.comment === before.comment && row.number === before.number
              ? before : {...before, number: row.number, comment: row.comment};
          }
          const nodes = structuredClone(row.nodes);
          identify(nodes);
          return {...row, nodes, draftRungId: before?.draftRungId ?? ++nextId};
        });
        if (next.length === rungs.length && next.every((row, i) => row === rungs[i])) return false;
        record(next);
        return true;
      },
      undo() {
        if (!past.length) return false;
        future.push(rungs);
        rungs = past.pop();
        return true;
      },
      redo() {
        if (!future.length) return false;
        past.push(rungs);
        rungs = future.pop();
        return true;
      }
    };
  }

  return {canEdit, create};
});
