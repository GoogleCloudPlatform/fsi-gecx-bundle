import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
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
  Globe
} from 'lucide-react';
import { useSettings } from '../context/SettingsContext.jsx';

function CreditCardsView({ activeBot, setActiveBot }) {
  const navigate = useNavigate();
  const { 
    bankName, 
    brandColorFrom, 
    brandColorTo
  } = useSettings();

  const [selectedCardIndex, setSelectedCardIndex] = useState(0);

  const cards = [
    {
      name: "Aura Elite Reserve",
      tag: "Premium Travel & Lifestyle",
      bonus: "75,000 Bonus Points",
      bonusDesc: "After spending $4,000 in the first 3 months",
      earnRate: "3x Points on Travel & Dining",
      introApr: "N/A",
      regApr: "18.99% - 24.99% Variable",
      annualFee: "$0",
      balanceTransferFee: "3%",
      foreignTxFee: "None",
      bestFor: "Frequent travelers seeking uncompromised luxury",
      cardStyle: "from-slate-900 via-slate-800 to-slate-950 border-amber-500/30 text-amber-400",
      chipStyle: "bg-amber-400/20 border-amber-500/40 text-amber-300",
      accentColor: "#f59e0b",
      badgeBg: "bg-amber-500/10 border-amber-500/20 text-amber-500 dark:text-amber-400",
      botName: "Travel Rewards Bot",
      features: [
        "Complimentary global airport lounge access",
        "Annual $200 travel statement credit",
        "Primary rental car collision damage waiver",
        "24/7 elite white-glove concierge service"
      ]
    },
    {
      name: "Velocity Cash Preferred",
      tag: "Maximum Cash Back",
      bonus: "$200 Cash Bonus",
      bonusDesc: "After spending $1,000 in the first 90 days",
      earnRate: "2% Unlimited Flat Cash Back",
      introApr: "0% Intro APR for 12 Months",
      regApr: "16.24% - 22.24% Variable",
      annualFee: "$0",
      balanceTransferFee: "$0 Intro Fee",
      foreignTxFee: "1%",
      bestFor: "Everyday spending with effortless statement credits",
      cardStyle: "from-emerald-900 via-teal-900 to-cyan-950 border-emerald-500/30 text-emerald-400",
      chipStyle: "bg-emerald-400/20 border-emerald-500/40 text-emerald-300",
      accentColor: "#10b981",
      badgeBg: "bg-emerald-500/10 border-emerald-500/20 text-emerald-600 dark:text-emerald-400",
      botName: "Cash Back Advisor",
      features: [
        "No rotating categories or earning caps",
        "Instant redemption directly to your checking account",
        "Purchase protection up to $1,000 per claim",
        "Extended warranty coverage on eligible items"
      ]
    },
    {
      name: "Equinox Horizon",
      tag: "Low APR & Balance Transfers",
      bonus: "0% Intro APR",
      bonusDesc: "For 18 months on balance transfers and purchases",
      earnRate: "1x Points on all purchases",
      introApr: "0% Intro APR for 18 Months",
      regApr: "13.99% - 19.99% Variable",
      annualFee: "$0",
      balanceTransferFee: "$0 Intro Fee for 60 days",
      foreignTxFee: "2%",
      bestFor: "Consolidating existing balances and financing large purchases",
      cardStyle: "from-sky-900 via-blue-950 to-slate-900 border-sky-500/30 text-sky-400",
      chipStyle: "bg-sky-400/20 border-sky-500/40 text-sky-300",
      accentColor: "#0ea5e9",
      badgeBg: "bg-sky-500/10 border-sky-500/20 text-sky-600 dark:text-sky-400",
      botName: "Balance Transfer Agent",
      features: [
        "Save on interest with our industry-leading low intro rate",
        "Customizable payment due dates to fit your schedule",
        "Free access to your live updated FICO® Score",
        "Zero liability on unauthorized transactions"
      ]
    },
    {
      name: "Vanguard Builder",
      tag: "Secured Rebuilding",
      bonus: "Instant Decision",
      bonusDesc: "No minimum credit score required to apply",
      earnRate: "1% Cash Back on Gas & Groceries",
      introApr: "N/A",
      regApr: "20.49% Variable",
      annualFee: "$0",
      balanceTransferFee: "N/A",
      foreignTxFee: "3%",
      bestFor: "Establishing or rebuilding a solid credit history safely",
      cardStyle: "from-indigo-950 via-slate-900 to-indigo-900 border-indigo-500/30 text-indigo-400",
      chipStyle: "bg-indigo-400/20 border-indigo-500/40 text-indigo-300",
      accentColor: "#6366f1",
      badgeBg: "bg-indigo-500/10 border-indigo-500/20 text-indigo-600 dark:text-indigo-400",
      botName: "Credit Support Bot",
      features: [
        "Credit limit matches your fully refundable security deposit",
        "Automatic reporting to Equifax, Experian, and TransUnion",
        "Path to unsecured upgrade review in as little as 6 months",
        "Complimentary financial literacy tools and personalized insights"
      ]
    }
  ];

  const selectedCard = cards[selectedCardIndex];

  return (
    <div className="pb-24">
      {/* Hero Section */}
      <section className="relative pt-32 pb-20 md:pt-44 md:pb-28 px-6 overflow-hidden">
        <div className="absolute inset-0 -z-10 overflow-hidden">
          <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[800px] h-[300px] bg-emerald-500/10 rounded-full blur-3xl"></div>
          <div className="absolute bottom-0 left-0 right-0 h-32 bg-gradient-to-t from-slate-50 dark:from-slate-950 to-transparent"></div>
        </div>

        <div className="max-w-7xl mx-auto text-center">
          <div className="inline-flex items-center space-x-2 px-4 py-2 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-600 dark:text-emerald-400 text-xs font-semibold tracking-wide mb-6">
            <Sparkles className="w-3.5 h-3.5" />
            <span>Next-Generation Credit Portfolio</span>
          </div>

          <h1 className="text-4xl md:text-6xl lg:text-7xl font-extrabold tracking-tight leading-tight max-w-4xl mx-auto mb-6">
            Purchasing power that rewards <br />
            <span className="bg-gradient-to-r from-emerald-400 via-teal-300 to-cyan-400 bg-clip-text text-transparent">
              your everyday ambition.
            </span>
          </h1>

          <p className="text-lg text-slate-600 dark:text-slate-400 max-w-2xl mx-auto leading-relaxed mb-10">
            Whether you're traveling the globe, maximizing cash back, or establishing your credit history, {bankName} offers a tailored credit card with zero annual fees.
          </p>
        </div>
      </section>

      {/* Interactive Card Showcase & Selector */}
      <section className="px-6 mb-24">
        <div className="max-w-7xl mx-auto">
          {/* Card Tabs */}
          <div className="flex flex-wrap justify-center gap-3 mb-12">
            {cards.map((card, idx) => {
              const isSelected = idx === selectedCardIndex;
              return (
                <button
                  key={idx}
                  onClick={() => setSelectedCardIndex(idx)}
                  className={`px-5 py-3 rounded-xl font-semibold text-sm transition-all duration-300 flex items-center space-x-2 border ${
                    isSelected 
                      ? 'bg-slate-900 dark:bg-white text-white dark:text-slate-900 border-transparent shadow-lg scale-105' 
                      : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-400 border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700'
                  }`}
                >
                  <CreditCard className={`w-4 h-4 ${isSelected ? 'text-emerald-400 dark:text-emerald-600' : ''}`} />
                  <span>{card.name.split(' ')[0]}</span>
                  <span className="text-xs opacity-70 hidden sm:inline">({card.tag.split(' ')[0]})</span>
                </button>
              );
            })}
          </div>

          {/* Active Card Detail Panel */}
          <div className="card-slate-900 grid grid-cols-1 lg:grid-cols-12 gap-12 items-center shadow-2xl border border-slate-200 dark:border-slate-800/80 rounded-3xl p-8 md:p-12" style={{ backgroundColor: 'var(--card-bg-color, #0f172a)' }}>
            
            {/* Left side: CSS Rendered Realistic Card Graphic */}
            <div className="lg:col-span-5 flex justify-center">
              <div className="relative w-full max-w-[420px] aspect-[1.58] rounded-2xl p-6 shadow-2xl flex flex-col justify-between overflow-hidden transition-all duration-500 hover:scale-105 hover:rotate-1 border border-white/10 bg-gradient-to-tr text-white group" style={{ backgroundImage: 'linear-gradient(to top right, #0f172a, #1e293b)' }}>
                {/* Glossy overlay */}
                <div className="absolute inset-0 bg-gradient-to-tr from-white/5 to-transparent opacity-50 pointer-events-none"></div>
                
                {/* Background glow based on active card */}
                <div className="absolute -right-20 -bottom-20 w-60 h-60 rounded-full blur-3xl opacity-30 transition-all duration-500 group-hover:opacity-50" style={{ backgroundColor: selectedCard.accentColor }}></div>

                {/* Top Row: Bank Name & Contactless icon */}
                <div className="flex justify-between items-center relative z-10">
                  <span className="font-bold tracking-wider text-sm opacity-90">{bankName}</span>
                  <div className="flex items-center space-x-1 opacity-80">
                    <Wifi className="w-4 h-4 rotate-90" />
                  </div>
                </div>

                {/* Middle Row: Smart Chip & Card Title */}
                <div className="relative z-10 my-auto space-y-3">
                  <div className={`w-11 h-9 rounded-md flex items-center justify-center border ${selectedCard.chipStyle}`}>
                    <div className="w-6 h-4 border-y border-current opacity-40"></div>
                  </div>
                  <div>
                    <div className="text-xs uppercase tracking-widest opacity-60 font-medium">Synthetic Portfolio</div>
                    <div className="text-xl md:text-2xl font-black tracking-tight mt-0.5 text-transparent bg-clip-text bg-gradient-to-r from-white to-slate-200">
                      {selectedCard.name}
                    </div>
                  </div>
                </div>

                {/* Bottom Row: Cardholder Placeholder & Hologram */}
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
            </div>

            {/* Right side: Deep Feature Breakdown */}
            <div className="lg:col-span-7 space-y-6">
              <div className="flex flex-wrap items-center gap-3">
                <span className={`px-3 py-1 rounded-full text-xs font-bold border ${selectedCard.badgeBg}`}>
                  {selectedCard.tag}
                </span>
                <span className="text-xs text-slate-500 flex items-center gap-1">
                  <Star className="w-3.5 h-3.5 fill-amber-400 text-amber-400" />
                  4.9/5 Member Rating
                </span>
              </div>

              <div className="border-b border-slate-200 dark:border-slate-800 pb-6">
                <div className="text-xs font-semibold text-emerald-500 uppercase tracking-wider">Introductory Offer</div>
                <div className="text-3xl md:text-4xl font-black text-slate-900 dark:text-white mt-1">
                  {selectedCard.bonus}
                </div>
                <p className="text-sm text-slate-600 dark:text-slate-400 mt-1">
                  {selectedCard.bonusDesc}
                </p>
              </div>

              {/* Quick Stat Badges */}
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
                <div className="bg-slate-50 dark:bg-slate-950/50 rounded-xl p-3 border border-slate-200 dark:border-slate-800/60">
                  <div className="text-[11px] text-slate-500">Rewards Rate</div>
                  <div className="text-sm font-bold text-slate-900 dark:text-white mt-0.5 truncate">{selectedCard.earnRate.split(' ')[0]}</div>
                </div>
                <div className="bg-slate-50 dark:bg-slate-950/50 rounded-xl p-3 border border-slate-200 dark:border-slate-800/60">
                  <div className="text-[11px] text-slate-500">Annual Fee</div>
                  <div className="text-sm font-bold text-emerald-500 mt-0.5">{selectedCard.annualFee}</div>
                </div>
                <div className="bg-slate-50 dark:bg-slate-950/50 rounded-xl p-3 border border-slate-200 dark:border-slate-800/60 col-span-2 sm:col-span-1">
                  <div className="text-[11px] text-slate-500">Regular APR</div>
                  <div className="text-xs font-bold text-slate-900 dark:text-white mt-0.5">{selectedCard.regApr.split(' ')[0]}</div>
                </div>
              </div>

              {/* Features Checklist */}
              <div className="space-y-2.5 pt-2">
                <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Key Advantages</div>
                {selectedCard.features.map((feat, idx) => (
                  <div key={idx} className="flex items-start space-x-3">
                    <div className="mt-0.5 w-4 h-4 rounded-full bg-emerald-500/10 flex items-center justify-center text-emerald-500 flex-shrink-0">
                      <Check className="w-2.5 h-2.5" />
                    </div>
                    <span className="text-sm text-slate-600 dark:text-slate-300">{feat}</span>
                  </div>
                ))}
              </div>

              {/* Action Buttons */}
              <div className="pt-4 flex flex-col sm:flex-row gap-4 items-center">
                <button
                  onClick={() => {
                    const cardSlug = selectedCard.name.toLowerCase().replace(/ /g, '-');
                    navigate(`/apply/credit-card?card=${cardSlug}`);
                  }}
                  className="w-full sm:w-auto px-8 py-3.5 rounded-full text-slate-950 font-bold text-sm shadow-lg hover:scale-105 transition-all duration-300 flex items-center justify-center space-x-2"
                  style={{ backgroundImage: `linear-gradient(to right, ${brandColorFrom}, ${brandColorTo})`, boxShadow: `0 10px 15px -3px ${brandColorFrom}33` }}
                >
                  <span>Apply Now</span>
                  <ArrowRight className="w-4 h-4" />
                </button>
                
                {activeBot !== undefined && setActiveBot && (
                  <button 
                    onClick={() => {
                      setActiveBot(selectedCard.botName);
                      setTimeout(() => setActiveBot(null), 4000);
                    }}
                    className="w-full sm:w-auto px-6 py-3.5 rounded-full bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 text-sm font-semibold transition-colors flex items-center justify-center space-x-2"
                  >
                    <span>Ask {selectedCard.botName.split(' ')[0]} Advisor</span>
                  </button>
                )}
              </div>
            </div>

          </div>
        </div>
      </section>

      {/* Comprehensive Comparison Table */}
      <section className="px-6 mb-24">
        <div className="max-w-7xl mx-auto">
          <div className="text-center max-w-2xl mx-auto mb-12">
            <h2 className="text-2xl md:text-4xl font-bold tracking-tight text-slate-900 dark:text-white mb-3">
              Compare Portfolio Options side-by-side
            </h2>
            <p className="text-slate-600 dark:text-slate-400 text-sm">
              Review interest rates, introductory timelines, and specific value triggers to find the perfect match.
            </p>
          </div>

          <div className="overflow-x-auto border border-slate-200 dark:border-slate-800/80 rounded-2xl bg-white dark:bg-slate-900 shadow-xl">
            <table className="w-full text-left border-collapse min-w-[800px]">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/50">
                  <th className="p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider">Card Product</th>
                  <th className="p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider">Welcome Bonus</th>
                  <th className="p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider">Earning Tier</th>
                  <th className="p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider">Intro APR</th>
                  <th className="p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider">Regular APR</th>
                  <th className="p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider text-center">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-800/60 text-sm">
                {cards.map((card, idx) => (
                  <tr key={idx} className="hover:bg-slate-50/80 dark:hover:bg-slate-800/30 transition-colors">
                    <td className="p-5">
                      <div className="font-bold text-slate-900 dark:text-white">{card.name}</div>
                      <div className="text-xs text-slate-500 mt-0.5">{card.bestFor}</div>
                    </td>
                    <td className="p-5">
                      <div className="font-bold text-emerald-600 dark:text-emerald-400">{card.bonus}</div>
                      <div className="text-[11px] text-slate-500 mt-0.5">{card.bonusDesc.replace('After spending', 'Spend')}</div>
                    </td>
                    <td className="p-5 font-medium text-slate-700 dark:text-slate-300">
                      {card.earnRate}
                    </td>
                    <td className="p-5 text-slate-600 dark:text-slate-400">
                      {card.introApr}
                    </td>
                    <td className="p-5 text-slate-600 dark:text-slate-400 font-mono text-xs">
                      {card.regApr}
                    </td>
                    <td className="p-5 text-center">
                      <button
                        onClick={() => {
                          const cardSlug = card.name.toLowerCase().replace(/ /g, '-');
                          navigate(`/apply/credit-card?card=${cardSlug}`);
                        }}
                        className="px-4 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 dark:bg-white dark:hover:bg-slate-100 text-white dark:text-slate-900 font-bold text-xs transition-colors"
                      >
                        Apply
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* Cardholder Standard Benefits Grid */}
      <section className="px-6 mb-20">
        <div className="max-w-7xl mx-auto">
          <div className="border-y border-slate-200 dark:border-slate-800/80 py-16 grid grid-cols-1 md:grid-cols-4 gap-8">
            <div className="space-y-3">
              <div className="w-10 h-10 rounded-lg bg-emerald-500/10 flex items-center justify-center text-emerald-500">
                <Lock className="w-5 h-5" />
              </div>
              <h3 className="text-base font-semibold text-slate-900 dark:text-white">Zero Fraud Liability</h3>
              <p className="text-xs text-slate-500 leading-relaxed">
                You are fully protected against unauthorized transactions if your card is ever lost, stolen, or fraudulently compromised.
              </p>
            </div>

            <div className="space-y-3">
              <div className="w-10 h-10 rounded-lg bg-teal-500/10 flex items-center justify-center text-teal-500">
                <Smartphone className="w-5 h-5" />
              </div>
              <h3 className="text-base font-semibold text-slate-900 dark:text-white">Instant Wallet Issuance</h3>
              <p className="text-xs text-slate-500 leading-relaxed">
                Upon approval, add your virtual card numbers directly to Apple Pay® or Google Wallet™ to start spending instantly.
              </p>
            </div>

            <div className="space-y-3">
              <div className="w-10 h-10 rounded-lg bg-cyan-500/10 flex items-center justify-center text-cyan-500">
                <Globe className="w-5 h-5" />
              </div>
              <h3 className="text-base font-semibold text-slate-900 dark:text-white">Global ATM Support</h3>
              <p className="text-xs text-slate-500 leading-relaxed">
                Access cash safely at over 30,000 fee-free network ATMs globally with active continuous monitoring.
              </p>
            </div>

            <div className="space-y-3">
              <div className="w-10 h-10 rounded-lg bg-indigo-500/10 flex items-center justify-center text-indigo-500">
                <Shield className="w-5 h-5" />
              </div>
              <h3 className="text-base font-semibold text-slate-900 dark:text-white">NCUA Insured Confidence</h3>
              <p className="text-xs text-slate-500 leading-relaxed">
                Partnering with top national safeguards, your core financial foundation operates within fully compliant regulatory boundaries.
              </p>
            </div>
          </div>
        </div>
      </section>



    </div>
  );
}

// Custom simple Wifi icon component for the chip/contactless emblem if missing or clean styling needed
function Wifi({ className }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 12.55a11 11 0 0 1 14.08 0" />
      <path d="M1.42 9a16 16 0 0 1 21.16 0" />
      <path d="M8.53 16.11a6 6 0 0 1 6.95 0" />
      <line x1="12" y1="20" x2="12.01" y2="20" />
    </svg>
  );
}

export default CreditCardsView;
