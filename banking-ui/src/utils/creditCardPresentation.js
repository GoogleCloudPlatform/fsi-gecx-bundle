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

import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useCreditProducts } from './creditProducts.js';
import { getCreditCardStyle } from './creditCardStyles.js';

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
 * Renders the side-by-side credit card comparison matrix table.
 */
export function CreditCardMatrix({ onApply, products: propsProducts }) {
  const navigate = useNavigate();
  const hookResult = useCreditProducts();

  const products = propsProducts || hookResult.products;
  const loading = propsProducts ? false : hookResult.loading;
  const error = propsProducts ? null : hookResult.error;

  const handleApplyClick = (productCode) => {
    if (onApply) {
      onApply(productCode);
    } else if (navigate) {
      navigate(`/apply/credit-card?card=${productCode}`);
    }
  };

  if (loading) {
    return React.createElement(
      'div',
      {
        'data-testid': 'credit-card-matrix-loading',
        className: 'p-12 text-center border border-slate-200 dark:border-slate-800 rounded-2xl bg-white dark:bg-slate-900',
      },
      React.createElement('div', { className: 'animate-pulse text-sm text-slate-500 font-medium' }, 'Loading credit card comparison...')
    );
  }

  if (error) {
    return React.createElement(
      'div',
      {
        'data-testid': 'credit-card-matrix-error',
        className: 'p-8 text-center border border-red-200 dark:border-red-800/40 rounded-2xl bg-red-50 dark:bg-red-950/20 text-red-600 dark:text-red-400',
      },
      React.createElement('p', { className: 'text-sm font-semibold' }, 'Unable to load credit card comparison.')
    );
  }

  if (!products || products.length === 0) {
    return React.createElement(
      'div',
      { className: 'p-8 text-center border border-slate-200 dark:border-slate-800 rounded-2xl bg-white dark:bg-slate-900 text-slate-500' },
      'No credit products available.'
    );
  }

  return React.createElement(
    'div',
    {
      'data-testid': 'credit-card-matrix',
      className: 'overflow-x-auto border border-slate-200 dark:border-slate-800/80 rounded-2xl bg-white dark:bg-slate-900 shadow-xl',
    },
    React.createElement(
      'table',
      { className: 'w-full text-left border-collapse min-w-[860px]' },
      React.createElement(
        'thead',
        null,
        React.createElement(
          'tr',
          { className: 'border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/50' },
          React.createElement('th', { className: 'p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider' }, 'Card Product'),
          React.createElement('th', { className: 'p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider' }, 'Rewards'),
          React.createElement('th', { className: 'p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider' }, 'Purchase APR'),
          React.createElement('th', { className: 'p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider' }, 'Intro Offers'),
          React.createElement('th', { className: 'p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider' }, 'Annual Fee'),
          React.createElement('th', { className: 'p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider' }, 'Credit Limit'),
          React.createElement('th', { className: 'p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider text-center' }, 'Action')
        )
      ),
      React.createElement(
        'tbody',
        { className: 'divide-y divide-slate-200 dark:divide-slate-800/60 text-sm' },
        products.map((product) => {
          const introText = formatIntroOffers(product);
          return React.createElement(
            'tr',
            { key: product.product_code, className: 'hover:bg-slate-50/80 dark:hover:bg-slate-800/30 transition-colors' },
            React.createElement(
              'td',
              { className: 'p-5' },
              React.createElement(
                'div',
                { className: 'flex items-center gap-2' },
                React.createElement('span', { className: 'font-bold text-slate-900 dark:text-white' }, product.product_name),
                product.is_secured &&
                  React.createElement(
                    'span',
                    {
                      className: 'px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/10 border border-amber-500/20 text-amber-600 dark:text-amber-400 uppercase tracking-wider',
                    },
                    'Secured'
                  )
              ),
              React.createElement('div', { className: 'text-xs text-slate-500 mt-0.5' }, product.best_for || product.tagline)
            ),
            React.createElement('td', { className: 'p-5 font-medium text-slate-700 dark:text-slate-300' }, product.rewards?.display_text || '—'),
            React.createElement('td', { className: 'p-5 text-slate-600 dark:text-slate-400 font-mono text-xs' }, product.purchase_apr?.display_text || '—'),
            React.createElement('td', { className: 'p-5 text-slate-600 dark:text-slate-400 text-xs' }, introText),
            React.createElement('td', { className: 'p-5 font-bold text-slate-900 dark:text-white' }, product.annual_fee?.display_text || '—'),
            React.createElement('td', { className: 'p-5 text-xs text-slate-600 dark:text-slate-400 font-mono' }, formatCreditLimitRange(product)),
            React.createElement(
              'td',
              { className: 'p-5 text-center' },
              React.createElement(
                'button',
                {
                  type: 'button',
                  'data-analytics-id': 'credit_card_matrix_apply',
                  onClick: () => handleApplyClick(product.product_code),
                  className: 'px-4 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 dark:bg-white dark:hover:bg-slate-100 text-white dark:text-slate-900 font-bold text-xs transition-colors cursor-pointer',
                },
                'Apply'
              )
            )
          );
        })
      )
    )
  );
}

/**
 * Visual card graphic component.
 */
export function CreditCardVisual({ product, bankName = 'Nova Horizon Bank' }) {
  if (!product) return null;
  const style = getCreditCardStyle(product.product_code);

  return React.createElement(
    'div',
    {
      'data-testid': 'credit-card-visual',
      className: `relative w-full max-w-[420px] aspect-[1.58] rounded-2xl p-6 shadow-2xl flex flex-col justify-between overflow-hidden transition-all duration-500 hover:scale-105 hover:rotate-1 border border-white/10 bg-gradient-to-tr text-white group ${style.cardStyle}`,
      style: { backgroundImage: 'linear-gradient(to top right, #0f172a, #1e293b)' },
    },
    React.createElement('div', { className: 'absolute inset-0 bg-gradient-to-tr from-white/5 to-transparent opacity-50 pointer-events-none' }),
    React.createElement('div', {
      className: 'absolute -right-20 -bottom-20 w-60 h-60 rounded-full blur-3xl opacity-30 transition-all duration-500 group-hover:opacity-50',
      style: { backgroundColor: style.accentColor },
    }),
    React.createElement(
      'div',
      { className: 'flex justify-between items-center relative z-10' },
      React.createElement('span', { className: 'font-bold tracking-wider text-sm opacity-90' }, bankName),
      React.createElement(
        'div',
        { className: 'flex items-center space-x-1 opacity-80' },
        React.createElement(
          'svg',
          { className: 'w-4 h-4 rotate-90', viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: '2' },
          React.createElement('path', { d: 'M5 12.55a11 11 0 0 1 14.08 0' }),
          React.createElement('path', { d: 'M1.42 9a16 16 0 0 1 21.16 0' }),
          React.createElement('path', { d: 'M8.53 16.11a6 6 0 0 1 6.95 0' }),
          React.createElement('line', { x1: '12', y1: '20', x2: '12.01', y2: '20' })
        )
      )
    ),
    React.createElement(
      'div',
      { className: 'relative z-10 my-auto space-y-3' },
      React.createElement(
        'div',
        { className: `w-11 h-9 rounded-md flex items-center justify-center border ${style.chipStyle}` },
        React.createElement('div', { className: 'w-6 h-4 border-y border-current opacity-40' })
      ),
      React.createElement(
        'div',
        null,
        React.createElement(
          'div',
          { className: 'text-xs uppercase tracking-widest opacity-60 font-medium' },
          product.is_secured ? 'Secured Credit Line' : 'Revolving Credit Line'
        ),
        React.createElement(
          'div',
          { className: 'text-xl md:text-2xl font-black tracking-tight mt-0.5 text-transparent bg-clip-text bg-gradient-to-r from-white to-slate-200' },
          product.product_name
        )
      )
    ),
    React.createElement(
      'div',
      { className: 'flex justify-between items-end relative z-10 pt-4 border-t border-white/10' },
      React.createElement(
        'div',
        null,
        React.createElement('div', { className: 'text-[10px] uppercase tracking-wider opacity-50' }, 'Authorized Member'),
        React.createElement('div', { className: 'font-mono text-xs tracking-widest mt-0.5 font-semibold' }, 'VALUED MEMBER')
      ),
      React.createElement(
        'div',
        { className: 'text-right' },
        React.createElement('div', { className: 'italic font-black tracking-tighter text-sm bg-gradient-to-r from-emerald-400 to-cyan-400 bg-clip-text text-transparent' }, 'VISA'),
        React.createElement('div', { className: 'text-[8px] tracking-widest opacity-40 uppercase' }, 'Signature')
      )
    )
  );
}

export default CreditCardMatrix;
