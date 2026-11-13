/* Resolve references and bounded index arithmetic from snapshots; no PLC reads or writes. */
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
    function indexValue(text, depth) {
      if (depth > 32 || text.length > 4096) throw Error('Index limit');
      const tokens = [], precedence = {OR: 1, XOR: 2, AND: 3, '+': 4, '-': 4, '*': 5, '/': 5};
      for (let i = 0; i < text.length;) {
        if (/\s/.test(text[i])) {i++;continue;}
        const rest = text.slice(i), number = rest.match(/^(?:(2|8|16)#([\da-fA-F_]+)|\d+)/);
        if (number) {
          const value = number[1] ? BigInt(({'2': '0b', '8': '0o', '16': '0x'})[number[1]] + number[2].replaceAll('_', '')) : BigInt(number[0]);
          tokens.push(['number', value]);i += number[0].length;
        } else if (/^[A-Za-z_]/.test(rest)) {
          const start = i;i += rest.match(/^[A-Za-z_][\w:]*/)[0].length;
          while (i < text.length) {
            if (text[i] === '.') {
              const member = text.slice(i).match(/^\.(?:[A-Za-z_]\w*|\d+)/);if (!member) throw Error('Index member');i += member[0].length;
            } else if (text[i] === '[') {
              let level = 1;i++;
              while (i < text.length && level) {if (text[i] === '[') level++;if (text[i] === ']') level--;i++;}
              if (level) throw Error('Index brackets');
            } else break;
          }
          const name = text.slice(start, i), upper = name.toUpperCase();
          tokens.push(upper in precedence || upper === 'NOT' ? [upper] : ['ref', name]);
        } else if ('+-*/()'.includes(text[i])) tokens.push([text[i++]]);
        else throw Error('Unsupported index token');
        if (tokens.length > 256) throw Error('Index tokens');
      }
      let pos = 0, nesting = 0;
      function parse(minimum = 0) {
        if (++nesting > 32) throw Error('Index nesting');
        const token = tokens[pos++];if (!token) throw Error('Index operand');let node;
        if (token[0] === 'ref' && tokens[pos]?.[0] === '(') {
          const name = token[1].toUpperCase();if (!['FRD', 'TOD', 'SQR'].includes(name)) throw Error('Unsupported index function');
          pos++;node = ['call', name, parse()];if (tokens[pos++]?.[0] !== ')') throw Error('Index function parentheses');
        } else if (token[0] === 'number' || token[0] === 'ref') node = token;
        else if (['+', '-', 'NOT'].includes(token[0])) node = ['unary', token[0], parse(6)];
        else if (token[0] === '(') {node = parse();if (tokens[pos++]?.[0] !== ')') throw Error('Index parentheses');}
        else throw Error('Index operand');
        while (tokens[pos]?.[0] in precedence && precedence[tokens[pos][0]] >= minimum) {
          const op = tokens[pos++][0];node = ['binary', op, node, parse(precedence[op] + 1)];
        }
        nesting--;return node;
      }
      const tree = parse();if (pos !== tokens.length) throw Error('Index suffix');
      const checked = value => {if (value < -2147483648n || value > 2147483647n) throw Error('Index overflow');return value;};
      function visit(node) {
        if (node[0] === 'number') return checked(node[1]);
        if (node[0] === 'ref') {
          const row = at(resolve(node[1], depth + 1));
          if (!widths[row?.type] || !/^-?\d+$/.test(String(row.value)) ||
              typeof row.value === 'number' && !Number.isSafeInteger(row.value)) throw Error('Unknown integer index');
          const value = BigInt(row.value), bits = BigInt(widths[row.type]), unsigned = row.type.startsWith('U');
          if (value < (unsigned ? 0n : -(1n << (bits - 1n))) || value >= (1n << (unsigned ? bits : bits - 1n))) throw Error('Index type range');
          if (node === tree) return value;
          if (!['SINT', 'INT', 'DINT'].includes(row.type)) throw Error('Wide index expression');
          return checked(value);
        }
        if (node[0] === 'call') {
          const x = visit(node[2]);
          if (node[1] === 'SQR') {
            const value = Math.fround(Math.sqrt(Math.abs(Math.fround(Number(x))))), low = Math.floor(value), fraction = value - low;
            return checked(BigInt(fraction < .5 ? low : fraction > .5 ? low + 1 : low % 2 ? low + 1 : low));
          }
          if (node[1] === 'FRD') {
            let bits = BigInt.asUintN(32, x), value = 0n, place = 1n;
            for (let i = 0; i < 8; i++) {value += (bits & 15n) * place;bits >>= 4n;place *= 10n;}
            return checked(value);
          }
          if (x < 0n || x > 99999999n) throw Error('Index BCD range');
          let remaining = x, value = 0n;
          for (let i = 0n; i < 8n; i++) {value |= (remaining % 10n) << (4n * i);remaining /= 10n;}
          return checked(BigInt.asIntN(32, value));
        }
        if (node[0] === 'unary') {
          if (node[1] === '-' && node[2][0] === 'number') return checked(-node[2][1]);
          const x = visit(node[2]);return checked(node[1] === '+' ? x : node[1] === '-' ? -x : ~x);
        }
        const x = visit(node[2]), y = visit(node[3]);
        return checked(node[1] === '+' ? x + y : node[1] === '-' ? x - y : node[1] === '*' ? x * y :
          node[1] === '/' ? x / y : node[1] === 'AND' ? x & y : node[1] === 'OR' ? x | y : x ^ y);
      }
      return visit(tree);
    }
    function resolve(ref, depth = 0) {
      if (depth > 32) return null;
      const text = String(ref).trim();let name = '';
      try {
        for (let i = 0; i < text.length;) {
          if (text[i] !== '[') {name += text[i++];continue;}
          const start = ++i;let level = 1;
          while (i < text.length && level) {if (text[i] === '[') level++;if (text[i] === ']') level--;i++;}
          if (level) return null;
          const content = text.slice(start, i - 1), indices = [];let part = 0, nested = 0;
          for (let j = 0; j <= content.length; j++) {
            if (content[j] === '[' || content[j] === '(') nested++;
            if (content[j] === ']' || content[j] === ')') nested--;
            if (j === content.length || content[j] === ',' && nested === 0) {
              const value = indexValue(content.slice(part, j), depth + 1);if (value < 0n) return null;
              indices.push(value.toString());part = j + 1;
            }
          }
          name += '[' + indices.join(',') + ']';
        }
      } catch (_) {return null;}
      return address(name);
    }
    function read(ref, options = {}) {
      const name = String(ref).trim(), row = at(resolve(name));
      if (row) return row;
      const word = (options.movRadix || options.dintRadix || options.bitwiseRadix || options.integerRadix) && name.match(/^(2|8|16)#([\da-fA-F_ ]+?)(UL|U|L)?$/i);
      if (word && (word[3] || options.movRadix || options.dintRadix)) {
        try {
          const suffix = (word[3] || '').toUpperCase(), digits = word[2];
          if (suffix && (!(options.movRadix || options.bitwiseRadix || options.integerRadix) || !/^[\da-fA-F](?:[\da-fA-F_ ]*[\da-fA-F])?$/.test(digits))) return null;
          const type = {'': 'DINT', L: 'LINT', U: 'UDINT', UL: 'ULINT'}[suffix], bits = BigInt(widths[type]);
          let value = BigInt(({'2': '0b', '8': '0o', '16': '0x'})[word[1]] + digits.replaceAll('_', '').replaceAll(' ', ''));
          if (value >= (1n << bits)) return null;
          if (!type.startsWith('U') && value >= (1n << (bits - 1n))) value -= 1n << bits;
          return {name, type: type + ' radix literal', value: value.toString()};
        } catch (_) {return null;}
      }
      const integer = name.match(/^([+-]?\d+)(UL|U|L)$/i);
      if (integer) {
        try {
          const type = {L: 'LINT', U: 'UDINT', UL: 'ULINT'}[integer[2].toUpperCase()], value = BigInt(integer[1]);
          const bits = BigInt(widths[type]), unsigned = type.startsWith('U');
          if (value < (unsigned ? 0n : -(1n << (bits - 1n))) || value >= (1n << (unsigned ? bits : bits - 1n))) return null;
          return {name, type: type + ' literal', value: value.toString()};
        } catch (_) {return null;}
      }
      const floating = name.match(/^([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?)[Ll]$/);
      if (floating && /[.Ee]/.test(floating[1])) {
        const value = Number(floating[1]);
        return Number.isFinite(value) ? {name, type: 'LREAL literal', value} : null;
      }
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
