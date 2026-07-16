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
import { creditCards } from '../utils/productData.js';
import AnalyticsButton from './AnalyticsButton.jsx';


export default function CreditCardMatrix({ onApply }) {
  const navigate = useNavigate();

  return (
    <div className="overflow-x-auto border border-slate-200 dark:border-slate-800/80 rounded-2xl bg-white dark:bg-slate-900 shadow-xl">
      <table className="w-full text-left border-collapse min-w-[800px]">
        <thead>
          <tr className="border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/50">
            <th className="p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider">Card Product</th>
            <th className="p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider">Welcome Bonus</th>
            <th className="p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider">Earning Tier</th>
            <th className="p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider">Intro APR</th>
            <th className="p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider">Regular APR</th>
            <th className="p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider text-center">Action</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-200 dark:divide-slate-800/60 text-sm">
          {creditCards.map((card, idx) => (
            <tr key={idx} className="hover:bg-slate-50/80 dark:hover:bg-slate-800/30 transition-colors">
              <td className="p-5">
                <div className="font-bold text-slate-900 dark:text-white">{card.name}</div>
                <div className="text-xs text-slate-500 mt-0.5">{card.bestFor}</div>
              </td>
              <td className="p-5">
                <div className="font-bold text-emerald-600 dark:text-emerald-400">{card.bonus}</div>
                <div className="text-[11px] text-slate-500 mt-0.5">{card.bonusDesc.replace('After spending', 'Spend')}</div>
              </td>
              <td className="p-5 font-medium text-slate-700 dark:text-slate-300">
                {card.earnRate}
              </td>
              <td className="p-5 text-slate-600 dark:text-slate-400">
                {card.introApr}
              </td>
              <td className="p-5 text-slate-600 dark:text-slate-400 font-mono text-xs">
                {card.regApr}
              </td>
              <td className="p-5 text-center">
                <AnalyticsButton trackingName="button_click_credit_card_matrix_01"
                  onClick={() => {
                    const cardSlug = card.name.toLowerCase().replace(/ /g, '-');
                    if (onApply) {
                      onApply(cardSlug);
                    } else {
                      navigate(`/apply/credit-card?card=${cardSlug}`);
                    }
                  }}
                  className="px-4 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 dark:bg-white dark:hover:bg-slate-100 text-white dark:text-slate-900 font-bold text-xs transition-colors cursor-pointer"
                >
                  Apply
                </AnalyticsButton>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
