/**
 * Copyright 2026 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

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
  Globe,
  AlertCircle,
  Loader2
} from 'lucide-react';
import { useSettings } from '../context/SettingsContext.jsx';
import { useCreditProducts } from '../hooks/useCreditProducts.js';
import { getCreditCardStyle } from '../utils/creditCardStyles.js';
import { buildCardFacts } from '../utils/creditCardPresentation.js';
import CreditCardMatrix from './CreditCardMatrix.jsx';
import CreditCardVisual from './CreditCardVisual.jsx';
import AnalyticsButton from './AnalyticsButton.jsx';


function CreditCardsView({ fbUser, activeBot, setActiveBot }) {
  const navigate = useNavigate();
  const { 
    bankName, 
    brandColorFrom, 
    brandColorTo
  } = useSettings();

  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);
  const [selectedCardIndex, setSelectedCardIndex] = useState(0);

  const { products, loading, error, retry } = useCreditProducts();

  const handleApply = (productCode) => {
    if (!fbUser) {
      setIsAuthModalOpen(true);
    } else {
      navigate(`/apply/credit-card?card=${productCode}`);
    }
  };

  const cardFactsList = (products || []).map(buildCardFacts).filter(Boolean);
  const selectedCard = cardFactsList[selectedCardIndex] || cardFactsList[0] || null;
  const cardStyle = getCreditCardStyle(selectedCard?.productCode);

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
          {loading && (
            <div data-testid="credit-cards-loading" className="py-20 text-center">
              <div className="inline-flex items-center gap-3 px-6 py-3 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-300 text-sm font-semibold shadow-sm">
                <Loader2 className="w-5 h-5 animate-spin text-emerald-500" />
                <span>Loading credit products catalog...</span>
              </div>
            </div>
          )}

          {error && !loading && (
            <div data-testid="credit-cards-error" className="max-w-xl mx-auto my-12 p-8 rounded-3xl bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-800/40 text-center">
              <AlertCircle className="w-10 h-10 text-red-500 mx-auto mb-3" />
              <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-2">Unable to Load Credit Cards</h2>
              <p className="text-sm text-slate-600 dark:text-slate-400">
                We could not load current credit card terms and rates. Please refresh or try again later.
              </p>
              {retry && (
                <button
                  type="button"
                  onClick={() => retry()}
                  className="mt-4 inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-red-600 hover:bg-red-700 text-white text-xs font-semibold shadow-sm transition cursor-pointer"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                  <span>Try again</span>
                </button>
              )}
            </div>
          )}

          {!loading && !error && selectedCard && (
            <>
              {/* Card Tabs */}
              <div className="flex flex-wrap justify-center gap-3 mb-12">
                {cardFactsList.map((card, idx) => {
                  const isSelected = idx === selectedCardIndex;
                  return (
                    <AnalyticsButton
                      analyticsId="credit_cards_view_01"
                      key={card.productCode}
                      onClick={() => setSelectedCardIndex(idx)}
                      className={`px-5 py-3 rounded-xl font-semibold text-sm transition-all duration-300 flex items-center space-x-2 border ${
                        isSelected 
                          ? 'bg-white dark:bg-slate-950 text-slate-900 dark:text-white border-slate-900 dark:border-slate-800 shadow-md scale-105' 
                          : 'bg-slate-100 dark:bg-slate-900 text-slate-550 dark:text-slate-400 border-slate-255 dark:border-slate-800/80 hover:bg-slate-200 dark:hover:bg-slate-800'
                      }`}
                    >
                      <CreditCard className={`w-4 h-4 ${isSelected ? 'text-emerald-400 dark:text-emerald-600' : ''}`} />
                      <span>{card.productName}</span>
                      {card.isSecured && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded font-bold bg-amber-500/10 text-amber-600 dark:text-amber-400 uppercase tracking-wider">Secured</span>
                      )}
                    </AnalyticsButton>
                  );
                })}
              </div>

              {/* Active Card Detail Panel */}
              <div className="bg-white dark:bg-slate-900/40 grid grid-cols-1 lg:grid-cols-12 gap-12 items-center shadow-2xl border border-slate-200 dark:border-slate-800/80 rounded-3xl p-8 md:p-12">
                
                {/* Left side: CSS Rendered Realistic Card Graphic */}
                <div className="lg:col-span-5 flex justify-center">
                  <CreditCardVisual product={selectedCard} bankName={bankName} />
                </div>

                {/* Right side: Deep Feature Breakdown */}
                <div className="lg:col-span-7 space-y-6">
                  <div className="flex flex-wrap items-center gap-3">
                    {selectedCard.isSecured && (
                      <span className="px-3 py-1 rounded-full text-xs font-bold border bg-amber-500/10 border-amber-500/20 text-amber-600 dark:text-amber-400 uppercase tracking-wider">
                        {selectedCard.securedBadgeText}
                      </span>
                    )}
                    <span className={`px-3 py-1 rounded-full text-xs font-bold border ${cardStyle.badgeBg}`}>
                      {selectedCard.bestFor}
                    </span>
                    <span className="text-xs text-slate-500 flex items-center gap-1">
                      <Star className="w-3.5 h-3.5 fill-amber-400 text-amber-400" />
                      4.9/5 Member Rating
                    </span>
                  </div>

                  <div className="border-b border-slate-200 dark:border-slate-800 pb-6">
                    <h2 className="text-3xl md:text-4xl font-black text-slate-900 dark:text-white mt-1">
                      {selectedCard.productName}
                    </h2>
                    <p className="text-sm text-slate-600 dark:text-slate-400 mt-2">
                      {selectedCard.tagline}
                    </p>
                    {selectedCard.hasIntroOffers && (
                      <div className="mt-4 p-4 rounded-2xl bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800/40">
                        <div className="text-xs font-bold text-emerald-600 dark:text-emerald-400 uppercase tracking-wider">
                          Introductory Offer
                        </div>
                        <div className="text-sm font-semibold text-slate-900 dark:text-white mt-1">
                          {selectedCard.introOffers}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Quick Stat Badges */}
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
                    <div className="bg-slate-50 dark:bg-slate-950/50 rounded-xl p-3 border border-slate-200 dark:border-slate-800/60">
                      <div className="text-[11px] text-slate-500">Rewards Program</div>
                      <div className="text-sm font-bold text-slate-900 dark:text-white mt-0.5 truncate" title={selectedCard.rewardsSummary}>
                        {selectedCard.rewardsSummary}
                      </div>
                    </div>
                    <div className="bg-slate-50 dark:bg-slate-950/50 rounded-xl p-3 border border-slate-200 dark:border-slate-800/60">
                      <div className="text-[11px] text-slate-500">Annual Fee</div>
                      <div className="text-sm font-bold text-emerald-500 mt-0.5">{selectedCard.annualFee}</div>
                    </div>
                    <div className="bg-slate-50 dark:bg-slate-950/50 rounded-xl p-3 border border-slate-200 dark:border-slate-800/60">
                      <div className="text-[11px] text-slate-500">Purchase APR</div>
                      <div className="text-sm font-bold text-slate-900 dark:text-white mt-0.5 font-mono">{selectedCard.purchaseApr}</div>
                    </div>
                    <div className="bg-slate-50 dark:bg-slate-950/50 rounded-xl p-3 border border-slate-200 dark:border-slate-800/60">
                      <div className="text-[11px] text-slate-500">Credit Limit Range</div>
                      <div className="text-xs font-bold text-slate-900 dark:text-white mt-0.5 font-mono">{selectedCard.creditLimitRange}</div>
                    </div>
                    <div className="bg-slate-50 dark:bg-slate-950/50 rounded-xl p-3 border border-slate-200 dark:border-slate-800/60">
                      <div className="text-[11px] text-slate-500">Balance Transfer Fee</div>
                      <div className="text-xs font-bold text-slate-900 dark:text-white mt-0.5">{selectedCard.balanceTransferFee}</div>
                    </div>
                    <div className="bg-slate-50 dark:bg-slate-950/50 rounded-xl p-3 border border-slate-200 dark:border-slate-800/60">
                      <div className="text-[11px] text-slate-500">Foreign Tx Fee</div>
                      <div className="text-xs font-bold text-slate-900 dark:text-white mt-0.5">{selectedCard.foreignTransactionFee}</div>
                    </div>
                  </div>

                  {/* Features Checklist */}
                  <div className="space-y-2.5 pt-2">
                    <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Key Advantages</div>
                    {selectedCard.features?.map((feat, idx) => (
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
                    <AnalyticsButton
                      analyticsId="credit_cards_view_apply_now"
                      onClick={() => handleApply(selectedCard.productCode)}
                      className="w-full sm:w-auto px-8 py-3.5 rounded-full text-slate-950 font-bold text-sm shadow-lg hover:scale-105 transition-all duration-300 flex items-center justify-center space-x-2 cursor-pointer"
                      style={{ backgroundImage: `linear-gradient(to right, ${brandColorFrom}, ${brandColorTo})`, boxShadow: `0 10px 15px -3px ${brandColorFrom}33` }}
                    >
                      <span>Apply Now</span>
                      <ArrowRight className="w-4 h-4" />
                    </AnalyticsButton>
                    
                    {activeBot !== undefined && setActiveBot && (
                      <AnalyticsButton
                        analyticsId="credit_cards_view_03" 
                        onClick={() => {
                          setActiveBot(cardStyle.botName);
                          setTimeout(() => setActiveBot(null), 4000);
                        }}
                        className="w-full sm:w-auto px-6 py-3.5 rounded-full bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 text-sm font-semibold transition-colors flex items-center justify-center space-x-2 cursor-pointer"
                      >
                        <span>Ask {cardStyle.botName.split(' ')[0]} Advisor</span>
                      </AnalyticsButton>
                    )}
                  </div>
                </div>

              </div>
            </>
          )}
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

          <CreditCardMatrix onApply={handleApply} />
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
          {isAuthModalOpen && (
            <div className="fixed inset-0 z-[250] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 animate-fade-in">
              <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl max-w-sm w-full overflow-hidden shadow-2xl p-6 text-center space-y-4">
                <div className="w-12 h-12 rounded-full bg-amber-500/10 text-amber-500 flex items-center justify-center mx-auto">
                  <Lock className="w-6 h-6" />
                </div>
                <h3 className="text-xl font-bold text-slate-900 dark:text-white">Sign In Required</h3>
                <p className="text-sm text-slate-600 dark:text-slate-400 leading-relaxed">
                  To apply for a credit card, please sign in using the profile button in the top-right of the page and then proceed with your application.
                </p>
                <AnalyticsButton
                  analyticsId="credit_cards_view_acknowledge"
                  onClick={() => setIsAuthModalOpen(false)}
                  className="w-full py-2.5 rounded-xl text-slate-950 font-bold text-sm shadow-md hover:scale-[1.02] transition-all duration-300 cursor-pointer"
                  style={{ backgroundImage: `linear-gradient(to right, ${brandColorFrom}, ${brandColorTo})` }}
                >
                  Acknowledge
                </AnalyticsButton>
              </div>
            </div>
          )}

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
