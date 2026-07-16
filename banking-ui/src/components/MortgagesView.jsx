import React, { useState } from 'react';
import { 
  Shield, 
  ArrowRight, 
  Home, 
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
  Percent,
  TrendingUp,
  HeartHandshake,
  Layers,
  Briefcase
} from 'lucide-react';
import { useSettings } from '../context/SettingsContext.jsx';
import AnalyticsButton from './AnalyticsButton.jsx';


function MortgagesView({ activeBot, setActiveBot }) {
  const { 
    bankName, 
    brandColorFrom, 
    brandColorTo
  } = useSettings();

  const [applyingProgram, setApplyingProgram] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submissionSuccess, setSubmissionSuccess] = useState(false);
  const [memberType, setMemberType] = useState('current');

  const programs = [
    {
      name: "Civic Vanguard Edge",
      tag: "First Responders & Military",
      subtitle: "Dedicated setup credits and core structural pricing adjustments for those who serve.",
      desc: "Available exclusively to Active Military, Veterans, Police, Firefighters, Nurses, and Certified EMTs. Unlock immediate fee deductions and personalized localized processing.",
      accentColor: "#0284c7",
      badgeBg: "bg-sky-500/10 border-sky-500/20 text-sky-600 dark:text-sky-400",
      icon: Shield,
      botName: "Civic Lending Bot",
      benefits: [
        "Zero lender application or automated processing fee overhead",
        "Dedicated municipal single-point underwriting support contact",
        "Automated pre-qualification validation line in under 15 minutes"
      ]
    },
    {
      name: "Equinox Closing Match",
      tag: "Accelerated Savings Vesting",
      subtitle: "Earn up to $1,000 in direct matching credits applied at final closing.",
      desc: "Commit to establishing a sequential monthly deposit schedule of $100. We contribute $1 for every $5 deposited securely, matching your dedication over a 10-month continuous holding threshold.",
      accentColor: "#10b981",
      badgeBg: "bg-emerald-500/10 border-emerald-500/20 text-emerald-600 dark:text-emerald-400",
      icon: Gift,
      botName: "Mortgage Savings Bot",
      benefits: [
        "20% effective direct contribution multiplier trigger on matched principal",
        "Seamless continuous principal transfer integration from active checking core",
        "Funds remain fully accessible inside dedicated sub-account structure"
      ]
    },
    {
      name: "Genesis Grant Suite",
      tag: "First-Time Buyer Empowerment",
      subtitle: "Substantial homebuyer liquidity grant matching integrated via partner frameworks.",
      desc: "Access curated regional funding pools designed to heavily subsidize initial out-of-pocket down payments and final settlement execution costs for qualified first-time buyers.",
      accentColor: "#8b5cf6",
      badgeBg: "bg-purple-500/10 border-purple-500/20 text-purple-600 dark:text-purple-400",
      icon: Award,
      botName: "First-Home Grant Bot",
      benefits: [
        "Direct municipal and regional housing equity credit assistance integration",
        "Combines natively with our low down-payment fixed rate lines",
        "Complimentary personalized one-on-one counseling framework included"
      ]
    },
    {
      name: "Apex Velocity Sweep (MAP)",
      tag: "Bi-Weekly Amortization Edge",
      subtitle: "Systematic principal reduction engine saving thousands in projected lifetime interest.",
      desc: "Our Mortgage Accelerator Program executes automated bi-weekly half-payment sweeps from your designated liquid deposit line. Twice per calendar year, a direct extra principal deduction is allocated.",
      accentColor: "#f59e0b",
      badgeBg: "bg-amber-500/10 border-amber-500/20 text-amber-600 dark:text-amber-400",
      icon: RefreshCw,
      botName: "Amortization Sweep Bot",
      benefits: [
        "Shave projected amortization timelines significantly without expensive refi overhead",
        "Fully flexible participation architecture allowing modification at any time",
        "Zero operational administrative enrollment or bi-weekly transfer charges"
      ]
    }
  ];

  const handleApplySubmit = (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    setTimeout(() => {
      setIsSubmitting(false);
      setSubmissionSuccess(true);
      setTimeout(() => {
        setSubmissionSuccess(false);
        setApplyingProgram(null);
      }, 3000);
    }, 1500);
  };

  return (
    <div className="pb-24">
      {/* Hero Section */}
      <section className="relative pt-32 pb-20 md:pt-44 md:pb-28 px-6 overflow-hidden">
        <div className="absolute inset-0 -z-10 overflow-hidden">
          <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[850px] h-[320px] bg-cyan-500/10 rounded-full blur-3xl"></div>
          <div className="absolute bottom-0 left-0 right-0 h-32 bg-gradient-to-t from-slate-50 dark:from-slate-950 to-transparent"></div>
        </div>

        <div className="max-w-7xl mx-auto text-center">
          <div className="inline-flex items-center space-x-2 px-4 py-2 rounded-full bg-cyan-500/10 border border-cyan-500/20 text-cyan-600 dark:text-cyan-400 text-xs font-semibold tracking-wide mb-6">
            <Home className="w-3.5 h-3.5" />
            <span>Residential Core Portfolio</span>
          </div>

          <h1 className="text-4xl md:text-6xl lg:text-7xl font-extrabold tracking-tight leading-tight max-w-4xl mx-auto mb-6">
            Financing tailored to turn <br />
            <span className="bg-gradient-to-r from-cyan-400 via-teal-300 to-emerald-400 bg-clip-text text-transparent">
              properties into legacies.
            </span>
          </h1>

          <p className="text-lg text-slate-600 dark:text-slate-400 max-w-2xl mx-auto leading-relaxed mb-10">
            Discover highly flexible fixed structures, variable interest adjustment models, and exclusive homeownership incentives backed by local decisioning precision.
          </p>

          <div className="flex flex-wrap justify-center gap-4">
            <a
              href="#programs"
              className="px-8 py-4 rounded-full text-slate-950 font-bold text-sm shadow-xl hover:scale-105 transition-all duration-300 flex items-center space-x-2"
              style={{ backgroundImage: `linear-gradient(to right, ${brandColorFrom}, ${brandColorTo})`, boxShadow: `0 10px 15px -3px ${brandColorFrom}33` }}
            >
              <span>Explore Specialized Programs</span>
              <ArrowRight className="w-4 h-4" />
            </a>
            
            <a 
              href="/mortgage-rates"
              className="px-8 py-4 rounded-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-200 font-semibold text-sm hover:bg-slate-50 dark:hover:bg-slate-800/80 transition-colors"
            >
              View Live Rate Sheets
            </a>
          </div>
        </div>
      </section>

      {/* Core Lending Options Breakdown Grid */}
      <section className="px-6 mb-20">
        <div className="max-w-7xl mx-auto">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            
            {/* Fixed Rate Card */}
            <div className="bg-white dark:bg-slate-900/40 p-8 md:p-12 rounded-3xl border border-slate-200 dark:border-slate-800/80 shadow-xl relative overflow-hidden flex flex-col justify-between group">
              <div className="absolute top-0 right-0 w-64 h-64 bg-emerald-500/5 rounded-full blur-2xl transition-all duration-500 group-hover:scale-125"></div>
              
              <div className="relative z-10 space-y-4">
                <div className="w-12 h-12 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-500 flex items-center justify-center">
                  <Lock className="w-6 h-6" />
                </div>
                <h3 className="text-2xl font-bold text-slate-900 dark:text-white">Nova Fixed Security</h3>
                <p className="text-sm text-slate-600 dark:text-slate-400 leading-relaxed">
                  Lock in absolute stability. Our standard 30-year and accelerated 15-year fixed-rate portfolios guarantee zero payment adjustments over the complete term duration. Ideal for long-term equity holding confidence.
                </p>
                <ul className="space-y-2 pt-2 text-xs text-slate-500 dark:text-slate-400">
                  <li className="flex items-center gap-2">
                    <div className="w-1.5 h-1.5 rounded-full bg-emerald-500"></div>
                    <span>Available in Conforming and Jumbo tier classifications</span>
                  </li>
                  <li className="flex items-center gap-2">
                    <div className="w-1.5 h-1.5 rounded-full bg-emerald-500"></div>
                    <span>Zero prepayment or principal acceleration payload penalty fees</span>
                  </li>
                </ul>
              </div>

              <div className="pt-8 relative z-10 flex flex-wrap items-center justify-between gap-4 border-t border-slate-100 dark:border-slate-800/60 mt-6">
                <div>
                  <div className="text-[10px] text-slate-400 uppercase tracking-wider">Base Starting Rate</div>
                  <div className="text-2xl font-black text-slate-900 dark:text-white">6.375% <span className="text-xs font-normal text-slate-500">(6.428% APR)</span></div>
                </div>
                <a 
                  href="/mortgage-rates" 
                  className="text-xs font-bold text-emerald-600 dark:text-emerald-400 flex items-center gap-1 hover:underline"
                >
                  <span>Audit Disclosures</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </a>
              </div>
            </div>

            {/* Adjustable Rate Card */}
            <div className="bg-white dark:bg-slate-900/40 p-8 md:p-12 rounded-3xl border border-slate-200 dark:border-slate-800/80 shadow-xl relative overflow-hidden flex flex-col justify-between group">
              <div className="absolute top-0 right-0 w-64 h-64 bg-cyan-500/5 rounded-full blur-2xl transition-all duration-500 group-hover:scale-125"></div>
              
              <div className="relative z-10 space-y-4">
                <div className="w-12 h-12 rounded-2xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-500 flex items-center justify-center">
                  <TrendingUp className="w-6 h-6" />
                </div>
                <h3 className="text-2xl font-bold text-slate-900 dark:text-white">Horizon Fluid ARM</h3>
                <p className="text-sm text-slate-600 dark:text-slate-400 leading-relaxed">
                  Optimize introductory liquidity. Secure heavily reduced initial principal costs over 5, 7, or 10-year static base periods. Subsequent bi-annual adjustments operate strictly within continuous structured multi-point caps.
                </p>
                <ul className="space-y-2 pt-2 text-xs text-slate-500 dark:text-slate-400">
                  <li className="flex items-center gap-2">
                    <div className="w-1.5 h-1.5 rounded-full bg-cyan-500"></div>
                    <span>Initial term pricing advantages perfectly suited for medium-term holding</span>
                  </li>
                  <li className="flex items-center gap-2">
                    <div className="w-1.5 h-1.5 rounded-full bg-cyan-500"></div>
                    <span>Protected natively by rigorous lifetime indexing threshold parameters</span>
                  </li>
                </ul>
              </div>

              <div className="pt-8 relative z-10 flex flex-wrap items-center justify-between gap-4 border-t border-slate-100 dark:border-slate-800/60 mt-6">
                <div>
                  <div className="text-[10px] text-slate-400 uppercase tracking-wider">Intro Rate Base (5/6 ARM)</div>
                  <div className="text-2xl font-black text-slate-900 dark:text-white">5.125% <span className="text-xs font-normal text-slate-500">(5.938% APR)</span></div>
                </div>
                <a 
                  href="/mortgage-rates" 
                  className="text-xs font-bold text-cyan-600 dark:text-cyan-400 flex items-center gap-1 hover:underline"
                >
                  <span>Audit Disclosures</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </a>
              </div>
            </div>

          </div>
        </div>
      </section>

      {/* Specialized Incentive & Accelerator Programs Section */}
      <section id="programs" className="px-6 mb-24">
        <div className="max-w-7xl mx-auto">
          <div className="text-center max-w-2xl mx-auto mb-12">
            <span className="text-xs font-bold uppercase tracking-widest text-cyan-600 dark:text-cyan-400">Tailored Portfolio Additions</span>
            <h2 className="text-2xl md:text-4xl font-bold tracking-tight text-slate-900 dark:text-white mt-2 mb-3">
              Specialized Homeownership Initiatives
            </h2>
            <p className="text-slate-600 dark:text-slate-400 text-sm">
              Leverage exclusive membership credit layers, matching savings frameworks, and amortization tuning engines to maximize leverage.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            {programs.map((prog, idx) => {
              const Icon = prog.icon;
              return (
                <div 
                  key={idx} 
                  className="bg-white dark:bg-slate-900/40 p-8 rounded-2xl border border-slate-200 dark:border-slate-800/60 shadow-lg hover:border-cyan-500/40 transition-all duration-300 flex flex-col justify-between space-y-6"
                >
                  <div className="space-y-4">
                    <div className="flex justify-between items-start gap-4">
                      <div className={`px-3 py-1 rounded-full text-xs font-bold border ${prog.badgeBg}`}>
                        {prog.tag}
                      </div>
                      <div className="w-10 h-10 rounded-xl flex items-center justify-center border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white">
                        <Icon className="w-5 h-5" style={{ color: prog.accentColor }} />
                      </div>
                    </div>

                    <div>
                      <h3 className="text-xl font-bold text-slate-900 dark:text-white">{prog.name}</h3>
                      <div className="text-xs font-semibold mt-1" style={{ color: prog.accentColor }}>{prog.subtitle}</div>
                    </div>

                    <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
                      {prog.desc}
                    </p>

                    <div className="space-y-2 pt-2 border-t border-slate-100 dark:border-slate-800/50">
                      {prog.benefits.map((b, bi) => (
                        <div key={bi} className="flex items-start gap-2 text-xs text-slate-500 dark:text-slate-400">
                          <Check className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" style={{ color: prog.accentColor }} />
                          <span>{b}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="pt-4 flex flex-wrap gap-3 items-center justify-between">
                    <AnalyticsButton
                      analyticsId="mortgages_view_connect_program_context"
                      onClick={() => setApplyingProgram(prog)}
                      className="px-5 py-2.5 rounded-xl bg-slate-900 hover:bg-slate-800 dark:bg-white dark:hover:bg-slate-100 text-white dark:text-slate-900 font-bold text-xs transition-colors"
                    >
                      Connect Program Context
                    </AnalyticsButton>
                    
                    {activeBot !== undefined && setActiveBot && (
                      <AnalyticsButton
                        analyticsId="mortgages_view_ask_advisor" 
                        onClick={() => {
                          setActiveBot(prog.botName);
                          setTimeout(() => setActiveBot(null), 4000);
                        }}
                        className="text-xs text-slate-400 hover:text-slate-900 dark:hover:text-white font-medium transition-colors"
                      >
                        Ask Advisor
                      </AnalyticsButton>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* Informative Expectations & Servicing Blueprint */}
      <section className="px-6 mb-20">
        <div className="max-w-7xl mx-auto border-y border-slate-200 dark:border-slate-800/80 py-16">
          <div className="text-center max-w-lg mx-auto mb-12">
            <h3 className="text-lg font-bold text-slate-900 dark:text-white">The {bankName} Servicing Standard</h3>
            <p className="text-xs text-slate-500 mt-1">Committed to uncompromised core support consistency.</p>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-6 text-center">
            <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-950/50 border border-slate-100 dark:border-slate-800/40">
              <div className="font-bold text-slate-900 dark:text-white text-sm">Local Decisioning</div>
              <div className="text-[11px] text-slate-500 mt-1">Regional context integration review</div>
            </div>
            <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-950/50 border border-slate-100 dark:border-slate-800/40">
              <div className="font-bold text-slate-900 dark:text-white text-sm">In-House Servicing</div>
              <div className="text-[11px] text-slate-500 mt-1">Continuous billing continuity</div>
            </div>
            <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-950/50 border border-slate-100 dark:border-slate-800/40">
              <div className="font-bold text-slate-900 dark:text-white text-sm">Guaranteed Pre-Approvals</div>
              <div className="text-[11px] text-slate-500 mt-1">Formal underwriting assurance</div>
            </div>
            <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-950/50 border border-slate-100 dark:border-slate-800/40">
              <div className="font-bold text-slate-900 dark:text-white text-sm">Zero Refi Penalties</div>
              <div className="text-[11px] text-slate-500 mt-1">Unfettered long-term prepayment leverage</div>
            </div>
          </div>
        </div>
      </section>

      {/* Program Context Hook Activation Simulation Modal */}
      {applyingProgram && (
        <div className="fixed inset-0 z-[200] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 animate-fade-in">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl max-w-lg w-full overflow-hidden shadow-2xl">
            
            {/* Top Header */}
            <div className="p-6 border-b border-slate-200 dark:border-slate-800 flex justify-between items-center bg-slate-50 dark:bg-slate-950/50">
              <div>
                <div className="text-xs font-semibold uppercase tracking-wider" style={{ color: applyingProgram.accentColor }}>
                  Initiative Intake Provisioning
                </div>
                <h3 className="text-xl font-bold text-slate-900 dark:text-white mt-0.5">{applyingProgram.name}</h3>
              </div>
              <AnalyticsButton
                analyticsId="mortgages_view_03" 
                onClick={() => setApplyingProgram(null)}
                className="p-2 rounded-full hover:bg-slate-200 dark:hover:bg-slate-800 text-slate-500 transition-colors"
              >
                <X className="w-5 h-5" />
              </AnalyticsButton>
            </div>

            {/* Body block */}
            <div className="p-6 space-y-6">
              {submissionSuccess ? (
                <div className="text-center py-8 space-y-4">
                  <div className="w-16 h-16 rounded-full bg-cyan-500/10 text-cyan-500 flex items-center justify-center mx-auto">
                    <CheckCircle2 className="w-10 h-10 animate-bounce" />
                  </div>
                  <h4 className="text-xl font-bold text-slate-900 dark:text-white">Program Context Connected!</h4>
                  <p className="text-sm text-slate-600 dark:text-slate-400 max-w-sm mx-auto">
                    Your specialized intake trigger is prepared. Our dedicated real estate underwriting advisors will dispatch immediate structural pre-qualification workflows to your dashboard line.
                  </p>
                </div>
              ) : (
                <form onSubmit={handleApplySubmit} className="space-y-6">
                  <div>
                    <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
                      Verify Primary Member Context Line
                    </label>
                    <div className="grid grid-cols-2 gap-3">
                      <AnalyticsButton
                        analyticsId="mortgages_view_existing_member_line"
                        type="button"
                        onClick={() => setMemberType('current')}
                        className={`p-3 rounded-xl border text-center text-sm font-bold transition-all ${
                          memberType === 'current'
                            ? 'bg-cyan-500/10 border-cyan-500 text-cyan-600 dark:text-cyan-400'
                            : 'border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-400 hover:border-slate-300'
                        }`}
                      >
                        Existing Member Line
                      </AnalyticsButton>
                      <AnalyticsButton
                        analyticsId="mortgages_view_new_prospective_line"
                        type="button"
                        onClick={() => setMemberType('new')}
                        className={`p-3 rounded-xl border text-center text-sm font-bold transition-all ${
                          memberType === 'new'
                            ? 'bg-cyan-500/10 border-cyan-500 text-cyan-600 dark:text-cyan-400'
                            : 'border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-400 hover:border-slate-300'
                        }`}
                      >
                        New Prospective Line
                      </AnalyticsButton>
                    </div>
                  </div>

                  <div className="bg-slate-50 dark:bg-slate-950/60 rounded-xl p-4 border border-slate-200 dark:border-slate-800/60 text-xs space-y-2 text-slate-600 dark:text-slate-400 leading-relaxed">
                    <div className="font-semibold text-slate-900 dark:text-slate-300">Underwriting Disclosure:</div>
                    <p>
                      Integrating specialized programmatic triggers links your core cloud authorization record with active multi-state conforming compliance filters. Appraisal reservation mandates are generated dynamically.
                    </p>
                  </div>

                  <div className="space-y-3 pt-2">
                    <AnalyticsButton
                      analyticsId="mortgages_view_06"
                      type="submit"
                      disabled={isSubmitting}
                      className="w-full py-4 rounded-xl text-slate-950 font-bold text-sm shadow-lg hover:scale-[1.02] transition-all duration-300 flex items-center justify-center space-x-2 disabled:opacity-50 disabled:pointer-events-none"
                      style={{ backgroundImage: `linear-gradient(to right, ${brandColorFrom}, ${brandColorTo})` }}
                    >
                      {isSubmitting ? (
                        <>
                          <RefreshCw className="w-4 h-4 animate-spin" />
                          <span>Validating Identity Records...</span>
                        </>
                      ) : (
                        <>
                          <span>Initialize Initiative Provisioning</span>
                          <ArrowRight className="w-4 h-4" />
                        </>
                      )}
                    </AnalyticsButton>
                    
                    <p className="text-[11px] text-center text-slate-500">
                      All extensions of home loan financing remain strictly subject to standard title and appraisal validation policies.
                    </p>
                  </div>
                </form>
              )}
            </div>

          </div>
        </div>
      )}

    </div>
  );
}

export default MortgagesView;
