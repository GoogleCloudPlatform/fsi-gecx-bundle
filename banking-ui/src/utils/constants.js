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

export const HELP_CATEGORIES = [
  'All',
  'Credit Mastery',
  'Digital Security',
  'Home Financing',
  'Vehicle Purchasing',
  'Wealth & Budgeting'
];

/**
 * Shared constants for LiveKit Data Channel event communication
 */
export const DataChannelEvent = {
  CARD_STATUS_LOCK: 'CARD_STATUS_LOCK',
  FRAUD_ALERT_INSPECTED: 'FRAUD_ALERT_INSPECTED',
  FRAUD_CASE_TRIAGED: 'FRAUD_CASE_TRIAGED',
  CARD_REPLACED: 'CARD_REPLACED',
  WALLET_PROVISIONING_QUEUED: 'WALLET_PROVISIONING_QUEUED',
  FRAUD_ALERT_RESOLVED: 'FRAUD_ALERT_RESOLVED',
  LIMIT_UPDATED: 'LIMIT_UPDATED',
  FEE_REVERSED: 'FEE_REVERSED',
  HIGHLIGHT_TRANSACTION: 'HIGHLIGHT_TRANSACTION',
  SESSION_END: 'SESSION_END',
  TRANSCRIPT: 'TRANSCRIPT'
};

export function showInfoModals() {
  const localVal = localStorage.getItem('show_info_modals');
  if (localVal !== null) {
    return localVal !== 'false';
  }
  const envVal = window.env?.SHOW_INFO_MODALS !== undefined ? window.env.SHOW_INFO_MODALS : import.meta.env.VITE_SHOW_INFO_MODALS;
  return envVal !== 'false' && envVal !== false;
}

export function enableCcai() {
  const envVal = window.env?.ENABLE_CCAI !== undefined ? window.env.ENABLE_CCAI : import.meta.env.VITE_ENABLE_CCAI;
  return envVal === 'true' || envVal === true;
}
