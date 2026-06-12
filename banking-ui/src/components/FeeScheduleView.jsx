import React, { useState, useMemo } from 'react';
import { 
  Shield, 
  Search, 
  FileText, 
  DollarSign, 
  Filter, 
  RefreshCw, 
  Check, 
  Info,
  ArrowRight,
  CreditCard,
  HelpCircle
} from 'lucide-react';
const categories = [
  'All',
  'Account Services',
  'Bill Pay Services',
  'Credit Card Services',
  'Funds Transfer'
];

const feeItems = [
  // Account Services
  { item: "ATM/Debit Card physical replacement", fee: "$5.00", cat: "Account Services" },
  { item: "Personalized blank check drafts (per line)", fee: "$1.00", cat: "Account Services" },
  { item: "Bond coupon processing & redemption", fee: "Core cost + $10.00", cat: "Account Services" },
  { item: "Custom checkbook bundle printing", fee: "Varies by design specification", cat: "Account Services" },
  { item: "Statement copy or deposited check record (over 25 annual limit)", fee: "$4.00 per duplicate", cat: "Account Services" },
  { item: "Official Certified Check payable to 3rd party entity", fee: "$7.00", cat: "Account Services" },
  { item: "Escheatment regulatory transfer overhead", fee: "$25.00", cat: "Account Services" },
  { item: "Item collection request transmission", fee: "Core cost + $15.00", cat: "Account Services" },
  { item: "Legal levy processing (subpoena, child support enforcement line)", fee: "$150.00 per execution", cat: "Account Services" },
  { item: "Audited legal document research (per hour assessment)", fee: "$30.00", cat: "Account Services" },
  { item: "Out-of-network regional ATM queries (exceeding 12 monthly reimbursements)", fee: "$2.00 per occurrence", cat: "Account Services" },
  { item: "Savings structural overdraft transfer protection sweep", fee: "$5.00 per sweep", cat: "Account Services" },
  { item: "Overdrawn liquid balance line presentment", fee: "$25.00", cat: "Account Services" },
  { item: "Premier Checking line standard assessment", fee: "$15.00 / month (waivable)", cat: "Account Services" },
  { item: "Stop payment mandate executed against live draft", fee: "$35.00", cat: "Account Services" },
  { item: "Tiered money market withdrawal threshold limit breach (>6 monthly)", fee: "$10.00 per breach", cat: "Account Services" },

  // Bill Pay Services
  { item: "Non-sufficient funds (NSF) check clearing presentment", fee: "$15.00", cat: "Bill Pay Services" },
  { item: "Expedited overnight physical draft fulfillment", fee: "$20.00", cat: "Bill Pay Services" },
  { item: "Automated stop payment instruction trigger", fee: "$35.00", cat: "Bill Pay Services" },
  { item: "Overdrawn automated draft clearing balance", fee: "$25.00", cat: "Bill Pay Services" },

  // Credit Card Services
  { item: "Revolving cash advance fee percentage", fee: "3% of total advance amount", cat: "Credit Card Services" },
  { item: "Expedited secure credential card replacement", fee: "$5.00", cat: "Credit Card Services" },
  { item: "International processing multi-currency transaction charge", fee: "Exchange conversion rate + 1% (Waived for Signature lines)", cat: "Credit Card Services" },
  { item: "Statement line late payment reconciliation penalty", fee: "$25.00", cat: "Credit Card Services" },
  { item: "Returned secondary convenience draft clearing check", fee: "Up to $35.00", cat: "Credit Card Services" },

  // Funds Transfer
  { item: "Instant Peer-to-Peer external gateway transfer", fee: "$1.50", cat: "Funds Transfer" },
  { item: "Domestic outbound bank-to-bank wire transfer", fee: "$25.00", cat: "Funds Transfer" },
  { item: "International outbound sovereign SWIFT transmission", fee: "$50.00", cat: "Funds Transfer" }
];

function FeeScheduleView({ activeBot, setActiveBot }) {

  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('All');

  const filteredFees = useMemo(() => {
    return feeItems.filter(item => {
      const matchesCat = selectedCategory === 'All' || item.cat === selectedCategory;
      const matchesSearch = searchQuery.trim() === '' || 
        item.item.toLowerCase().includes(searchQuery.toLowerCase()) ||
        item.fee.toLowerCase().includes(searchQuery.toLowerCase());
      return matchesCat && matchesSearch;
    });
  }, [searchQuery, selectedCategory]);

  return (
    <div className="pb-24">
      {/* Header Section */}
      <section className="relative pt-32 pb-16 md:pt-44 md:pb-24 px-6 overflow-hidden">
        <div className="absolute inset-0 -z-10 overflow-hidden">
          <div className="absolute top-1/3 left-1/2 -translate-x-1/2 w-[750px] h-[280px] bg-emerald-500/10 rounded-full blur-3xl"></div>
          <div className="absolute bottom-0 left-0 right-0 h-32 bg-gradient-to-t from-slate-50 dark:from-slate-950 to-transparent"></div>
        </div>

        <div className="max-w-5xl mx-auto text-center">
          <div className="inline-flex items-center space-x-2 px-4 py-2 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-600 dark:text-emerald-400 text-xs font-semibold tracking-wide mb-6">
            <DollarSign className="w-3.5 h-3.5" />
            <span>Audited Consumer Index</span>
          </div>

          <h1 className="text-4xl md:text-5xl lg:text-6xl font-extrabold tracking-tight leading-tight mb-4 text-slate-900 dark:text-white">
            Transparent Schedule of <br />
            <span className="bg-gradient-to-r from-emerald-400 via-teal-400 to-cyan-400 bg-clip-text text-transparent">
              Personal Account Assessments.
            </span>
          </h1>

          <p className="text-base text-slate-600 dark:text-slate-400 max-w-2xl mx-auto leading-relaxed">
            Clear pricing parameters mapped to specific service overhead tranches. Fully standardized and audited continuously to guarantee uncompromised banking value.
          </p>

          {/* Dynamic Search Filter Bar */}
          <div className="relative max-w-xl mx-auto mt-8">
            <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none text-slate-400">
              <Search className="w-4 h-4" />
            </div>
            <input 
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Filter fee schedules (e.g. wire, late, replacement, stop)..."
              className="w-full pl-11 pr-4 py-3 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white placeholder-slate-400 text-xs font-medium shadow-md focus:border-emerald-500 outline-none transition-all"
            />
          </div>
        </div>
      </section>

      {/* Tabs Filter Selector */}
      <section className="px-6 mb-8">
        <div className="max-w-6xl mx-auto flex flex-wrap justify-center gap-2">
          {categories.map((cat, idx) => {
            const isSelected = selectedCategory === cat;
            return (
              <button
                key={idx}
                onClick={() => setSelectedCategory(cat)}
                className={`px-4 py-2 rounded-lg text-xs font-bold transition-all duration-300 cursor-pointer ${
                  isSelected
                    ? 'bg-slate-900 dark:bg-white text-white dark:text-slate-900 shadow-sm scale-105'
                    : 'bg-slate-100 dark:bg-slate-900 hover:bg-slate-200 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-400'
                }`}
              >
                {cat}
              </button>
            );
          })}
        </div>
      </section>

      {/* Audited Table Structure */}
      <section className="px-6 mb-20">
        <div className="max-w-6xl mx-auto">
          <div className="border border-slate-200 dark:border-slate-800/80 rounded-2xl overflow-hidden bg-white dark:bg-slate-900 shadow-xl">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/50">
                  <th className="p-4 text-xs font-semibold text-slate-400 uppercase tracking-wider">Service Context Definition</th>
                  <th className="p-4 text-xs font-semibold text-slate-400 uppercase tracking-wider text-right">Associated Fee Assessment</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-800/60 text-xs md:text-sm">
                {filteredFees.length === 0 ? (
                  <tr>
                    <td colSpan="2" className="p-8 text-center text-slate-400 text-xs">
                      No matching service assessments indexed against search query.
                    </td>
                  </tr>
                ) : (
                  filteredFees.map((f, fi) => (
                    <tr key={fi} className="hover:bg-slate-50/80 dark:hover:bg-slate-800/30 transition-colors">
                      <td className="p-4">
                        <div className="font-bold text-slate-900 dark:text-white">{f.item}</div>
                        <div className="text-[10px] font-semibold text-emerald-600 dark:text-emerald-400 uppercase mt-0.5 tracking-wider">
                          {f.cat}
                        </div>
                      </td>
                      <td className="p-4 text-right font-mono font-black text-slate-900 dark:text-white text-sm">
                        {f.fee}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <div className="mt-4 p-4 rounded-xl bg-slate-50 dark:bg-slate-950/50 border border-slate-200 dark:border-slate-800/60 flex items-start gap-3 text-xs text-slate-500">
            <Info className="w-4 h-4 text-emerald-500 flex-shrink-0 mt-0.5" />
            <div>
              <span className="font-semibold text-slate-700 dark:text-slate-300">Automated Relationship Waivers:</span> Standard checking maintenance charges and check copy overhead are waived programmatically for premier qualifying accounts maintaining defined combined daily balances or processing minimum monthly automated payroll deposits.
            </div>
          </div>
        </div>
      </section>

      {/* Help support fallback */}
      <section className="px-6">
        <div className="max-w-4xl mx-auto text-center space-y-4">
          <h3 className="text-sm font-bold text-slate-900 dark:text-white uppercase tracking-wider">Unsure about an item charge?</h3>
          <p className="text-xs text-slate-500 max-w-md mx-auto">
            Our digital advisors instantly trace any statement line context to resolve balance queries.
          </p>
          {activeBot !== undefined && setActiveBot && (
            <button
              onClick={() => {
                setActiveBot('Account Support Bot');
                setTimeout(() => setActiveBot(null), 4000);
              }}
              className="px-5 py-2 rounded-full bg-slate-900 dark:bg-white text-white dark:text-slate-900 font-bold text-xs hover:scale-105 transition-all"
            >
              Launch Account Concierge
            </button>
          )}
        </div>
      </section>

    </div>
  );
}

export default FeeScheduleView;
