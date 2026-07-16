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
import { ArrowRight } from 'lucide-react';
import { certificateAccounts } from '../utils/productData.js';
import AnalyticsButton from './AnalyticsButton.jsx';


export default function CertificateMatrix({ onOpenAccount }) {
  return (
    <div className="overflow-x-auto border border-slate-200 dark:border-slate-800/80 rounded-3xl bg-white dark:bg-slate-900 shadow-2xl">
      <div className="p-6 border-b border-slate-200 dark:border-slate-800 flex flex-wrap justify-between items-center gap-4 bg-slate-50/55 dark:bg-slate-955/55">
        <div>
          <div className="text-xs font-bold text-slate-400 uppercase tracking-wider">Certificate Account comparison</div>
          <div className="text-sm font-semibold text-slate-900 dark:text-white mt-0.5">Secure guaranteed growth over set terms</div>
        </div>
      </div>

      <table className="w-full text-left border-collapse min-w-[700px]">
        <thead>
          <tr className="border-b border-slate-200 dark:border-slate-800 bg-slate-50/80 dark:bg-slate-950/80">
            <th className="p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider">Certificate Product</th>
            <th className="p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider">Term</th>
            <th className="p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider">Base APY</th>
            <th className="p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider">Min. to Open</th>
            <th className="p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider text-right">Action</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-200 dark:divide-slate-800/60 text-sm">
          {certificateAccounts.map((prod, idx) => (
            <tr key={idx} className="hover:bg-slate-50/80 dark:hover:bg-slate-800/30 transition-colors">
              <td className="p-5">
                <div className="font-bold text-slate-900 dark:text-white">{prod.name}</div>
                <div className="text-[10px] uppercase px-2 py-0.5 rounded font-semibold bg-slate-100 dark:bg-slate-800 text-slate-500 inline-block mt-1">
                  {prod.tag}
                </div>
              </td>
              <td className="p-5 font-medium text-slate-700 dark:text-slate-300">
                {prod.term} Months
              </td>
              <td className="p-5 font-black text-slate-900 dark:text-white">
                {prod.baseApy.toFixed(2)}% APY
              </td>
              <td className="p-5 font-mono text-xs text-slate-700 dark:text-slate-300">
                ${prod.minDeposit.toLocaleString()}
              </td>
              <td className="p-5 text-right">
                <AnalyticsButton analyticsId="certificate_matrix_open"
                  onClick={() => onOpenAccount && onOpenAccount(prod)}
                  className="px-4 py-2 rounded-xl bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-600 dark:text-cyan-400 font-bold text-xs transition-colors flex items-center gap-1 ml-auto"
                >
                  <span>Open</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </AnalyticsButton>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
