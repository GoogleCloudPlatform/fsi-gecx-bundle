import React, { useState, useMemo } from 'react';

const CATEGORY_COLORS = {
  MERCHANDISE: '#3b82f6',      // Vibrant Blue
  GROCERY: '#10b981',          // Emerald Green
  DINING: '#f59e0b',           // Amber Gold
  OTHER_TRAVEL: '#06b6d4',     // Cyan Sky
  TRAVEL: '#06b6d4',
  HEALTHCARE: '#f43f5e',       // Rose Red
  GAS_AUTOMOTIVE: '#8b5cf6',   // Violet Purple
  OTHER: '#6366f1',            // Indigo
  FEES: '#64748b',             // Slate Grey
  GENERAL: '#475569'
};

const CATEGORY_LABELS = {
  MERCHANDISE: 'Merchandise',
  GROCERY: 'Grocery',
  DINING: 'Dining',
  OTHER: 'Other',
  HEALTHCARE: 'Healthcare',
  GAS_AUTOMOTIVE: 'Gas/Automotive',
  OTHER_TRAVEL: 'Other Travel',
  TRAVEL: 'Travel',
  FEES: 'Fees & Interest',
  GENERAL: 'General Spending'
};

export default function SpendAnalyzerModal({ isOpen, onClose, transactions = [] }) {
  const [dateRange, setDateRange] = useState('3 Months');
  const [selectedUser, setSelectedUser] = useState('ALL');

  // Filter and calculate category spendings from real posted ledger transactions
  const { totalSpending, categoryBreakdown, conicGradient } = useMemo(() => {
    const validTxs = transactions.filter(tx => {
      if (tx.pending) return false;
      const amountVal = tx.amount_cents !== undefined ? tx.amount_cents : (tx.amount ? -tx.amount * 100 : 0);
      return amountVal < 0 && !tx.description?.toUpperCase().includes('PAYMENT');
    });

    let total = 0;
    const catMap = {};

    validTxs.forEach(tx => {
      const rawCat = tx.personal_finance_category?.primary || 'GENERAL';
      const catKey = rawCat.toUpperCase();
      const amount = tx.amount_cents !== undefined ? Math.abs(tx.amount_cents) / 100 : Math.abs(tx.amount || 0);
      
      if (!catMap[catKey]) {
        catMap[catKey] = 0;
      }
      catMap[catKey] += amount;
      total += amount;
    });

    if (total === 0) {
      return { totalSpending: 0, categoryBreakdown: [], conicGradient: 'conic-gradient(#cbd5e1 0% 100%)' };
    }

    const sortedCats = Object.keys(catMap)
      .map(key => ({
        key,
        label: CATEGORY_LABELS[key] || key.split('_').map(w => w.charAt(0) + w.slice(1).toLowerCase()).join(' '),
        amount: catMap[key],
        percentage: Math.round((catMap[key] / total) * 100),
        color: CATEGORY_COLORS[key] || '#64748b'
      }))
      .sort((a, b) => b.amount - a.amount);

    let currentPct = 0;
    const gradientStops = sortedCats.map(cat => {
      const start = currentPct;
      const end = currentPct + (cat.amount / total) * 100;
      currentPct = end;
      return `${cat.color} ${start.toFixed(2)}% ${end.toFixed(2)}%`;
    });

    return {
      totalSpending: total,
      categoryBreakdown: sortedCats,
      conicGradient: `conic-gradient(${gradientStops.join(', ')})`
    };
  }, [transactions]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-950/80 backdrop-blur-md flex items-center justify-center p-4 sm:p-6 animate-fadeIn">
      <div className="bg-white dark:bg-slate-900 rounded-3xl shadow-2xl max-w-4xl w-full overflow-hidden border border-slate-200 dark:border-slate-800 animate-scaleUp">
        {/* Sleek Theme Header Banner */}
        <div className="bg-gradient-to-r from-slate-900 via-slate-800 to-slate-900 border-b border-slate-800 p-6 sm:p-8 text-white relative">
          <button
            onClick={onClose}
            className="absolute top-6 right-6 text-slate-400 hover:text-white bg-slate-800/80 hover:bg-slate-700 p-2.5 rounded-full transition-all cursor-pointer"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-emerald-400 mb-1.5">
            <span className="inline-block w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            <span>Nova Everyday Visa</span>
            <span>&bull;</span>
            <span>Spend Analyzer</span>
          </div>
          <h2 className="text-2xl sm:text-3xl font-black tracking-tight text-white">Spend Analyzer</h2>
          <p className="text-sm text-slate-300 mt-1">
            Real-time categorization computed from your posted account ledger transactions.
          </p>
        </div>

        {/* Filter Controls Bar */}
        <div className="bg-slate-50 dark:bg-slate-800/80 p-5 border-b border-slate-200 dark:border-slate-800 grid grid-cols-1 sm:grid-cols-2 gap-6">
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-1.5">Select date range</label>
            <div className="relative">
              <input
                type="text"
                readOnly
                value="06/01/2026 - 06/30/2026"
                className="w-full bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-xl px-3.5 py-2 text-sm font-semibold text-slate-800 dark:text-slate-200 pr-9 shadow-sm"
              />
              <svg className="w-4 h-4 text-slate-400 absolute right-3.5 top-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
            </div>
            <div className="flex items-center gap-1.5 mt-2.5">
              {['3 Months', 'YTD', '1 Year'].map((pill) => (
                <button
                  key={pill}
                  onClick={() => setDateRange(pill)}
                  className={`text-xs font-bold px-3 py-1 rounded-full border transition-all cursor-pointer ${
                    dateRange === pill
                      ? 'bg-blue-600 border-blue-600 text-white shadow-sm'
                      : 'bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'
                  }`}
                >
                  {pill}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-1.5">Select account users</label>
            <select
              value={selectedUser}
              onChange={(e) => setSelectedUser(e.target.value)}
              className="w-full bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-xl px-3.5 py-2 text-sm font-semibold text-slate-800 dark:text-slate-200 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500/50"
            >
              <option value="ALL">All account users</option>
              <option value="ERIK">Erik V. ...2304</option>
            </select>
          </div>
        </div>

        {/* Main Content Area: Donut Chart & Category Breakdown Legend */}
        <div className="p-6 sm:p-10 grid grid-cols-1 md:grid-cols-12 gap-8 items-center bg-white dark:bg-slate-900">
          {/* Donut Chart (Left Side) */}
          <div className="md:col-span-6 flex flex-col items-center justify-center">
            <div className="relative w-64 h-64 sm:w-72 sm:h-72 rounded-full shadow-xl flex items-center justify-center transition-transform hover:scale-105 duration-300" style={{ background: conicGradient }}>
              {/* Inner Cutout for Donut Ring */}
              <div className="w-44 h-44 sm:w-52 sm:h-52 rounded-full bg-white dark:bg-slate-900 shadow-inner flex flex-col items-center justify-center p-4 text-center border border-slate-100 dark:border-slate-800">
                <div className="text-3xl sm:text-4xl font-black text-slate-900 dark:text-white tracking-tight">
                  ${totalSpending.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </div>
                <div className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 mt-1">
                  Total Spending
                </div>
              </div>
            </div>
          </div>

          {/* Category Breakdown Table (Right Side) */}
          <div className="md:col-span-6 space-y-3">
            <div className="flex items-center justify-between pb-2 border-b border-slate-200 dark:border-slate-800">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500">
                Spending Breakdown by Category
              </h4>
            </div>

            {categoryBreakdown.length === 0 ? (
              <p className="text-sm text-slate-500 italic py-6 text-center bg-slate-50 dark:bg-slate-800/40 rounded-2xl border border-slate-200 dark:border-slate-800">
                No posted spending transactions found for this period.
              </p>
            ) : (
              <div className="space-y-2.5 max-h-72 overflow-y-auto pr-1">
                {categoryBreakdown.map((cat) => (
                  <div
                    key={cat.key}
                    className="flex items-center justify-between p-3 rounded-2xl bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-800 transition-all"
                  >
                    <div className="flex items-center gap-3">
                      <span className="w-3.5 h-3.5 rounded-full flex-shrink-0 shadow-sm" style={{ backgroundColor: cat.color }}></span>
                      <span className="text-sm font-bold text-slate-800 dark:text-slate-200">
                        {cat.label}
                      </span>
                    </div>
                    <div className="text-right flex items-center gap-3">
                      <span className="text-sm font-black text-slate-900 dark:text-white">
                        ${cat.amount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </span>
                      <span className="text-xs font-bold text-slate-500 dark:text-slate-400 w-12 text-right">
                        ({cat.percentage}%)
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Footer actions */}
        <div className="bg-slate-100 dark:bg-slate-800/90 px-6 py-4 border-t border-slate-200 dark:border-slate-700 flex justify-between items-center">
          <div className="text-xs text-slate-600 dark:text-slate-300">
            Computed from <span className="font-bold text-slate-900 dark:text-white">{transactions.filter(t => !t.pending).length}</span> posted entries
          </div>
          <button
            onClick={onClose}
            className="px-6 py-2.5 rounded-xl bg-slate-900 dark:bg-slate-700 text-white font-bold text-sm hover:bg-slate-800 dark:hover:bg-slate-600 shadow-md hover:shadow-lg transition-all cursor-pointer"
          >
            Close Spend Analyzer
          </button>
        </div>
      </div>
    </div>
  );
}
