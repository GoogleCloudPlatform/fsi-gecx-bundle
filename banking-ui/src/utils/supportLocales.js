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

export const SUPPORT_LOCALES = [
  { code: 'en-US', label: 'English (US)' },
  { code: 'fr-CA', label: 'Français (Canada)' },
  { code: 'fr-FR', label: 'Français (France)' },
  { code: 'de-DE', label: 'Deutsch (Deutschland)' },
  { code: 'it-IT', label: 'Italiano (Italia)' },
  { code: 'pt-BR', label: 'Português (Brasil)' },
  { code: 'es-MX', label: 'Español (México)' },
  { code: 'es-ES', label: 'Español (España)' },
  { code: 'es-US', label: 'Español (EE. UU.)' },
];

export function getSupportLocale(value) {
  return SUPPORT_LOCALES.find(({ code }) => code === value) || SUPPORT_LOCALES[0];
}

// Only runtime-confirmed changes affect display; transcript language is not evidence.
export function confirmedVoiceLocale(event) {
  if (!['VOICE_LANGUAGE_CHANGED', 'VOICE_LANGUAGE_FALLBACK'].includes(event?.type)) return null;
  return SUPPORT_LOCALES.some(({ code }) => code === event.locale) ? event.locale : null;
}
