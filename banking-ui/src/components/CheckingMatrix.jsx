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
import { checkingAccounts } from '../utils/productData.js';
import AnalyticsButton from './AnalyticsButton.jsx';


export default function CheckingMatrix({ onOpenAccount }) {
  return (
    <div className="overflow-x-auto border border-slate-200 dark:border-slate-800/80 rounded-2xl bg-white dark:bg-slate-900 shadow-xl">
      <table className="w-full text-left border-collapse min-w-[850px]">
        <thead>
          <tr className="border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/50">
            <th className="p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider">Product Base</th>
            <th className="p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider">Active Yield</th>
            <th className="p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider">Monthly Fee</th>
            <th className="p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider">Out-of-Network ATMs</th>
            <th className="p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider">Lending Edge</th>
            <th className="p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider text-center">Trigger</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-200 dark:divide-slate-800/60 text-sm">
          {checkingAccounts.map((acc, idx) => (
            <tr key={idx} className="hover:bg-slate-50/80 dark:hover:bg-slate-800/30 transition-colors">
              <td className="p-5">
                <div className="font-bold text-slate-900 dark:text-white">{acc.name}</div>
                <div className="text-xs text-slate-500 mt-0.5 line-clamp-1">{acc.bestFor}</div>
              </td>
              <td className="p-5 font-bold text-teal-600 dark:text-teal-400">
                {acc.apy}
              </td>
              <td className="p-5">
                <div className="font-semibold text-slate-900 dark:text-white">{acc.monthlyFee}</div>
                {acc.monthlyFee !== "$0" && (
                  <div className="text-[10px] text-slate-400 mt-0.5 leading-tight max-w-xs">
                    {acc.feeWaiver}
                  </div>
                )}
              </td>
              <td className="p-5 text-slate-600 dark:text-slate-400 text-xs max-w-xs">
                {acc.atmAccess}
              </td>
              <td className="p-5 text-slate-600 dark:text-slate-400 text-xs">
                {acc.loanDiscount}
              </td>
              <td className="p-5 text-center">
                <AnalyticsButton trackingName="checking_matrix_open"
                  onClick={() => onOpenAccount && onOpenAccount(acc)}
                  className="px-4 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 dark:bg-white dark:hover:bg-slate-100 text-white dark:text-slate-900 font-bold text-xs transition-colors cursor-pointer"
                >
                  Open
                </AnalyticsButton>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
