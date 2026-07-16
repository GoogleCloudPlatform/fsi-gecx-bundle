import React, { useState, useMemo } from 'react';
import { 
  Calculator, 
  TrendingUp, 
  Layers, 
  ShieldCheck, 
  Info, 
  Percent, 
  ArrowRight,
  Coins,
  Calendar,
  HelpCircle
} from 'lucide-react';
import { certificateAccounts as ratesData } from '../utils/productData.js';
import AnalyticsButton from './AnalyticsButton.jsx';


function CertificateAccountsView() {

  const [depositAmount, setDepositAmount] = useState(10000);
  const [selectedTermIndex, setSelectedTermIndex] = useState(2); // Default to 12-Month Fixed

  // Calculate bonus based on deposit tier and whether the certificate is a Fixed Rate (Flex does not get bonuses)
  const calculatedStats = useMemo(() => {
    const selected = ratesData[selectedTermIndex];
    let bonus = 0;
    let tierName = "Standard Tier";

    if (!selected.isFlex) {
      if (depositAmount >= 100000) {
        bonus = 0.10;
        tierName = "Jumbo Tier Plus (>= $100k)";
      } else if (depositAmount >= 50000) {
        bonus = 0.05;
        tierName = "Jumbo Tier (>= $50k)";
      }
    } else {
      tierName = "Flex Account Standard Rate";
    }

    const effectiveApy = selected.baseApy + bonus;
    const isBelowMin = depositAmount < selected.minDeposit;

    // A = P * (1 + APY / 100)^(t_months / 12)
    const total = isBelowMin ? 0 : depositAmount * Math.pow(1 + effectiveApy / 100, selected.term / 12);
    const interestEarned = isBelowMin ? 0 : total - depositAmount;

    return {
      effectiveApy,
      interestEarned,
      total,
      bonus,
      tierName,
      isBelowMin,
      selected
    };
  }, [depositAmount, selectedTermIndex]);

  const [activeTab, setActiveTab] = useState("laddering");

  // Visual simulation data for laddering $25,000 example (5 Certificates of $5,000 each)
  const ladderSteps = [
    { term: "12-Month", rate: "3.40%", amount: "$5,000", maturity: "Year 1" },
    { term: "24-Month", rate: "3.50%", amount: "$5,000", maturity: "Year 2" },
    { term: "36-Month", rate: "3.60%", amount: "$5,000", maturity: "Year 3" },
    { term: "48-Month", rate: "3.60%", amount: "$5,000", maturity: "Year 4" },
    { term: "60-Month", rate: "3.65%", amount: "$5,000", maturity: "Year 5" }
  ];

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
            <span>NCUA Federally Insured Savings</span>
          </div>

          <h1 className="text-4xl md:text-6xl lg:text-7xl font-extrabold tracking-tight leading-tight max-w-4xl mx-auto mb-6">
            Guaranteed High-Yield <br />
            <span className="bg-gradient-to-r from-emerald-400 via-teal-300 to-cyan-400 bg-clip-text text-transparent">
              Certificate Portfolios.
            </span>
          </h1>

          <p className="text-lg text-slate-600 dark:text-slate-400 max-w-2xl mx-auto leading-relaxed">
            Maximize your returns with zero market risk. Earn competitive yields on short-term deposits or unlock premium rates with our Jumbo tiers.
          </p>
        </div>
      </section>

      {/* Interactive CD Calculator & Active Rates */}
      <section className="px-6 mb-16">
        <div className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-8">
          
          {/* CD Calculator Column (7 cols) */}
          <div className="lg:col-span-7 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl p-6 md:p-8 shadow-xl flex flex-col justify-between">
            <div>
              <div className="flex items-center gap-2 mb-6">
                <div className="p-2 rounded-xl bg-emerald-500/10 text-emerald-500">
                  <Calculator className="w-5 h-5" />
                </div>
                <div>
                  <h2 className="text-lg font-bold text-slate-900 dark:text-white">Earnings Estimator</h2>
                  <p className="text-xs text-slate-500">Simulate yields on various terms and deposit thresholds</p>
                </div>
              </div>

              {/* Amount Input */}
              <div className="space-y-4 mb-8">
                <div className="flex justify-between items-center">
                  <label htmlFor="depositAmount" className="text-sm font-semibold text-slate-700 dark:text-slate-300">Opening Deposit</label>
                  <div className="flex items-center gap-1 bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-1 font-mono text-sm font-bold text-slate-900 dark:text-white">
                    <span>$</span>
                    <input 
                      type="number" 
                      id="depositAmount"
                      value={depositAmount}
                      onChange={(e) => setDepositAmount(Number(e.target.value))}
                      className="w-24 bg-transparent outline-none border-none text-right font-bold"
                      min="100"
                    />
                  </div>
                </div>
                <input 
                  type="range" 
                  min="500" 
                  max="250000" 
                  step="500"
                  value={depositAmount}
                  onChange={(e) => setDepositAmount(Number(e.target.value))}
                  className="w-full h-2 bg-slate-200 dark:bg-slate-800 rounded-lg appearance-none cursor-pointer accent-emerald-500"
                />
                <div className="flex justify-between text-[10px] font-semibold text-slate-400">
                  <span>Min $500</span>
                  <span>$50,000 (Jumbo +0.05%)</span>
                  <span>$100,000 (Jumbo +0.10%)</span>
                  <span>$250,000 Max Slider</span>
                </div>
              </div>

              {/* Term Selector */}
              <div className="space-y-3 mb-8">
                <label className="text-sm font-semibold text-slate-700 dark:text-slate-300">Select Certificate Term</label>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  {ratesData.map((item, idx) => (
                    <AnalyticsButton trackingName="button_click_certificate_accounts_view_01"
                      key={idx}
                      onClick={() => setSelectedTermIndex(idx)}
                      className={`py-3 px-4 rounded-xl border text-left flex flex-col justify-between h-20 transition-all ${
                        selectedTermIndex === idx 
                          ? 'border-emerald-500 bg-emerald-500/5 ring-2 ring-emerald-500/20' 
                          : 'border-slate-200 dark:border-slate-800 bg-transparent hover:border-slate-300 dark:hover:border-slate-700'
                      }`}
                    >
                      <span className="text-xs font-bold text-slate-500 dark:text-slate-400">{item.name.replace(" Certificate", "")}</span>
                      <span className="text-sm font-black text-slate-900 dark:text-white mt-1">
                        {item.baseApy.toFixed(2)}% <span className="text-[10px] font-normal text-slate-400">APY</span>
                      </span>
                    </AnalyticsButton>
                  ))}
                </div>
              </div>
            </div>

            {/* Calculations Result Block */}
            <div className="bg-slate-50 dark:bg-slate-950 rounded-2xl p-5 border border-slate-200/50 dark:border-slate-800/80 space-y-4">
              {calculatedStats.isBelowMin ? (
                <div className="text-center py-4 space-y-2">
                  <div className="text-amber-500 dark:text-amber-400 font-bold text-sm">Deposit amount is below minimum</div>
                  <p className="text-xs text-slate-500">
                    The minimum balance required to open this account is <span className="font-bold text-slate-900 dark:text-white">${calculatedStats.selected.minDeposit}</span>.
                  </p>
                </div>
              ) : (
                <>
                  <div className="grid grid-cols-3 gap-4 text-center">
                    <div className="space-y-1">
                      <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Interest Rate Tier</div>
                      <div className="text-xs font-semibold text-slate-700 dark:text-slate-300 truncate" title={calculatedStats.tierName}>
                        {calculatedStats.bonus > 0 ? (
                          <span className="text-emerald-500 font-bold">Jumbo Boost!</span>
                        ) : (
                          "Standard Rate"
                        )}
                      </div>
                    </div>
                    <div className="space-y-1 border-x border-slate-200 dark:border-slate-800">
                      <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Effective APY</div>
                      <div className="text-xl font-black text-slate-900 dark:text-white flex items-center justify-center gap-0.5">
                        <Percent className="w-4 h-4 text-emerald-500" />
                        <span>{calculatedStats.effectiveApy.toFixed(2)}%</span>
                      </div>
                    </div>
                    <div className="space-y-1">
                      <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Est. Earnings</div>
                      <div className="text-xl font-black text-emerald-600 dark:text-emerald-400">
                        +${calculatedStats.interestEarned.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </div>
                    </div>
                  </div>

                  <div className="pt-3 border-t border-slate-200 dark:border-slate-800 flex justify-between items-center text-xs">
                    <span className="text-slate-500 font-medium">Estimated maturity value ({calculatedStats.selected.term} months):</span>
                    <span className="font-bold text-slate-900 dark:text-white text-sm">
                      ${calculatedStats.total.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </span>
                  </div>
                </>
              )}
            </div>
          </div>

          {/* CD Rates Table Column (5 cols) */}
          <div className="lg:col-span-5 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl p-6 shadow-xl flex flex-col justify-between gap-6">
            <div>
              <div className="flex items-center gap-2 mb-4">
                <div className="p-2 rounded-xl bg-cyan-500/10 text-cyan-500 animate-pulse">
                  <TrendingUp className="w-5 h-5" />
                </div>
                <div>
                  <h2 className="text-lg font-bold text-slate-900 dark:text-white">Active Rates Index</h2>
                  <p className="text-xs text-slate-500">Effective as of 4/1/2026. Subject to change.</p>
                </div>
              </div>

              <div className="divide-y divide-slate-100 dark:divide-slate-800 text-xs">
                {ratesData.map((row, idx) => (
                  <div 
                    key={idx} 
                    onClick={() => setSelectedTermIndex(idx)}
                    className={`py-3 flex justify-between items-center cursor-pointer transition-colors px-2 rounded-xl ${
                      selectedTermIndex === idx 
                        ? 'bg-slate-50 dark:bg-slate-850 font-bold' 
                        : 'hover:bg-slate-50/50 dark:hover:bg-slate-800/20'
                    }`}
                  >
                    <div>
                      <div className="font-bold text-slate-800 dark:text-slate-200">{row.name}</div>
                      <div className="text-[10px] text-slate-400 mt-0.5 font-medium">{row.tag}</div>
                    </div>
                    <div className="text-right">
                      <div className="font-black text-slate-900 dark:text-white text-sm">{row.baseApy.toFixed(2)}% APY</div>
                      <div className="text-[9px] text-slate-400">Min: ${row.minDeposit}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="p-4 bg-emerald-500/5 rounded-2xl border border-emerald-500/10 flex gap-3 text-xs leading-relaxed text-slate-600 dark:text-slate-400">
              <Info className="w-4 h-4 text-emerald-500 shrink-0 mt-0.5" />
              <div>
                <span className="font-bold text-slate-800 dark:text-slate-200">Jumbo Boost:</span> Get +0.05% APY for deposits between $50k and $100k, and +0.10% APY for deposits $100k or greater (valid on Fixed Certificates only).
              </div>
            </div>
          </div>

        </div>
      </section>

      {/* Strategy and Info Tabs */}
      <section className="px-6">
        <div className="max-w-7xl mx-auto bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800/80 rounded-3xl p-6 md:p-8">
          
          {/* Tab Navigation */}
          <div className="flex border-b border-slate-200 dark:border-slate-800 mb-6 gap-6 overflow-x-auto pb-px">
            <AnalyticsButton trackingName="button_click_certificate_accounts_view_02" 
              onClick={() => setActiveTab("laddering")}
              className={`pb-4 text-sm font-semibold relative flex items-center gap-2 cursor-pointer transition-colors ${
                activeTab === "laddering" 
                  ? 'text-emerald-500 font-bold' 
                  : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-300'
              }`}
            >
              <Layers className="w-4 h-4" />
              <span>Certificate Laddering</span>
              {activeTab === "laddering" && (
                <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-emerald-500 rounded-full" />
              )}
            </AnalyticsButton>
            <AnalyticsButton trackingName="button_click_certificate_accounts_view_03" 
              onClick={() => setActiveTab("flex")}
              className={`pb-4 text-sm font-semibold relative flex items-center gap-2 cursor-pointer transition-colors ${
                activeTab === "flex" 
                  ? 'text-emerald-500 font-bold' 
                  : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-300'
              }`}
            >
              <TrendingUp className="w-4 h-4" />
              <span>Flex Certificates</span>
              {activeTab === "flex" && (
                <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-emerald-500 rounded-full" />
              )}
            </AnalyticsButton>
            <AnalyticsButton trackingName="button_click_certificate_accounts_view_04" 
              onClick={() => setActiveTab("faqs")}
              className={`pb-4 text-sm font-semibold relative flex items-center gap-2 cursor-pointer transition-colors ${
                activeTab === "faqs" 
                  ? 'text-emerald-500 font-bold' 
                  : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-300'
              }`}
            >
              <HelpCircle className="w-4 h-4" />
              <span>Policies & FAQs</span>
              {activeTab === "faqs" && (
                <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-emerald-500 rounded-full" />
              )}
            </AnalyticsButton>
          </div>

          {/* Tab Contents */}
          <div className="space-y-6 text-sm text-slate-600 dark:text-slate-400 leading-relaxed">
            
            {activeTab === "laddering" && (
              <div className="grid grid-cols-1 md:grid-cols-12 gap-8 items-center">
                <div className="md:col-span-7 space-y-4">
                  <h3 className="text-lg font-bold text-slate-900 dark:text-white">What is Certificate Laddering?</h3>
                  <p>
                    Staggering the maturity dates of your certificate accounts ensures regular liquidity while still allowing you to lock in the highest rates of longer-term certificates. This helps you avoid early withdrawal penalties when you need cash, since an account matures periodically.
                  </p>
                  <h4 className="font-bold text-slate-800 dark:text-slate-200 mt-4">Example: Staggering a $25,000 Investment</h4>
                  <p>
                    Instead of placing the entire $25,000 into a single 60-Month certificate, you open five separate $5,000 certificates maturing at 12, 24, 36, 48, and 60 months. As the first certificate matures in Year 1, you roll it into a new 60-Month certificate. This pattern is repeated annually, resulting in one high-yield 60-Month certificate maturing every single year.
                  </p>
                </div>
                <div className="md:col-span-5 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-6 rounded-2xl shadow-md space-y-4">
                  <div className="text-xs font-bold text-slate-400 uppercase tracking-wider">Example Ladder visual: $25,000</div>
                  <div className="space-y-2.5">
                    {ladderSteps.map((step, index) => (
                      <div key={index} className="flex justify-between items-center bg-slate-50 dark:bg-slate-950 p-2.5 rounded-xl border border-slate-150 dark:border-slate-800/50">
                        <div className="flex items-center gap-2">
                          <Coins className="w-4 h-4 text-emerald-500" />
                          <div>
                            <div className="font-bold text-slate-800 dark:text-slate-200 text-xs">{step.term} Term</div>
                            <div className="text-[10px] text-slate-400 font-medium">Yield: {step.rate} APY</div>
                          </div>
                        </div>
                        <div className="text-right">
                          <div className="font-bold text-slate-900 dark:text-white text-xs">{step.amount}</div>
                          <div className="text-[9px] text-slate-400 font-semibold bg-emerald-50 dark:bg-emerald-950 text-emerald-600 dark:text-emerald-400 px-1.5 py-0.5 rounded mt-0.5">{step.maturity}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {activeTab === "flex" && (
              <div className="space-y-4">
                <h3 className="text-lg font-bold text-slate-900 dark:text-white">Flex Certificate Accounts</h3>
                <p>
                  Our 12-Month Flex Certificate account offers a variable quarterly dividend rate indexed directly to the Effective Federal Funds Rate (EFFR).
                </p>
                <ul className="list-disc pl-5 space-y-2 text-slate-500">
                  <li>Minimum deposit: <span className="font-semibold text-slate-700 dark:text-slate-300">$750</span></li>
                  <li>Variable quarterly adjustments matching macro interest changes automatically</li>
                  <li>Allows you to benefit from rising-rate environments without lock-in regrets</li>
                  <li>Note: Flex certificates earn a flat rate. Jumbo boosts (+0.05% / +0.10%) are not credited to Flex accounts.</li>
                </ul>
              </div>
            )}

            {activeTab === "faqs" && (
              <div className="space-y-4">
                <h3 className="text-lg font-bold text-slate-900 dark:text-white">Account Disclosures & FAQs</h3>
                
                <div className="space-y-3">
                  <div className="font-bold text-slate-850 dark:text-slate-250 flex items-center gap-1.5">
                    <Info className="w-4 h-4 text-sky-500" />
                    <span>How are dividends computed and credited?</span>
                  </div>
                  <p className="pl-6 text-xs">
                    Dividends are compounded daily based on your daily balance and credited back to the certificate account on a monthly basis. APY assumes dividends remain in the account until maturity.
                  </p>
                </div>

                <div className="space-y-3 border-t border-slate-200 dark:border-slate-800/60 pt-4">
                  <div className="font-bold text-slate-850 dark:text-slate-250 flex items-center gap-1.5">
                    <Info className="w-4 h-4 text-sky-500" />
                    <span>Is there a penalty for early withdrawal?</span>
                  </div>
                  <p className="pl-6 text-xs">
                    Yes. A substantial dividend penalty will be imposed for early withdrawals made prior to the maturity date. Early withdrawal may reduce your principal balance.
                  </p>
                </div>

                <div className="space-y-3 border-t border-slate-200 dark:border-slate-800/60 pt-4">
                  <div className="font-bold text-slate-850 dark:text-slate-250 flex items-center gap-1.5">
                    <Info className="w-4 h-4 text-sky-500" />
                    <span>What happens at maturity?</span>
                  </div>
                  <p className="pl-6 text-xs">
                    Upon maturity, certificate accounts automatically roll over into the same term configuration at the then-active default interest rate, unless you request otherwise during the 10-day grace period.
                  </p>
                </div>
              </div>
            )}

          </div>
        </div>
      </section>
    </div>
  );
}

export default CertificateAccountsView;
