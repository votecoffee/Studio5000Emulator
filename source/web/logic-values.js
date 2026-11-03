/* Resolve snapshot addresses only. No expression execution, polling or tag writes. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.LogixLogicValues = api;
})(typeof globalThis === 'object' ? globalThis : this, function () {
  'use strict';
  const widths = {SINT: 8, USINT: 8, INT: 16, UINT: 16, DINT: 32, UDINT: 32, LINT: 64, ULINT: 64};
  function create(tags, {routine = '', context = '', bindings = {}} = {}) {
    const values = new Map(tags.map(row => [row.name.toLowerCase(), row])), known = new Set(values.keys());
    const bound = new Map(Object.entries(bindings).map(([name, ref]) => [name.toLowerCase(), ref]));
    for (const name of values.keys()) for (let i = 0; i < name.length; i++) {
      if (name[i] === '.' || name[i] === '[') known.add(name.slice(0, i));
    }
    function address(ref) {
      if (/^Program:[A-Za-z_][\w]*\./i.test(ref)) return ref;
      const root = ref.match(/^([A-Za-z_][\w:]*)(.*)$/);if (!root) return null;
      if (routine.startsWith('AOI:')) {
        if (!context) return null;
        return bound.has(root[1].toLowerCase()) ? bound.get(root[1].toLowerCase()) + root[2] : context + '.' + ref;
      }
      const prefix = 'Program:' + routine.split('/')[0] + '.';
      // A declared local structure/array shadows globals even when this member is unavailable.
      return known.has((prefix + root[1]).toLowerCase()) ? prefix + ref : ref;
    }
    function at(canonical) {
      if (!canonical) return null;
      const key = canonical.toLowerCase(), row = values.get(key);if (row) return row;
      if (known.has(key)) return {name: canonical, type: 'Aggregate', value: 'Members', aggregate: true};
      const bit = canonical.match(/^(.*)\.(\d+)$/), base = bit && values.get(bit[1].toLowerCase());
      const width = widths[base?.type];
      if (width && base.value != null && Number(bit[2]) < width) {
        try {return {name: canonical, type: 'BOOL', value: !!((BigInt(base.value) >> BigInt(bit[2])) & 1n)};} catch (_) { /* Unavailable snapshot values stay unknown. */ }
      }
      return null;
    }
    function resolve(ref) {
      const name = String(ref).trim().replace(/\[([A-Za-z_][\w.:]*)\]/g, (all, index) => {
        const row = at(address(index));
        return widths[row?.type] && /^\d+$/.test(String(row.value)) ? '[' + row.value + ']' : all;
      });
      return address(name);
    }
    function read(ref) {
      const name = String(ref).trim(), row = at(resolve(name));
      if (row) return row;
      if (/^(TRUE|FALSE)$/i.test(name)) return {name, type: 'BOOL literal', value: name.toUpperCase() === 'TRUE'};
      if (/^[+-]?\d+(?:\.\d*)?(?:[Ee][+-]?\d+)?$/.test(name)) return {name, type: 'Literal', value: name};
      const radix = name.match(/^(2|8|16)#([\da-fA-F_]+)$/);
      if (radix) {
        try {return {name, type: 'Literal', value: BigInt(({'2': '0b', '8': '0o', '16': '0x'})[radix[1]] + radix[2].replaceAll('_', '')).toString()};} catch (_) { /* Invalid source is not evaluated. */ }
      }
      return null;
    }
    return {read, resolve};
  }
  return {create};
});
