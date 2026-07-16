// Copyright 2026 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     https://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import React, { useState } from 'react';
import {
  Sparkles,
  Wallet,
  PiggyBank,
  Layers,
  CreditCard,
  Home,
  Lock,
  X,
  CheckCircle2,
  Calendar,
  ArrowRight,
  RefreshCw
} from 'lucide-react';
import { useSettings } from '../context/SettingsContext.jsx';
import { useNavigate } from 'react-router-dom';
import CheckingMatrix from './CheckingMatrix.jsx';
import SavingsMatrix from './SavingsMatrix.jsx';
import CertificateMatrix from './CertificateMatrix.jsx';
import CreditCardMatrix from './CreditCardMatrix.jsx';
import MortgageMatrix from './MortgageMatrix.jsx';
import AccountOpeningModal from './AccountOpeningModal.jsx';
import AnalyticsButton from './AnalyticsButton.jsx';


export default function CompareProducts({ fbUser }) {
  const navigate = useNavigate();
  const {
    brandColorFrom,
    brandColorTo
  } = useSettings();

  const [activeTab, setActiveTab] = useState('checking');
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);

  const handleApply = (cardSlug) => {
    if (!fbUser) {
      setIsAuthModalOpen(true);
    } else {
      navigate(`/apply/credit-card?card=${cardSlug}`);
    }
  };
  const [openingAccount, setOpeningAccount] = useState(null);
  const [accountType, setAccountType] = useState('CHECKING');

  // Mortgage Rate simulation state
  const [simulatingLock, setSimulatingLock] = useState(null);
  const [isLocked, setIsLocked] = useState(false);

  const handleOpenChecking = (acc) => {
    setAccountType('CHECKING');
    setOpeningAccount(acc);
  };

  const handleOpenSavings = (prod) => {
    setAccountType('SAVINGS');
    setOpeningAccount(prod);
  };

  const handleOpenCertificates = (prod) => {
    setAccountType('CERTIFICATE');
    setOpeningAccount(prod);
  };

  const handleSimulateLockSubmit = (e) => {
    e.preventDefault();
    setIsLocked(true);
    setTimeout(() => {
      setIsLocked(false);
      setSimulatingLock(null);
    }, 3000);
  };

  const tabs = [
    { id: 'checking', label: 'Checking Tiers', icon: Wallet },
    { id: 'savings', label: 'Savings Milestones', icon: PiggyBank },
    { id: 'certificates', label: 'Certificates', icon: Layers },
    { id: 'credit', label: 'Credit Cards', icon: CreditCard },
    { id: 'mortgage', label: 'Mortgage Rates', icon: Home }
  ];

  return (
    <div className="pb-24">
      {/* Hero Section */}
      <section className="relative pt-32 pb-16 md:pt-44 md:pb-24 px-6 overflow-hidden">
        <div className="absolute inset-0 -z-10 overflow-hidden">
          <div className="absolute top-1/3 left-1/2 -translate-x-1/2 w-[850px] h-[320px] bg-emerald-500/15 rounded-full blur-3xl"></div>
          <div className="absolute bottom-0 left-0 right-0 h-32 bg-gradient-to-t from-slate-50 dark:from-slate-950 to-transparent"></div>
        </div>

        <div className="max-w-7xl mx-auto text-center">
          <div className="inline-flex items-center space-x-2 px-4 py-2 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-600 dark:text-emerald-400 text-xs font-semibold tracking-wide mb-6">
            <Sparkles className="w-3.5 h-3.5 animate-pulse" />
            <span>Comprehensive Portfolio Comparison</span>
          </div>

          <h1 className="text-4xl md:text-6xl lg:text-7xl font-extrabold tracking-tight leading-tight max-w-4xl mx-auto mb-6">
            Compare all products <br />
            <span className="bg-gradient-to-r from-emerald-400 via-teal-300 to-cyan-400 bg-clip-text text-transparent">
              side-by-side.
            </span>
          </h1>

          <p className="text-lg text-slate-655 dark:text-slate-400 max-w-2xl mx-auto leading-relaxed">
            Review checking APYs, high-yield savings structures, travel rewards rates, and live mortgage interest indices. Make the smart move for your wealth.
          </p>
        </div>
      </section>

      {/* Tabs Selector */}
      <section className="px-6 mb-12">
        <div className="max-w-7xl mx-auto flex flex-wrap justify-center gap-3">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <AnalyticsButton trackingName="button_click_compare_products_01"
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`px-6 py-4 rounded-2xl font-bold text-sm transition-all duration-300 flex items-center space-x-2.5 border cursor-pointer ${isActive
                  ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-950 border-slate-900 dark:border-white shadow-xl scale-105'
                  : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-400 border-slate-200 dark:border-slate-800/80 hover:bg-slate-50 dark:hover:bg-slate-800'
                  }`}
              >
                <Icon className={`w-4 h-4 ${isActive ? 'text-emerald-400 dark:text-emerald-600' : ''}`} />
                <span>{tab.label}</span>
              </AnalyticsButton>
            );
          })}
        </div>
      </section>

      {/* Matrix Display Container */}
      <section className="px-6">
        <div className="max-w-7xl mx-auto">
          {activeTab === 'checking' && (
            <CheckingMatrix onOpenAccount={handleOpenChecking} />
          )}
          {activeTab === 'savings' && (
            <SavingsMatrix onOpenAccount={handleOpenSavings} />
          )}
          {activeTab === 'certificates' && (
            <CertificateMatrix onOpenAccount={handleOpenCertificates} />
          )}
          {activeTab === 'credit' && (
            <CreditCardMatrix onApply={handleApply} />
          )}
          {activeTab === 'mortgage' && (
            <MortgageMatrix onReserveRate={setSimulatingLock} />
          )}
        </div>
      </section>

      {/* Shared Account Opening Integration Modal */}
      <AccountOpeningModal
        openingAccount={openingAccount}
        onClose={() => setOpeningAccount(null)}
        accountType={accountType}
        brandColorFrom={brandColorFrom}
        brandColorTo={brandColorTo}
      />

      {/* Mortgage Rate Reservation Simulation Modal */}
      {simulatingLock && (
        <div className="fixed inset-0 z-[200] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 animate-fade-in">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl max-w-md w-full overflow-hidden shadow-2xl">

            {/* Header */}
            <div className="p-6 border-b border-slate-200 dark:border-slate-800 flex justify-between items-center bg-slate-50 dark:bg-slate-950/50">
              <div>
                <div className="text-xs font-bold text-sky-500 uppercase tracking-wider">Simulate Rate Reservation Lock</div>
                <h3 className="text-lg font-bold text-slate-900 dark:text-white mt-0.5">{simulatingLock.type}</h3>
              </div>
              <AnalyticsButton trackingName="button_click_compare_products_02"
                onClick={() => setSimulatingLock(null)}
                className="p-2 rounded-full hover:bg-slate-200 dark:hover:bg-slate-800 text-slate-500 transition-colors cursor-pointer"
              >
                <X className="w-5 h-5" />
              </AnalyticsButton>
            </div>

            {/* Body */}
            <div className="p-6 space-y-6">
              {isLocked ? (
                <div className="text-center py-8 space-y-4">
                  <div className="w-16 h-16 rounded-full bg-sky-500/10 text-sky-500 flex items-center justify-center mx-auto">
                    <CheckCircle2 className="w-10 h-10 animate-bounce" />
                  </div>
                  <h4 className="text-xl font-bold text-slate-900 dark:text-white">Base Lock-in Guaranteed!</h4>
                  <p className="text-sm text-slate-655 dark:text-slate-400 max-w-xs mx-auto leading-relaxed">
                    Pricing parameters locked securely at <span className="font-bold text-slate-900 dark:text-white">{simulatingLock.rate}</span> for a continuous 60-day window. Your verified digital lock certificate has been indexed.
                  </p>
                </div>
              ) : (
                <form onSubmit={handleSimulateLockSubmit} className="space-y-5">
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

                  <AnalyticsButton trackingName="button_click_compare_products_03"
                    type="submit"
                    className="w-full py-3.5 rounded-xl text-slate-950 font-bold text-sm shadow-lg hover:scale-[1.02] transition-all duration-300 flex items-center justify-center space-x-2 cursor-pointer"
                    style={{ backgroundImage: `linear-gradient(to right, ${brandColorFrom}, ${brandColorTo})` }}
                  >
                    <span>Authorize 60-Day Guarantee Lock</span>
                    <ArrowRight className="w-4 h-4" />
                  </AnalyticsButton>
                </form>
              )}
            </div>

          </div>
        </div>
      )}

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
            <AnalyticsButton trackingName="button_click_compare_products_04"
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
  );
}
