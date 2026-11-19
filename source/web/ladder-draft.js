/* Browser-only draft commands over the ladder viewer's source nodes. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.LogixLadderDraft = api;
})(typeof globalThis === 'object' ? globalThis : this, function () {
  'use strict';

  const palette = Object.freeze({XIC: 1, XIO: 1, OTE: 1, OTL: 1, OTU: 1, MOV: 2, ADD: 3, TON: 3, Branch: 0});
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

  function create(routine) {
    if (!canEdit(routine)) throw new Error('This routine is read-only');
    let nextId = 0;
    function identify(nodes) {
      for (const node of nodes) {
        node.draftId = ++nextId;
        for (const leg of node.branch || []) identify(leg);
      }
    }
    const base = structuredClone(routine.rungs);
    for (const rung of base) identify(rung.nodes);
    let rungs = base;
    const past = [], future = [];

    function commit(updates) {
      const next = rungs.slice();
      for (const [index, nodes] of updates) {
        const logic = serialize(nodes);
        const text = logic === serialize(base[index].nodes) ? base[index].text : logic + ';';
        next[index] = {...rungs[index], nodes, text};
      }
      record(next);
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

    return {
      get rungs() {return rungs;},
      get changed() {return rungs.some((rung, i) => rung.text !== base[i].text || rung.comment !== base[i].comment);},
      get canUndo() {return past.length > 0;},
      get canRedo() {return future.length > 0;},
      insert(rung, gap, opcode) {
        if (!Object.hasOwn(palette, opcode)) return null;
        return change(rung, nodes => {
          const series = atGap(nodes, gap);
          if (!series) return null;
          const draftId = ++nextId;
          const node = opcode === 'Branch' ? {branch: [[], []], draftId}
            : {name: opcode, args: Array(palette[opcode]).fill('?'), draftId};
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
          if (!found || found.node.branch || found.node.args.length !== args.length ||
              args.every((arg, i) => arg === found.node.args[i])) return null;
          found.node.args = args;
          delete found.node.literal_values;
          return id;
        });
      },
      restore(rows) {
        if (!Array.isArray(rows) || rows.length !== rungs.length || rows.some((row, i) =>
          !row || row.number !== rungs[i].number || typeof row.text !== 'string' ||
          typeof row.comment !== 'string' || !Array.isArray(row.nodes))) {
          throw new Error('The opened draft does not match this routine');
        }
        const next = rows.map((row, i) => {
          const before = rungs[i];
          if (row.text === before.text) return row.comment === before.comment ? before : {...before, comment: row.comment};
          const restored = structuredClone(row);
          identify(restored.nodes);
          return restored;
        });
        if (next.every((row, i) => row === rungs[i])) return false;
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

  return {palette, canEdit, create};
});
