/**
 * Copyright 2026 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

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
