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
import { X, CheckCircle2, RefreshCw, ArrowRight, AlertCircle } from 'lucide-react';
import { createDepositAccount } from '../utils/api.js';
import AnalyticsButton from './AnalyticsButton.jsx';


function AccountOpeningModal({ openingAccount, onClose, accountType = 'CHECKING', brandColorFrom = '#14b8a6', brandColorTo = '#06b6d4' }) {
  const [memberType, setMemberType] = useState('current');
  const [initialDepositDollars, setInitialDepositDollars] = useState(100);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submissionSuccess, setSubmissionSuccess] = useState(false);
  const [errorMessage, setErrorMessage] = useState(null);
  const [createdAccountInfo, setCreatedAccountInfo] = useState(null);

  if (!openingAccount) return null;

  const handleOpenSubmit = async (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    setErrorMessage(null);

    try {
      const depositCents = Math.max(0, Math.round(Number(initialDepositDollars) * 100));
      const payload = {
        account_type: accountType,
        product_name: openingAccount.name,
        member_type: memberType,
        initial_deposit_cents: depositCents
      };

      const result = await createDepositAccount(payload);
      setCreatedAccountInfo(result);
      setSubmissionSuccess(true);
      setTimeout(() => {
        onClose();
      }, 3500);
    } catch (err) {
      console.error("Account creation failed:", err);
      const detail = err.response?.data?.detail || err.message || "Failed to provision account. Please try again.";
      setErrorMessage(detail);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[200] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 animate-fade-in">
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl max-w-lg w-full overflow-hidden shadow-2xl">
        
        {/* Header Line */}
        <div className="p-6 border-b border-slate-200 dark:border-slate-800 flex justify-between items-center bg-slate-50 dark:bg-slate-950/50">
          <div>
            <div className="text-xs text-teal-500 font-semibold uppercase tracking-wider">Secure Primary Deposit Context</div>
            <h3 className="text-xl font-bold text-slate-900 dark:text-white mt-0.5">{openingAccount.name}</h3>
          </div>
          <AnalyticsButton
            analyticsId="account_opening_modal_01" 
            onClick={onClose}
            className="p-2 rounded-full hover:bg-slate-200 dark:hover:bg-slate-800 text-slate-500 transition-colors"
          >
            <X className="w-5 h-5" />
          </AnalyticsButton>
        </div>

        {/* Flow Body */}
        <div className="p-6 space-y-6">
          {submissionSuccess ? (
            <div className="text-center py-8 space-y-4">
              <div className="w-16 h-16 rounded-full bg-teal-500/10 text-teal-500 flex items-center justify-center mx-auto">
                <CheckCircle2 className="w-10 h-10 animate-bounce" />
              </div>
              <h4 className="text-xl font-bold text-slate-900 dark:text-white">Deposit Core Provisioned!</h4>
              {createdAccountInfo && (
                <div className="p-3 bg-slate-100 dark:bg-slate-800 rounded-xl text-xs font-mono text-slate-700 dark:text-slate-300">
                  <div>Account Number: {createdAccountInfo.account_number}</div>
                  <div>Status: {createdAccountInfo.status}</div>
                </div>
              )}
              <p className="text-sm text-slate-600 dark:text-slate-400 max-w-sm mx-auto">
                Your deposit context signature line is prepared and live in PostgreSQL. Initial automated routing metadata parameters and personalized options are accessible via your direct dashboard portal.
              </p>
            </div>
          ) : (
            <form onSubmit={handleOpenSubmit} className="space-y-6">
              {errorMessage && (
                <div className="p-3 bg-red-50 dark:bg-red-950/50 border border-red-200 dark:border-red-800/80 rounded-xl flex items-center gap-2 text-red-600 dark:text-red-400 text-xs">
                  <AlertCircle className="w-4 h-4 flex-shrink-0" />
                  <span>{errorMessage}</span>
                </div>
              )}

              <div>
                <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
                  Core Ownership Layer Status
                </label>
                <div className="grid grid-cols-2 gap-3">
                  <AnalyticsButton
                    analyticsId="account_opening_modal_existing_depositor"
                    type="button"
                    onClick={() => setMemberType('current')}
                    className={`p-3 rounded-xl border text-center text-sm font-bold transition-all ${
                      memberType === 'current'
                        ? 'bg-teal-500/10 border-teal-500 text-teal-600 dark:text-teal-400'
                        : 'border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-400 hover:border-slate-300'
                    }`}
                  >
                    Existing Depositor
                  </AnalyticsButton>
                  <AnalyticsButton
                    analyticsId="account_opening_modal_new_primary_member"
                    type="button"
                    onClick={() => setMemberType('new')}
                    className={`p-3 rounded-xl border text-center text-sm font-bold transition-all ${
                      memberType === 'new'
                        ? 'bg-teal-500/10 border-teal-500 text-teal-600 dark:text-teal-400'
                        : 'border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-400 hover:border-slate-300'
                    }`}
                  >
                    New Primary Member
                  </AnalyticsButton>
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                  Initial Deposit Funding ($ USD)
                </label>
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={initialDepositDollars}
                  onChange={(e) => setInitialDepositDollars(e.target.value)}
                  className="w-full p-3 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-white font-mono text-sm focus:outline-none focus:border-teal-500"
                  required
                />
              </div>

              <div className="bg-slate-50 dark:bg-slate-950/60 rounded-xl p-4 border border-slate-200 dark:border-slate-800/60 text-xs space-y-2 text-slate-600 dark:text-slate-400 leading-relaxed">
                <div className="font-semibold text-slate-900 dark:text-slate-300">Mandatory Core Disclosures:</div>
                <p>
                  Pursuant to standard verification checkpoints, opening a primary digital liquid line seamlessly anchors your account to our multi-region cloud identity protocol. Immediate digital disclosures will be dispatched.
                </p>
              </div>

              <div className="space-y-3 pt-2">
                <AnalyticsButton
                  analyticsId="account_opening_modal_04"
                  type="submit"
                  disabled={isSubmitting}
                  className="w-full py-4 rounded-xl text-slate-950 font-bold text-sm shadow-lg hover:scale-[1.02] transition-all duration-300 flex items-center justify-center space-x-2 disabled:opacity-50 disabled:pointer-events-none"
                  style={{ backgroundImage: `linear-gradient(to right, ${brandColorFrom}, ${brandColorTo})` }}
                >
                  {isSubmitting ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      <span>Allocating Liquid Line...</span>
                    </>
                  ) : (
                    <>
                      <span>Validate & Provision Account</span>
                      <ArrowRight className="w-4 h-4" />
                    </>
                  )}
                </AnalyticsButton>
                
                <p className="text-[11px] text-center text-slate-500">
                  All shared deposit structures adhere continuously to national risk frameworks.
                </p>
              </div>
            </form>
          )}
        </div>

      </div>
    </div>
  );
}

export default AccountOpeningModal;
