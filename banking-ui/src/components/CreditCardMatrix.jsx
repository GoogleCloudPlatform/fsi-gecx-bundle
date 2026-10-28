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
import { ArrowRight, RefreshCw } from 'lucide-react';
import { useCreditProducts } from '../hooks/useCreditProducts.js';
import { buildComparisonRows, applyHref } from '../utils/creditCardPresentation.js';

export function CreditCardMatrix({ onApply, products: propsProducts }) {
  const navigate = useNavigate();
  const hookResult = useCreditProducts();

  const products = propsProducts || hookResult.products;
  const loading = propsProducts ? false : hookResult.loading;
  const error = propsProducts ? null : hookResult.error;
  const retry = hookResult.retry;

  const handleApplyClick = (productCode) => {
    if (onApply) {
      onApply(productCode);
    } else {
      navigate(applyHref(productCode));
    }
  };

  if (loading) {
    return (
      <div data-testid="credit-card-matrix-loading" className="p-12 text-center border border-slate-200 dark:border-slate-800 rounded-2xl bg-white dark:bg-slate-900">
        <div className="animate-pulse text-sm text-slate-500 font-medium">Loading credit card comparison...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div data-testid="credit-card-matrix-error" className="p-8 text-center border border-red-200 dark:border-red-800/40 rounded-2xl bg-red-50 dark:bg-red-950/20 text-red-600 dark:text-red-400">
        <p className="text-sm font-semibold">Unable to load credit card comparison.</p>
        {retry && (
          <button
            type="button"
            onClick={() => retry()}
            className="mt-3 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-600 hover:bg-red-700 text-white text-xs font-semibold shadow-sm transition cursor-pointer"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Try again</span>
          </button>
        )}
      </div>
    );
  }

  if (!products || products.length === 0) {
    return (
      <div className="p-8 text-center border border-slate-200 dark:border-slate-800 rounded-2xl bg-white dark:bg-slate-900 text-slate-500">
        No credit products available.
      </div>
    );
  }

  const rows = buildComparisonRows(products);

  return (
    <div data-testid="credit-card-matrix" className="overflow-x-auto border border-slate-200 dark:border-slate-800/80 rounded-2xl bg-white dark:bg-slate-900 shadow-xl">
      <table className="w-full text-left border-collapse min-w-[860px]">
        <thead>
          <tr className="border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/50">
            <th className="p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider w-1/4">
              Feature
            </th>
            {products.map((product) => (
              <th key={product.product_code} className="p-5 text-left align-top">
                <div className="text-base font-bold text-slate-900 dark:text-white">
                  {product.product_name}
                </div>
                {product.tagline && (
                  <p className="text-xs text-slate-500 dark:text-slate-400 font-normal mt-0.5">
                    {product.tagline}
                  </p>
                )}
                <button
                  type="button"
                  onClick={() => handleApplyClick(product.product_code)}
                  className="mt-3 inline-flex items-center gap-1 text-xs font-bold text-emerald-600 dark:text-emerald-400 hover:underline cursor-pointer"
                >
                  <span>Apply Now</span>
                  <ArrowRight className="w-3 h-3" />
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
          {rows.map((row) => (
            <tr key={row.key} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/30 transition-colors">
              <td className="p-5 text-sm font-semibold text-slate-700 dark:text-slate-300 bg-slate-50/30 dark:bg-slate-950/20">
                {row.label}
              </td>
              {row.values.map((val, idx) => (
                <td key={products[idx]?.product_code || idx} className="p-5 text-sm text-slate-600 dark:text-slate-300 font-medium">
                  {val}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default CreditCardMatrix;
