// Copyright 2026 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     https://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import test from 'node:test';
import assert from 'node:assert/strict';
import { parseMoneyInput, formatMoney, sumMoneyByCurrency, paymentIntent } from '../src/utils/money.js';

for (const [code, text, amount] of [['USD', '12.34', 1234], ['MXN', '12.34', 1234], ['JPY', '1234', 1234], ['BHD', '1.234', 1234]]) {
  test(`exact ${code} input`, () => {
    assert.deepEqual(parseMoneyInput(text, code), { amount_minor: amount, currency_code: code });
    assert.equal(parseMoneyInput('-' + text, code).amount_minor, -amount);
  });
}
test('unsafe integers, unsupported codes, and ambiguous decimals fail', () => {
  for (const text of ['1,000.00', '1,23', '1e2', 'Infinity', 'NaN', '', '.5', '1.234', '90071992547409.92']) {
    assert.throws(() => parseMoneyInput(text, 'USD'));
  }
  assert.throws(() => parseMoneyInput('1.0', 'JPY'));
  assert.throws(() => parseMoneyInput('1', 'usd'));
  assert.throws(() => parseMoneyInput('1', 'EUR'));
});
test('formatting preserves the last minor unit at the safe-integer boundary', () => {
  const money = parseMoneyInput('90071992547409.91', 'USD');
  assert.equal(money.amount_minor, Number.MAX_SAFE_INTEGER);
  assert.equal(formatMoney(money), '$90,071,992,547,409.91');
  assert.equal(formatMoney({ ...money, amount_minor: -money.amount_minor }), '-$90,071,992,547,409.91');
  assert.equal(formatMoney({ amount_minor: -1, currency_code: 'USD' }), '-$0.01');
  assert.throws(() => formatMoney({ amount_minor: 1.5, currency_code: 'USD' }));
});
test('deposit totals stay separated by currency', () => {
  assert.deepEqual(sumMoneyByCurrency([
    {amount_minor: 125, currency_code: 'USD'}, {amount_minor: 100, currency_code: 'MXN'},
    {amount_minor: 75, currency_code: 'USD'},
  ]), [{amount_minor: 200, currency_code: 'USD'}, {amount_minor: 100, currency_code: 'MXN'}]);
});
test('retries retain intent identity; changing account, currency or amount creates a new key', () => {
  let count = 0;
  const key = () => String(++count);
  const request = {source_account_id: 'source', credit_account_id: 'card', money: {amount_minor: 125, currency_code: 'USD'}};
  const first = paymentIntent(null, request, key);
  assert.equal(paymentIntent(first, structuredClone(request), key), first);
  for (const change of [
    {...request, source_account_id: 'another'},
    {...request, credit_account_id: 'another'},
    {...request, money: {...request.money, currency_code: 'MXN'}},
    {...request, money: {...request.money, amount_minor: 126}},
  ]) assert.notEqual(paymentIntent(first, change, key).key, first.key);
});
