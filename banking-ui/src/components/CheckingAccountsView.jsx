import React, { useState } from 'react';
import { 
  Shield, 
  ArrowRight, 
  CreditCard, 
  Sparkles, 
  Award, 
  Gift, 
  Zap, 
  Smartphone, 
  RefreshCw, 
  Lock, 
  Check, 
  Star, 
  Compass,
  X,
  CheckCircle2,
  Globe,
  Percent,
  TrendingUp,
  Activity,
  PiggyBank
} from 'lucide-react';
import { useSettings } from '../context/SettingsContext.jsx';
import AccountOpeningModal from './AccountOpeningModal.jsx';

function CheckingAccountsView({ activeBot, setActiveBot }) {
  const { 
    bankName, 
    brandColorFrom, 
    brandColorTo
  } = useSettings();

  const [selectedAccountIndex, setSelectedAccountIndex] = useState(0);
  const [openingAccount, setOpeningAccount] = useState(null);

  const accounts = [
    {
      name: "Nova Classic Everyday",
      tag: "Core Digital Convenience",
      apy: "0.02% APY",
      monthlyFee: "$0",
      feeWaiver: "No minimum balance or direct deposit required",
      minOpen: "$0",
      atmAccess: "Up to 12 out-of-network fee reimbursements monthly",
      rewards: "Standard rewards points on signature debit purchases",
      loanDiscount: "None",
      bestFor: "Students, young professionals, and simple transparent day-to-day banking",
      cardStyle: "from-slate-900 via-teal-950 to-slate-900 border-teal-500/30 text-teal-400",
      chipStyle: "bg-teal-400/20 border-teal-500/40 text-teal-300",
      accentColor: "#14b8a6",
      badgeBg: "bg-teal-500/10 border-teal-500/20 text-teal-600 dark:text-teal-400",
      botName: "Checking Support Bot",
      features: [
        "Zero monthly maintenance fees or hidden tier thresholds",
        "Complimentary multi-layer overdraft protection integration",
        "Instant digital debit card provisioning for Apple Pay® & Google Wallet™",
        "Free specialized paper check supply for members aged 65 or older"
      ]
    },
    {
      name: "Horizon Apex Premier",
      tag: "High-Yield & Elite Rewards",
      apy: "0.05% APY",
      monthlyFee: "$15",
      feeWaiver: "Waived with $15,000 combined balance + $1,000 monthly direct deposit",
      minOpen: "$0",
      atmAccess: "Unlimited global out-of-network ATM fee reimbursements",
      rewards: "Additional 25% bonus reward multiplier on paired credit cards",
      loanDiscount: "0.25% APR discount on vehicle and home equity lines",
      bestFor: "Members seeking optimized yield, premium loan rates, and full fee waivers",
      cardStyle: "from-slate-950 via-emerald-950 to-teal-950 border-emerald-500/30 text-emerald-400",
      chipStyle: "bg-emerald-400/20 border-emerald-500/40 text-emerald-300",
      accentColor: "#10b981",
      badgeBg: "bg-emerald-500/10 border-emerald-500/20 text-emerald-600 dark:text-emerald-400",
      botName: "Premier Wealth Bot",
      features: [
        "0.25% automated discount triggers on select consumer lending products",
        "25% accelerated portfolio reward point accruals credited monthly",
        "$350 dedicated credit towards primary mortgage origination costs",
        "Waived incoming wire transfer fees and expedited card replacement delivery"
      ]
    },
    {
      name: "Vanguard Ascend Teen",
      tag: "Empowered Early Access",
      apy: "0.02% APY",
      monthlyFee: "$0",
      feeWaiver: "No fees ever for active members aged 13-17",
      minOpen: "$0",
      atmAccess: "Access to 30,000+ standard network fee-free machines",
      rewards: "Gamified savings milestones and automated round-up targets",
      loanDiscount: "N/A",
      bestFor: "Ages 13-17 developing strong lifelong budgeting and spending habits",
      cardStyle: "from-indigo-950 via-slate-900 to-purple-950 border-indigo-500/30 text-indigo-400",
      chipStyle: "bg-indigo-400/20 border-indigo-500/40 text-indigo-300",
      accentColor: "#6366f1",
      badgeBg: "bg-indigo-500/10 border-indigo-500/20 text-indigo-600 dark:text-indigo-400",
      botName: "Youth Banking Bot",
      features: [
        "Joint adult security oversight layer requiring parental/guardian sign-off",
        "Real-time instant spending threshold alert notifications via SMS/push",
        "Automated integration with tailored educational micro-literacy chapters",
        "Zero minimum opening deposit to start building a secure future today"
      ]
    },
    {
      name: "Aura Health Reserve",
      tag: "Triple-Tax Advantaged HSA",
      apy: "Tiered Premium APY",
      monthlyFee: "$0",
      feeWaiver: "No maintenance fees when linked to qualifying health plans",
      minOpen: "$0",
      atmAccess: "Direct point-of-sale pharmacy network terminal optimization",
      rewards: "Tax-free principal accumulation and zero-cost investment tier access",
      loanDiscount: "N/A",
      bestFor: "Managing high-deductible out-of-pocket clinical and preventative care expenses",
      cardStyle: "from-cyan-950 via-slate-900 to-sky-950 border-cyan-500/30 text-cyan-400",
      chipStyle: "bg-cyan-400/20 border-cyan-500/40 text-cyan-300",
      accentColor: "#06b6d4",
      badgeBg: "bg-cyan-500/10 border-cyan-500/20 text-cyan-600 dark:text-cyan-400",
      botName: "Health Advisor Bot",
      features: [
        "Contributions, qualified disbursements, and annual interest grow 100% tax-free",
        "Full account ownership portability that carries forward across career transitions",
        "Dedicated separate secure healthcare tracking physical Visa® Debit line",
        "Automated direct deposit splitting to effortlessly build clinical safety reserves"
      ]
    }
  ];

  const selectedAccount = accounts[selectedAccountIndex];

  return (
    <div className="pb-24">
      {/* Hero Section */}
      <section className="relative pt-32 pb-20 md:pt-44 md:pb-28 px-6 overflow-hidden">
        <div className="absolute inset-0 -z-10 overflow-hidden">
          <div className="absolute top-1/3 left-1/2 -translate-x-1/2 w-[900px] h-[350px] bg-teal-500/10 rounded-full blur-3xl"></div>
          <div className="absolute bottom-0 left-0 right-0 h-32 bg-gradient-to-t from-slate-50 dark:from-slate-950 to-transparent"></div>
        </div>

        <div className="max-w-7xl mx-auto text-center">
          <div className="inline-flex items-center space-x-2 px-4 py-2 rounded-full bg-teal-500/10 border border-teal-500/20 text-teal-600 dark:text-teal-400 text-xs font-semibold tracking-wide mb-6">
            <Activity className="w-3.5 h-3.5 animate-pulse" />
            <span>Fluid Daily Liquid Core</span>
          </div>

          <h1 className="text-4xl md:text-6xl lg:text-7xl font-extrabold tracking-tight leading-tight max-w-4xl mx-auto mb-6">
            Checking designed for <br />
            <span className="bg-gradient-to-r from-teal-400 via-emerald-300 to-cyan-400 bg-clip-text text-transparent">
              uncompromising liquidity.
            </span>
          </h1>

          <p className="text-lg text-slate-600 dark:text-slate-400 max-w-2xl mx-auto leading-relaxed mb-10">
            Experience immediate direct deposits, advanced multi-tiered APY scaling, and full access to global out-of-network automated teller coverage.
          </p>

          <div className="flex flex-wrap justify-center gap-4">
            <button
              onClick={() => setOpeningAccount(accounts[0])}
              className="px-8 py-4 rounded-full text-slate-950 font-bold text-sm shadow-xl hover:scale-105 transition-all duration-300 flex items-center space-x-2"
              style={{ backgroundImage: `linear-gradient(to right, ${brandColorFrom}, ${brandColorTo})`, boxShadow: `0 10px 15px -3px ${brandColorFrom}33` }}
            >
              <span>Open Account Instantly</span>
              <ArrowRight className="w-4 h-4" />
            </button>
            
            <a 
              href="#matrix"
              className="px-8 py-4 rounded-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-200 font-semibold text-sm hover:bg-slate-50 dark:hover:bg-slate-800/80 transition-colors"
            >
              Compare Checking Tiers
            </a>
          </div>
        </div>
      </section>

      {/* Interactive Showcase & Dynamic Detail Selector */}
      <section className="px-6 mb-24">
        <div className="max-w-7xl mx-auto">
          {/* Portfolio Tabs */}
          <div className="flex flex-wrap justify-center gap-3 mb-12">
            {accounts.map((acc, idx) => {
              const isSelected = idx === selectedAccountIndex;
              return (
                <button
                  key={idx}
                  onClick={() => setSelectedAccountIndex(idx)}
                  className={`px-5 py-3 rounded-xl font-semibold text-sm transition-all duration-300 flex items-center space-x-2 border ${
                    isSelected 
                      ? 'bg-slate-900 dark:bg-white text-white dark:text-slate-900 border-transparent shadow-lg scale-105' 
                      : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-400 border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700'
                  }`}
                >
                  <PiggyBank className={`w-4 h-4 ${isSelected ? 'text-teal-400 dark:text-teal-600' : ''}`} />
                  <span>{acc.name.split(' ')[1] || acc.name.split(' ')[0]}</span>
                  <span className="text-xs opacity-70 hidden sm:inline">({acc.tag.split(' ')[0]})</span>
                </button>
              );
            })}
          </div>

          {/* Active Account Comprehensive Panel */}
          <div className="bg-white dark:bg-slate-900/40 grid grid-cols-1 lg:grid-cols-12 gap-12 items-center shadow-2xl border border-slate-200 dark:border-slate-800/80 rounded-3xl p-8 md:p-12">
            
            {/* Left side: Premium Rendered Realistic Debit Card Emblem */}
            <div className="lg:col-span-5 flex justify-center">
              <div className="relative w-full max-w-[420px] aspect-[1.58] rounded-2xl p-6 shadow-2xl flex flex-col justify-between overflow-hidden transition-all duration-500 hover:scale-105 hover:-rotate-1 border border-white/10 bg-gradient-to-tr text-white group" style={{ backgroundImage: 'linear-gradient(to bottom left, #020617, #0f172a)' }}>
                {/* Glossy overlay */}
                <div className="absolute inset-0 bg-gradient-to-tr from-white/5 via-transparent to-white/5 opacity-60 pointer-events-none"></div>
                
                {/* Dynamic Background Aura */}
                <div className="absolute -left-20 -top-20 w-60 h-60 rounded-full blur-3xl opacity-30 transition-all duration-500 group-hover:opacity-50" style={{ backgroundColor: selectedAccount.accentColor }}></div>

                {/* Top Row: Brand & Indicator */}
                <div className="flex justify-between items-center relative z-10">
                  <div className="flex items-center space-x-2">
                    <Shield className="w-4 h-4 text-teal-400" />
                    <span className="font-bold tracking-wider text-sm opacity-90">{bankName}</span>
                  </div>
                  <span className="text-[9px] uppercase tracking-widest font-bold px-2 py-0.5 rounded bg-white/10 text-teal-300 border border-white/10">
                    DEBIT
                  </span>
                </div>

                {/* Middle Row: Smart Core Emblems */}
                <div className="relative z-10 my-auto space-y-3">
                  <div className={`w-11 h-9 rounded-md flex items-center justify-center border ${selectedAccount.chipStyle}`}>
                    <div className="w-6 h-4 border-y border-current opacity-40"></div>
                  </div>
                  <div>
                    <div className="text-xs uppercase tracking-widest opacity-60 font-medium">Checking Core Access</div>
                    <div className="text-xl md:text-2xl font-black tracking-tight mt-0.5 text-transparent bg-clip-text bg-gradient-to-r from-white via-slate-100 to-slate-300">
                      {selectedAccount.name}
                    </div>
                  </div>
                </div>

                {/* Bottom Row: Secure Persona */}
                <div className="flex justify-between items-end relative z-10 pt-4 border-t border-white/10">
                  <div>
                    <div className="text-[10px] uppercase tracking-wider opacity-50">Core Verification Line</div>
                    <div className="font-mono text-xs tracking-widest mt-0.5 font-semibold">PRIMARY DEPOSITOR</div>
                  </div>
                  <div className="text-right">
                    <div className="italic font-black tracking-tighter text-sm bg-gradient-to-r from-teal-400 via-emerald-300 to-cyan-400 bg-clip-text text-transparent">
                      VISA
                    </div>
                    <div className="text-[8px] tracking-widest opacity-40 uppercase">Global Network</div>
                  </div>
                </div>
              </div>
            </div>

            {/* Right side: Advanced Specification Highlights */}
            <div className="lg:col-span-7 space-y-6">
              <div className="flex flex-wrap items-center gap-3">
                <span className={`px-3 py-1 rounded-full text-xs font-bold border ${selectedAccount.badgeBg}`}>
                  {selectedAccount.tag}
                </span>
                <span className="text-xs font-semibold text-emerald-500 flex items-center gap-1">
                  <TrendingUp className="w-3.5 h-3.5" />
                  Instant Account Activation
                </span>
              </div>

              <div className="border-b border-slate-200 dark:border-slate-800 pb-6">
                <div className="text-xs font-semibold text-teal-500 uppercase tracking-wider">Base Annual Percentage Yield</div>
                <div className="text-3xl md:text-4xl font-black text-slate-900 dark:text-white mt-1">
                  {selectedAccount.apy}
                </div>
                <p className="text-xs text-slate-500 mt-1">
                  Interest credited securely at monthly maturity checkpoints.
                </p>
              </div>

              {/* Operational Parameters */}
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
                <div className="bg-slate-50 dark:bg-slate-950/50 rounded-xl p-3 border border-slate-200 dark:border-slate-800/60">
                  <div className="text-[11px] text-slate-500">Monthly Charge</div>
                  <div className="text-sm font-bold text-slate-900 dark:text-white mt-0.5">{selectedAccount.monthlyFee}</div>
                </div>
                <div className="bg-slate-50 dark:bg-slate-950/50 rounded-xl p-3 border border-slate-200 dark:border-slate-800/60">
                  <div className="text-[11px] text-slate-500">Minimum Opening</div>
                  <div className="text-sm font-bold text-emerald-500 mt-0.5">{selectedAccount.minOpen}</div>
                </div>
                <div className="bg-slate-50 dark:bg-slate-950/50 rounded-xl p-3 border border-slate-200 dark:border-slate-800/60 col-span-2 sm:col-span-1">
                  <div className="text-[11px] text-slate-500">Lending Discount</div>
                  <div className="text-xs font-bold text-teal-600 dark:text-teal-400 mt-0.5 truncate">{selectedAccount.loanDiscount.split(' ')[0]}</div>
                </div>
              </div>

              {/* Core Feature Specifications */}
              <div className="space-y-2.5 pt-2">
                <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Included Portfolio Features</div>
                {selectedAccount.features.map((feat, idx) => (
                  <div key={idx} className="flex items-start space-x-3">
                    <div className="mt-0.5 w-4 h-4 rounded-full bg-teal-500/10 flex items-center justify-center text-teal-500 flex-shrink-0">
                      <Check className="w-2.5 h-2.5" />
                    </div>
                    <span className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed">{feat}</span>
                  </div>
                ))}
              </div>

              {/* Context Actions */}
              <div className="pt-4 flex flex-col sm:flex-row gap-4 items-center">
                <button
                  onClick={() => setOpeningAccount(selectedAccount)}
                  className="w-full sm:w-auto px-8 py-3.5 rounded-full text-slate-950 font-bold text-sm shadow-lg hover:scale-105 transition-all duration-300 flex items-center justify-center space-x-2"
                  style={{ backgroundImage: `linear-gradient(to right, ${brandColorFrom}, ${brandColorTo})`, boxShadow: `0 10px 15px -3px ${brandColorFrom}33` }}
                >
                  <span>Open {selectedAccount.name.split(' ')[1]} Now</span>
                  <ArrowRight className="w-4 h-4" />
                </button>
                
                {activeBot !== undefined && setActiveBot && (
                  <button 
                    onClick={() => {
                      setActiveBot(selectedAccount.botName);
                      setTimeout(() => setActiveBot(null), 4000);
                    }}
                    className="w-full sm:w-auto px-6 py-3.5 rounded-full bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 text-sm font-semibold transition-colors flex items-center justify-center space-x-2"
                  >
                    <span>Ask {selectedAccount.botName.split(' ')[0]} Specialist</span>
                  </button>
                )}
              </div>
            </div>

          </div>
        </div>
      </section>

      {/* Comprehensive Side-by-Side Checking Comparison Matrix */}
      <section id="matrix" className="px-6 mb-24">
        <div className="max-w-7xl mx-auto">
          <div className="text-center max-w-2xl mx-auto mb-12">
            <span className="text-xs font-bold uppercase tracking-widest text-teal-600 dark:text-teal-400">Full Granular Audit</span>
            <h2 className="text-2xl md:text-4xl font-bold tracking-tight text-slate-900 dark:text-white mt-2 mb-3">
              Checking Configuration Matrix
            </h2>
            <p className="text-slate-600 dark:text-slate-400 text-sm">
              Compare baseline APY yields, minimum threshold checks, and ancillary lending credit adjustments seamlessly.
            </p>
          </div>

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
                {accounts.map((acc, idx) => (
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
                      <button
                        onClick={() => setOpeningAccount(acc)}
                        className="px-4 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 dark:bg-white dark:hover:bg-slate-100 text-white dark:text-slate-900 font-bold text-xs transition-colors"
                      >
                        Open
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* Upgrade / Clickswitch Incentive Showcase Banner */}
      <section className="px-6 mb-20">
        <div className="max-w-5xl mx-auto bg-gradient-to-tr from-slate-950 via-teal-950 to-slate-900 rounded-3xl p-8 md:p-12 border border-teal-500/20 text-white text-center relative overflow-hidden shadow-2xl">
          <div className="absolute -right-20 -bottom-20 w-80 h-80 bg-teal-500/10 rounded-full blur-3xl"></div>
          
          <div className="relative z-10 max-w-2xl mx-auto space-y-4">
            <div className="w-12 h-12 rounded-2xl bg-teal-500/20 border border-teal-500/30 text-teal-400 flex items-center justify-center mx-auto">
              <RefreshCw className="w-6 h-6" />
            </div>
            <h3 className="text-2xl md:text-3xl font-bold tracking-tight">
              Seamless Direct Deposit ClickSwitch Optimization
            </h3>
            <p className="text-slate-400 text-sm leading-relaxed">
              Transferring your legacy primary payroll direct deposit lines to {bankName} takes less than 90 seconds. Existing base classic checking depositors immediately qualify for automatic waiver upgrades upon validation.
            </p>
            <div className="pt-2">
              <button
                onClick={() => setOpeningAccount(accounts[1])}
                className="px-6 py-3 rounded-full bg-white text-slate-950 font-bold text-xs hover:bg-slate-100 transition-colors"
              >
                Execute Switch Context
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* Shared Account Opening Integration Modal */}
      <AccountOpeningModal
        openingAccount={openingAccount}
        onClose={() => setOpeningAccount(null)}
        accountType="CHECKING"
        brandColorFrom={brandColorFrom}
        brandColorTo={brandColorTo}
      />

    </div>
  );
}

export default CheckingAccountsView;
