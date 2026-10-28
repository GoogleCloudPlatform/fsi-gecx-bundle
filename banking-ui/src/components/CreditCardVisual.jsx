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
import { Wifi } from 'lucide-react';
import { getCreditCardStyle } from '../utils/creditCardStyles.js';
import { buildCardFacts } from '../utils/creditCardPresentation.js';

export function CreditCardVisual({ product, bankName = 'Nova Horizon Bank' }) {
  if (!product) return null;
  const facts = product.productCode ? product : buildCardFacts(product);
  if (!facts) return null;

  const cardStyle = getCreditCardStyle(facts.productCode);

  return (
    <div
      data-testid="credit-card-visual"
      className={`relative w-full max-w-[420px] aspect-[1.58] rounded-2xl p-6 shadow-2xl flex flex-col justify-between overflow-hidden transition-all duration-500 hover:scale-105 hover:rotate-1 border border-white/10 bg-gradient-to-tr text-white group ${cardStyle.cardStyle}`}
      style={{ backgroundImage: 'linear-gradient(to top right, #0f172a, #1e293b)' }}
    >
      <div className="absolute inset-0 bg-gradient-to-tr from-white/5 to-transparent opacity-50 pointer-events-none" />
      <div
        className="absolute -right-20 -bottom-20 w-60 h-60 rounded-full blur-3xl opacity-30 transition-all duration-500 group-hover:opacity-50"
        style={{ backgroundColor: cardStyle.accentColor }}
      />
      <div className="flex justify-between items-center relative z-10">
        <span className="font-bold tracking-wider text-sm opacity-90">{bankName}</span>
        <div className="flex items-center space-x-1 opacity-80">
          <Wifi className="w-4 h-4 rotate-90" />
        </div>
      </div>
      <div className="relative z-10 my-auto space-y-3">
        <div className={`w-11 h-9 rounded-md flex items-center justify-center border ${cardStyle.chipStyle}`}>
          <div className="w-6 h-4 border-y border-current opacity-40" />
        </div>
        <div>
          <div className="text-xs uppercase tracking-widest opacity-60 font-medium">
            {facts.isSecured ? 'Secured Credit Line' : 'Revolving Credit Line'}
          </div>
          <div className="text-xl md:text-2xl font-black tracking-tight mt-0.5 text-transparent bg-clip-text bg-gradient-to-r from-white to-slate-200">
            {facts.productName}
          </div>
        </div>
      </div>
      <div className="flex justify-between items-end relative z-10 pt-4 border-t border-white/10">
        <div>
          <div className="text-[10px] uppercase tracking-wider opacity-50">Authorized Member</div>
          <div className="font-mono text-xs tracking-widest mt-0.5 font-semibold">VALUED MEMBER</div>
        </div>
        <div className="text-right">
          <div className="italic font-black tracking-tighter text-sm bg-gradient-to-r from-emerald-400 to-cyan-400 bg-clip-text text-transparent">
            VISA
          </div>
          <div className="text-[8px] tracking-widest opacity-40 uppercase">Signature</div>
        </div>
      </div>
    </div>
  );
}

export default CreditCardVisual;
