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
 * Returns the application URL for a credit product or product code.
 */
export function applyHref(productOrCode) {
  const code = typeof productOrCode === 'string'
    ? productOrCode
    : productOrCode?.product_code || '';
  return `/apply/credit-card?card=${encodeURIComponent(code)}`;
}

/**
 * Format intro APR offers for a credit product, or 'None'.
 */
export function formatIntroOffers(product) {
  if (!product) return 'None';
  const offers = [
    product.intro_purchase_apr?.display_text,
    product.intro_balance_transfer_apr?.display_text,
  ].filter(Boolean);
  return offers.length > 0 ? offers.join(' • ') : 'None';
}

/**
 * Format credit limit range using API display_text strings.
 */
export function formatCreditLimitRange(product) {
  if (!product?.min_credit_limit?.display_text || !product?.max_credit_limit?.display_text) {
    return '—';
  }
  return `${product.min_credit_limit.display_text} – ${product.max_credit_limit.display_text}`;
}

/**
 * Format balance transfer fee disclosure using API display_text.
 */
export function formatBalanceTransferFee(product) {
  if (!product?.balance_transfer_fee_rate?.display_text) return '—';
  if (product.balance_transfer_fee_minimum?.display_text) {
    return `${product.balance_transfer_fee_rate.display_text} (min. ${product.balance_transfer_fee_minimum.display_text})`;
  }
  return product.balance_transfer_fee_rate.display_text;
}

/**
 * Extracts and formats the primary facts for a single credit card product.
 */
export function buildCardFacts(product) {
  if (!product) return null;
  return {
    productCode: product.product_code,
    productName: product.product_name,
    tagline: product.tagline || '',
    bestFor: product.best_for || '',
    purchaseApr: product.purchase_apr?.display_text || 'Variable',
    introPurchaseApr: product.intro_purchase_apr?.display_text || 'None',
    introBalanceTransferApr: product.intro_balance_transfer_apr?.display_text || 'None',
    annualFee: product.annual_fee?.display_text || '$0',
    creditLimitRange: formatCreditLimitRange(product),
    balanceTransferFee: formatBalanceTransferFee(product),
    penaltyApr: product.penalty_apr?.display_text || 'None',
    isSecured: Boolean(product.is_secured),
    rewards: Array.isArray(product.rewards) ? product.rewards : [],
    features: Array.isArray(product.features) ? product.features : [],
    applyHref: applyHref(product),
  };
}

/**
 * Builds table rows for the comparison matrix from an array of products.
 * Returns an array of:
 *   { key: string, label: string, values: string[] }
 * where each values[i] corresponds to products[i].
 *
 * Rules:
 * - Rows and labels come from API display_text.
 * - Null intro offers and penalty values render as "None".
 */
export function buildComparisonRows(products) {
  const safeProducts = Array.isArray(products) ? products : [];

  return [
    {
      key: 'annual_fee',
      label: 'Annual Fee',
      values: safeProducts.map((p) => p.annual_fee?.display_text || '$0'),
    },
    {
      key: 'purchase_apr',
      label: 'Purchase APR',
      values: safeProducts.map((p) => p.purchase_apr?.display_text || 'Variable'),
    },
    {
      key: 'intro_purchase_apr',
      label: 'Intro Purchase APR',
      values: safeProducts.map((p) => p.intro_purchase_apr?.display_text || 'None'),
    },
    {
      key: 'intro_balance_transfer_apr',
      label: 'Intro Balance Transfer APR',
      values: safeProducts.map((p) => p.intro_balance_transfer_apr?.display_text || 'None'),
    },
    {
      key: 'credit_limit_range',
      label: 'Credit Limit Range',
      values: safeProducts.map((p) => formatCreditLimitRange(p)),
    },
    {
      key: 'balance_transfer_fee',
      label: 'Balance Transfer Fee',
      values: safeProducts.map((p) => formatBalanceTransferFee(p)),
    },
    {
      key: 'penalty_apr',
      label: 'Penalty APR',
      values: safeProducts.map((p) => p.penalty_apr?.display_text || 'None'),
    },
    {
      key: 'best_for',
      label: 'Best For',
      values: safeProducts.map((p) => p.best_for || '—'),
    },
  ];
}
