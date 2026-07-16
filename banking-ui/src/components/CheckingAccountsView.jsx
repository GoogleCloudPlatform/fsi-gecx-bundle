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
import { checkingAccounts as accounts } from '../utils/productData.js';
import CheckingMatrix from './CheckingMatrix.jsx';
import AnalyticsButton from './AnalyticsButton.jsx';


function CheckingAccountsView({ activeBot, setActiveBot }) {
  const { 
    bankName, 
    brandColorFrom, 
    brandColorTo
  } = useSettings();

  const [selectedAccountIndex, setSelectedAccountIndex] = useState(0);
  const [openingAccount, setOpeningAccount] = useState(null);



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
            <AnalyticsButton analyticsId="checking_accounts_view_open_account_instantly"
              onClick={() => setOpeningAccount(accounts[0])}
              className="px-8 py-4 rounded-full text-slate-950 font-bold text-sm shadow-xl hover:scale-105 transition-all duration-300 flex items-center space-x-2"
              style={{ backgroundImage: `linear-gradient(to right, ${brandColorFrom}, ${brandColorTo})`, boxShadow: `0 10px 15px -3px ${brandColorFrom}33` }}
            >
              <span>Open Account Instantly</span>
              <ArrowRight className="w-4 h-4" />
            </AnalyticsButton>
            
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
                <AnalyticsButton analyticsId="checking_accounts_view_02"
                  key={idx}
                  onClick={() => setSelectedAccountIndex(idx)}
                  className={`px-5 py-3 rounded-xl font-semibold text-sm transition-all duration-300 flex items-center space-x-2 border ${
                    isSelected 
                      ? 'bg-white dark:bg-slate-950 text-slate-900 dark:text-white border-slate-900 dark:border-slate-800 shadow-md scale-105' 
                      : 'bg-slate-100 dark:bg-slate-900 text-slate-550 dark:text-slate-400 border-slate-250 dark:border-slate-800/80 hover:bg-slate-200 dark:hover:bg-slate-800'
                  }`}
                >
                  <PiggyBank className={`w-4 h-4 ${isSelected ? 'text-teal-400 dark:text-teal-600' : ''}`} />
                  <span>{acc.name.split(' ')[1] || acc.name.split(' ')[0]}</span>
                  <span className="text-xs opacity-70 hidden sm:inline">({acc.tag.split(' ')[0]})</span>
                </AnalyticsButton>
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
                <AnalyticsButton analyticsId="checking_accounts_view_03"
                  onClick={() => setOpeningAccount(selectedAccount)}
                  className="w-full sm:w-auto px-8 py-3.5 rounded-full text-slate-950 font-bold text-sm shadow-lg hover:scale-105 transition-all duration-300 flex items-center justify-center space-x-2"
                  style={{ backgroundImage: `linear-gradient(to right, ${brandColorFrom}, ${brandColorTo})`, boxShadow: `0 10px 15px -3px ${brandColorFrom}33` }}
                >
                  <span>Open {selectedAccount.name.split(' ')[1]} Now</span>
                  <ArrowRight className="w-4 h-4" />
                </AnalyticsButton>
                
                {activeBot !== undefined && setActiveBot && (
                  <AnalyticsButton analyticsId="checking_accounts_view_04" 
                    onClick={() => {
                      setActiveBot(selectedAccount.botName);
                      setTimeout(() => setActiveBot(null), 4000);
                    }}
                    className="w-full sm:w-auto px-6 py-3.5 rounded-full bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 text-sm font-semibold transition-colors flex items-center justify-center space-x-2"
                  >
                    <span>Ask {selectedAccount.botName.split(' ')[0]} Specialist</span>
                  </AnalyticsButton>
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

          <CheckingMatrix onOpenAccount={setOpeningAccount} />
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
              <AnalyticsButton analyticsId="checking_accounts_view_execute_switch_context"
                onClick={() => setOpeningAccount(accounts[1])}
                className="px-6 py-3 rounded-full bg-white text-slate-950 font-bold text-xs hover:bg-slate-100 transition-colors"
              >
                Execute Switch Context
              </AnalyticsButton>
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
