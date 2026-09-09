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

import { useSyncExternalStore } from 'react';

export const presentationLocales = Object.freeze({
  'en-US': 'English (US)', 'es-MX': 'Español (México)',
  'ja-JP': '日本語', 'ar-BH': 'العربية',
});
const eventName = 'money-locale-change';
export function getPresentationLocale() {
  const saved = globalThis.localStorage?.getItem('money.locale');
  if (Object.hasOwn(presentationLocales, saved)) return saved;
  return globalThis.navigator?.language?.startsWith('es') ? 'es-MX' : 'en-US';
}
export function setPresentationLocale(locale) {
  if (!Object.hasOwn(presentationLocales, locale)) throw new Error('Unsupported presentation locale.');
  localStorage.setItem('money.locale', locale);
  window.dispatchEvent(new Event(eventName));
}
function subscribe(notify) {
  window.addEventListener(eventName, notify);
  window.addEventListener('storage', notify);
  return () => { window.removeEventListener(eventName, notify); window.removeEventListener('storage', notify); };
}
export function useMoneyLocale() {
  return [useSyncExternalStore(subscribe, getPresentationLocale, () => 'en-US'), setPresentationLocale];
}

const en = {
  available: 'Available', close: 'Close', title: 'Credit Card Bill Payment', description: 'Pay your credit card using a checking or savings account.',
  language: 'Display language', from: 'Pay From', to: 'Pay To', amount: 'Payment Amount',
  noDeposits: 'No checking/savings accounts available', noCards: 'No credit accounts available',
  card: 'Credit card', outstanding: 'Outstanding', submit: 'Submit Payment', processing: 'Processing Payment...',
  hint: 'Use a decimal point, without grouping (for example, 12.34).',
  positive: 'Please enter a positive payment amount.', sourceRequired: 'Please select a funding account.',
  cardRequired: 'Please select a target credit account.', mismatch: 'Both accounts must use the same currency.',
  funds: 'Insufficient funds. Available:', overpayment: 'Payment exceeds the outstanding balance:',
  invalid: 'Invalid amount. Check decimal precision and the supported amount range.',
  success: 'Payment posted:', failure: 'Payment could not be completed. Check the amount and retry.',
  conflict: 'Payment conflict. Retry this payment with the same details.',
};
const es = {
  available: 'Disponible', close: 'Cerrar', title: 'Pago de tarjeta de crédito', description: 'Paga tu tarjeta con una cuenta de cheques o de ahorros.',
  language: 'Idioma de presentación', from: 'Pagar desde', to: 'Pagar a', amount: 'Importe del pago',
  noDeposits: 'No hay cuentas de cheques o ahorros', noCards: 'No hay cuentas de crédito',
  card: 'Tarjeta de crédito', outstanding: 'Saldo pendiente', submit: 'Enviar pago', processing: 'Procesando pago...',
  hint: 'Usa punto decimal, sin separadores de miles (por ejemplo, 12.34).',
  positive: 'Ingresa un importe de pago positivo.', sourceRequired: 'Selecciona una cuenta de origen.',
  cardRequired: 'Selecciona una cuenta de crédito.', mismatch: 'Ambas cuentas deben usar la misma moneda.',
  funds: 'Fondos insuficientes. Disponible:', overpayment: 'El pago supera el saldo pendiente:',
  invalid: 'Importe no válido. Revisa los decimales y el límite del importe.',
  success: 'Pago registrado:', failure: 'No se pudo completar el pago. Revisa el importe e inténtalo de nuevo.',
  conflict: 'Conflicto de pago. Reintenta el pago con los mismos datos.',
};
export function moneyCopy(locale) { return locale.startsWith('es') ? es : en; }
