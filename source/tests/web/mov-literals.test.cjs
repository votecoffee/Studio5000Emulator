const test = require('node:test');
const assert = require('node:assert/strict');
const values = require('../../web/logic-values.js');

test('typed decimal integer constants retain exact digits and declared type', () => {
  const reader = values.create([]);
  for (const [source, type, value] of [
    ['9223372036854775807L', 'LINT', '9223372036854775807'],
    ['-9223372036854775808l', 'LINT', '-9223372036854775808'],
    ['4294967295u', 'UDINT', '4294967295'],
    ['18446744073709551615UL', 'ULINT', '18446744073709551615'],
    ['+00042Ul', 'ULINT', '42'], ['-0U', 'UDINT', '0']
  ]) assert.deepEqual(reader.read(source), {name: source, type: type + ' literal', value});
});

test('floating LREAL constants retain precision, range, subnormals and zero sign', () => {
  const reader = values.create([]);
  for (const [source, value] of [['0.1L', .1], ['1.0000000000000002L', 1.0000000000000002],
    ['1e308L', 1e308], ['5e-324l', Number.MIN_VALUE], ['.5l', .5], ['1.L', 1], ['1E+2l', 100]]) {
    assert.deepEqual(reader.read(source), {name: source, type: 'LREAL literal', value});
  }
  assert(Object.is(reader.read('-0.0L').value, -0));
});

test('invalid typed constants are unavailable and names/index rules stay separate', () => {
  const row = {name: 'Signal1L', type: 'LINT', value: '9007199254740993'};
  const reader = values.create([row, {name: 'Values[0]', type: 'DINT', value: 7}]);
  assert.equal(reader.read('Signal1L'), row);
  for (const source of ['9223372036854775808L', '-9223372036854775809L', '4294967296U', '-1U',
    '18446744073709551616UL', '-1UL', '1e309L', '1LU', '1ULL', '1 U', '16#FFUL',
    '1_000L', '(1L)', '1L+1L', 'LINT#1', '1.0UL', '1L2', 'Values[0L]']) {
    assert.equal(reader.read(source), null, source);
  }
});
