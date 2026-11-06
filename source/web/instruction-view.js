/* Instruction faceplates are presentation metadata, independent of graph topology. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.LogixInstructionView = api;
})(typeof globalThis === 'object' ? globalThis : this, function () {
  'use strict';
  const catalog = {};
  function add(op, title, labels = '') {catalog[op] = {title, labels: labels ? labels.split('|') : []};}
  for (const [op, title] of Object.entries({XIC: 'Examine On', XIO: 'Examine Off', OTE: 'Output Energize',
    OTL: 'Output Latch', OTU: 'Output Unlatch', ONS: 'One Shot', AFI: 'Always False', NOP: 'No Operation',
    MCR: 'Master Control Reset', TND: 'Temporary End', BRK: 'Break', UID: 'User Interrupt Disable', UIE: 'User Interrupt Enable'})) add(op, title, ['XIC', 'XIO', 'OTE', 'OTL', 'OTU', 'ONS'].includes(op) ? 'Bit' : '');
  add('OSR', 'One Shot Rising', 'Storage Bit|Output Bit');add('OSF', 'One Shot Falling', 'Storage Bit|Output Bit');
  for (const [op, title] of Object.entries({EQU: 'Equal', NEQ: 'Not Equal', LES: 'Less Than', LEQ: 'Less Than or Equal',
    GRT: 'Greater Than', GEQ: 'Greater Than or Equal'})) add(op, title, 'Source A|Source B');
  add('LIM', 'Limit Test', 'Low Limit|Test|High Limit');add('MEQ', 'Masked Equal', 'Source|Mask|Compare');add('CMP', 'Compare', 'Expression');
  for (const [op, title] of Object.entries({ADD: 'Add', SUB: 'Subtract', MUL: 'Multiply', DIV: 'Divide', MOD: 'Modulo',
    AND: 'Bitwise AND', OR: 'Bitwise OR', XOR: 'Bitwise XOR', XPY: 'X to Power of Y'})) add(op, title, 'Source A|Source B|Dest');
  for (const [op, title] of Object.entries({MOV: 'Move', NEG: 'Negate', ABS: 'Absolute Value', NOT: 'Bitwise NOT',
    SQR: 'Square Root', LN: 'Natural Log', LOG: 'Log Base 10', DEG: 'Radians to Degrees', RAD: 'Degrees to Radians',
    SIN: 'Sine', COS: 'Cosine', TAN: 'Tangent', ASN: 'Arc Sine', ACS: 'Arc Cosine', ATN: 'Arc Tangent',
    FRD: 'From BCD', TOD: 'To BCD', TRN: 'Truncate', DTOS: 'DINT to String', STOD: 'String to DINT',
    STOR: 'String to REAL', LOWER: 'Lower Case', UPPER: 'Upper Case'})) add(op, title, 'Source|Dest');
  add('CLR', 'Clear', 'Dest');add('CPT', 'Compute', 'Dest|Expression');
  add('MVM', 'Masked Move', 'Source|Mask|Dest');add('BTD', 'Bit Field Distribute', 'Source|Source Bit|Dest|Dest Bit|Length');
  for (const [op, title] of Object.entries({COP: 'Copy File', CPS: 'Synchronous Copy File', FLL: 'File Fill'})) add(op, title, 'Source|Dest|Length');
  add('SIZE', 'Size', 'Source|Dimension|Dest');add('SWPB', 'Swap Byte', 'Source|Order Mode|Dest');
  for (const [op, title] of Object.entries({TON: 'Timer On Delay', TOF: 'Timer Off Delay', RTO: 'Retentive Timer On'})) add(op, title, 'Timer|Preset|Accum');
  add('CTU', 'Count Up', 'Counter|Preset|Accum');add('CTD', 'Count Down', 'Counter|Preset|Accum');add('RES', 'Reset', 'Control');
  add('JSR', 'Jump to Subroutine', 'Routine Name|Input Par');add('SBR', 'Subroutine');add('RET', 'Return');
  add('JMP', 'Jump to Label', 'Label');add('LBL', 'Label', 'Label');
  add('FOR', 'For', 'Routine Name|Index|Initial Value|Terminal Value|Step Size');
  add('EVENT', 'Event Task', 'Task');
  for (const op of ['GSV', 'SSV']) add(op, op === 'GSV' ? 'Get System Value' : 'Set System Value', 'Class Name|Instance Name|Attribute Name|' + (op === 'GSV' ? 'Dest' : 'Source'));
  add('CONCAT', 'String Concatenate', 'Source A|Source B|Dest');add('MID', 'Middle String', 'Source|Qty|Start|Dest');
  add('FIND', 'Find String', 'Source|Search|Start|Result');add('INSERT', 'Insert String', 'Source|Insert|Start|Dest');
  add('DELETE', 'Delete String', 'Source|Qty|Start|Dest');add('RTOS', 'REAL to String', 'Source|Dest');
  for (const op of ['BSL', 'BSR']) add(op, op === 'BSL' ? 'Bit Shift Left' : 'Bit Shift Right', 'Array|Control|Source Bit|Length');
  for (const [op, title] of Object.entries({FFL: 'FIFO Load', FFU: 'FIFO Unload', LFL: 'LIFO Load', LFU: 'LIFO Unload'})) {
    const storage = op.startsWith('F') ? 'FIFO' : 'LIFO';
    add(op, title, (op.endsWith('L') ? 'Source|' + storage : storage + '|Dest') + '|Control|Length|Position');
  }
  for (const op of ['SQO', 'SQI']) add(op, op === 'SQO' ? 'Sequencer Output' : 'Sequencer Input', 'File|Mask|' + (op === 'SQO' ? 'Dest' : 'Source') + '|Control|Length|Position');
  add('SQL', 'Sequencer Load', 'File|Source|Control|Length|Position');
  for (const op of ['AVE', 'STD']) add(op, op === 'AVE' ? 'Average' : 'Standard Deviation', 'Array|Dimension|Dest|Control|Length|Position');
  add('SRT', 'Sort', 'Array|Dimension|Control|Length|Position');
  add('FSC', 'File Search and Compare', 'Control|Length|Position|Mode|Expression');
  add('FAL', 'File Arithmetic and Logic', 'Control|Length|Position|Mode|Dest|Expression');
  for (const op of ['FBC', 'DDT']) add(op, op === 'FBC' ? 'File Bit Compare' : 'Diagnostic Detect', 'Source|Reference|Result|Cmp Control|Cmp Length|Cmp Position|Result Control|Result Length|Result Position');
  add('DTR', 'Data Transition', 'Source|Mask|Reference');
  add('ALMD', 'Digital Alarm', 'ALMD|ProgAck|ProgReset|ProgDisable|ProgEnable|MinDurationPRE|MinDurationACC');
  add('PID', 'PID', 'PID|Process Variable|Tieback|Control Variable|PID Master Loop|Inhold Bit|Inhold Value');

  const contacts = new Set(['XIC', 'XIO']), coils = new Set(['OTE', 'OTL', 'OTU']);
  const inline = new Set([...contacts, ...coils, 'ONS', 'AFI', 'NOP', 'MCR', 'TND', 'BRK', 'UID', 'UIE', 'JMP', 'LBL']);
  const control = {BSL: 1, BSR: 1, FFL: 2, FFU: 2, LFL: 2, LFU: 2, SQL: 2, SQO: 3, SQI: 3, AVE: 3, STD: 3, SRT: 2, FSC: 0, FAL: 0};
  function describe(node, definitions = {}) {
    const op = node.opcode.toUpperCase(), args = node.operands;
    const definition = Object.values(definitions).find(item => item.name.toUpperCase() === op);
    if (definition) {
      let argument = 1;
      const instance = args[0] || '?', fields = [{label: 'Instance', ref: instance, instance: true, visible: true}];
      for (const parameter of definition.parameters) {
        if (['enablein', 'enableout'].includes(parameter.name.toLowerCase())) continue;
        // Consume required arguments even when hidden; optional parameters live in the instance.
        const ref = parameter.required ? args[argument++] || '?' : instance + '.' + parameter.name;
        fields.push({label: parameter.name, ref, usage: parameter.usage, type: parameter.type,
          dimensions: parameter.dimensions, description: parameter.description, required: parameter.required, visible: parameter.visible});
      }
      for (; argument < args.length; argument++) fields.push({label: 'Extra argument ' + argument, ref: args[argument], visible: true});
      return {kind: 'aoi', title: definition.name, description: definition.description, fields,
        rows: fields.filter(row => row.visible), flags: ['EnableIn', 'EnableOut'].map((name, i) => ({label: i ? 'ENO' : 'EN', ref: instance + '.' + name}))};
    }
    const entry = catalog[op], fields = args.map((ref, i) => ({ref, visible: true,
      label: entry?.labels[i] || (op === 'SBR' ? 'Input Par ' : op === 'RET' ? 'Return Par ' : 'Operand ') + (i + 1)}));
    if (op === 'JSR') {
      const count = Number(args[1]);fields.splice(1, 1);
      fields.slice(1).forEach((field, i) => {field.label = i < count ? 'Input Par ' + (i + 1) : 'Return Par ' + (i - count + 1);});
    }
    let flags = [];
    if (['TON', 'TOF', 'RTO', 'CTU', 'CTD'].includes(op)) {
      fields[1] = {label: 'Preset', ref: args[0] + '.PRE', member: true, visible: true};fields[2] = {label: 'Accum', ref: args[0] + '.ACC', member: true, visible: true};
      flags = (['CTU', 'CTD'].includes(op) ? [op === 'CTU' ? 'CU' : 'CD', 'DN'] : ['EN', 'DN']).map(label => ({label, ref: args[0] + '.' + label}));
    }
    if (op === 'ALMD') {
      for (const [i, member] of [[5, 'MinDurationPRE'], [6, 'MinDurationACC']]) {
        if (fields[i]?.ref === '?') fields[i] = {label: member, ref: args[0] + '.' + member, member: true, visible: true};
      }
      flags = [['ALM', 'InAlarm'], ['ACK', 'Acked'], ['SUP', 'Suppressed'], ['SHV', 'Shelved'],
        ['DIS', 'Disabled'], ['FLT', 'Status.0'], ['BAD', 'Status.1'], ['SEV', 'Status.2']]
        .map(([label, member]) => ({label, ref: args[0] + '.' + member}));
    }
    if (Object.hasOwn(control, op)) {
      const at = control[op], length = op === 'BSL' || op === 'BSR' ? 3 : at + 1;
      for (const [index, member] of [[length, 'LEN'], [length + 1, 'POS']]) {
        if (index < fields.length) {fields[index].ref = args[at] + '.' + member;fields[index].member = true;}
      }
      flags = ['EN', 'DN', 'ER'].map(label => ({label, ref: args[at] + '.' + label}));
    }
    if (op === 'FBC' || op === 'DDT') {
      for (const at of [3, 6]) for (const [offset, member] of [[1, 'LEN'], [2, 'POS']]) {
        if (fields[at + offset]) {fields[at + offset].ref = args[at] + '.' + member;fields[at + offset].member = true;}
      }
    }
    // Routine names, class names and expressions are source, not missing tag values.
    for (let i = 0; i < fields.length; i++) {
      fields[i].sourceOnly = (['JSR', 'FOR', 'EVENT', 'JMP', 'LBL'].includes(op) && i === 0) ||
        (['GSV', 'SSV'].includes(op) && i < 3) || (op === 'CMP' || (op === 'CPT' && i === 1)) ||
        (['FSC', 'FAL'].includes(op) && (i === 3 || i === fields.length - 1));
    }
    return {kind: contacts.has(op) ? 'contact' : coils.has(op) ? 'coil' : inline.has(op) ? 'inline' : 'box',
      title: entry?.title || op, fields, rows: fields, flags, known: !!entry};
  }
  function dimensions(node, presentation = describe(node)) {
    if (['contact', 'coil', 'inline'].includes(presentation.kind)) {
      const longest = Math.max(0, ...node.operands.map(x => x.length));
      return {width: Math.max(150, Math.min(320, longest * 7 + 24)), above: 43, below: 34, symbol: true};
    }
    const label = Math.max(65, ...presentation.rows.map(row => row.label.length * 6));
    const reference = Math.max(95, ...presentation.rows.map(row => Math.min(40, row.ref.length) * 6.6));
    const boxWidth = Math.max(245, label + reference + 30, presentation.title.length * 6.6 + 62);
    return {width: boxWidth + (presentation.flags.length ? 45 : 0), boxWidth, labelWidth: label,
      above: 45, below: presentation.rows.length * 34 + 15, rows: presentation.rows.length, symbol: false};
  }
  return {describe, dimensions, catalog};
});
