import React, { useState, useMemo } from 'react';
import { 
  Calculator, 
  TrendingUp, 
  ShieldCheck, 
  Info, 
  Percent, 
  ArrowRight,
  Coins,
  Home,
  HelpCircle
} from 'lucide-react';
import { useSettings } from '../context/SettingsContext.jsx';
import AccountOpeningModal from './AccountOpeningModal.jsx';

function SavingsAccountsView() {
  const { brandColorFrom = '#10b981', brandColorTo = '#059669' } = useSettings();
  const [openingAccount, setOpeningAccount] = useState(null);
  const [premierBalance, setPremierBalance] = useState(25000);
  const [mortgageBalance, setMortgageBalance] = useState(2500);

  const savingsProducts = useMemo(() => [
    {
      name: "Premier Savings",
      minDeposit: 0,
      baseApy: 0.02,
      tag: "High-yield tiered savings",
      details: "Earn premium yields on balances over $50,000. Requires $500 monthly direct deposit to checking."
    },
    {
      name: "Traditional Savings",
      minDeposit: 0.01,
      baseApy: 0.02,
      tag: "Establish membership",
      details: "Our standard savings account. Establishes your credit union membership share."
    },
    {
      name: "Mortgage Savings",
      minDeposit: 100,
      baseApy: 0.02,
      tag: "Earn lender credits",
      details: "Save for a home and earn $1 in lender credit toward closing costs for every $5 deposited (up to $1,000)."
    },
    {
      name: "Holiday Club",
      minDeposit: 0,
      baseApy: 0.02,
      tag: "Save for the holidays",
      details: "Stash money away throughout the year. Disbursed annually in October just in time for shopping."
    },
    {
      name: "College Savings",
      minDeposit: 5.00,
      baseApy: 0.02,
      tag: "Youth & Minor savings",
      details: "Start kids and teens on the path to financial literacy. Stated APY with annual anniversary bonuses."
    }
  ], []);

  // Calculate Premier Savings yields
  const premierStats = useMemo(() => {
    let apy = 0.02;
    let tierName = "Standard Savings Tier";

    if (premierBalance >= 100000) {
      apy = 3.25;
      tierName = "Tier 5 (Balances >= $100k)";
    } else if (premierBalance >= 75000) {
      apy = 2.75;
      tierName = "Tier 4 (Balances >= $75k)";
    } else if (premierBalance >= 50000) {
      apy = 2.25;
      tierName = "Tier 3 (Balances >= $50k)";
    }

    const annualInterest = premierBalance * (apy / 100);
    return {
      apy,
      tierName,
      annualInterest
    };
  }, [premierBalance]);

  // Calculate Mortgage Savings Credit
  const mortgageStats = useMemo(() => {
    // $1 credit for every $5 saved, max $1,000 credit
    const credit = Math.min(1000, mortgageBalance / 5);
    const progressPercent = (credit / 1000) * 100;
    return {
      credit,
      progressPercent
    };
  }, [mortgageBalance]);

  const [activeTab, setActiveTab] = useState("premier");

  return (
    <div className="pb-24">
      {/* Hero Section */}
      <section className="relative pt-32 pb-16 md:pt-44 md:pb-24 px-6 overflow-hidden">
        <div className="absolute inset-0 -z-10 overflow-hidden">
          <div className="absolute top-1/3 left-1/2 -translate-x-1/2 w-[800px] h-[300px] bg-emerald-500/10 rounded-full blur-3xl"></div>
          <div className="absolute bottom-0 left-0 right-0 h-32 bg-gradient-to-t from-slate-50 dark:from-slate-950 to-transparent"></div>
        </div>

        <div className="max-w-7xl mx-auto text-center">
          <div className="inline-flex items-center space-x-2 px-4 py-2 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-600 dark:text-emerald-400 text-xs font-semibold tracking-wide mb-6">
            <ShieldCheck className="w-3.5 h-3.5" />
            <span>NCUA Share Insurance Coverage Up to $250k</span>
          </div>

          <h1 className="text-4xl md:text-6xl lg:text-7xl font-extrabold tracking-tight leading-tight max-w-4xl mx-auto mb-6">
            Build Your Savings <br />
            <span className="bg-gradient-to-r from-emerald-400 via-teal-300 to-cyan-400 bg-clip-text text-transparent">
              With Secure Portfolios.
            </span>
          </h1>

          <p className="text-lg text-slate-600 dark:text-slate-400 max-w-2xl mx-auto leading-relaxed">
            Grow your money securely. From high-yield tiered premier accounts to custom savings for home buying, we have a solution for every milestone.
          </p>
        </div>
      </section>

      {/* Interactive Savings Calculators */}
      <section className="px-6 mb-16">
        <div className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-8">
          
          {/* Premier Savings Calculator (7 cols) */}
          <div className="lg:col-span-7 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl p-6 md:p-8 shadow-xl flex flex-col justify-between">
            <div>
              <div className="flex items-center gap-2 mb-6">
                <div className="p-2 rounded-xl bg-emerald-500/10 text-emerald-500">
                  <Calculator className="w-5 h-5" />
                </div>
                <div>
                  <h2 className="text-lg font-bold text-slate-900 dark:text-white">Premier Savings Estimator</h2>
                  <p className="text-xs text-slate-500">Unlock up to 3.25% APY by reaching higher savings thresholds</p>
                </div>
              </div>

              {/* Slider for Premier Savings */}
              <div className="space-y-4 mb-8">
                <div className="flex justify-between items-center">
                  <label htmlFor="premierBalance" className="text-sm font-semibold text-slate-700 dark:text-slate-300">Target Balance</label>
                  <div className="flex items-center gap-1 bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-1 font-mono text-sm font-bold text-slate-900 dark:text-white">
                    <span>$</span>
                    <input 
                      type="number" 
                      id="premierBalance"
                      value={premierBalance}
                      onChange={(e) => setPremierBalance(Number(e.target.value))}
                      className="w-24 bg-transparent outline-none border-none text-right font-bold"
                      min="0"
                    />
                  </div>
                </div>
                <input 
                  type="range" 
                  min="0" 
                  max="150000" 
                  step="1000"
                  value={premierBalance}
                  onChange={(e) => setPremierBalance(Number(e.target.value))}
                  className="w-full h-2 bg-slate-200 dark:bg-slate-800 rounded-lg appearance-none cursor-pointer accent-emerald-500"
                />
                <div className="flex justify-between text-[10px] font-semibold text-slate-400">
                  <span>Base (0.02%)</span>
                  <span>$50,000 (Tier 3: 2.25%)</span>
                  <span>$75,000 (Tier 4: 2.75%)</span>
                  <span>$100,000 (Tier 5: 3.25%)</span>
                </div>
              </div>
            </div>

            {/* Premier Calculations Result Block */}
            <div className="bg-slate-50 dark:bg-slate-950 rounded-2xl p-5 border border-slate-200/50 dark:border-slate-800/80 space-y-4">
              <div className="grid grid-cols-3 gap-4 text-center">
                <div className="space-y-1">
                  <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Interest Tier</div>
                  <div className="text-xs font-bold text-slate-700 dark:text-slate-300 truncate" title={premierStats.tierName}>
                    {premierStats.apy > 0.02 ? (
                      <span className="text-emerald-500">Premium Tier</span>
                    ) : (
                      "Base Savings"
                    )}
                  </div>
                </div>
                <div className="space-y-1 border-x border-slate-200 dark:border-slate-800">
                  <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Estimated APY</div>
                  <div className="text-xl font-black text-slate-900 dark:text-white flex items-center justify-center gap-0.5">
                    <Percent className="w-4 h-4 text-emerald-500" />
                    <span>{premierStats.apy.toFixed(2)}%</span>
                  </div>
                </div>
                <div className="space-y-1">
                  <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Annual Interest</div>
                  <div className="text-xl font-black text-emerald-600 dark:text-emerald-400">
                    +${premierStats.annualInterest.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </div>
                </div>
              </div>
              <div className="pt-3 border-t border-slate-200 dark:border-slate-800 text-[10px] text-slate-500 text-center leading-relaxed">
                Requires direct deposits of $500+ monthly to your checking. Accounts that fail to meet this threshold convert automatically to traditional savings at a 0.02% APY dividend rate.
              </div>
            </div>
          </div>

          {/* Mortgage Savings Closer Cost Credit Estimator (5 cols) */}
          <div className="lg:col-span-5 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl p-6 shadow-xl flex flex-col justify-between gap-6">
            <div>
              <div className="flex items-center gap-2 mb-4">
                <div className="p-2 rounded-xl bg-cyan-500/10 text-cyan-500">
                  <Home className="w-5 h-5" />
                </div>
                <div>
                  <h2 className="text-lg font-bold text-slate-900 dark:text-white">Mortgage Credit Builder</h2>
                  <p className="text-xs text-slate-500">Earn $1 towards closing costs for every $5 saved</p>
                </div>
              </div>

              {/* Slider for Mortgage Savings */}
              <div className="space-y-4 mb-6">
                <div className="flex justify-between items-center text-xs">
                  <label htmlFor="mortgageBalance" className="font-semibold text-slate-700 dark:text-slate-300">Home Purchase Fund</label>
                  <div className="flex items-center gap-1 bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg px-2.5 py-0.5 font-mono font-bold text-slate-900 dark:text-white">
                    <span>$</span>
                    <input 
                      type="number" 
                      id="mortgageBalance"
                      value={mortgageBalance}
                      onChange={(e) => setMortgageBalance(Number(e.target.value))}
                      className="w-16 bg-transparent outline-none border-none text-right font-bold"
                      min="0"
                    />
                  </div>
                </div>
                <input 
                  type="range" 
                  min="0" 
                  max="10000" 
                  step="250"
                  value={mortgageBalance}
                  onChange={(e) => setMortgageBalance(Number(e.target.value))}
                  className="w-full h-2 bg-slate-200 dark:bg-slate-800 rounded-lg appearance-none cursor-pointer accent-cyan-500"
                />
              </div>

              {/* Calculation of credit progress */}
              <div className="space-y-3">
                <div className="flex justify-between items-end text-xs">
                  <span className="text-slate-500 font-medium">Earned Mortgage Closing Credit:</span>
                  <span className="font-black text-slate-900 dark:text-white text-base">
                    ${mortgageStats.credit.toLocaleString()} <span className="text-[10px] text-slate-400 font-normal">/ $1,000 max</span>
                  </span>
                </div>
                
                {/* Progress bar */}
                <div className="w-full h-2.5 bg-slate-150 dark:bg-slate-800 rounded-full overflow-hidden">
                  <div 
                    className="h-full rounded-full bg-gradient-to-r from-cyan-400 to-emerald-400 transition-all duration-300"
                    style={{ width: `${mortgageStats.progressPercent}%` }}
                  />
                </div>

                <div className="text-[10px] text-slate-400 leading-relaxed pt-1 font-medium">
                  {mortgageBalance >= 5000 ? (
                    <span className="text-emerald-500 font-semibold">🎉 Maximum closing credit milestone unlocked!</span>
                  ) : (
                    <span>Save another <strong className="text-slate-700 dark:text-slate-350">${(5000 - mortgageBalance).toLocaleString()}</strong> to qualify for the full $1,000 lender credit toward your HVCU mortgage loan closing.</span>
                  )}
                </div>
              </div>
            </div>

            <div className="p-3.5 bg-cyan-500/5 rounded-2xl border border-cyan-500/10 text-[11px] leading-relaxed text-slate-500">
              <span className="font-bold text-slate-800 dark:text-slate-200">Eligibility details:</span> Requires opening deposit of $100, monthly deposits of $100 for at least 10 months, and securing approval to close on an HVCU mortgage loan within 36 months.
            </div>
          </div>

        </div>
      </section>

      {/* Comparison Matrix Table */}
      <section className="px-6 mb-16">
        <div className="max-w-7xl mx-auto">
          <div className="overflow-x-auto border border-slate-200 dark:border-slate-800/80 rounded-3xl bg-white dark:bg-slate-900 shadow-2xl">
            
            <div className="p-6 border-b border-slate-200 dark:border-slate-800 flex flex-wrap justify-between items-center gap-4 bg-slate-50/50 dark:bg-slate-950/50">
              <div>
                <div className="text-xs font-bold text-slate-400 uppercase tracking-wider">Savings Product comparison</div>
                <div className="text-sm font-semibold text-slate-900 dark:text-white mt-0.5">Find the right account for your milestones</div>
              </div>
            </div>

            <table className="w-full text-left border-collapse min-w-[700px]">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-800 bg-slate-50/80 dark:bg-slate-950/80">
                  <th className="p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider">Account Type</th>
                  <th className="p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider">Min. to Open</th>
                  <th className="p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider">Base APY</th>
                  <th className="p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider">Key Details</th>
                  <th className="p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-800/60 text-sm">
                {savingsProducts.map((prod, idx) => (
                  <tr key={idx} className="hover:bg-slate-50/80 dark:hover:bg-slate-800/30 transition-colors">
                    <td className="p-5">
                      <div className="font-bold text-slate-900 dark:text-white">{prod.name}</div>
                      <div className="text-[10px] uppercase px-2 py-0.5 rounded font-semibold bg-slate-100 dark:bg-slate-800 text-slate-500 inline-block mt-1">
                        {prod.tag}
                      </div>
                    </td>
                    <td className="p-5 font-mono text-xs text-slate-700 dark:text-slate-300">
                      ${prod.minDeposit.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </td>
                    <td className="p-5 font-black text-slate-900 dark:text-white">
                      {prod.name === "Premier Savings" ? (
                        <span>Up to 3.25%</span>
                      ) : (
                        <span>{prod.baseApy.toFixed(2)}%</span>
                      )}
                    </td>
                    <td className="p-5 text-xs text-slate-500 leading-relaxed max-w-sm">
                      {prod.details}
                    </td>
                    <td className="p-5 text-right">
                      <button
                        onClick={() => setOpeningAccount(prod)}
                        className="px-4 py-2 rounded-xl bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 font-bold text-xs transition-colors flex items-center gap-1 ml-auto"
                      >
                        <span>Open</span>
                        <ArrowRight className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* Program Details Tabs */}
      <section className="px-6">
        <div className="max-w-7xl mx-auto bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800/80 rounded-3xl p-6 md:p-8">
          
          <div className="flex border-b border-slate-200 dark:border-slate-800 mb-6 gap-6 overflow-x-auto pb-px">
            <button 
              onClick={() => setActiveTab("premier")}
              className={`pb-4 text-sm font-semibold relative flex items-center gap-2 cursor-pointer transition-colors ${
                activeTab === "premier" 
                  ? 'text-emerald-500 font-bold' 
                  : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-300'
              }`}
            >
              <Coins className="w-4 h-4" />
              <span>Premier Qualifications</span>
              {activeTab === "premier" && (
                <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-emerald-500 rounded-full" />
              )}
            </button>
            <button 
              onClick={() => setActiveTab("clubs")}
              className={`pb-4 text-sm font-semibold relative flex items-center gap-2 cursor-pointer transition-colors ${
                activeTab === "clubs" 
                  ? 'text-emerald-500 font-bold' 
                  : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-300'
              }`}
            >
              <TrendingUp className="w-4 h-4" />
              <span>Clubs & Minor Accounts</span>
              {activeTab === "clubs" && (
                <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-emerald-500 rounded-full" />
              )}
            </button>
            <button 
              onClick={() => setActiveTab("faqs")}
              className={`pb-4 text-sm font-semibold relative flex items-center gap-2 cursor-pointer transition-colors ${
                activeTab === "faqs" 
                  ? 'text-emerald-500 font-bold' 
                  : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-300'
              }`}
            >
              <HelpCircle className="w-4 h-4" />
              <span>Share Rules & FAQs</span>
              {activeTab === "faqs" && (
                <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-emerald-500 rounded-full" />
              )}
            </button>
          </div>

          <div className="space-y-6 text-sm text-slate-600 dark:text-slate-400 leading-relaxed">
            
            {activeTab === "premier" && (
              <div className="space-y-4">
                <h3 className="text-lg font-bold text-slate-900 dark:text-white">Premier Savings Guidelines</h3>
                <p>
                  Premier Savings allows members to capture higher yields on larger deposit amounts. To open and keep the Premier Savings account, you must satisfy the following checking account activity requirements:
                </p>
                <ul className="list-disc pl-5 space-y-2 text-slate-500">
                  <li>Maintain an aggregate minimum of <span className="font-semibold text-slate-700 dark:text-slate-300">$500 monthly</span> in direct deposit(s) to your primary checking account.</li>
                  <li>Maintain an average daily balance of <span className="font-semibold text-slate-700 dark:text-slate-300">$500</span> in your primary checking account.</li>
                  <li>The account is limited to one joint owner and only one Premier Savings account is permitted per primary member.</li>
                  <li>There is an annual account maintenance fee of $45 charged to the account.</li>
                </ul>
              </div>
            )}

            {activeTab === "clubs" && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="space-y-3">
                  <h4 className="font-bold text-slate-900 dark:text-white">Holiday Club Account</h4>
                  <p>
                    Save for seasonal gift shopping and expenses without stress. Transfer funds manually or set up auto-deposits during the year. The accumulated balance is swept automatically and deposited back to your primary savings account in October, just in time for holiday purchases.
                  </p>
                </div>
                <div className="space-y-3">
                  <h4 className="font-bold text-slate-900 dark:text-white">College Savings Minor Account</h4>
                  <p>
                    Open with a $5 minimum balance for minors. Parent or guardian must act as a joint owner. Minor must also maintain a Primary savings share ($0.01 balance). Features special variable dividends and annual anniversary bonuses credited directly to the account.
                  </p>
                </div>
              </div>
            )}

            {activeTab === "faqs" && (
              <div className="space-y-4">
                <h3 className="text-lg font-bold text-slate-900 dark:text-white">Share Rules & Dividends FAQs</h3>
                
                <div className="space-y-3">
                  <div className="font-bold text-slate-850 dark:text-slate-250 flex items-center gap-1.5">
                    <Info className="w-4 h-4 text-emerald-500 animate-bounce" />
                    <span>What is a primary savings share?</span>
                  </div>
                  <p className="pl-6 text-xs">
                    To become a credit union member, you must open a primary savings share account with a par value of $0.01. Maintaining a balance of at least $0.01 in this account keeps your membership active and grants access to borrowing and other services.
                  </p>
                </div>

                <div className="space-y-3 border-t border-slate-200 dark:border-slate-800/60 pt-4">
                  <div className="font-bold text-slate-850 dark:text-slate-250 flex items-center gap-1.5">
                    <Info className="w-4 h-4 text-emerald-500" />
                    <span>How are dividends paid on savings accounts?</span>
                  </div>
                  <p className="pl-6 text-xs">
                    Dividends are paid from current income and available earnings after required transfers to reserves. Dividends compound monthly based on the daily balance and are credited to accounts monthly.
                  </p>
                </div>
              </div>
            )}

          </div>
        </div>
      </section>

      {/* Shared Account Opening Integration Modal */}
      <AccountOpeningModal
        openingAccount={openingAccount}
        onClose={() => setOpeningAccount(null)}
        accountType="SAVINGS"
        brandColorFrom={brandColorFrom}
        brandColorTo={brandColorTo}
      />
    </div>
  );
}

export default SavingsAccountsView;
