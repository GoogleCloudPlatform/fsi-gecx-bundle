import React, { useState } from 'react';
import { 
  Shield, 
  FileText, 
  ExternalLink, 
  Download, 
  X,
  CheckCircle2,
  Info,
  ArrowRight,
  Lock
} from 'lucide-react';
import { useSettings } from '../context/SettingsContext.jsx';
import AnalyticsButton from './AnalyticsButton.jsx';


function DisclosuresView() {
  const { 
    bankName
  } = useSettings();

  const [viewingDocument, setViewingDocument] = useState(null);

  const disclosures = [
    {
      id: "doc-membership",
      title: "Nova Sovereign Membership Protocol & Disclosures",
      revised: "January 2026",
      badgeBg: "bg-sky-500/10 border-sky-500/20 text-sky-600 dark:text-sky-400",
      desc: "Comprehensive consumer operational onboarding blueprint. Incorporates primary share draft holding covenants, Truth-in-Savings (TIS) baseline equations, standard continuous disclosure intervals, and native par share clearing cycles.",
      body: `THE MEMBER COVENANT & OPERATING BLUEPRINT
      
      1. MULTI-REGION CLOUD ONBOARDING
      Establishing a secure consumer digital persona binds individual underlying shares to our automated global identity framework. Par value share holdings mandate an uncompromised minimum deposit threshold maintained continuously to guarantee voting status.
      
      2. TRUTH-IN-SAVINGS (TIS) CALCULATIONS
      Dividend accrual models execute using daily continuous par balance validation equations. Yield parameters are generated dynamically inside our secure backend logic and applied directly to member portfolios at scheduled monthly maturity intervals.
      
      3. FUNDS AVAILABILITY REGULATORY BOUNDARIES
      Incoming direct clearing line items are subject to standard national settlement security verification buffers. Standard local checks clear within two processing tranches, whereas out-of-state manual checks remain subject to supplemental compliance processing windows.`
    },
    {
      id: "doc-addendum",
      title: "Horizon Apex Checking Incentive Addendum",
      revised: "April 2026",
      badgeBg: "bg-emerald-500/10 border-emerald-500/20 text-emerald-600 dark:text-emerald-400",
      desc: "Direct payroll integration metadata rules, baseline share tier metrics, and automated maintenance cost exemption validation instructions.",
      body: `DIRECT DEPOSIT & WAIVER METADATA PROTOCOL
      
      1. AUTOMATED CLICKSWITCH MAPPING
      Depositors transmitting initial qualifying employer primary digital payroll streams through integrated Core Clickswitch protocols instantly bypass manual verification queues.
      
      2. TIER ONE EXEMPTION EVALUATION
      Accounts tracking aggregate direct deposit parameters matching or exceeding $1,000 inside a given month automatically qualify for immediate internal tier level scaling, clearing persistent monthly ledger item charges.`
    },
    {
      id: "doc-lending",
      title: "Velocity Premium Reserve Lending Framework",
      revised: "February 2026",
      badgeBg: "bg-amber-500/10 border-amber-500/20 text-amber-600 dark:text-amber-400",
      desc: "Variable consumer revolving purchase credit agreements, Truth-in-Lending disclosure calculations, and continuous billing dispute processing definitions.",
      body: `TRUTH-IN-LENDING ASSURANCE & PORTFOLIO PARAMETERS
      
      1. REVOLVING BALANCE ASSESSMENT
      Interest indices track standard floating base reserve thresholds and adjust natively inside pre-defined multi-month check cycles. Uncompromised billing verification protects cardholders natively against unverified commercial assertions.
      
      2. GRACE PERIOD CONTINUITY
      Clearing completely indexed statement closing values prior to assigned monthly due date checkpoints programmatically forces a total waiver of current cycle interest calculations.`
    },
    {
      id: "doc-eft",
      title: "Equinox Electronic Fund Transfer Policy (EFT)",
      revised: "March 2026",
      badgeBg: "bg-purple-500/10 border-purple-500/20 text-purple-600 dark:text-purple-400",
      desc: "Instant credential provisioning guardrails, continuous mobile wallet cryptochip verification parameters, and zero-liability consumer protection guidelines.",
      body: `SECURE TRANSFER ARCHITECTURE & PROTECTION LAYER
      
      1. TOKENIZED PROVISIONING
      Virtual numbers generated dynamically for immediate Apple Pay® and Google Wallet™ insertion utilize localized cryptoprocessor isolation to eliminate intercept vulnerabilities.
      
      2. ZERO-LIABILITY MANDATE
      Consumers reporting unauthorized transactional activity inside defined reporting timelines receive comprehensive provisional ledger credits while automated security audits resolve underlying bad-actor vectors.`
    }
  ];

  return (
    <div className="pb-24">
      {/* Hero Section */}
      <section className="relative pt-32 pb-16 md:pt-44 md:pb-24 px-6 overflow-hidden">
        <div className="absolute inset-0 -z-10 overflow-hidden">
          <div className="absolute top-1/3 left-1/2 -translate-x-1/2 w-[800px] h-[300px] bg-sky-500/10 rounded-full blur-3xl"></div>
          <div className="absolute bottom-0 left-0 right-0 h-32 bg-gradient-to-t from-slate-50 dark:from-slate-950 to-transparent"></div>
        </div>

        <div className="max-w-5xl mx-auto text-center">
          <div className="inline-flex items-center space-x-2 px-4 py-2 rounded-full bg-sky-500/10 border border-sky-500/20 text-sky-600 dark:text-sky-400 text-xs font-semibold tracking-wide mb-6">
            <FileText className="w-3.5 h-3.5" />
            <span>Regulatory Documentation Blueprint</span>
          </div>

          <h1 className="text-4xl md:text-5xl lg:text-6xl font-extrabold tracking-tight leading-tight mb-4 text-slate-900 dark:text-white">
            Unified Account Disclosures <br />
            <span className="bg-gradient-to-r from-sky-400 via-cyan-400 to-teal-400 bg-clip-text text-transparent">
              & Legal Covenants.
            </span>
          </h1>

          <p className="text-base text-slate-600 dark:text-slate-400 max-w-2xl mx-auto leading-relaxed">
            Authoritative operating terms, national funds availability compliance indices, and uncompromised consumer protections indexed for immediate verifiable validation.
          </p>
        </div>
      </section>

      {/* Documents Grid */}
      <section className="px-6 mb-20">
        <div className="max-w-6xl mx-auto">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            {disclosures.map((doc) => (
              <div
                key={doc.id}
                onClick={() => setViewingDocument(doc)}
                className="bg-white dark:bg-slate-900/40 p-8 rounded-3xl border border-slate-200 dark:border-slate-800/60 shadow-sm dark:shadow-none hover:border-sky-500/40 hover:-translate-y-1 transition-all duration-300 flex flex-col justify-between space-y-6 group cursor-pointer"
              >
                <div className="space-y-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className={`px-3 py-0.5 rounded-full text-[11px] font-bold border ${doc.badgeBg}`}>
                      Audit Compliance Line
                    </span>
                    <span className="text-[11px] text-slate-400 font-mono">
                      Revised: {doc.revised}
                    </span>
                  </div>

                  <h3 className="text-xl font-bold text-slate-900 dark:text-white group-hover:text-sky-500 transition-colors leading-snug">
                    {doc.title}
                  </h3>

                  <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
                    {doc.desc}
                  </p>
                </div>

                <div className="pt-4 border-t border-slate-100 dark:border-slate-800/60 flex items-center justify-between text-xs font-bold text-sky-600 dark:text-sky-400">
                  <span className="flex items-center gap-1.5">
                    <FileText className="w-4 h-4" />
                    <span>Audit Digital Certificate</span>
                  </span>
                  <ArrowRight className="w-4 h-4 transition-transform duration-300 group-hover:translate-x-1" />
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Supplementary links */}
      <section className="px-6">
        <div className="max-w-4xl mx-auto bg-slate-50 dark:bg-slate-950/50 rounded-2xl p-6 border border-slate-200 dark:border-slate-800/60 flex flex-wrap items-center justify-between gap-4 text-xs text-slate-500">
          <div className="flex items-center gap-2">
            <Lock className="w-4 h-4 text-sky-500 flex-shrink-0" />
            <span>Looking for physical paper transmission replacements?</span>
          </div>
          <div className="flex items-center gap-4">
            <a href="/fee-schedule" className="font-bold text-slate-900 dark:text-white hover:underline">Audit Fee Index</a>
            <span>•</span>
            <a href="/help-center" className="font-bold text-slate-900 dark:text-white hover:underline">Access Knowledge Center</a>
          </div>
        </div>
      </section>

      {/* Simulated Complete PDF Document Overlay View Modal */}
      {viewingDocument && (
        <div className="fixed inset-0 z-[200] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 animate-fade-in">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl max-w-2xl w-full overflow-hidden shadow-2xl max-h-[90vh] flex flex-col">
            
            {/* Header */}
            <div className="p-6 border-b border-slate-200 dark:border-slate-800 flex justify-between items-center bg-slate-50 dark:bg-slate-950/50 flex-shrink-0">
              <div>
                <div className="text-[10px] font-mono text-sky-500 uppercase tracking-wider">Verified Certificate Record</div>
                <h3 className="text-base font-bold text-slate-900 dark:text-white mt-0.5">{viewingDocument.title}</h3>
              </div>
              <AnalyticsButton analyticsId="disclosures_view_01" 
                onClick={() => setViewingDocument(null)}
                className="p-2 rounded-full hover:bg-slate-200 dark:hover:bg-slate-800 text-slate-500 transition-colors"
              >
                <X className="w-5 h-5" />
              </AnalyticsButton>
            </div>

            {/* Scrolling document lines */}
            <div className="p-8 overflow-y-auto space-y-6 flex-grow font-mono text-xs text-slate-700 dark:text-slate-300 whitespace-pre-line leading-relaxed">
              <div className="text-center pb-4 border-b border-slate-100 dark:border-slate-800">
                <span className="font-bold block text-sm text-slate-900 dark:text-white">{bankName} Sovereign Disclosures</span>
                <span className="text-[10px] text-slate-400">Document Revision Identifier: {viewingDocument.revised.toUpperCase()}</span>
              </div>

              {viewingDocument.body}

              <div className="pt-8 mt-4 border-t border-dashed border-slate-200 dark:border-slate-800 text-center text-[11px] text-slate-400 font-sans">
                By inspecting this digital framework, member identity assertions validate automated compliance tranches.
              </div>
            </div>

            {/* Action buttons */}
            <div className="p-5 border-t border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/50 flex justify-end gap-3 flex-shrink-0">
              <AnalyticsButton analyticsId="disclosures_view_store_document_locally" 
                onClick={() => {
                  alert('Digital document downloaded successfully.');
                  setViewingDocument(null);
                }}
                className="px-4 py-2 rounded-xl bg-sky-500 text-slate-950 font-bold text-xs hover:bg-sky-400 transition-colors flex items-center gap-1.5"
              >
                <Download className="w-3.5 h-3.5" />
                <span>Store Document Locally</span>
              </AnalyticsButton>
              <AnalyticsButton analyticsId="disclosures_view_close_interface" 
                onClick={() => setViewingDocument(null)}
                className="px-4 py-2 rounded-xl bg-slate-200 dark:bg-slate-800 text-slate-700 dark:text-slate-300 font-bold text-xs hover:bg-slate-300 dark:hover:bg-slate-700 transition-colors"
              >
                Close Interface
              </AnalyticsButton>
            </div>

          </div>
        </div>
      )}

    </div>
  );
}

export default DisclosuresView;
