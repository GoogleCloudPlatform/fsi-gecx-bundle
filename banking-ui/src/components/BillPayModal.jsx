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

import { useMoneyLocale, presentationLocales, moneyCopy } from '../utils/moneyLocale.js';
import React, { useState, useEffect, useMemo, useRef } from 'react';
import { X, CheckCircle2, AlertCircle } from 'lucide-react';
import { payCreditCard } from '../utils/api.js';
import { formatMoney, parseMoneyInput, paymentIntent } from '../utils/money.js';
import AnalyticsButton from './AnalyticsButton.jsx';


export default function BillPayModal({ 
  isOpen, 
  onClose, 
  accountsData, 
  creditAccounts: directCreditAccounts, 
  depositAccounts: directDepositAccounts,
  onPaymentSuccess,
  onSuccess 
}) {
  const [locale, setLocale] = useMoneyLocale();
  const copy = moneyCopy(locale);
  const depositAccounts = useMemo(
    () => directDepositAccounts || accountsData?.deposit_accounts || [],
    [accountsData?.deposit_accounts, directDepositAccounts]
  );
  const creditAccounts = useMemo(
    () => directCreditAccounts || accountsData?.credit_accounts || [],
    [accountsData?.credit_accounts, directCreditAccounts]
  );
  const handleSuccess = onPaymentSuccess || onSuccess || (() => {});

  const [selectedSourceId, setSelectedSourceId] = useState(depositAccounts[0]?.account_id || '');
  const [selectedCreditId, setSelectedCreditId] = useState(creditAccounts[0]?.account_id || '');
  const [amountStr, setAmountStr] = useState('');
  const retryIntent = useRef(null);
  useEffect(() => {
    if (!isOpen && retryIntent.current?.completed) retryIntent.current = null;
  }, [isOpen]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  // Keep selected values synced if accounts list loaded asynchronously
  useEffect(() => {
    if (depositAccounts.length > 0 && !selectedSourceId) {
      setSelectedSourceId(depositAccounts[0].account_id);
    }
  }, [depositAccounts, selectedSourceId]);

  useEffect(() => {
    if (creditAccounts.length > 0 && !selectedCreditId) {
      setSelectedCreditId(creditAccounts[0].account_id);
    }
  }, [creditAccounts, selectedCreditId]);

  const sourceAccount = depositAccounts.find(a => a.account_id === selectedSourceId);
  const creditAccount = creditAccounts.find(a => a.account_id === selectedCreditId);

  if (!isOpen) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMsg('');
    setSuccessMsg('');

    if (!sourceAccount) {
      setErrorMsg({ code: "sourceRequired" });
      return;
    }

    if (!creditAccount) {
      setErrorMsg({ code: "cardRequired" });
      return;
    }

    try {
      let money;
      try { money = parseMoneyInput(amountStr, sourceAccount.currency_code); }
      catch { throw new Error("invalid"); }
      if (money.amount_minor <= 0) throw new Error("positive");
      if (creditAccount.currency_code !== money.currency_code) throw new Error("mismatch");
      if (money.amount_minor > sourceAccount.cleared_balance.amount_minor) {
        throw Object.assign(new Error("funds"), { money: sourceAccount.cleared_balance });
      }
      if (money.amount_minor > creditAccount.cleared_balance.amount_minor) {
        throw Object.assign(new Error("overpayment"), { money: creditAccount.cleared_balance });
      }
      const request = { source_account_id: selectedSourceId, credit_account_id: selectedCreditId, money };
      retryIntent.current = paymentIntent(retryIntent.current, request);
      setIsSubmitting(true);
      const result = await payCreditCard(request, retryIntent.current.key);
      retryIntent.current.completed = true;
      setSuccessMsg(result.money);
      setTimeout(() => {
        handleSuccess();
        onClose();
        setSuccessMsg('');
        setAmountStr('');
      }, 2000);
    } catch (err) {
      setErrorMsg({ code: err.response ? (err.response.status === 409 ? "conflict" : "failure")
        : Object.hasOwn(copy, err.message) ? err.message : "failure", money: err.money });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-fade-in">
      <div role="dialog" aria-modal="true" aria-label={copy.title}
        className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl p-6 w-full max-w-md max-h-[90vh] overflow-y-auto shadow-2xl relative">
        <AnalyticsButton
          analyticsId="bill_pay_modal_01"
          aria-label={copy.close}
          onClick={onClose}
          className="absolute top-4 right-4 text-slate-400 hover:text-slate-600 dark:hover:text-white transition-colors"
        >
          <X size={20} />
        </AnalyticsButton>

        <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-2">{copy.title}</h3>
        <p className="text-xs text-slate-500 dark:text-slate-400 mb-6">{copy.description}</p>

        <label className="block text-xs text-slate-500 mb-4">
          {copy.language}
          <select aria-label={copy.language} value={locale} onChange={e => setLocale(e.target.value)}
            className="ml-2 rounded border border-slate-300 bg-white dark:bg-slate-900 p-1">
            {Object.entries(presentationLocales).map(([code, label]) => <option key={code} value={code}>{label}</option>)}
          </select>
        </label>
        {successMsg ? (
          <div className="bg-emerald-500/10 dark:bg-emerald-950/20 border border-emerald-500/20 dark:border-emerald-800/30 text-emerald-600 dark:text-emerald-400 p-4 rounded-2xl flex items-center gap-3 text-xs font-semibold mb-4">
            <CheckCircle2 size={16} />
            <span>{copy.success} {formatMoney(successMsg, locale)}</span>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            {errorMsg && (
              <div className="bg-rose-500/10 dark:bg-rose-950/20 border border-rose-500/20 dark:border-rose-800/30 text-rose-600 dark:text-rose-400 p-4 rounded-2xl flex items-center gap-3 text-xs font-semibold">
                <AlertCircle size={16} />
                <span>{copy[errorMsg.code]} {errorMsg.money && formatMoney(errorMsg.money, locale)}</span>
              </div>
            )}

            <div>
              <label className="block text-xs font-bold text-slate-500 dark:text-slate-400 mb-1.5 uppercase tracking-wide">{copy.from}</label>
              <select
                aria-label={copy.from}
                value={selectedSourceId}
                onChange={(e) => setSelectedSourceId(e.target.value)}
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white rounded-xl px-4 py-3 text-xs font-semibold focus:outline-none focus:border-blue-500"
              >
                {depositAccounts.length === 0 ? (
                  <option value="">{copy.noDeposits}</option>
                ) : (
                  depositAccounts.map(a => (
                    <option key={a.account_id} value={a.account_id}>
                      {a.product_name} (**** {a.account_number?.slice(-4) ?? '----'})
                    </option>
                  ))
                )}
              </select>
              <p className="mt-1 text-xs text-slate-600">{copy.available}: {formatMoney(sourceAccount?.cleared_balance, locale)}</p>
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-500 dark:text-slate-400 mb-1.5 uppercase tracking-wide">{copy.to}</label>
              <select
                aria-label={copy.to}
                value={selectedCreditId}
                onChange={(e) => setSelectedCreditId(e.target.value)}
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white rounded-xl px-4 py-3 text-xs font-semibold focus:outline-none focus:border-blue-500"
              >
                {creditAccounts.length === 0 ? (
                  <option value="">{copy.noCards}</option>
                ) : (
                  creditAccounts.map(c => (
                    <option key={c.account_id} value={c.account_id}>
                      {copy.card} (**** {c.account_id.slice(-4)})
                    </option>
                  ))
                )}
              </select>
              <p className="mt-1 text-xs text-slate-600">{copy.outstanding}: {formatMoney(creditAccount?.cleared_balance, locale)}</p>
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-500 dark:text-slate-400 mb-1.5 uppercase tracking-wide">{copy.amount} ({sourceAccount?.currency_code || "—"})</label>
              <input
                type="text"
                inputMode="decimal"
                placeholder="0"
                aria-label={copy.amount}
                aria-describedby="money-input-hint"
                value={amountStr}
                onChange={(e) => setAmountStr(e.target.value)}
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white rounded-xl px-4 py-3 text-xs font-semibold focus:outline-none focus:border-blue-500"
              />
            </div>

            <p id="money-input-hint" className="text-xs text-slate-500">{copy.hint}</p>

            <AnalyticsButton
              analyticsId="bill_pay_modal_02"
              type="submit"
              disabled={isSubmitting || depositAccounts.length === 0 || creditAccounts.length === 0}
              className="w-full py-3.5 rounded-xl bg-blue-500 hover:bg-blue-600 text-white font-bold text-xs active:scale-95 transition-all shadow-lg shadow-blue-500/20 disabled:bg-slate-100 dark:disabled:bg-slate-800 disabled:text-slate-400 dark:disabled:text-slate-500 disabled:cursor-not-allowed"
            >
              {isSubmitting ? copy.processing : copy.submit}
            </AnalyticsButton>
          </form>
        )}
      </div>
    </div>
  );
}
