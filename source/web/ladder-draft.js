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

  function instruction(nodes, id) {
    for (const [index, node] of nodes.entries()) {
      if (!node.branch && node.draftId === id) return {series: nodes, index, node};
      for (const leg of node.branch || []) {
        const found = instruction(leg, id);
        if (found) return found;
      }
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

    function change(rungIndex, edit) {
      const before = rungs[rungIndex];
      if (!before) return null;
      const nodes = structuredClone(before.nodes), result = edit(nodes);
      if (!result) return null;
      const logic = serialize(nodes);
      const text = logic === serialize(base[rungIndex].nodes) ? base[rungIndex].text : logic + ';';
      past.push(rungs);
      if (past.length > 100) past.shift();
      future.length = 0;
      rungs = rungs.slice();
      rungs[rungIndex] = {...before, nodes, text};
      return result;
    }

    return {
      get rungs() {return rungs;},
      get changed() {return rungs.some((rung, i) => rung.text !== base[i].text);},
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
      remove(rung, id) {
        return change(rung, nodes => {
          const found = instruction(nodes, id);
          if (!found) return null;
          found.series.splice(found.index, 1);
          return id;
        });
      },
      setOperands(rung, id, operands) {
        const args = operands.map(operandText);
        return change(rung, nodes => {
          const found = instruction(nodes, id);
          if (!found || found.node.args.length !== args.length ||
              args.every((arg, i) => arg === found.node.args[i])) return null;
          found.node.args = args;
          delete found.node.literal_values;
          return id;
        });
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
