import React from 'react';
import { 
  Shield, 
  ArrowRight, 
  TrendingUp, 
  CreditCard, 
  Percent, 
  Lock, 
  Smartphone, 
  Globe, 
  Check 
} from 'lucide-react';
import { useSettings } from '../context/SettingsContext.jsx';

function HomeView({
  loanAmount,
  setLoanAmount,
  loanTerm,
  setLoanTerm,
  activeBot,
  setActiveBot,
  calculateMonthlyPayment,
  interestRate
}) {
  const { 
    bankName,
    brandColorFrom,
    brandColorTo
  } = useSettings();
  return (
    <>
      {/* Hero Section */}
      <section className="relative pt-32 pb-24 md:pt-48 md:pb-32 px-6">
        <div className="absolute inset-0 -z-10 overflow-hidden">
          <img 
            src="/hero_bg.png" 
            alt="Abstract background" 
            className="w-full h-full object-cover opacity-40 mix-blend-screen"
          />
          <div className="absolute inset-0 bg-gradient-to-b from-slate-50/50 via-slate-50/80 to-slate-50 dark:from-slate-950/50 dark:via-slate-950/80 dark:to-slate-950"></div>
        </div>

        <div className="max-width-7xl mx-auto grid grid-cols-1 lg:grid-cols-2 gap-16 items-center">
          <div className="space-y-8">
            <div className="inline-flex items-center space-x-2 px-4 py-2 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-600 dark:text-emerald-400 text-xs font-semibold tracking-wide">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
              <span>Voted #1 Digital Credit Union 2026</span>
            </div>
            
            <h1 className="text-5xl md:text-7xl font-extrabold tracking-tight leading-tight">
              Banking that works <br />
              <span className="bg-gradient-to-r from-emerald-400 via-teal-300 to-cyan-400 bg-clip-text text-transparent">
                in your best interest.
              </span>
            </h1>
            
            <p className="text-lg text-slate-600 dark:text-slate-400 max-w-xl leading-relaxed">
              Experience next-generation retail banking combined with the trusted values of a member-owned credit union. Higher yields, lower rates, zero hidden fees.
            </p>

            <div className="flex flex-col sm:flex-row gap-4">
              <button 
                className="flex items-center justify-center space-x-2 px-8 py-4 rounded-full text-slate-950 font-bold text-base shadow-xl hover:scale-[1.02] transition-all duration-300"
                style={{ backgroundImage: `linear-gradient(to right, ${brandColorFrom}, ${brandColorTo})`, boxShadow: `0 20px 25px -5px ${brandColorFrom}33` }}
              >
                <span>Become a Member</span>
                <ArrowRight className="w-5 h-5" />
              </button>
              <button className="flex items-center justify-center px-8 py-4 rounded-full bg-slate-900 border border-slate-800 text-slate-200 font-semibold hover:bg-slate-800 transition-colors">
                Compare Accounts
              </button>
            </div>

            <div className="pt-8 border-t border-slate-200 dark:border-slate-900 flex items-center justify-between max-w-md">
              <div>
                <div className="text-3xl font-bold text-slate-900 dark:text-white">4.85%</div>
                <div className="text-xs text-slate-600 dark:text-slate-500">APY on High-Yield Savings</div>
              </div>
              <div className="w-px h-12 bg-slate-200 dark:bg-slate-950"></div>
              <div>
                <div className="text-3xl font-bold text-slate-900 dark:text-white">0.00%</div>
                <div className="text-xs text-slate-600 dark:text-slate-500">Maintenance Fees</div>
              </div>
              <div className="w-px h-12 bg-slate-200 dark:bg-slate-950"></div>
              <div>
                <div className="text-3xl font-bold text-slate-900 dark:text-white">150k+</div>
                <div className="text-xs text-slate-600 dark:text-slate-500">Active Members</div>
              </div>
            </div>
          </div>

          {/* Interactive Glassmorphism Dashboard Preview */}
          <div className="relative hidden lg:block">
            <div className="absolute -inset-4 bg-gradient-to-tr from-emerald-500/20 to-cyan-500/20 rounded-3xl blur-3xl -z-10"></div>
            <div className="relative border border-slate-800/80 rounded-2xl p-8 shadow-2xl shadow-black/50" style={{ backgroundColor: 'var(--card-bg-color, #0f172a)' }}>
              <div className="flex items-center justify-between mb-8">
                <div>
                  <div className="text-sm text-slate-400">Total Balance</div>
                  <div className="text-4xl font-bold text-white mt-1">$124,580.45</div>
                </div>
                <div className="w-12 h-12 rounded-xl bg-emerald-500/10 flex items-center justify-center border border-emerald-500/20 text-emerald-400">
                  <TrendingUp className="w-6 h-6" />
                </div>
              </div>

              <div className="space-y-4 mb-8">
                <div className="bg-slate-950/50 rounded-xl p-4 border border-slate-800/50 flex items-center justify-between">
                  <div className="flex items-center space-x-4">
                    <div className="w-10 h-10 rounded-lg bg-teal-500/20 flex items-center justify-center text-teal-400">
                      <CreditCard className="w-5 h-5" />
                    </div>
                    <div>
                      <div className="font-medium text-white">Nova Signature Checking</div>
                      <div className="text-xs text-slate-400">**** 4829</div>
                    </div>
                  </div>
                  <div className="font-semibold text-white">$14,250.00</div>
                </div>

                <div className="bg-slate-950/50 rounded-xl p-4 border border-slate-800/50 flex items-center justify-between">
                  <div className="flex items-center space-x-4">
                    <div className="w-10 h-10 rounded-lg bg-emerald-500/20 flex items-center justify-center text-emerald-400">
                      <Percent className="w-5 h-5" />
                    </div>
                    <div>
                      <div className="font-medium text-white">High-Yield Growth</div>
                      <div className="text-xs text-slate-400">4.85% APY Earned</div>
                    </div>
                  </div>
                  <div className="font-semibold text-white">$110,330.45</div>
                </div>
              </div>

              <div className="flex items-center justify-between text-xs text-slate-500">
                <span>Secured by 256-bit AES Encryption</span>
                <div className="flex items-center space-x-1 text-emerald-400">
                  <Lock className="w-3 h-3" />
                  <span>End-to-End Encrypted</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section id="features" className="py-24 px-6 bg-slate-50 dark:bg-slate-900/30 border-y border-slate-200 dark:border-slate-900">
        <div className="max-w-7xl mx-auto">
          <div className="text-center max-w-2xl mx-auto mb-16">
            <h2 className="text-3xl md:text-5xl font-bold tracking-tight mb-4 text-slate-900 dark:text-white">
              Designed for your financial freedom
            </h2>
            <p className="text-slate-600 dark:text-slate-400">
              We provide the tools, rates, and security you need to grow your wealth effortlessly.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {[
              {
                icon: Smartphone,
                title: "Modern Digital Experience",
                desc: "Manage everything from our lightning-fast mobile app with biometric login and instant transfers."
              },
              {
                icon: Shield,
                title: "NCUA Insured Security",
                desc: "Your deposits are federally insured up to $250,000 by the National Credit Union Administration."
              },
              {
                icon: Globe,
                title: "Global ATM Access",
                desc: "Access your cash anywhere with zero ATM fees worldwide. We automatically reimburse all charges."
              }
            ].map((item, idx) => (
              <div key={idx} className="card-themeable hover:border-emerald-500/50 transition-all duration-300 group hover:-translate-y-1">
                <div className="w-12 h-12 rounded-xl bg-slate-100 dark:bg-slate-900 flex items-center justify-center mb-6 group-hover:scale-110 transition-transform duration-300 border border-slate-200 dark:border-slate-700/50">
                  <item.icon className="w-6 h-6 text-emerald-500" />
                </div>
                <h3 className="text-xl font-semibold mb-3 text-theme-main">{item.title}</h3>
                <p className="text-theme-muted text-sm leading-relaxed">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Interactive Loan Calculator Section */}
      <section id="calculator" className="py-24 px-6">
        <div className="max-width-7xl mx-auto grid grid-cols-1 lg:grid-cols-2 gap-16 items-center">
          <div>
            <span className="text-emerald-600 dark:text-emerald-400 font-medium text-sm tracking-wider uppercase">Smart Planning</span>
            <h2 className="text-4xl font-bold tracking-tight mt-3 mb-6 text-slate-900 dark:text-white">
              Calculate your loan with transparent rates.
            </h2>
            <p className="text-slate-600 dark:text-slate-400 mb-8 leading-relaxed">
              No hidden fees, no origination costs. Slide to adjust your desired amount and term to see exactly what you'll pay each month.
            </p>

            <div className="space-y-4">
              {[
                "Same-day approval for personal and auto loans",
                "Fixed rates so your payment never changes",
                "No prepayment penalties—pay off anytime"
              ].map((text, i) => (
                <div key={i} className="flex items-center space-x-3">
                  <div className="w-5 h-5 rounded-full bg-emerald-500/20 flex items-center justify-center text-emerald-600 dark:text-emerald-400 flex-shrink-0">
                    <Check className="w-3 h-3" />
                  </div>
                  <span className="text-sm text-slate-600 dark:text-slate-300">{text}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="card-slate-900 shadow-2xl">
            <h3 className="text-xl font-semibold mb-8 text-white">Personal Loan Estimator</h3>
            
            {/* Loan Amount Slider */}
            <div className="mb-8">
              <div className="flex justify-between items-center mb-3">
                <label className="text-sm font-medium text-slate-400">Loan Amount</label>
                <span className="text-xl font-bold text-white">${loanAmount.toLocaleString()}</span>
              </div>
              <input 
                type="range" 
                min="1000" 
                max="100000" 
                step="1000"
                value={loanAmount}
                onChange={(e) => setLoanAmount(Number(e.target.value))}
                className="w-full h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-emerald-500"
              />
              <div className="flex justify-between text-xs text-slate-600 mt-2">
                <span>$1,000</span>
                <span>$100,000</span>
              </div>
            </div>

            {/* Loan Term Slider */}
            <div className="mb-12">
              <div className="flex justify-between items-center mb-3">
                <label className="text-sm font-medium text-slate-400">Loan Term (Months)</label>
                <span className="text-xl font-bold text-white">{loanTerm} Months</span>
              </div>
              <input 
                type="range" 
                min="12" 
                max="84" 
                step="12"
                value={loanTerm}
                onChange={(e) => setLoanTerm(Number(e.target.value))}
                className="w-full h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-emerald-500"
              />
              <div className="flex justify-between text-xs text-slate-600 mt-2">
                <span>12 months</span>
                <span>84 months</span>
              </div>

              {/* Result Display */}
              <div className="bg-sky-50 dark:bg-slate-950 rounded-xl p-6 border border-sky-200 dark:border-slate-800 flex items-center justify-between mb-6">
                <div>
                  <div className="text-xs text-slate-500 mb-1">Estimated Monthly Payment</div>
                  <div className="text-4xl font-black text-emerald-400">${calculateMonthlyPayment()}</div>
                </div>
                <div className="text-right">
                  <div className="text-xs text-slate-500 mb-1">Fixed APR</div>
                  <div className="text-2xl font-bold text-slate-900 dark:text-white">{interestRate}%</div>
                </div>
              </div>
            </div>

            <button 
              className="w-full py-4 rounded-xl text-slate-950 font-bold shadow-lg hover:scale-[1.02] transition-all duration-300"
              style={{ backgroundImage: `linear-gradient(to right, ${brandColorFrom}, ${brandColorTo})`, boxShadow: `0 10px 15px -3px ${brandColorFrom}33` }}
            >
              Apply for Loan Now
            </button>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-20 px-6 relative overflow-hidden border-y border-slate-800" style={{ backgroundColor: 'var(--card-bg-color, #0f172a)' }}>
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-96 bg-emerald-500/10 rounded-full blur-3xl"></div>
        <div className="max-w-4xl mx-auto text-center relative z-10">
          <h2 className="text-3xl md:text-5xl font-black mb-6 text-white">
            Ready to take control of your wealth?
          </h2>
          <p className="text-slate-400 max-w-xl mx-auto mb-8">
            Join thousands of members who are earning more and paying less with {bankName} Credit Union.
          </p>
                <button
                  className="px-8 py-4 rounded-full text-slate-950 font-bold text-base shadow-xl hover:scale-105 transition-all duration-300"
                  style={{ backgroundImage: `linear-gradient(to right, ${brandColorFrom}, ${brandColorTo})`, boxShadow: `0 20px 25px -5px ${brandColorFrom}33` }}
                >
            Open an Account in 5 Minutes
          </button>
        </div>
      </section>

      {/* Help Center & AI Support */}
      <section id="help" className="py-24 px-6 bg-slate-50 dark:bg-slate-950">
        <div className="max-width-7xl mx-auto">
          <div className="text-center max-w-2xl mx-auto mb-16">
            <span className="text-teal-600 dark:text-teal-400 font-medium text-sm tracking-wider uppercase">Automated Assistance</span>
            <h2 className="text-3xl md:text-5xl font-bold tracking-tight mt-3 mb-4 text-slate-900 dark:text-white">
              How can we help you today?
            </h2>
            <p className="text-slate-600 dark:text-slate-400">
              Select an inquiry below to instantly launch a specialized AI support agent trained to resolve your specific request.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {[
              {
                title: "Account & Login",
                desc: "Unlock your account, reset passwords, or troubleshoot two-factor authentication issues.",
                botName: "Account Support Bot"
              },
              {
                title: "Loan Applications",
                desc: "Check pre-approval status, calculate customized rates, or upload pending documents.",
                botName: "Loan Advisor Bot"
              },
              {
                title: "Fraud & Security",
                desc: "Report unauthorized charges, freeze debit/credit cards instantly, or dispute a transaction.",
                botName: "Security & Fraud Bot"
              },
              {
                title: "Rates & Yields",
                desc: "Learn about high-yield savings tiers, certificate of deposit (CD) rates, and IRA structures.",
                botName: "Wealth Management Bot"
              },
              {
                title: "Lost Credit Card",
                desc: "Instantly freeze a missing card, report it lost or stolen, and request an expedited replacement.",
                botName: "Lost Card Agent"
              }
            ].map((inquiry, idx) => (
              <div key={idx} className="card-slate-900 flex flex-col justify-between hover:border-teal-500/50 hover:bg-slate-800 transition-all duration-300 group">
                <div>
                  <h3 className="text-lg font-semibold text-white mb-2 group-hover:text-teal-400 transition-colors">
                    {inquiry.title}
                  </h3>
                  <p className="text-slate-400 text-sm leading-relaxed mb-6">
                    {inquiry.desc}
                  </p>
                </div>
                <button 
                  onClick={() => {
                    setActiveBot(inquiry.botName);
                    setTimeout(() => setActiveBot(null), 3500);
                  }}
                  className="w-full py-3 rounded-xl bg-slate-800 text-slate-200 text-sm font-semibold hover:bg-teal-500 hover:text-slate-950 transition-all duration-300 shadow-sm hover:shadow-teal-500/20"
                >
                  Launch {inquiry.botName}
                </button>
              </div>
            ))}
          </div>

          {/* Interactive Bot Launch Modal/Toast */}
          {activeBot && (
            <div className="fixed bottom-8 right-8 z-50 border border-teal-500/50 rounded-2xl p-4 shadow-2xl shadow-teal-500/20 flex items-center space-x-4 animate-bounce" style={{ backgroundColor: 'var(--card-bg-color, #0f172a)' }}>
              <div className="w-10 h-10 rounded-xl bg-teal-500/20 flex items-center justify-center text-teal-400">
                <div className="w-2 h-2 bg-teal-400 rounded-full animate-ping"></div>
              </div>
              <div>
                <div className="text-xs text-teal-400 font-semibold uppercase tracking-wider">Connecting...</div>
                <div className="text-sm font-medium text-white">Initializing {activeBot}</div>
              </div>
            </div>
          )}

        </div>
      </section>
    </>
  );
}

export default HomeView;
