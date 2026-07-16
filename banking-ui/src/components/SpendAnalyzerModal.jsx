import React, { useState, useMemo } from 'react';
import AnalyticsButton from './AnalyticsButton.jsx';


const CATEGORY_COLORS = {
  MERCHANDISE: '#3b82f6',      // Vibrant Blue
  GROCERY: '#10b981',          // Emerald Green
  GROCERIES: '#10b981',
  DINING: '#f59e0b',           // Amber Gold
  OTHER_TRAVEL: '#06b6d4',     // Cyan Sky
  TRAVEL: '#06b6d4',
  HEALTHCARE: '#f43f5e',       // Rose Red
  GAS_AUTOMOTIVE: '#8b5cf6',   // Violet Purple
  ENTERTAINMENT: '#ec4899',
  DIGITAL_GOODS: '#6366f1',
  TELECOM: '#14b8a6',
  FITNESS: '#84cc16',
  SERVICES: '#64748b',
  OTHER: '#6366f1',            // Indigo
  FEES: '#64748b',             // Slate Grey
  GENERAL: '#475569'
};

const CATEGORY_LABELS = {
  MERCHANDISE: 'Merchandise',
  GROCERY: 'Grocery',
  GROCERIES: 'Groceries',
  DINING: 'Dining',
  OTHER: 'Other',
  HEALTHCARE: 'Healthcare',
  GAS_AUTOMOTIVE: 'Gas/Automotive',
  OTHER_TRAVEL: 'Other Travel',
  TRAVEL: 'Travel',
  ENTERTAINMENT: 'Entertainment',
  DIGITAL_GOODS: 'Digital Goods',
  TELECOM: 'Telecom',
  FITNESS: 'Fitness',
  SERVICES: 'Services',
  FEES: 'Fees & Interest',
  GENERAL: 'General Spending'
};

function getTransactionAmountCents(tx) {
  if (tx.amount_cents !== undefined && tx.amount_cents !== null) return Number(tx.amount_cents);
  if (tx.amount !== undefined && tx.amount !== null) return Math.round(Number(tx.amount) * -100);
  return 0;
}

function getTransactionDate(tx) {
  return tx.posted_at || tx.posted_timestamp || tx.created_at || tx.transaction_timestamp || null;
}

function getCardOptionId(card) {
  return String(card.card_id || card.id || card.card_token || card.last_four || 'unknown');
}

function getTxCardOptionId(tx) {
  return String(tx.card_id || tx.card_token || tx.last_four || tx.card_last_four || 'unknown');
}

function buildCardOptions(cards, transactions) {
  const optionMap = new Map();
  (cards || []).forEach((card) => {
    const id = getCardOptionId(card);
    optionMap.set(id, {
      id,
      lastFour: card.last_four,
      label: `${card.cardholder_name || 'Cardholder'} ...${card.last_four}${card.is_virtual ? ' (Virtual Card)' : ' (Primary)'}`,
    });
  });
  (transactions || []).forEach((tx) => {
    const lastFour = tx.last_four || tx.card_last_four;
    if (!lastFour) return;
    const id = getTxCardOptionId(tx);
    if (!optionMap.has(id)) {
      optionMap.set(id, {
        id,
        lastFour,
        label: `${tx.cardholder_name || 'Cardholder'} ...${lastFour}`,
      });
    }
  });
  return Array.from(optionMap.values()).sort((a, b) => a.label.localeCompare(b.label));
}

function dateRangeLabel(transactions) {
  const dates = transactions
    .map(getTransactionDate)
    .filter(Boolean)
    .map((value) => new Date(value))
    .filter((date) => !Number.isNaN(date.getTime()))
    .sort((a, b) => a - b);
  if (dates.length === 0) return 'No posted date range';
  const format = (date) => date.toLocaleDateString(undefined, { month: '2-digit', day: '2-digit', year: 'numeric' });
  return `${format(dates[0])} - ${format(dates[dates.length - 1])}`;
}

export default function SpendAnalyzerModal({ isOpen, onClose, transactions = [], cards = [], accountName = 'Credit Card Account' }) {
  const [dateRange, setDateRange] = useState('3 Months');
  const [selectedCard, setSelectedCard] = useState('ALL');
  const cardOptions = useMemo(() => buildCardOptions(cards, transactions), [cards, transactions]);

  // Filter and calculate category spendings from real posted ledger transactions
  const { totalSpending, categoryBreakdown, conicGradient, postedCount, rangeLabel } = useMemo(() => {
    const validTxs = transactions.filter(tx => {
      if (tx.pending) return false;
      if (selectedCard !== 'ALL') {
        const txCardId = getTxCardOptionId(tx);
        const txLastFour = String(tx.last_four || tx.card_last_four || '');
        const selected = cardOptions.find((option) => option.id === selectedCard);
        if (txCardId !== selectedCard && (!selected?.lastFour || txLastFour !== String(selected.lastFour))) {
          return false;
        }
      }
      const amountVal = getTransactionAmountCents(tx);
      return amountVal < 0 && !tx.description?.toUpperCase().includes('PAYMENT');
    });

    let total = 0;
    const catMap = {};

    validTxs.forEach(tx => {
      const rawCat = tx.personal_finance_category?.primary || 'GENERAL';
      const catKey = rawCat.toUpperCase();
      const amount = Math.abs(getTransactionAmountCents(tx)) / 100;
      
      if (!catMap[catKey]) {
        catMap[catKey] = 0;
      }
      catMap[catKey] += amount;
      total += amount;
    });

    if (total === 0) {
      return {
        totalSpending: 0,
        categoryBreakdown: [],
        conicGradient: 'conic-gradient(#cbd5e1 0% 100%)',
        postedCount: validTxs.length,
        rangeLabel: dateRangeLabel(validTxs),
      };
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
      conicGradient: `conic-gradient(${gradientStops.join(', ')})`,
      postedCount: validTxs.length,
      rangeLabel: dateRangeLabel(validTxs),
    };
  }, [transactions, selectedCard, cardOptions]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-950/80 backdrop-blur-md flex items-center justify-center p-4 sm:p-6 animate-fadeIn">
      <div className="bg-white dark:bg-slate-900 rounded-3xl shadow-2xl max-w-4xl w-full overflow-hidden border border-slate-200 dark:border-slate-800 animate-scaleUp">
        {/* Sleek Theme Header Banner */}
        <div className="bg-gradient-to-r from-emerald-50 via-white to-blue-50 dark:from-slate-900 dark:via-slate-800 dark:to-slate-900 border-b border-slate-200 dark:border-slate-800 p-6 sm:p-8 relative">
          <AnalyticsButton analyticsId="spend_analyzer_modal_01"
            onClick={onClose}
            className="absolute top-6 right-6 text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white bg-white/80 hover:bg-white dark:bg-slate-800/80 dark:hover:bg-slate-700 border border-slate-200 dark:border-slate-700 p-2.5 rounded-full transition-all cursor-pointer shadow-sm"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </AnalyticsButton>
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-emerald-700 dark:text-emerald-400 mb-1.5">
            <span className="inline-block w-2 h-2 rounded-full bg-emerald-500 dark:bg-emerald-400 animate-pulse"></span>
            <span>{accountName}</span>
            <span>&bull;</span>
            <span>Spend Analyzer</span>
          </div>
          <h2 className="text-2xl sm:text-3xl font-black tracking-tight text-slate-950 dark:text-white">Spend Analyzer</h2>
          <p className="text-sm text-slate-600 dark:text-slate-300 mt-1">
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
                value={rangeLabel}
                className="w-full bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-xl px-3.5 py-2 text-sm font-semibold text-slate-800 dark:text-slate-200 pr-9 shadow-sm"
              />
              <svg className="w-4 h-4 text-slate-400 absolute right-3.5 top-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
            </div>
            <div className="flex items-center gap-1.5 mt-2.5">
              {['3 Months', 'YTD', '1 Year'].map((pill) => (
                <AnalyticsButton analyticsId="spend_analyzer_modal_02"
                  key={pill}
                  onClick={() => setDateRange(pill)}
                  className={`text-xs font-bold px-3 py-1 rounded-full border transition-all cursor-pointer ${
                    dateRange === pill
                      ? 'bg-blue-600 border-blue-600 text-white shadow-sm'
                      : 'bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'
                  }`}
                >
                  {pill}
                </AnalyticsButton>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-1.5">Select account users</label>
            <select
              value={selectedCard}
              onChange={(e) => setSelectedCard(e.target.value)}
              className="w-full bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-xl px-3.5 py-2 text-sm font-semibold text-slate-800 dark:text-slate-200 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500/50"
            >
              <option value="ALL">All account cards</option>
              {cardOptions.map((option) => (
                <option key={option.id} value={option.id}>{option.label}</option>
              ))}
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
            Computed from <span className="font-bold text-slate-900 dark:text-white">{postedCount}</span> posted spending entries
          </div>
          <AnalyticsButton analyticsId="spend_analyzer_modal_close_spend_analyzer"
            onClick={onClose}
            className="px-6 py-2.5 rounded-xl bg-slate-900 dark:bg-slate-700 text-white font-bold text-sm hover:bg-slate-800 dark:hover:bg-slate-600 shadow-md hover:shadow-lg transition-all cursor-pointer"
          >
            Close Spend Analyzer
          </AnalyticsButton>
        </div>
      </div>
    </div>
  );
}
