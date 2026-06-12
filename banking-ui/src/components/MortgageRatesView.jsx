import React, { useState } from 'react';
import { 
  Shield, 
  ArrowRight, 
  Percent, 
  Sparkles, 
  Info, 
  FileText, 
  CheckCircle2, 
  X,
  Lock,
  Calendar
} from 'lucide-react';
import { useSettings } from '../context/SettingsContext.jsx';

function MortgageRatesView() {
  const { 
    brandColorFrom, 
    brandColorTo
  } = useSettings();

  const [simulatingLock, setSimulatingLock] = useState(null);
  const [isLocked, setIsLocked] = useState(false);

  const rates = [
    {
      type: "30-Year Fixed Conforming",
      rate: "6.375%",
      points: "0.000",
      apr: "6.428%",
      tag: "Standard Conforming",
      notesIndex: [1, 2, 3]
    },
    {
      type: "15-Year Fixed Conforming",
      rate: "5.750%",
      points: "0.000",
      apr: "5.835%",
      tag: "Accelerated Principal",
      notesIndex: [1, 2, 3]
    },
    {
      type: "30-Year Fixed Jumbo Tier",
      rate: "6.375%",
      points: "0.000",
      apr: "6.393%",
      tag: "High-Balance Conforming",
      notesIndex: [4, 3]
    },
    {
      type: "15-Year Fixed Jumbo Tier",
      rate: "5.375%",
      points: "0.000",
      apr: "5.403%",
      tag: "Elite High-Balance",
      notesIndex: [4, 3]
    },
    {
      type: "10/6 Adjustable Rate Tier",
      rate: "5.625%",
      points: "0.000",
      apr: "5.941%",
      tag: "Extended Fixed Base",
      notesIndex: [1, 5, 3]
    },
    {
      type: "7/6 Adjustable Rate Tier",
      rate: "5.250%",
      points: "0.000",
      apr: "5.856%",
      tag: "Optimal Medium Hold",
      notesIndex: [1, 5, 3]
    },
    {
      type: "5/6 Adjustable Rate Tier",
      rate: "5.125%",
      points: "0.000",
      apr: "5.938%",
      tag: "Maximum Base Intro",
      notesIndex: [1, 5, 3]
    }
  ];

  const handleSimulateSubmit = (e) => {
    e.preventDefault();
    setIsLocked(true);
    setTimeout(() => {
      setIsLocked(false);
      setSimulatingLock(null);
    }, 3000);
  };

  return (
    <div className="pb-24">
      {/* Hero Section */}
      <section className="relative pt-32 pb-16 md:pt-44 md:pb-24 px-6 overflow-hidden">
        <div className="absolute inset-0 -z-10 overflow-hidden">
          <div className="absolute top-1/3 left-1/2 -translate-x-1/2 w-[800px] h-[300px] bg-sky-500/10 rounded-full blur-3xl"></div>
          <div className="absolute bottom-0 left-0 right-0 h-32 bg-gradient-to-t from-slate-50 dark:from-slate-950 to-transparent"></div>
        </div>

        <div className="max-w-7xl mx-auto text-center">
          <div className="inline-flex items-center space-x-2 px-4 py-2 rounded-full bg-sky-500/10 border border-sky-500/20 text-sky-600 dark:text-sky-400 text-xs font-semibold tracking-wide mb-6">
            <Percent className="w-3.5 h-3.5" />
            <span>Real-Time Pricing Index</span>
          </div>

          <h1 className="text-4xl md:text-6xl lg:text-7xl font-extrabold tracking-tight leading-tight max-w-4xl mx-auto mb-6">
            Live Home Financing <br />
            <span className="bg-gradient-to-r from-sky-400 via-cyan-300 to-teal-400 bg-clip-text text-transparent">
              Pricing Portfolios.
            </span>
          </h1>

          <p className="text-lg text-slate-600 dark:text-slate-400 max-w-2xl mx-auto leading-relaxed">
            Lock in your base fixed interest guarantee up to 60 continuous days prior to final disclosure settlement. Pricing accuracy audited directly against active local conforming indices.
          </p>
        </div>
      </section>

      {/* Rate Sheet Matrix Table */}
      <section className="px-6 mb-16">
        <div className="max-w-7xl mx-auto">
          <div className="overflow-x-auto border border-slate-200 dark:border-slate-800/80 rounded-3xl bg-white dark:bg-slate-900 shadow-2xl">
            
            {/* Table Header Line */}
            <div className="p-6 border-b border-slate-200 dark:border-slate-800 flex flex-wrap justify-between items-center gap-4 bg-slate-50/50 dark:bg-slate-950/50">
              <div>
                <div className="text-xs font-bold text-slate-400 uppercase tracking-wider">Active Index Snapshot</div>
                <div className="text-sm font-semibold text-slate-900 dark:text-white mt-0.5">Conforming & Jumbo Core Tiers</div>
              </div>
              <div className="flex items-center space-x-2 text-xs font-semibold text-emerald-500 bg-emerald-500/10 px-3 py-1.5 rounded-full border border-emerald-500/20">
                <Lock className="w-3 h-3" />
                <span>60-Day Lock Available</span>
              </div>
            </div>

            <table className="w-full text-left border-collapse min-w-[800px]">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-800 bg-slate-50/80 dark:bg-slate-950/80">
                  <th className="p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider">Mortgage Classification</th>
                  <th className="p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider">Base Interest Rate</th>
                  <th className="p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider">Discount Points</th>
                  <th className="p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider">Audited APR</th>
                  <th className="p-5 text-xs font-semibold text-slate-400 uppercase tracking-wider text-center">Lock Trigger</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-800/60 text-sm">
                {rates.map((row, idx) => (
                  <tr key={idx} className="hover:bg-slate-50/80 dark:hover:bg-slate-800/30 transition-colors">
                    <td className="p-5">
                      <div className="font-bold text-slate-900 dark:text-white flex items-center gap-2">
                        <span>{row.type}</span>
                        <span className="text-[10px] uppercase px-2 py-0.5 rounded font-semibold bg-slate-100 dark:bg-slate-800 text-slate-500">
                          {row.tag}
                        </span>
                      </div>
                      <div className="text-[11px] text-slate-500 mt-1 flex items-center gap-1">
                        <span>Disclosures:</span>
                        {row.notesIndex.map((num, ni) => (
                          <a href={`#note-${num}`} key={ni} className="text-sky-600 dark:text-sky-400 hover:underline">
                            <sup>{num}</sup>
                          </a>
                        ))}
                      </div>
                    </td>
                    <td className="p-5 font-black text-lg text-slate-900 dark:text-white">
                      {row.rate}
                    </td>
                    <td className="p-5 text-slate-600 dark:text-slate-400 font-mono text-xs">
                      {row.points}
                    </td>
                    <td className="p-5 font-bold text-sky-600 dark:text-sky-400">
                      {row.apr}
                    </td>
                    <td className="p-5 text-center">
                      <button
                        onClick={() => setSimulatingLock(row)}
                        className="px-4 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 dark:bg-white dark:hover:bg-slate-100 text-white dark:text-slate-900 font-bold text-xs transition-colors"
                      >
                        Reserve Rate
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {/* Footer Disclaimer Line */}
            <div className="p-5 border-t border-slate-200 dark:border-slate-800 bg-slate-50/30 dark:bg-slate-950/30 text-[11px] text-slate-500 leading-relaxed">
              <span className="font-semibold text-slate-600 dark:text-slate-400">Pricing Continuity Assurance:</span> Base line structures remain active subject to standard intra-day continuous bond indexing adjustments. Variable indices for 5/6, 7/6, and 10/6 ARM configurations adjust bi-annually upon initial fixed maturity threshold validation.
            </div>

          </div>
        </div>
      </section>

      {/* Audited Footnotes & Disclosures Block */}
      <section className="px-6">
        <div className="max-w-7xl mx-auto bg-slate-50 dark:bg-slate-950/60 rounded-3xl p-8 md:p-12 border border-slate-200 dark:border-slate-800/60">
          <div className="flex items-center space-x-2 mb-6 pb-4 border-b border-slate-200 dark:border-slate-800">
            <FileText className="w-5 h-5 text-sky-500" />
            <h2 className="text-lg font-bold text-slate-900 dark:text-white">Formal Disclosures & Assumptions Index</h2>
          </div>

          <div className="space-y-6 text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
            
            <div id="note-1" className="space-y-1.5 scroll-mt-24">
              <div className="font-bold text-slate-900 dark:text-slate-300"><sup>1</sup> Standard Conforming Loan Rate Blueprint Assumptions:</div>
              <ul className="grid grid-cols-2 sm:grid-cols-3 gap-2 pl-3 pt-1 list-disc list-inside text-slate-500">
                <li>Base Funding: $300,000</li>
                <li>Property Value: $500,000</li>
                <li>Estimated Closing Costs: $6,550</li>
                <li>Credit Score Baseline: 780+</li>
                <li>Property Type: Detached Single Family</li>
                <li>Occupancy: Primary Legal Residence</li>
              </ul>
            </div>

            <div id="note-2" className="space-y-1 scroll-mt-24 border-t border-slate-200 dark:border-slate-800/60 pt-4">
              <div className="font-bold text-slate-900 dark:text-slate-300"><sup>2</sup> Amortization Payment Trajectory Example:</div>
              <p>
                A standardized 360-month amortization structure funded at a fixed interest baseline of 6.000% with an associated 60% Loan-to-Value (LTV) operational parameter mandates an estimated principal obligation of $59.96 per each $10,000 drawn. Municipal property assessments and core structural hazard insurance policy escrow reserves are completely separate; real-world payment outputs will scale above base principal parameters.
              </p>
            </div>

            <div id="note-3" className="space-y-1 scroll-mt-24 border-t border-slate-200 dark:border-slate-800/60 pt-4">
              <div className="font-bold text-slate-900 dark:text-slate-300"><sup>3</sup> Audited APR (Annual Percentage Rate) Disclaimer:</div>
              <p>
                APR indexing parameters incorporate foundational underwriting charges, direct closing adjustments, and baseline pre-paid escrow mapping. Final individual APR execution numbers adjust natively based on formal certified appraisal reports, final LTV thresholds, and audited personal FICO® score tranches. Offer parameters remain strictly non-binding until formal digital underwriting locking is executed securely.
              </p>
            </div>

            <div id="note-4" className="space-y-1.5 scroll-mt-24 border-t border-slate-200 dark:border-slate-800/60 pt-4">
              <div className="font-bold text-slate-900 dark:text-slate-300"><sup>4</sup> Jumbo High-Balance Funding Blueprint Assumptions:</div>
              <ul className="grid grid-cols-2 sm:grid-cols-3 gap-2 pl-3 pt-1 list-disc list-inside text-slate-500">
                <li>Base Funding: $900,000</li>
                <li>Property Value: $1,500,000</li>
                <li>Estimated Closing Costs: $36,550</li>
                <li>Credit Score Baseline: 780+</li>
                <li>Property Type: Detached Single Family</li>
                <li>Occupancy: Primary Legal Residence</li>
              </ul>
            </div>

            <div id="note-5" className="space-y-1 scroll-mt-24 border-t border-slate-200 dark:border-slate-800/60 pt-4">
              <div className="font-bold text-slate-900 dark:text-slate-300"><sup>5</sup> Variable Adjustment Index Framework (ARM Core):</div>
              <p>
                Adjustable Rate Mortgage structures execute fixed starting continuity periods matching their initial term prefix (5, 7, or 10 years). Upon introductory term expiration, pricing parameters shift automatically to follow continuous standard market index margins with bi-annual checkpoint checks. Individual operational adjustments operate inside strict structural guardrails: annual limits enforce a standard adjustment cap of +/- 2.00%, and a strict lifetime interest floor/ceiling boundary enforced at +/- 5.00% absolute limits.
              </p>
            </div>

          </div>
        </div>
      </section>

      {/* Rate Reservation Context Simulation Modal */}
      {simulatingLock && (
        <div className="fixed inset-0 z-[200] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 animate-fade-in">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl max-w-md w-full overflow-hidden shadow-2xl">
            
            {/* Header */}
            <div className="p-6 border-b border-slate-200 dark:border-slate-800 flex justify-between items-center bg-slate-50 dark:bg-slate-950/50">
              <div>
                <div className="text-xs font-bold text-sky-500 uppercase tracking-wider">Simulate Rate Reservation Lock</div>
                <h3 className="text-lg font-bold text-slate-900 dark:text-white mt-0.5">{simulatingLock.type}</h3>
              </div>
              <button 
                onClick={() => setSimulatingLock(null)}
                className="p-2 rounded-full hover:bg-slate-200 dark:hover:bg-slate-800 text-slate-500 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Body block */}
            <div className="p-6 space-y-6">
              {isLocked ? (
                <div className="text-center py-8 space-y-4">
                  <div className="w-16 h-16 rounded-full bg-sky-500/10 text-sky-500 flex items-center justify-center mx-auto">
                    <CheckCircle2 className="w-10 h-10 animate-bounce" />
                  </div>
                  <h4 className="text-xl font-bold text-slate-900 dark:text-white">Base Lock-in Guaranteed!</h4>
                  <p className="text-sm text-slate-600 dark:text-slate-400 max-w-xs mx-auto leading-relaxed">
                    Pricing parameters locked securely at <span className="font-bold text-slate-900 dark:text-white">{simulatingLock.rate}</span> for a continuous 60-day window. Your verified digital lock certificate has been indexed.
                  </p>
                </div>
              ) : (
                <form onSubmit={handleSimulateSubmit} className="space-y-5">
                  <div className="bg-slate-50 dark:bg-slate-950/60 rounded-xl p-4 border border-slate-200 dark:border-slate-800/60 space-y-3 text-sm">
                    <div className="flex justify-between items-center">
                      <span className="text-slate-500 text-xs">Target Base Rate:</span>
                      <span className="font-bold text-slate-900 dark:text-white text-base">{simulatingLock.rate}</span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-slate-500 text-xs">Associated APR:</span>
                      <span className="font-semibold text-sky-600 dark:text-sky-400">{simulatingLock.apr}</span>
                    </div>
                    <div className="flex justify-between items-center pt-2 border-t border-slate-200 dark:border-slate-800/60">
                      <span className="text-slate-500 text-xs">Guarantee Duration:</span>
                      <span className="font-medium text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
                        <Calendar className="w-3.5 h-3.5" />
                        <span>60 Continuous Days</span>
                      </span>
                    </div>
                  </div>

                  <p className="text-xs text-slate-500 leading-relaxed text-center">
                    Reserving this base pricing guarantee simulates our high-availability real estate integration framework. No initial fee check processing required.
                  </p>

                  <button
                    type="submit"
                    className="w-full py-3.5 rounded-xl text-slate-950 font-bold text-sm shadow-lg hover:scale-[1.02] transition-all duration-300 flex items-center justify-center space-x-2"
                    style={{ backgroundImage: `linear-gradient(to right, ${brandColorFrom}, ${brandColorTo})` }}
                  >
                    <span>Authorize 60-Day Guarantee Lock</span>
                    <ArrowRight className="w-4 h-4" />
                  </button>
                </form>
              )}
            </div>

          </div>
        </div>
      )}

    </div>
  );
}

export default MortgageRatesView;
