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
