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

/** Canonical Money utilities. No legacy field normalization or FX. */
export const currencyExponents = Object.freeze({ USD: 2, MXN: 2, JPY: 0, BHD: 3 });

export function validateMoney(money) {
  if (!money || !Number.isSafeInteger(money.amount_minor) ||
      !Object.hasOwn(currencyExponents, money.currency_code)) {
    throw new Error('Invalid Money amount or currency.');
  }
  return money;
}

export function parseMoneyInput(input, currencyCode) {
  if (!Object.hasOwn(currencyExponents, currencyCode)) throw new Error('Unsupported currency.');
  const exponent = currencyExponents[currencyCode];
  const match = /^([+-]?)([0-9]+)(?:\.([0-9]+))?$/.exec(input.trim());
  if (!match || (match[3] || '').length > exponent) {
    throw new Error(`Enter an ungrouped amount with at most ${exponent} decimal places, using a decimal point.`);
  }
  const minor = BigInt(match[2]) * (10n ** BigInt(exponent)) + BigInt((match[3] || '').padEnd(exponent, '0') || '0');
  const signed = match[1] === '-' ? -minor : minor;
  if (signed > BigInt(Number.MAX_SAFE_INTEGER) || signed < -BigInt(Number.MAX_SAFE_INTEGER)) {
    throw new Error('Amount exceeds the supported range.');
  }
  return { amount_minor: Number(signed), currency_code: currencyCode };
}

export function formatMoney(money, locale = 'en-US') {
  if (money == null) return '—';
  validateMoney(money);
  const exponent = currencyExponents[money.currency_code];
  const value = BigInt(money.amount_minor);
  const digits = (value < 0n ? -value : value).toString().padStart(exponent + 1, '0');
  const decimal = (value < 0n ? '-' : '') + (exponent
    ? `${digits.slice(0, -exponent)}.${digits.slice(-exponent)}` : digits);
  // Intl accepts an exact decimal string, avoiding Number division/rounding.
  return new Intl.NumberFormat(locale, { style: 'currency', currency: money.currency_code,
    minimumFractionDigits: exponent, maximumFractionDigits: exponent }).format(decimal);
}

export function sumMoneyByCurrency(values) {
  const totals = new Map();
  for (const value of values) {
    validateMoney(value);
    totals.set(value.currency_code, (totals.get(value.currency_code) || 0n) + BigInt(value.amount_minor));
  }
  return [...totals].map(([currency_code, amount]) => validateMoney({currency_code, amount_minor: Number(amount)}));
}

export function paymentIntent(previous, request, createKey = () => crypto.randomUUID()) {
  const signature = JSON.stringify([request.source_account_id, request.credit_account_id,
    request.money.currency_code, request.money.amount_minor]);
  return previous?.signature === signature ? previous : { signature, key: createKey(), completed: false };
}
