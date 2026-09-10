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
import { confirmedVoiceLocale } from '../src/utils/supportLocales.js';
import { formatMoney } from '../src/utils/money.js';

test('confirmed language changes and fallback reformat unchanged canonical money', () => {
  const money = Object.freeze({ amount_minor: 123499, currency_code: 'USD' });
  let locale = 'en-US';
  const english = formatMoney(money, locale);
  locale = confirmedVoiceLocale({ type: 'VOICE_LANGUAGE_CHANGED', locale: 'it-IT' });
  assert.equal(locale, 'it-IT');
  assert.notEqual(formatMoney(money, locale), english);
  assert.match(formatMoney(money, locale), /1\.?234,99/);
  locale = confirmedVoiceLocale({ type: 'VOICE_LANGUAGE_FALLBACK', locale: 'en-US' });
  assert.equal(formatMoney(money, locale), english);
  assert.deepEqual(money, { amount_minor: 123499, currency_code: 'USD' });
});

test('unconfirmed requests and unknown locales do not change the display locale', () => {
  for (const event of [null, {type:'TRANSCRIPT',locale:'it-IT'}, {type:'VOICE_LANGUAGE_CHANGED',locale:'invalid'}]) {
    assert.equal(confirmedVoiceLocale(event), null);
  }
});
