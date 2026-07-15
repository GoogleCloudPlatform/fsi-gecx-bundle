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

export const PAGE_TITLES = {
  '/': 'Home',
  '/accounts': 'Account Ledger',
  '/checking-accounts': 'Checking Accounts',
  '/commpare-products': 'Compare Products',
  '/savings-accounts': 'Savings Accounts',
  '/certificate-accounts': 'Certificate Accounts',
  '/credit-cards': 'Credit Cards',
  '/mortgages': 'Mortgages & Home Loans',
  '/mortgage-rates': 'Mortgage Rates',
  '/help-center': 'Help & Learning Center',
  '/fee-schedule': 'Fee Schedule',
  '/disclosures': 'Account Disclosures',
  '/settings': 'Settings',
  '/edit-profile': 'Edit Profile',
  '/apply/credit-card': 'Apply for Credit Card',
  '/search': 'Search Site',
  '/support/voice': 'Voice Support Consultation',
  '/locator': 'Find Branch/ATM',
};

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
  GUIDANCE_SNAPSHOT: 'GUIDANCE_SNAPSHOT',
  CUSTOMER_TEXT_INPUT: 'CUSTOMER_TEXT_INPUT',
  CUSTOMER_TEXT_ACCEPTED: 'CUSTOMER_TEXT_ACCEPTED',
  CUSTOMER_TEXT_REJECTED: 'CUSTOMER_TEXT_REJECTED',
  AVATAR_FALLBACK: 'AVATAR_FALLBACK',
  SESSION_END: 'SESSION_END',
  TRANSCRIPT: 'TRANSCRIPT'
};


export function enableCcai() {
  const envVal = window.env?.ENABLE_CCAI !== undefined ? window.env.ENABLE_CCAI : import.meta.env.VITE_ENABLE_CCAI;
  return envVal === 'true' || envVal === true;
}
