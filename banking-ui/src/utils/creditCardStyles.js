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
 * Visual presentation styles keyed by product_code.
 * Contains only UI presentation properties (gradients, chip/badge classes, accent color, bot name).
 * No financial figures or catalog terms are stored here.
 * All Tailwind class strings are static to support Tailwind CSS extraction.
 */

export const DEFAULT_CARD_STYLE = {
  cardStyle: 'from-slate-900 via-slate-800 to-slate-950 border-slate-500/30 text-slate-200',
  chipStyle: 'bg-slate-400/20 border-slate-500/40 text-slate-300',
  accentColor: '#64748b',
  badgeBg: 'bg-slate-500/10 border-slate-500/20 text-slate-600 dark:text-slate-400',
  botName: 'Credit Support Bot',
};

export const CREDIT_CARD_STYLES = {
  PLATINUM_TRAVEL_REWARDS: {
    cardStyle: 'from-slate-900 via-slate-800 to-slate-950 border-amber-500/30 text-amber-400',
    chipStyle: 'bg-amber-400/20 border-amber-500/40 text-amber-300',
    accentColor: '#f59e0b',
    badgeBg: 'bg-amber-500/10 border-amber-500/20 text-amber-500 dark:text-amber-400',
    botName: 'Travel Rewards Bot',
  },
  CASHBACK_EVERYDAY: {
    cardStyle: 'from-emerald-900 via-teal-900 to-cyan-950 border-emerald-500/30 text-emerald-400',
    chipStyle: 'bg-emerald-400/20 border-emerald-500/40 text-emerald-300',
    accentColor: '#10b981',
    badgeBg: 'bg-emerald-500/10 border-emerald-500/20 text-emerald-600 dark:text-emerald-400',
    botName: 'Cash Back Advisor',
  },
  LOW_APR_BALANCE_TRANSFER: {
    cardStyle: 'from-sky-900 via-blue-950 to-slate-900 border-sky-500/30 text-sky-400',
    chipStyle: 'bg-sky-400/20 border-sky-500/40 text-sky-300',
    accentColor: '#0ea5e9',
    badgeBg: 'bg-sky-500/10 border-sky-500/20 text-sky-600 dark:text-sky-400',
    botName: 'Balance Transfer Agent',
  },
  BUSINESS_ADVANTAGE: {
    cardStyle: 'from-purple-950 via-slate-900 to-indigo-950 border-purple-500/30 text-purple-400',
    chipStyle: 'bg-purple-400/20 border-purple-500/40 text-purple-300',
    accentColor: '#a855f7',
    badgeBg: 'bg-purple-500/10 border-purple-500/20 text-purple-600 dark:text-purple-400',
    botName: 'Business Credit Advisor',
  },
  SECURED_STARTER: {
    cardStyle: 'from-indigo-950 via-slate-900 to-indigo-900 border-indigo-500/30 text-indigo-400',
    chipStyle: 'bg-indigo-400/20 border-indigo-500/40 text-indigo-300',
    accentColor: '#6366f1',
    badgeBg: 'bg-indigo-500/10 border-indigo-500/20 text-indigo-600 dark:text-indigo-400',
    botName: 'Credit Support Bot',
  },
};

/**
 * Returns the presentation style for a given product_code, or DEFAULT_CARD_STYLE if unknown.
 */
export function getCreditCardStyle(productCode) {
  if (!productCode) return DEFAULT_CARD_STYLE;
  return CREDIT_CARD_STYLES[productCode] || DEFAULT_CARD_STYLE;
}
