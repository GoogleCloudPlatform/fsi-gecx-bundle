import React, { useState, useEffect, useMemo } from 'react';
import { 
  Search, 
  BookOpen, 
  Clock, 
  ArrowRight, 
  X, 
  Shield, 
  Car, 
  TrendingUp, 
  ChevronRight, 
  Lightbulb, 
  Sparkles, 
  Filter, 
  FileText,
  HelpCircle,
  Compass
} from 'lucide-react';
import { useLocation } from 'react-router-dom';

import { HELP_CATEGORIES } from '../utils/constants.js';
import AnalyticsButton from './AnalyticsButton.jsx';


const articles = [
  {
    id: 1,
    title: "Navigating the Competitive Real Estate Landscape in 2026",
    category: "Home Financing",
    readTime: "5 min read",
    badgeBg: "bg-cyan-500/10 border-cyan-500/20 text-cyan-600 dark:text-cyan-400",
    excerpt: "Explore modern alternative appraisal clauses, escalated bridge funding strategies, and pre-underwritten guaranteed tranches to secure your bid.",
    body: `Securing a property line in highly accelerated regional markets demands entering negotiations equipped with uncompromised financial readiness. Legacy conditional pre-qualification documentation no longer holds standard weight against sophisticated competing cash buyers.
    
    By initializing our formal digital underwriting lock tranches prior to drafting initial purchase agreements, prospective homeowners gain immediate priority positioning. Furthermore, bridging appraisal shortfalls securely using dynamic supplemental matching options provides the absolute structural certainty listing agents require. Combine these workflows seamlessly with our multi-year locked fixed tranches to insulate long-term household budgets from unforeseen interest velocity.`
  },
  {
    id: 2,
    title: "Unlocking the Complete Potential of Your Home Equity",
    category: "Home Financing",
    readTime: "4 min read",
    badgeBg: "bg-cyan-500/10 border-cyan-500/20 text-cyan-600 dark:text-cyan-400",
    excerpt: "Understand the distinct mathematical advantages of fixed-rate home equity loans versus dynamic credit lines for major structural additions.",
    body: `Translating accrued real estate valuation appreciation into accessible primary liquidity offers an incredibly cost-effective avenue for funding capital-intensive endeavors. Deciding between fixed closed-end structures and flexible continuous draw parameters depends primarily on immediate cash deployment timing.
    
    Fixed structural loans establish absolute upfront continuity, making them mathematically perfect for major contracted remodeling scopes where total costs are capped immediately. Conversely, variable credit lines operate flawlessly as emergency secondary safety buffers, accruing interest charges strictly against actively distributed par balances.`
  },
  {
    id: 3,
    title: "Mastering the 50/30/20 Dynamic Budgeting Framework",
    category: "Wealth & Budgeting",
    readTime: "6 min read",
    badgeBg: "bg-emerald-500/10 border-emerald-500/20 text-emerald-600 dark:text-emerald-400",
    excerpt: "A granular blueprint for automating primary share allocations, aggressive liquid reserve scaling, and uncompromised lifestyle spending.",
    body: `Achieving long-term financial sovereignty requires separating raw emotional income triggers from automated allocation targets. The multi-tiered 50/30/20 framework maps structural survival baseline needs to exactly 50% of total net realized payroll inflows.
    
    Secondary unconstrained discretionary lifestyle choices scale securely inside a protected 30% holding band. Crucially, the final 20% payload must execute immediately upon check arrival via automated splitting metadata, distributing direct capital flows straight into high-yield dividend-bearing digital deposit tranches to secure accelerated compounding tranches.`
  },
  {
    id: 4,
    title: "Anatomy of a High-Yield Digital Certificate Strategy",
    category: "Wealth & Budgeting",
    readTime: "7 min read",
    badgeBg: "bg-emerald-500/10 border-emerald-500/20 text-emerald-600 dark:text-emerald-400",
    excerpt: "Build a robust fixed-income laddering structure using staggered maturity intervals to guarantee continuous liquidity check access.",
    body: `Mitigating standard market yield erosion while avoiding absolute capital access restrictions is achieved optimally through algorithmic duration laddering. Committing the entirety of core reserves to a single static multi-year block exposes the portfolio to severe reinvestment mismatch risk if broader market indices escalate.
    
    Executing a staggered quarterly or semi-annual maturity mapping sequence ensures continuous rolling access to highly competitive locked dividend tranches. As each individual step matures, principal payloads can be redirected instantly into elevated peak term rates or liquidated seamlessly to support sudden primary life milestones.`
  },
  {
    id: 5,
    title: "Next-Generation Phishing & Identity Intrusion Vectors",
    category: "Digital Security",
    readTime: "4 min read",
    badgeBg: "bg-rose-500/10 border-rose-500/20 text-rose-600 dark:text-rose-400",
    excerpt: "Identify highly sophisticated AI-voice simulation attempts, malicious credential portals, and secure hardware key enforcement techniques.",
    body: `Modern digital bad actors deploy advanced continuous synthetic voice and conversational modeling architectures to simulate highly convincing authorized service checks. A fundamental internal operational mandate to remember: our core cloud routing staff will never demand outbound provisioning verification text readbacks or raw secondary factor token pins over untracked lines.
    
    Securing personal access tokens mandates integrating native device biometrics and passkey cryptographic protocols. Enabling native real-time push alert frameworks ensures immediate visibility across all regional web portal authorization check points.`
  },
  {
    id: 6,
    title: "Securing Your Digital Footprint Across Public Wireless Nodes",
    category: "Digital Security",
    readTime: "3 min read",
    badgeBg: "bg-rose-500/10 border-rose-500/20 text-rose-600 dark:text-rose-400",
    excerpt: "Essential core transport layer precautions for mobile banking consumers interacting with open unencrypted regional hotspots.",
    body: `Interacting with dynamic cloud banking infrastructure over untrusted regional municipal wifi nodes introduces significant interception layer vulnerabilities. While mobile native apps utilize end-to-end encrypted communication payloads, underlying transport layers remain exposed to malicious local routing redirects.
    
    Maintaining uncompromised privacy requires utilizing authenticated virtual private tunneling structures and restricting critical outbound fund transfers to secured private network connections. Always audit web context session integrity indicators before initializing financial execution checks.`
  },
  {
    id: 7,
    title: "Electric & Hybrid Vehicle Financing: The 2026 Horizon Blueprint",
    category: "Vehicle Purchasing",
    readTime: "5 min read",
    badgeBg: "bg-amber-500/10 border-amber-500/20 text-amber-600 dark:text-amber-400",
    excerpt: "Maximize federal instant point-of-sale rebate credits while securing specialized ultra-low rate green mobility lending lines.",
    body: `Acquiring next-generation zero-emission consumer transit hardware unlocks substantial integrated point-of-sale point reduction incentives. Navigating dealership validation channels requires establishing clean title coordination directly with state tax validation authorities.
    
    Our specialized eco-mobility funding configurations provide reduced base APR metrics and extended sequential amortization intervals designed specifically to match unique modern battery component depreciation trajectories. Lock in direct draft access prior to visiting showroom lots to guarantee zero negotiation friction.`
  },
  {
    id: 8,
    title: "Demystifying the Dealership Finance and Insurance (F&I) Office",
    category: "Vehicle Purchasing",
    readTime: "6 min read",
    badgeBg: "bg-amber-500/10 border-amber-500/20 text-amber-600 dark:text-amber-400",
    excerpt: "A tactical negotiation manual to navigate gap coverage add-ons, third-party warranties, and direct credit union draft pre-approvals.",
    body: `The secondary financial origination suite inside commercial vehicle dealerships operates as a highly targeted margin-generation hub. Consumers often experience pressure to absorb inflated third-party maintenance contracts and legacy gap insurance tranches directly into principal balances.
    
    Arriving equipped with a formally executed digital loan draft line provides absolute leverage, decoupling base vehicle price agreements from ancillary financial add-on payloads. Our direct GAP protection options operate at wholesale cost tiers, saving members substantial unnecessary compounding interest debt.`
  },
  {
    id: 9,
    title: "Accelerated Credit Rehabilitation via Secured Cash Builders",
    category: "Credit Mastery",
    readTime: "5 min read",
    badgeBg: "bg-indigo-500/10 border-indigo-500/20 text-indigo-600 dark:text-indigo-400",
    excerpt: "Harness fully refundable par value deposits to programmatically force positive monthly trade-line reporting across major auditing bureaus.",
    body: `Establishing or restoring a positive multi-year consumer borrowing footprint requires establishing systematic continuous positive monthly reporting indicators. Secured cash builder accounts isolate personal risk by mapping physical revolving line availability to matched underlying share deposits.
    
    Operating these tools optimally mandates keeping aggregate monthly statement balances below 10% of total line capacity and ensuring absolute automated due date payments. Consistent structural discipline triggers automatic internal review algorithms, transitioning legacy restricted setups directly into top-tier unsecured signature lines within 6 months.`
  },
  {
    id: 10,
    title: "Understanding the Nuances of FICO® Score 10T Predictive Models",
    category: "Credit Mastery",
    readTime: "8 min read",
    badgeBg: "bg-indigo-500/10 border-indigo-500/20 text-indigo-600 dark:text-indigo-400",
    excerpt: "How trended continuous historical payment metadata impacts algorithmic soft inquiry outcomes and top-tier approval tranches.",
    body: `Advanced risk classification frameworks evaluate dynamic multi-year behavioral trajectories rather than static single-month point-in-time balance statements. Trended data sets track historical principal payment sizing, revolving credit baseline stabilization, and intra-month balance clearance speed across past 24-month horizons.
    
    Consumers who systematically clear complete statement balances achieve highly elevated scoring tranches compared to those carrying persistent rolling interest line items, even if gross utilization ratios remain identical. Master these trend parameters to easily secure premium tier financing lock guarantees.`
  },
  {
    id: 11,
    title: "Seamless Direct Deposit Payroll Relocation Integration",
    category: "Wealth & Budgeting",
    readTime: "3 min read",
    badgeBg: "bg-emerald-500/10 border-emerald-500/20 text-emerald-600 dark:text-emerald-400",
    excerpt: "A 90-second guide to executing automated digital employer checking switches using instant account context metadata.",
    body: `Migrating primary payroll structures away from legacy commercial institutions no longer requires manual corporate human resource paperwork submissions. Utilizing integrated ClickSwitch routing authorization metadata lets depositors securely communicate account updates instantly.
    
    Connecting these automated payroll deposits directly to your core deposit profile unlocks immediate internal tier level upgrades, waiving continuous maintenance charges and qualifying accounts for exclusive long-term consumer lending rate discounts.`
  },
  {
    id: 12,
    title: "Maximizing Cardholder Reward Point Conversion Formulas",
    category: "Wealth & Budgeting",
    readTime: "4 min read",
    badgeBg: "bg-emerald-500/10 border-emerald-500/20 text-emerald-600 dark:text-emerald-400",
    excerpt: "Strategic deployment of dynamic spending multiplier categories to yield uncompromised long-term travel and statement redemption value.",
    body: `Optimizing transactional reward structures demands aligning continuous consumer operational outlays with targeted dynamic multiplier triggers. Utilizing standalone flat-rate cash cards for generic everyday check out needs while reserving specialized elevated point structures for dedicated travel and culinary bookings yields maximum compound redemption efficiency.
    
    Consolidating core banking structures inside unified membership suites frequently activates compounding bonus multipliers, accelerating point accumulation timelines and granting cardholders complimentary white-glove concierge privileges.`
  }
];

function HelpCenterView({ activeBot, setActiveBot }) {
  const location = useLocation();

  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('All');
  const [viewingArticle, setViewingArticle] = useState(null);

  useEffect(() => {
    if (location.state?.category) {
      setSelectedCategory(location.state.category);
    }
  }, [location.state?.category]);

  const categories = HELP_CATEGORIES;

  const filteredArticles = useMemo(() => {
    const filtered = articles.filter(art => {
      const matchesCat = selectedCategory === 'All' || art.category === selectedCategory;
      const matchesSearch = searchQuery.trim() === '' || 
        art.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        art.excerpt.toLowerCase().includes(searchQuery.toLowerCase()) ||
        art.body.toLowerCase().includes(searchQuery.toLowerCase());
      return matchesCat && matchesSearch;
    });

    return filtered.sort((a, b) => {
      if (selectedCategory === 'All') {
        const catCompare = a.category.localeCompare(b.category);
        if (catCompare !== 0) return catCompare;
      }
      return a.title.localeCompare(b.title);
    });
  }, [searchQuery, selectedCategory]);

  return (
    <div className="pb-24">
      {/* Hero Search Engine Block */}
      <section className="relative pt-32 pb-16 md:pt-44 md:pb-24 px-6 overflow-hidden">
        <div className="absolute inset-0 -z-10 overflow-hidden">
          <div className="absolute top-1/3 left-1/2 -translate-x-1/2 w-[800px] h-[300px] bg-emerald-500/10 rounded-full blur-3xl"></div>
          <div className="absolute bottom-0 left-0 right-0 h-32 bg-gradient-to-t from-slate-50 dark:from-slate-950 to-transparent"></div>
        </div>

        <div className="max-w-4xl mx-auto text-center">
          <div className="inline-flex items-center space-x-2 px-4 py-2 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-600 dark:text-emerald-400 text-xs font-semibold tracking-wide mb-6">
            <HelpCircle className="w-3.5 h-3.5" />
            <span>Unified Knowledge Index</span>
          </div>

          <h1 className="text-4xl md:text-5xl lg:text-6xl font-extrabold tracking-tight leading-tight mb-6 text-slate-900 dark:text-white">
            How can we help you <br />
            <span className="bg-gradient-to-r from-emerald-400 via-teal-400 to-cyan-400 bg-clip-text text-transparent">
              navigate your goals today?
            </span>
          </h1>

          {/* Large Dynamic Search input */}
          <div className="relative max-w-2xl mx-auto mt-8">
            <div className="absolute inset-y-0 left-0 pl-5 flex items-center pointer-events-none text-slate-400">
              <Search className="w-5 h-5" />
            </div>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search articles, guidelines, routing FAQs, or security tips..."
              className="w-full pl-13 pr-12 py-4 rounded-full bg-white dark:bg-slate-900 border-2 border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white placeholder-slate-400 text-sm font-medium shadow-xl focus:border-emerald-500 dark:focus:border-emerald-500 outline-none transition-all duration-300"
            />
            {searchQuery && (
              <AnalyticsButton analyticsId="help_center_view_01"
                onClick={() => setSearchQuery('')}
                className="absolute inset-y-0 right-0 pr-4 flex items-center text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors"
              >
                <X className="w-4 h-4" />
              </AnalyticsButton>
            )}
          </div>

          {/* Quick search metrics */}
          <div className="mt-4 text-xs text-slate-500 flex items-center justify-center gap-4">
            <span>⚡ Indexed against core library metadata</span>
            <span>•</span>
            <span>🔍 {filteredArticles.length} Articles mapping criteria</span>
          </div>
        </div>
      </section>

      {/* Category Tabs Selector */}
      <section className="px-6 mb-12">
        <div className="max-w-7xl mx-auto">
          <div className="flex flex-wrap items-center justify-center gap-2 border-b border-slate-200 dark:border-slate-800/80 pb-6">
            <div className="text-xs font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1 mr-2">
              <Filter className="w-3.5 h-3.5" />
              <span>Filter:</span>
            </div>
            {categories.map((cat, idx) => {
              const isSelected = selectedCategory === cat;
              return (
                <AnalyticsButton analyticsId="help_center_view_02"
                  key={idx}
                  onClick={() => setSelectedCategory(cat)}
                  className={`px-4 py-2 rounded-xl text-xs font-bold transition-all duration-300 cursor-pointer border ${
                    isSelected
                      ? 'bg-white dark:bg-slate-950 text-slate-900 dark:text-white border-slate-900 dark:border-slate-800 shadow-md scale-105'
                      : 'bg-slate-100 dark:bg-slate-900 border-transparent hover:bg-slate-200 dark:hover:bg-slate-800 text-slate-550 dark:text-slate-400'
                  }`}
                >
                  {cat}
                </AnalyticsButton>
              );
            })}
          </div>
        </div>
      </section>

      {/* Search Results & Grid Traverse Content */}
      <section className="px-6 mb-20">
        <div className="max-w-7xl mx-auto">
          {filteredArticles.length === 0 ? (
            <div className="text-center py-16 bg-slate-50 dark:bg-slate-950/50 rounded-3xl border border-slate-200 dark:border-slate-800/60 max-w-xl mx-auto space-y-4">
              <BookOpen className="w-12 h-12 text-slate-400 mx-auto opacity-50" />
              <h3 className="text-lg font-bold text-slate-900 dark:text-white">No Articles Found</h3>
              <p className="text-xs text-slate-500 max-w-sm mx-auto leading-relaxed">
                We couldn't locate specific documentation targeting "<span className="font-semibold text-slate-700 dark:text-slate-300">{searchQuery}</span>" within this filtered category. Try expanding your search keywords or reset filter metrics.
              </p>
              <AnalyticsButton analyticsId="help_center_view_reset_knowledge_index_filters"
                onClick={() => { setSearchQuery(''); setSelectedCategory('All'); }}
                className="px-4 py-2 rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 font-bold text-xs hover:bg-emerald-500/20 transition-colors"
              >
                Reset Knowledge Index Filters
              </AnalyticsButton>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
              {filteredArticles.map((art) => (
                <div
                  key={art.id}
                  onClick={() => setViewingArticle(art)}
                  className="bg-white dark:bg-slate-900/40 border border-slate-200 dark:border-slate-800/60 rounded-3xl p-8 shadow-sm dark:shadow-none hover:border-emerald-500/40 hover:-translate-y-1 transition-all duration-300 flex flex-col justify-between space-y-4 group cursor-pointer"
                >
                  <div className="space-y-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className={`px-2.5 py-0.5 rounded-full text-[11px] font-bold border ${art.badgeBg}`}>
                        {art.category}
                      </span>
                      <span className="text-[11px] text-slate-500 flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {art.readTime}
                      </span>
                    </div>

                    <h3 className="text-base font-bold text-slate-900 dark:text-white group-hover:text-emerald-500 transition-colors leading-snug">
                      {art.title}
                    </h3>

                    <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed line-clamp-3">
                      {art.excerpt}
                    </p>
                  </div>

                  <div className="pt-4 border-t border-slate-100 dark:border-slate-800/60 flex items-center justify-between text-xs font-bold text-emerald-600 dark:text-emerald-400">
                    <span>Read Complete Document</span>
                    <ArrowRight className="w-3.5 h-3.5 transition-transform duration-300 group-hover:translate-x-1" />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>

      {/* Direct Concierge & Help Hooks Callout */}
      <section className="px-6">
        <div className="max-w-5xl mx-auto bg-slate-50 dark:bg-slate-905 rounded-3xl p-8 md:p-12 border border-slate-200 dark:border-slate-800 shadow-sm dark:shadow-2xl text-center relative overflow-hidden">
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-96 h-96 bg-emerald-500/5 rounded-full blur-3xl"></div>
          
          <div className="relative z-10 max-w-xl mx-auto space-y-4">
            <Sparkles className="w-8 h-8 text-emerald-500 dark:text-emerald-400 mx-auto" />
            <h3 className="text-xl md:text-2xl font-bold tracking-tight text-slate-900 dark:text-white">Need Live Customized Direction?</h3>
            <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
              Launch our highly capable context bots at any time from the floating primary desktop module, or directly connect with specialized regional consumer loan and security staff.
            </p>
            
            {activeBot !== undefined && setActiveBot && (
              <div className="pt-2 flex flex-wrap justify-center gap-3">
                <AnalyticsButton analyticsId="help_center_view_launch_security_advisor"
                  onClick={() => {
                    setActiveBot('Security & Fraud Bot');
                    setTimeout(() => setActiveBot(null), 4000);
                  }}
                  className="px-4 py-2 rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-xs font-bold text-slate-700 dark:text-slate-200 transition-colors cursor-pointer"
                >
                  Launch Security Advisor
                </AnalyticsButton>
                <AnalyticsButton analyticsId="help_center_view_launch_wealth_expert"
                  onClick={() => {
                    setActiveBot('Wealth Management Bot');
                    setTimeout(() => setActiveBot(null), 4000);
                  }}
                  className="px-4 py-2 rounded-lg bg-emerald-500 text-xs font-bold text-slate-950 hover:bg-emerald-400 transition-colors"
                >
                  Launch Wealth Expert
                </AnalyticsButton>
              </div>
            )}
          </div>
        </div>
      </section>

      {/* Simulated Complete Article Overlay View Modal */}
      {viewingArticle && (
        <div className="fixed inset-0 z-[200] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 animate-fade-in">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl max-w-2xl w-full overflow-hidden shadow-2xl max-h-[90vh] flex flex-col">
            
            {/* Header Bar */}
            <div className="p-6 border-b border-slate-200 dark:border-slate-800 flex justify-between items-center bg-slate-50 dark:bg-slate-950/50 flex-shrink-0">
              <div className="flex items-center gap-3">
                <span className={`px-2.5 py-0.5 rounded-full text-[11px] font-bold border ${viewingArticle.badgeBg}`}>
                  {viewingArticle.category}
                </span>
                <span className="text-xs text-slate-500 flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  {viewingArticle.readTime}
                </span>
              </div>
              <AnalyticsButton analyticsId="help_center_view_06" 
                onClick={() => setViewingArticle(null)}
                className="p-2 rounded-full hover:bg-slate-200 dark:hover:bg-slate-800 text-slate-500 transition-colors"
              >
                <X className="w-5 h-5" />
              </AnalyticsButton>
            </div>

            {/* Scrolling Body block */}
            <div className="p-8 overflow-y-auto space-y-6 flex-grow">
              <h2 className="text-xl md:text-2xl font-bold text-slate-900 dark:text-white leading-snug">
                {viewingArticle.title}
              </h2>

              <div className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed space-y-4 whitespace-pre-line font-normal">
                {viewingArticle.body}
              </div>

              <div className="pt-6 border-t border-slate-100 dark:border-slate-800 text-center">
                <p className="text-xs text-slate-400 mb-3">Did this documentation resolve your context needs?</p>
                <div className="flex justify-center gap-3">
                  <AnalyticsButton analyticsId="help_center_view_yes_bounded_context_fully_met" 
                    onClick={() => setViewingArticle(null)}
                    className="px-4 py-1.5 rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 font-bold text-xs hover:bg-emerald-500/20 transition-colors"
                  >
                    Yes, Bounded Context Fully Met
                  </AnalyticsButton>
                  <AnalyticsButton analyticsId="help_center_view_close_window" 
                    onClick={() => setViewingArticle(null)}
                    className="px-4 py-1.5 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-500 font-bold text-xs hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
                  >
                    Close Window
                  </AnalyticsButton>
                </div>
              </div>
            </div>

          </div>
        </div>
      )}

    </div>
  );
}

export default HelpCenterView;
