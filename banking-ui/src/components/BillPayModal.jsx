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
import { X, CheckCircle2, AlertCircle } from 'lucide-react';
import { payCreditCard } from '../utils/api.js';

export default function BillPayModal({ isOpen, onClose, accountsData, onPaymentSuccess }) {
  if (!isOpen) return null;

  const depositAccounts = accountsData?.deposit_accounts || [];
  const creditAccounts = accountsData?.credit_accounts || [];

  const [selectedSourceId, setSelectedSourceId] = useState(depositAccounts[0]?.account_id || '');
  const [selectedCreditId, setSelectedCreditId] = useState(creditAccounts[0]?.account_id || '');
  const [amountStr, setAmountStr] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  const sourceAccount = depositAccounts.find(a => a.account_id === selectedSourceId);
  const creditAccount = creditAccounts.find(a => a.account_id === selectedCreditId);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMsg('');
    setSuccessMsg('');

    const amountCents = Math.round(parseFloat(amountStr) * 100);
    if (isNaN(amountCents) || amountCents <= 0) {
      setErrorMsg("Please enter a valid payment amount.");
      return;
    }

    if (!sourceAccount) {
      setErrorMsg("Please select a valid funding account.");
      return;
    }

    if (!creditAccount) {
      setErrorMsg("Please select a valid target credit account.");
      return;
    }

    if (amountCents > sourceAccount.cleared_balance_cents) {
      setErrorMsg(`Insufficient funds. Your selected funding account has $${(sourceAccount.cleared_balance_cents / 100).toFixed(2)}.`);
      return;
    }

    if (amountCents > creditAccount.cleared_balance_cents) {
      setErrorMsg(`Payment amount exceeds outstanding credit card balance of $${(creditAccount.cleared_balance_cents / 100).toFixed(2)}.`);
      return;
    }

    try {
      setIsSubmitting(true);
      await payCreditCard({
        source_account_id: selectedSourceId,
        credit_account_id: selectedCreditId,
        amount_cents: amountCents
      });
      setSuccessMsg("Payment successfully processed! Balances have been updated.");
      setTimeout(() => {
        onPaymentSuccess();
        onClose();
        setSuccessMsg('');
        setAmountStr('');
      }, 2000);
    } catch (err) {
      setErrorMsg(err.response?.data?.detail || "An unexpected error occurred processing your payment.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-fade-in">
      <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 w-full max-w-md shadow-2xl relative">
        <button 
          onClick={onClose}
          className="absolute top-4 right-4 text-slate-400 hover:text-white transition-colors"
        >
          <X size={20} />
        </button>

        <h3 className="text-lg font-bold text-white mb-2">Credit Card Bill Payment</h3>
        <p className="text-xs text-slate-400 mb-6">Pay off your outstanding credit line using your checking or savings deposits.</p>

        {successMsg ? (
          <div className="bg-emerald-950/20 border border-emerald-800/30 text-emerald-400 p-4 rounded-2xl flex items-center gap-3 text-xs font-semibold mb-4">
            <CheckCircle2 size={16} />
            <span>{successMsg}</span>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            {errorMsg && (
              <div className="bg-rose-950/20 border border-rose-800/30 text-rose-400 p-4 rounded-2xl flex items-center gap-3 text-xs font-semibold">
                <AlertCircle size={16} />
                <span>{errorMsg}</span>
              </div>
            )}

            <div>
              <label className="block text-xs font-bold text-slate-400 mb-1.5 uppercase tracking-wide">Pay From</label>
              <select
                value={selectedSourceId}
                onChange={(e) => setSelectedSourceId(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 text-white rounded-xl px-4 py-3 text-xs font-semibold focus:outline-none focus:border-blue-500"
              >
                {depositAccounts.map(a => (
                  <option key={a.account_id} value={a.account_id}>
                    {a.product_name} (**** {a.account_number.slice(-4)}) - ${(a.cleared_balance_cents / 100).toFixed(2)}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-400 mb-1.5 uppercase tracking-wide">Pay To</label>
              <select
                value={selectedCreditId}
                onChange={(e) => setSelectedCreditId(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 text-white rounded-xl px-4 py-3 text-xs font-semibold focus:outline-none focus:border-blue-500"
              >
                {creditAccounts.map(c => (
                  <option key={c.account_id} value={c.account_id}>
                    Nova Credit Card (Outstanding: ${(c.cleared_balance_cents / 100).toFixed(2)})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-400 mb-1.5 uppercase tracking-wide">Payment Amount ($)</label>
              <input
                type="number"
                step="0.01"
                min="0.01"
                placeholder="0.00"
                value={amountStr}
                onChange={(e) => setAmountStr(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 text-white rounded-xl px-4 py-3 text-xs font-semibold focus:outline-none focus:border-blue-500"
              />
            </div>

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full py-3.5 rounded-xl bg-blue-500 hover:bg-blue-600 text-white font-bold text-xs active:scale-95 transition-all shadow-lg shadow-blue-500/20 disabled:bg-slate-800 disabled:text-slate-500 disabled:cursor-not-allowed"
            >
              {isSubmitting ? "Processing Payment..." : "Submit Payment"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
