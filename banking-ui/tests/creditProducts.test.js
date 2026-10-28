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

import {
  fetchCreditProducts,
  resetCreditProductsCache,
  setCreditProductsFetcher,
  resetCreditProductsFetcher,
  getCreditProductsSnapshot,
  resolveCreditProduct,
  buildCardApplicationPayload,
} from '../src/utils/creditProducts.js';
import {
  buildComparisonRows,
  buildCardFacts,
  applyHref,
  formatIntroOffers,
  formatCreditLimitRange,
  formatBalanceTransferFee,
} from '../src/utils/creditCardPresentation.js';
import { getCreditCardStyle, DEFAULT_CARD_STYLE } from '../src/utils/creditCardStyles.js';

const mockProducts = [
  {
    product_code: 'PLATINUM_TRAVEL_REWARDS',
    product_name: 'Nova Horizon Platinum Travel',
    display_order: 1,
    tagline: 'Premium travel rewards with lounge access',
    best_for: 'Frequent travelers',
    currency_code: 'USD',
    is_secured: false,
    features: ['$200 annual travel statement credit', 'Airport lounge access'],
    min_credit_limit: { money: { amount_minor: 1000000, currency_code: 'USD' }, locale: 'en-US', display_text: '$10,000.00' },
    max_credit_limit: { money: { amount_minor: 7500000, currency_code: 'USD' }, locale: 'en-US', display_text: '$75,000.00' },
    annual_fee: { money: { amount_minor: 39500, currency_code: 'USD' }, locale: 'en-US', display_text: '$395.00' },
    purchase_apr: { rate: '0.2199', display_text: '21.99%' },
    intro_purchase_apr: null,
    intro_balance_transfer_apr: null,
    penalty_apr: { rate: '0.2999', display_text: '29.99%' },
    balance_transfer_fee_rate: { rate: '0.0500', display_text: '5%' },
    balance_transfer_fee_minimum: { money: { amount_minor: 500, currency_code: 'USD' }, locale: 'en-US', display_text: '$5.00' },
    cash_advance_apr: { rate: '0.2999', display_text: '29.99%' },
    cash_advance_fee_rate: { rate: '0.0500', display_text: '5%' },
    cash_advance_fee_minimum: { money: { amount_minor: 1000, currency_code: 'USD' }, locale: 'en-US', display_text: '$10.00' },
    foreign_transaction_fee_rate: { rate: '0.0000', display_text: '0%' },
    late_fee_maximum: { money: { amount_minor: 4000, currency_code: 'USD' }, locale: 'en-US', display_text: '$40.00' },
    returned_payment_fee_maximum: { money: { amount_minor: 4000, currency_code: 'USD' }, locale: 'en-US', display_text: '$40.00' },
    rewards: {
      type: 'POINTS',
      cashback_rate: { rate: '0.0000', display_text: '0%' },
      travel_multiplier: 3,
      dining_multiplier: 3,
      display_text: '3x points on travel, 3x points on dining, 1x points on everything else',
    },
  },
  {
    product_code: 'CASHBACK_EVERYDAY',
    product_name: 'Nova Horizon Everyday Cash',
    display_order: 2,
    tagline: 'Simple, unlimited cash back on everything you buy',
    best_for: 'Everyday spending with effortless cash back',
    currency_code: 'USD',
    is_secured: false,
    features: ['No rotating categories or earning caps', 'Zero liability'],
    min_credit_limit: { money: { amount_minor: 100000, currency_code: 'USD' }, locale: 'en-US', display_text: '$1,000.00' },
    max_credit_limit: { money: { amount_minor: 2500000, currency_code: 'USD' }, locale: 'en-US', display_text: '$25,000.00' },
    annual_fee: { money: { amount_minor: 0, currency_code: 'USD' }, locale: 'en-US', display_text: '$0.00' },
    purchase_apr: { rate: '0.2249', display_text: '22.49%' },
    intro_purchase_apr: { apr: { rate: '0.0000', display_text: '0%' }, months: 12, display_text: '0% intro APR for 12 months' },
    intro_balance_transfer_apr: null,
    penalty_apr: { rate: '0.2999', display_text: '29.99%' },
    balance_transfer_fee_rate: { rate: '0.0500', display_text: '5%' },
    balance_transfer_fee_minimum: { money: { amount_minor: 500, currency_code: 'USD' }, locale: 'en-US', display_text: '$5.00' },
    cash_advance_apr: { rate: '0.2999', display_text: '29.99%' },
    cash_advance_fee_rate: { rate: '0.0500', display_text: '5%' },
    cash_advance_fee_minimum: { money: { amount_minor: 1000, currency_code: 'USD' }, locale: 'en-US', display_text: '$10.00' },
    foreign_transaction_fee_rate: { rate: '0.0300', display_text: '3%' },
    late_fee_maximum: { money: { amount_minor: 4000, currency_code: 'USD' }, locale: 'en-US', display_text: '$40.00' },
    returned_payment_fee_maximum: { money: { amount_minor: 4000, currency_code: 'USD' }, locale: 'en-US', display_text: '$40.00' },
    rewards: {
      type: 'CASHBACK',
      cashback_rate: { rate: '0.0150', display_text: '1.5%' },
      travel_multiplier: 1,
      dining_multiplier: 1,
      display_text: '1.5% cash back on all purchases',
    },
  },
  {
    product_code: 'SECURED_STARTER',
    product_name: 'Nova Horizon Secured Starter',
    display_order: 5,
    tagline: 'Build credit with a deposit-backed card',
    best_for: 'Establishing or rebuilding credit',
    currency_code: 'USD',
    is_secured: true,
    features: ['Credit limit equals security deposit', 'Reports to all three bureaus'],
    min_credit_limit: { money: { amount_minor: 20000, currency_code: 'USD' }, locale: 'en-US', display_text: '$200.00' },
    max_credit_limit: { money: { amount_minor: 250000, currency_code: 'USD' }, locale: 'en-US', display_text: '$2,500.00' },
    annual_fee: { money: { amount_minor: 0, currency_code: 'USD' }, locale: 'en-US', display_text: '$0.00' },
    purchase_apr: { rate: '0.2799', display_text: '27.99%' },
    intro_purchase_apr: null,
    intro_balance_transfer_apr: null,
    penalty_apr: null,
    balance_transfer_fee_rate: { rate: '0.0500', display_text: '5%' },
    balance_transfer_fee_minimum: { money: { amount_minor: 500, currency_code: 'USD' }, locale: 'en-US', display_text: '$5.00' },
    cash_advance_apr: { rate: '0.2999', display_text: '29.99%' },
    cash_advance_fee_rate: { rate: '0.0500', display_text: '5%' },
    cash_advance_fee_minimum: { money: { amount_minor: 1000, currency_code: 'USD' }, locale: 'en-US', display_text: '$10.00' },
    foreign_transaction_fee_rate: { rate: '0.0300', display_text: '3%' },
    late_fee_maximum: { money: { amount_minor: 2500, currency_code: 'USD' }, locale: 'en-US', display_text: '$25.00' },
    returned_payment_fee_maximum: { money: { amount_minor: 2500, currency_code: 'USD' }, locale: 'en-US', display_text: '$25.00' },
    rewards: {
      type: 'CASHBACK',
      cashback_rate: { rate: '0.0100', display_text: '1%' },
      travel_multiplier: 1,
      dining_multiplier: 1,
      display_text: '1% cash back on all purchases',
    },
  },
];

// ---------------- 1. Store states, error clearance, retry, and concurrent fetch ----------------

test('store initial snapshot state is loading with empty products', () => {
  resetCreditProductsCache();
  const snapshot = getCreditProductsSnapshot();
  assert.equal(snapshot.loading, true);
  assert.deepEqual(snapshot.products, []);
  assert.equal(snapshot.error, null);
});

test('fetchCreditProducts success updates snapshot products and loading', async () => {
  resetCreditProductsCache();
  setCreditProductsFetcher(async () => ({ products: mockProducts }));

  try {
    const products = await fetchCreditProducts();
    assert.equal(products.length, 3);
    const snapshot = getCreditProductsSnapshot();
    assert.equal(snapshot.loading, false);
    assert.equal(snapshot.error, null);
    assert.equal(snapshot.products.length, 3);
    assert.equal(snapshot.products[0].product_code, 'PLATINUM_TRAVEL_REWARDS');
  } finally {
    resetCreditProductsFetcher();
    resetCreditProductsCache();
  }
});

test('fetchCreditProducts error captures failure and does not cache error forever', async () => {
  resetCreditProductsCache();
  let attempt = 0;
  setCreditProductsFetcher(async () => {
    attempt++;
    if (attempt === 1) {
      throw new Error('Catalog network timeout');
    }
    return { products: mockProducts };
  });

  try {
    // First attempt fails
    await assert.rejects(async () => {
      await fetchCreditProducts();
    }, /Catalog network timeout/);

    const failSnapshot = getCreditProductsSnapshot();
    assert.equal(failSnapshot.loading, false);
    assert.deepEqual(failSnapshot.products, []);
    assert.match(failSnapshot.error?.message, /Catalog network timeout/);

    // Subsequent call or retry fetches again and succeeds
    const recovered = await fetchCreditProducts(true);
    assert.equal(recovered.length, 3);
    assert.equal(attempt, 2);

    const successSnapshot = getCreditProductsSnapshot();
    assert.equal(successSnapshot.loading, false);
    assert.equal(successSnapshot.error, null);
    assert.equal(successSnapshot.products.length, 3);
  } finally {
    resetCreditProductsFetcher();
    resetCreditProductsCache();
  }
});

test('concurrent callers share one in-flight request', async () => {
  resetCreditProductsCache();
  let calls = 0;
  setCreditProductsFetcher(async () => {
    calls++;
    return { products: mockProducts };
  });

  try {
    const [res1, res2, res3] = await Promise.all([
      fetchCreditProducts(),
      fetchCreditProducts(),
      fetchCreditProducts(),
    ]);
    assert.equal(calls, 1, 'Only one HTTP request dispatched for concurrent callers');
    assert.equal(res1, res2);
    assert.equal(res2, res3);

    // Subsequent call uses cached data without dispatching a new fetch
    const cached = await fetchCreditProducts();
    assert.equal(calls, 1);
    assert.equal(cached.length, 3);
  } finally {
    resetCreditProductsFetcher();
    resetCreditProductsCache();
  }
});

// ---------------- 2. Pure view-model functions ----------------

test('buildComparisonRows maps API display_text to rows and labels, with None for null values', () => {
  const rows = buildComparisonRows(mockProducts);

  const annualFeeRow = rows.find((r) => r.key === 'annual_fee');
  assert.equal(annualFeeRow.label, 'Annual Fee');
  assert.deepEqual(annualFeeRow.values, ['$395.00', '$0.00', '$0.00']);

  const purchaseAprRow = rows.find((r) => r.key === 'purchase_apr');
  assert.equal(purchaseAprRow.label, 'Purchase APR');
  assert.deepEqual(purchaseAprRow.values, ['21.99%', '22.49%', '27.99%']);

  const introPurchaseAprRow = rows.find((r) => r.key === 'intro_purchase_apr');
  assert.equal(introPurchaseAprRow.label, 'Intro Purchase APR');
  // First product has null intro APR -> 'None', second has 0% intro -> display_text
  assert.equal(introPurchaseAprRow.values[0], 'None');
  assert.equal(introPurchaseAprRow.values[1], '0% intro APR for 12 months');
  assert.equal(introPurchaseAprRow.values[2], 'None');

  const introBalanceTransferAprRow = rows.find((r) => r.key === 'intro_balance_transfer_apr');
  assert.equal(introBalanceTransferAprRow.label, 'Intro Balance Transfer APR');
  assert.deepEqual(introBalanceTransferAprRow.values, ['None', 'None', 'None']);

  const penaltyAprRow = rows.find((r) => r.key === 'penalty_apr');
  assert.equal(penaltyAprRow.label, 'Penalty APR');
  // Third product has null penalty APR -> 'None'
  assert.equal(penaltyAprRow.values[0], '29.99%');
  assert.equal(penaltyAprRow.values[1], '29.99%');
  assert.equal(penaltyAprRow.values[2], 'None');

  const creditLimitRow = rows.find((r) => r.key === 'credit_limit_range');
  assert.equal(creditLimitRow.label, 'Credit Limit Range');
  assert.equal(creditLimitRow.values[0], '$10,000.00 – $75,000.00');
  assert.equal(creditLimitRow.values[1], '$1,000.00 – $25,000.00');
  assert.equal(creditLimitRow.values[2], '$200.00 – $2,500.00');
});

test('applyHref constructs URL using raw product_code', () => {
  assert.equal(applyHref('CASHBACK_EVERYDAY'), '/apply/credit-card?card=CASHBACK_EVERYDAY');
  assert.equal(applyHref(mockProducts[0]), '/apply/credit-card?card=PLATINUM_TRAVEL_REWARDS');
});

test('buildCardFacts extracts product facts and includes applyHref', () => {
  const facts = buildCardFacts(mockProducts[0]);
  assert.equal(facts.productCode, 'PLATINUM_TRAVEL_REWARDS');
  assert.equal(facts.productName, 'Nova Horizon Platinum Travel');
  assert.equal(facts.purchaseApr, '21.99%');
  assert.equal(facts.introPurchaseApr, 'None');
  assert.equal(facts.annualFee, '$395.00');
  assert.equal(facts.applyHref, '/apply/credit-card?card=PLATINUM_TRAVEL_REWARDS');
  assert.equal(facts.isSecured, false);
});

test('formatting utilities use API display_text without float math', () => {
  assert.equal(formatCreditLimitRange(mockProducts[0]), '$10,000.00 – $75,000.00');
  assert.equal(formatCreditLimitRange(null), '—');
  assert.equal(formatIntroOffers(mockProducts[1]), '0% intro APR for 12 months');
  assert.equal(formatIntroOffers(mockProducts[0]), 'None');
  assert.equal(formatBalanceTransferFee(mockProducts[0]), '5% (min. $5.00)');
  assert.equal(formatBalanceTransferFee(null), '—');
});

// ---------------- 3. Apply flow submits product_type equal to product_code ----------------

test('buildCardApplicationPayload sets product_category to CARD and product_type to product_code', () => {
  const payload1 = buildCardApplicationPayload('PLATINUM_TRAVEL_REWARDS', '85000');
  assert.deepEqual(payload1, {
    product_category: 'CARD',
    product_type: 'PLATINUM_TRAVEL_REWARDS',
    requested_amount: 85000,
  });

  const payload2 = buildCardApplicationPayload('CASHBACK_EVERYDAY', 50000);
  assert.deepEqual(payload2, {
    product_category: 'CARD',
    product_type: 'CASHBACK_EVERYDAY',
    requested_amount: 50000,
  });

  const payload3 = buildCardApplicationPayload('SECURED_STARTER', 500);
  assert.deepEqual(payload3, {
    product_category: 'CARD',
    product_type: 'SECURED_STARTER',
    requested_amount: 500,
  });
});

// ---------------- 4. Prefill resolver: code first, name second, null on no match ----------------

test('resolveCreditProduct matches by exact product_code', () => {
  const matched = resolveCreditProduct(mockProducts, 'PLATINUM_TRAVEL_REWARDS');
  assert.notEqual(matched, null);
  assert.equal(matched.product_code, 'PLATINUM_TRAVEL_REWARDS');
});

test('resolveCreditProduct matches by case-insensitive product_code', () => {
  const matched = resolveCreditProduct(mockProducts, 'cashback_everyday');
  assert.notEqual(matched, null);
  assert.equal(matched.product_code, 'CASHBACK_EVERYDAY');
});

test('resolveCreditProduct matches by hyphenated product_code', () => {
  const matched = resolveCreditProduct(mockProducts, 'secured-starter');
  assert.notEqual(matched, null);
  assert.equal(matched.product_code, 'SECURED_STARTER');
});

test('resolveCreditProduct matches by case-insensitive product_name', () => {
  const matched = resolveCreditProduct(mockProducts, 'Nova Horizon Everyday Cash');
  assert.notEqual(matched, null);
  assert.equal(matched.product_code, 'CASHBACK_EVERYDAY');

  const matchedLower = resolveCreditProduct(mockProducts, 'nova horizon platinum travel');
  assert.notEqual(matchedLower, null);
  assert.equal(matchedLower.product_code, 'PLATINUM_TRAVEL_REWARDS');
});

test('resolveCreditProduct prioritizes product_code over product_name collision', () => {
  const collisionList = [
    { product_code: 'CODE_A', product_name: 'CODE_B' },
    { product_code: 'CODE_B', product_name: 'Product Bravo' },
  ];
  const matched = resolveCreditProduct(collisionList, 'CODE_B');
  assert.equal(matched.product_code, 'CODE_B');
});

test('resolveCreditProduct returns null on no match or invalid input', () => {
  assert.equal(resolveCreditProduct(mockProducts, 'Aura Elite Reserve'), null);
  assert.equal(resolveCreditProduct(mockProducts, 'AURA_ELITE_RESERVE'), null);
  assert.equal(resolveCreditProduct(mockProducts, 'NONEXISTENT_CARD'), null);
  assert.equal(resolveCreditProduct(mockProducts, ''), null);
  assert.equal(resolveCreditProduct(mockProducts, null), null);
  assert.equal(resolveCreditProduct(mockProducts, undefined), null);
  assert.equal(resolveCreditProduct([], 'PLATINUM_TRAVEL_REWARDS'), null);
});

// ---------------- 5. Presentation style map ----------------

test('getCreditCardStyle returns distinct static styles and falls back for unknown codes', () => {
  const platinum = getCreditCardStyle('PLATINUM_TRAVEL_REWARDS');
  assert.match(platinum.cardStyle, /border-amber-500/);
  assert.equal(platinum.accentColor, '#f59e0b');

  const unknown = getCreditCardStyle('FUTURE_CARD_CODE');
  assert.deepEqual(unknown, DEFAULT_CARD_STYLE);
  assert.match(unknown.cardStyle, /border-slate-500/);
});
