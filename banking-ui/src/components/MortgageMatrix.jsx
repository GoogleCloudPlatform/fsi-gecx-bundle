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
import { Lock } from 'lucide-react';
import { mortgageRates } from '../utils/productData.js';
import AnalyticsButton from './AnalyticsButton.jsx';


export default function MortgageMatrix({ onReserveRate }) {
  return (
    <div className="overflow-x-auto border border-slate-200 dark:border-slate-800/80 rounded-3xl bg-white dark:bg-slate-900 shadow-2xl">
      {/* Table Header Line */}
      <div className="p-6 border-b border-slate-200 dark:border-slate-800 flex flex-wrap justify-between items-center gap-4 bg-slate-50/50 dark:bg-slate-950/50">
        <div>
          <div className="text-xs font-bold text-slate-400 uppercase tracking-wider">Active Index Snapshot</div>
          <div className="text-sm font-semibold text-slate-900 dark:text-white mt-0.5">Conforming & Jumbo Core Tiers</div>
        </div>
        <div className="flex items-center space-x-2 text-xs font-semibold text-emerald-500 bg-emerald-500/10 px-3 py-1.5 rounded-full border border-emerald-500/20">
          <Lock className="w-3 h-3" />
          <span>60-Day Lock Available</span>
        </div>
      </div>

      <table className="w-full text-left border-collapse min-w-[800px]">
        <thead>
          <tr className="border-b border-slate-200 dark:border-slate-800 bg-slate-50/80 dark:bg-slate-950/80">
            <th className="p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider">Mortgage Classification</th>
            <th className="p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider">Base Interest Rate</th>
            <th className="p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider">Discount Points</th>
            <th className="p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider">Audited APR</th>
            <th className="p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider text-center">Lock Trigger</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-200 dark:divide-slate-800/60 text-sm">
          {mortgageRates.map((row, idx) => (
            <tr key={idx} className="hover:bg-slate-50/80 dark:hover:bg-slate-800/30 transition-colors">
              <td className="p-5">
                <div className="font-bold text-slate-900 dark:text-white flex items-center gap-2">
                  <span>{row.type}</span>
                  <span className="text-[10px] uppercase px-2 py-0.5 rounded font-semibold bg-slate-100 dark:bg-slate-800 text-slate-500">
                    {row.tag}
                  </span>
                </div>
                <div className="text-[11px] text-slate-500 mt-1 flex items-center gap-1">
                  <span>Disclosures:</span>
                  {row.notesIndex.map((num, ni) => (
                    <a href={`#note-${num}`} key={ni} className="text-sky-600 dark:text-sky-400 hover:underline">
                      <sup>{num}</sup>
                    </a>
                  ))}
                </div>
              </td>
              <td className="p-5 font-black text-lg text-slate-900 dark:text-white">
                {row.rate}
              </td>
              <td className="p-5 text-slate-600 dark:text-slate-400 font-mono text-xs">
                {row.points}
              </td>
              <td className="p-5 font-bold text-sky-600 dark:text-sky-400">
                {row.apr}
              </td>
              <td className="p-5 text-center">
                <AnalyticsButton analyticsId="mortgage_matrix_reserve_rate"
                  onClick={() => onReserveRate && onReserveRate(row)}
                  className="px-4 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 dark:bg-white dark:hover:bg-slate-100 text-white dark:text-slate-900 font-bold text-xs transition-colors cursor-pointer"
                >
                  Reserve Rate
                </AnalyticsButton>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Footer Disclaimer Line */}
      <div className="p-5 border-t border-slate-200 dark:border-slate-800 bg-slate-50/30 dark:bg-slate-950/30 text-[11px] text-slate-500 leading-relaxed">
        <span className="font-semibold text-slate-600 dark:text-slate-400">Pricing Continuity Assurance:</span> Base line structures remain active subject to standard intra-day continuous bond indexing adjustments. Variable indices for 5/6, 7/6, and 10/6 ARM configurations adjust bi-annually upon initial fixed maturity threshold validation.
      </div>
    </div>
  );
}
