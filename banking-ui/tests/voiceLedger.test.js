import assert from 'node:assert/strict';
import test from 'node:test';

import { formatVoiceLedgerAmount } from '../src/utils/voiceLedger.js';


test('voice ledger displays pending and posted amounts without accounting signs', () => {
  assert.equal(formatVoiceLedgerAmount(123456), '$1234.56');
  assert.equal(formatVoiceLedgerAmount(-123456), '$1234.56');
});

test('voice ledger safely formats missing values', () => {
  assert.equal(formatVoiceLedgerAmount(undefined), '$0.00');
});
