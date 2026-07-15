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

/**
 * Format phone numbers dynamically based on browser locale
 */
export const formatPhoneNumber = (value, locale = navigator.language) => {
  if (!value) return value;
  
  // Strip all non-digit characters
  const phoneNumber = value.replace(/[^\d]/g, '');
  const phoneNumberLength = phoneNumber.length;

  // US Format: (XXX) XXX-XXXX (up to 10 digits)
  if (locale.startsWith('en-US')) {
    if (phoneNumberLength < 4) return phoneNumber;
    if (phoneNumberLength < 7) {
      return `(${phoneNumber.slice(0, 3)}) ${phoneNumber.slice(3)}`;
    }
    return `(${phoneNumber.slice(0, 3)}) ${phoneNumber.slice(3, 6)}-${phoneNumber.slice(6, 10)}`;
  }
  
  // UK Format: XXXXX XXXXXX (up to 11 digits)
  if (locale.startsWith('en-GB')) {
    if (phoneNumberLength < 6) return phoneNumber;
    return `${phoneNumber.slice(0, 5)} ${phoneNumber.slice(5, 11)}`;
  }

  // France Format: XX XX XX XX XX (up to 10 digits)
  if (locale.startsWith('fr-FR')) {
    const segments = [];
    for (let i = 0; i < phoneNumberLength && i < 10; i += 2) {
      segments.push(phoneNumber.slice(i, i + 2));
    }
    return segments.join(' ');
  }

  // Italy Format: XXX XXX XXXX (up to 10 digits)
  if (locale.startsWith('it-IT')) {
    if (phoneNumberLength < 4) return phoneNumber;
    if (phoneNumberLength < 7) {
      return `${phoneNumber.slice(0, 3)} ${phoneNumber.slice(3)}`;
    }
    return `${phoneNumber.slice(0, 3)} ${phoneNumber.slice(3, 6)} ${phoneNumber.slice(6, 10)}`;
  }

  // Fallback Format: XXX XXX XXXX...
  if (phoneNumberLength <= 3) return phoneNumber;
  if (phoneNumberLength <= 6) {
    return `${phoneNumber.slice(0, 3)} ${phoneNumber.slice(3)}`;
  }
  return `${phoneNumber.slice(0, 3)} ${phoneNumber.slice(3, 6)} ${phoneNumber.slice(6)}`;
};

/**
 * Return phone number input placeholder based on browser locale
 */
export const getPhonePlaceholder = (locale = navigator.language) => {
  if (locale.startsWith('en-US')) return "Phone Number (e.g. (555) 019-9988)";
  if (locale.startsWith('en-GB')) return "Phone Number (e.g. 07700 900077)";
  if (locale.startsWith('fr-FR')) return "Phone Number (e.g. 06 12 34 56 78)";
  if (locale.startsWith('it-IT')) return "Phone Number (e.g. 333 123 4567)";
  return "Phone Number";
};

/**
 * Format the build time from the environment variable
 */
export const getFormattedBuildTime = () => {
  if (window.env?.BUILD_VERSION === 'local-dev') {
    window.env.BUILD_TIME = Date.now();
  }
  if (!window.env?.BUILD_TIME || window.env.BUILD_TIME === '${BUILD_TIME}' || window.env.BUILD_TIME === '0') return 'unknown';
  const buildTimeMs = parseInt(window.env.BUILD_TIME, 10);
  if (isNaN(buildTimeMs)) return 'unknown';
  return new Date(buildTimeMs).toLocaleString();
};
