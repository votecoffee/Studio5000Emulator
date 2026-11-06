/* Ladder source adapter and graph layout. No DOM, tag writes or execution. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.LadderGraph = api;
})(typeof globalThis === 'object' ? globalThis : this, function () {
  'use strict';
  const CONTACTS = new Set(['XIC', 'XIO']);
  const COILS = new Set(['OTE', 'OTL', 'OTU']);
  const INLINE = new Set([...CONTACTS, ...COILS, 'ONS', 'AFI']);
  const CONDITIONS = new Set([...CONTACTS, 'ONS', 'AFI', 'EQU', 'NEQ', 'LES', 'LEQ', 'GRT', 'GEQ', 'LIM', 'MEQ', 'CMP', 'LBL']);
  const port = (node, name) => ({node, port: name});

  function compile(rung, routine = '') {
    const id = `${routine}#${rung.number}`, nodes = [], edges = [], order = [];
    function add(id, kind, inputs, outputs, extra = {}) {
      const node = {id, kind, ports: [...inputs.map(id => ({id, direction: 'in', type: 'power'})),
        ...outputs.map(id => ({id, direction: 'out', type: 'power'}))], ...extra};
      nodes.push(node);return node;
    }
    function wire(from, to) { edges.push({id: `${id}:e${edges.length}`, from, to, type: 'power'}); }
    const left = add(`${id}:left`, 'rail', [], ['out'], {side: 'left'});
    const right = add(`${id}:right`, 'rail', ['in'], [], {side: 'right'});
    function sequence(source, path, incoming) {
      const items = [];let previous = incoming;
      source.forEach((op, index) => {
        const key = `${path}.${index}`;
        if (Array.isArray(op.branch)) {
          const ports = op.branch.map((_, i) => 'path' + i);
          const split = add(key + ':split', 'junction', ['in'], ports, {side: 'split'});
          const join = add(key + ':join', 'junction', ports, ['out'], {side: 'join'});
          wire(previous, port(split.id, 'in'));
          const paths = op.branch.map((branch, i) => {
            const result = sequence(branch, key + '.b' + i, port(split.id, 'path' + i));
            wire(result.end, port(join.id, 'path' + i));return result.region;
          });
          items.push({kind: 'parallel', split: split.id, join: join.id, paths});
          previous = port(join.id, 'out');
        } else {
          const node = add(key, 'instruction', ['in'], ['out'], {opcode: String(op.name),
            operands: op.args.map(String), sourcePath: key.slice(id.length + 1), ordinal: order.length,
            ...(op.literal_values ? {literalValues: structuredClone(op.literal_values)} : {})});
          wire(previous, port(node.id, 'in'));order.push(node.id);
          items.push({kind: 'instruction', node: node.id});previous = port(node.id, 'out');
        }
      });
      return {region: {kind: 'sequence', items}, end: previous};
    }
    const result = sequence(rung.nodes || [], id + ':n', port(left.id, 'out'));
    wire(result.end, port(right.id, 'in'));
    return {schemaVersion: 1, id, routine, number: String(rung.number), comment: rung.comment || '',
      source: rung.text || '', nodes, edges, order, regions: result.region};
  }

  function dimensions(node) {
    if (INLINE.has(node.opcode)) {
      const longest = Math.max(0, ...node.operands.map(x => x.length));
      return {width: Math.max(150, Math.min(240, longest * 7 + 24)), above: 40, below: 34, symbol: true};
    }
    const rows = ['TON', 'TOF', 'RTO', 'CTU', 'CTD'].includes(node.opcode) ? 3 : Math.max(1, node.operands.length);
    return {width: 238, above: 36, below: rows * 27 + 24, rows, symbol: false};
  }

  function layout(graph, minimumWidth = 0, measureInstruction = dimensions) {
    const byId = new Map(graph.nodes.map(n => [n.id, n])), measured = new Map(), placed = {}, ports = {};
    function measure(region) {
      if (measured.has(region)) return measured.get(region);
      let value;
      if (region.kind === 'instruction') value = measureInstruction(byId.get(region.node));
      else if (region.kind === 'sequence') {
        const rows = region.items.map(measure);
        value = {width: rows.reduce((n, x) => n + x.width, 0) + Math.max(0, rows.length - 1) * 30,
          above: Math.max(36, ...rows.map(x => x.above)), below: Math.max(32, ...rows.map(x => x.below))};
      } else {
        const rows = region.paths.map(measure), above = rows[0]?.above || 36;
        value = {width: Math.max(0, ...rows.map(x => x.width)) + 48, above,
          below: rows.reduce((n, x) => n + x.above + x.below, 0) + Math.max(0, rows.length - 1) * 10 - above};
      }
      measured.set(region, value);return value;
    }
    function output(item) {
      if (item.kind === 'instruction') return !CONDITIONS.has(byId.get(item.node).opcode);
      return item.paths.some(path => path.items.length && output(path.items.at(-1)));
    }
    function set(id, geometry, coordinates) {
      placed[id] = geometry;
      for (const [name, point] of Object.entries(coordinates)) ports[id + '/' + name] = point;
    }
    function place(region, x, y, available = measure(region).width) {
      const size = measure(region);
      if (region.kind === 'instruction') {
        set(region.node, {x, y, ...size}, {in: {x, y}, out: {x: x + size.width, y}});return;
      }
      if (region.kind === 'sequence') {
        let trailing = region.items.length;
        while (trailing && output(region.items[trailing - 1])) trailing--;
        const extra = Math.max(0, available - size.width);
        region.items.forEach((item, i) => {
          let width = measure(item).width;
          const stretch = trailing === region.items.length - 1 && item.kind === 'parallel' && i === trailing;
          if (i === trailing && !stretch) x += extra;
          if (stretch) width += extra;
          place(item, x, y, width);x += width + 30;
        });return;
      }
      const split = {in: {x, y}}, joinX = x + available, join = {out: {x: joinX, y}};
      let baseline = y, bottom = y;
      region.paths.forEach((path, i) => {
        const row = measure(path);
        if (i) baseline = bottom + row.above + 10;
        split['path' + i] = {x, y: baseline};join['path' + i] = {x: joinX, y: baseline};
        place(path, x + 24, baseline, available - 48);bottom = baseline + row.below;
      });
      const last = split['path' + Math.max(0, region.paths.length - 1)]?.y || y;
      set(region.split, {x, y, endY: last}, split);set(region.join, {x: joinX, y, endY: last}, join);
    }
    const size = measure(graph.regions), width = Math.max(760, minimumWidth, size.width + 130);
    const y = size.above + 16, height = y + size.below + 20, left = graph.nodes.find(n => n.side === 'left'), right = graph.nodes.find(n => n.side === 'right');
    set(left.id, {x: 54, y, top: 14, bottom: height - 14}, {out: {x: 54, y}});
    set(right.id, {x: width - 28, y, top: 14, bottom: height - 14}, {in: {x: width - 28, y}});
    place(graph.regions, 78, y, width - 130);
    return {width, height, nodes: placed, ports};
  }

  function power(graph, trace, rungIndex) {
    const values = {}, wires = {}, inputs = new Map(graph.nodes.map(n => [n.id, []]));
    const outgoing = new Map(graph.nodes.map(n => [n.id, []])), pending = new Map(graph.nodes.map(n => [n.id, 0]));
    for (const edge of graph.edges) {outgoing.get(edge.from.node).push(edge);pending.set(edge.to.node, pending.get(edge.to.node) + 1);}
    const queue = graph.nodes.filter(n => !pending.get(n.id)), nodes = new Map(graph.nodes.map(n => [n.id, n]));
    const any = xs => xs.includes(true) ? true : xs.includes(undefined) || !xs.length ? undefined : false;
    const recoveryMatches = Number.isInteger(rungIndex) && trace?.rung_index === rungIndex && trace.recovery_source === graph.source;
    while (queue.length) {
      const node = queue.shift(), event = trace?.events?.[node.ordinal];
      const matched = node.kind === 'instruction' && event?.instruction === node.opcode;
      const incoming = node.side === 'left' ? (trace ? trace.events?.[0]?.in ?? trace.power : undefined) : any(inputs.get(node.id));
      const fault = matched && recoveryMatches ? event.recovered_fault : null;
      const recoveredFault = Number.isInteger(fault?.type) && Number.isInteger(fault.code) &&
        Array.isArray(event.args) && node.operands.length === event.args.length &&
        node.operands.every((operand, i) => operand === event.args[i]) ? fault : null;
      values[node.id] = {in: matched ? event.in : incoming, out: node.kind === 'instruction' ? (matched ? event.out : undefined) : incoming,
        event: matched ? event : null, recoveredFault};
      for (const edge of outgoing.get(node.id)) {
        const target = nodes.get(edge.to.node), nextEvent = trace?.events?.[target.ordinal];
        const visited = target.kind !== 'instruction' || nextEvent?.instruction === target.opcode;
        wires[edge.id] = visited ? values[node.id].out : undefined;inputs.get(edge.to.node).push(wires[edge.id]);
        pending.set(edge.to.node, pending.get(edge.to.node) - 1);
        if (!pending.get(edge.to.node)) queue.push(nodes.get(edge.to.node));
      }
    }
    return {nodes: values, edges: wires};
  }

  return {compile, layout, power, dimensions, contacts: CONTACTS, coils: COILS};
});
