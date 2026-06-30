import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  ArrowLeft,
  CreditCard,
  Percent,
  Shield,
  Activity,
  Plus,
  ExternalLink,
  Lock,
  Sparkles,
  TrendingUp,
  AlertCircle
} from 'lucide-react';
import { useSettings } from '../context/SettingsContext.jsx';
import { 
  getAccountsSummary, 
  getDepositTransactions, 
  getCreditCardTransactions,
  payCreditCard,
  provisionMyDemo
} from '../utils/api.js';
import BillPayModal from './BillPayModal.jsx';

function AccountsView({ fbUser, customerProfile }) {
  const navigate = useNavigate();
  const { bankName, brandColorFrom, brandColorTo } = useSettings();

  const [accountsData, setAccountsData] = useState(null);
  const [selectedAccountId, setSelectedAccountId] = useState(null);
  const [selectedAccountType, setSelectedAccountType] = useState(null); // 'checking' | 'savings' | 'credit'
  const [transactions, setTransactions] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isTxsLoading, setIsTxsLoading] = useState(false);
  const [isBillPayOpen, setIsBillPayOpen] = useState(false);
  const [showDocModal, setShowDocModal] = useState(false);

  const fetchSummaryAndTransactions = useCallback(async () => {
    try {
      setIsLoading(true);
      const summary = await getAccountsSummary();
      setAccountsData(summary);
    } catch (err) {
      console.error("Failed to load accounts summary:", err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (fbUser) {
      fetchSummaryAndTransactions();
    }
  }, [fbUser, fetchSummaryAndTransactions]);

  const loadTransactions = useCallback(async (accountId, type) => {
    try {
      setIsTxsLoading(true);
      if (type === 'credit') {
        const txs = await getCreditCardTransactions(null);
        setTransactions(txs || []);
      } else {
        const txs = await getDepositTransactions(accountId);
        setTransactions(txs || []);
      }
    } catch (err) {
      console.error("Failed to load transactions for account:", err);
      setTransactions([]);
    } finally {
      setIsTxsLoading(false);
    }
  }, []);

  const handleSelectAccount = (accountId, type) => {
    setSelectedAccountId(accountId);
    setSelectedAccountType(type);
    loadTransactions(accountId, type);
  };

  const handleBackToMaster = () => {
    setSelectedAccountId(null);
    setSelectedAccountType(null);
    setTransactions([]);
  };

  if (!fbUser) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center p-6 text-center">
        <div className="max-w-md space-y-6">
          <Lock className="w-16 h-16 text-rose-500 mx-auto animate-pulse" />
          <h2 className="text-3xl font-extrabold text-white">Access Denied</h2>
          <p className="text-slate-400">Please sign in via your identity provider to access secure bank accounts.</p>
          <button 
            onClick={() => navigate('/')}
            className="px-6 py-3 rounded-full bg-slate-800 text-slate-200 font-semibold hover:bg-slate-700 transition"
          >
            Back to Home
          </button>
        </div>
      </div>
    );
  }

  const checkingAccounts = accountsData?.deposit_accounts?.filter(a => a.account_type === 'CHECKING') || [];
  const savingsAccounts = accountsData?.deposit_accounts?.filter(a => a.account_type === 'SAVINGS') || [];
  const creditAccounts = accountsData?.credit_accounts || [];
  const hasAccounts = checkingAccounts.length > 0 || savingsAccounts.length > 0 || creditAccounts.length > 0;

  // Find active account object for detail view
  let activeAccountObj = null;
  if (selectedAccountType === 'checking' || selectedAccountType === 'savings') {
    activeAccountObj = accountsData?.deposit_accounts?.find(a => String(a.account_id) === String(selectedAccountId));
  } else if (selectedAccountType === 'credit') {
    activeAccountObj = accountsData?.credit_accounts?.find(a => String(a.account_id) === String(selectedAccountId));
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-6 md:p-12">
      <div className="max-w-6xl mx-auto space-y-12">
        {/* Header bar */}
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-6 pb-6 border-b border-slate-900">
          <div>
            <span className="text-emerald-400 font-semibold text-xs uppercase tracking-wider">Member Dashboard</span>
            <h1 className="text-3xl md:text-5xl font-black text-white mt-1">
              {selectedAccountId ? "Account Ledger" : "My Accounts"}
            </h1>
            <p className="text-slate-400 text-sm mt-1">
              Hello, <span className="text-emerald-400 font-bold">{customerProfile?.first_name || fbUser.email.split('@')[0]}</span>
            </p>
          </div>

          {selectedAccountId && (
            <button 
              onClick={handleBackToMaster}
              className="flex items-center space-x-2 px-5 py-2.5 rounded-full bg-slate-900 border border-slate-800 text-slate-300 hover:bg-slate-850 hover:text-white transition-all cursor-pointer font-semibold text-sm"
            >
              <ArrowLeft className="w-4 h-4" />
              <span>Back to Accounts</span>
            </button>
          )}
        </div>

        {isLoading ? (
          <div className="py-24 flex flex-col items-center justify-center space-y-4">
            <div className="w-12 h-12 rounded-full border-4 border-slate-800 border-t-emerald-500 animate-spin"></div>
            <span className="text-slate-400 font-medium">Decrypting account ledgers...</span>
          </div>
        ) : !hasAccounts ? (
          <div className="max-w-md mx-auto bg-slate-900/60 border border-slate-850 rounded-3xl p-8 text-center space-y-6">
            <Shield className="w-16 h-16 text-emerald-400 mx-auto animate-pulse" />
            <h2 className="text-2xl font-bold text-white">Setup Your Sandbox</h2>
            <p className="text-slate-400 text-sm leading-relaxed">
              Your profile is verified, but you have no active ledger accounts. Provision your isolated personal demo suite to get started.
            </p>
            <button 
              onClick={async () => {
                setIsLoading(true);
                try {
                  await provisionMyDemo();
                  await fetchSummaryAndTransactions();
                } catch (err) {
                  console.error(err);
                } finally {
                  setIsLoading(false);
                }
              }}
              className="w-full py-4 rounded-xl text-slate-950 font-bold bg-gradient-to-r from-emerald-400 to-cyan-400 hover:scale-[1.02] active:scale-95 transition-all shadow-lg"
            >
              Provision Demo Suite
            </button>
          </div>
        ) : !selectedAccountId ? (
          /* MASTER VIEW: Snapshot of accounts */
          <div className="space-y-8">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
              {/* Checking Account Card */}
              {checkingAccounts.map((acc, idx) => (
                <div 
                  key={`chk-${idx}`} 
                  onClick={() => handleSelectAccount(acc.account_id, 'checking')}
                  className="bg-slate-900/40 backdrop-blur-md border border-slate-800/60 hover:border-teal-500/40 rounded-3xl p-8 hover:-translate-y-1 transition-all duration-300 cursor-pointer flex flex-col justify-between group h-64 shadow-xl hover:shadow-teal-500/5"
                >
                  <div className="flex justify-between items-start">
                    <div className="w-12 h-12 rounded-2xl bg-teal-500/10 border border-teal-500/20 flex items-center justify-center text-teal-400">
                      <CreditCard className="w-6 h-6" />
                    </div>
                    <span className="text-[10px] font-bold text-teal-400 bg-teal-500/10 border border-teal-500/20 px-2.5 py-1 rounded-full uppercase">Checking</span>
                  </div>
                  <div>
                    <h3 className="text-lg font-bold text-white group-hover:text-teal-300 transition-colors">{acc.product_name}</h3>
                    <p className="text-xs text-slate-500 mt-1">**** {acc.account_number.slice(-4)}</p>
                  </div>
                  <div className="border-t border-slate-850/80 pt-4 flex justify-between items-end">
                    <span className="text-xs text-slate-400">Balance</span>
                    <span className="text-2xl font-extrabold text-white">${(acc.cleared_balance_cents / 100).toLocaleString('en-US', { minimumFractionDigits: 2 })}</span>
                  </div>
                </div>
              ))}

              {/* Savings Account Card */}
              {savingsAccounts.map((acc, idx) => (
                <div 
                  key={`sav-${idx}`} 
                  onClick={() => handleSelectAccount(acc.account_id, 'savings')}
                  className="bg-slate-900/40 backdrop-blur-md border border-slate-800/60 hover:border-emerald-500/40 rounded-3xl p-8 hover:-translate-y-1 transition-all duration-300 cursor-pointer flex flex-col justify-between group h-64 shadow-xl hover:shadow-emerald-500/5"
                >
                  <div className="flex justify-between items-start">
                    <div className="w-12 h-12 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
                      <Percent className="w-6 h-6" />
                    </div>
                    <span className="text-[10px] font-bold text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2.5 py-1 rounded-full uppercase">Savings</span>
                  </div>
                  <div>
                    <h3 className="text-lg font-bold text-white group-hover:text-emerald-300 transition-colors">{acc.product_name}</h3>
                    <p className="text-xs text-slate-500 mt-1">Active High-Yield Growth</p>
                  </div>
                  <div className="border-t border-slate-850/80 pt-4 flex justify-between items-end">
                    <span className="text-xs text-slate-400">Balance</span>
                    <span className="text-2xl font-extrabold text-white">${(acc.cleared_balance_cents / 100).toLocaleString('en-US', { minimumFractionDigits: 2 })}</span>
                  </div>
                </div>
              ))}

              {/* Credit Card Account Card */}
              {creditAccounts.map((acc, idx) => (
                <div 
                  key={`cred-${idx}`} 
                  onClick={() => handleSelectAccount(acc.account_id, 'credit')}
                  className="bg-slate-900/40 backdrop-blur-md border border-slate-800/60 hover:border-indigo-500/40 rounded-3xl p-8 hover:-translate-y-1 transition-all duration-300 cursor-pointer flex flex-col justify-between group h-64 shadow-xl hover:shadow-indigo-500/5"
                >
                  <div className="flex justify-between items-start">
                    <div className="w-12 h-12 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
                      <CreditCard className="w-6 h-6" />
                    </div>
                    <span className="text-[10px] font-bold text-indigo-400 bg-indigo-500/10 border border-indigo-500/20 px-2.5 py-1 rounded-full uppercase">Credit Card</span>
                  </div>
                  <div>
                    <h3 className="text-lg font-bold text-white group-hover:text-indigo-300 transition-colors">Nova Everyday Visa</h3>
                    <p className="text-xs text-slate-500 mt-1">**** {acc.cards?.[0]?.last_four || "9921"}</p>
                  </div>
                  <div className="border-t border-slate-850/80 pt-4 flex justify-between items-end">
                    <span className="text-xs text-slate-400">Current Balance</span>
                    <span className="text-2xl font-extrabold text-slate-200">${(acc.cleared_balance_cents / 100).toLocaleString('en-US', { minimumFractionDigits: 2 })}</span>
                  </div>
                </div>
              ))}
            </div>

            {/* Personalized Offers Banner directly below account tiles in Master View */}
            <div className="bg-gradient-to-r from-emerald-500/10 to-teal-500/10 border border-emerald-500/25 rounded-3xl p-8 flex flex-col sm:flex-row items-center justify-between gap-6">
              <div className="flex items-center space-x-5">
                <div className="w-14 h-14 rounded-2xl bg-emerald-500/20 flex items-center justify-center text-emerald-400 flex-shrink-0">
                  <Sparkles className="w-7 h-7 animate-pulse" />
                </div>
                <div>
                  <h4 className="font-extrabold text-slate-900 dark:text-white text-base">Earn 4.85% APY on Savings</h4>
                  <p className="text-xs text-slate-650 dark:text-slate-400 mt-1 max-w-xl">Move your idle deposits into our high-yield growth tier. Federally insured, no monthly fees, and instant liquidity.</p>
                </div>
              </div>
              <button 
                onClick={() => {
                  const firstSavings = savingsAccounts[0];
                  if (firstSavings) {
                    handleSelectAccount(firstSavings.account_id, 'savings');
                  }
                }}
                className="px-6 py-3 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold text-sm transition-all cursor-pointer flex-shrink-0"
              >
                Boost Yield Now
              </button>
            </div>
          </div>
        ) : (
          /* DETAIL VIEW */
          <div className="space-y-8">
            {/* 1. Details header block */}
            <div className="bg-slate-900/60 border border-slate-850 rounded-3xl p-8">
              {selectedAccountType === 'credit' ? (
                /* CREDIT ACCOUNT DETAILS HEADER */
                <div className="space-y-8">
                  <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                    <div>
                      <h2 className="text-2xl font-bold text-white">Nova Everyday Visa</h2>
                      <p className="text-xs text-slate-400 mt-1">Status: <span className="text-emerald-400 font-semibold">{activeAccountObj?.status}</span></p>
                    </div>
                    <div className="flex items-center gap-3">
                      <button 
                        onClick={() => setIsBillPayOpen(true)}
                        className="px-6 py-2.5 rounded-full bg-emerald-500 text-slate-950 font-bold hover:scale-[1.02] active:scale-95 transition-all text-sm cursor-pointer"
                      >
                        Pay Bill
                      </button>
                      <button 
                        onClick={() => setShowDocModal(true)}
                        className="px-6 py-2.5 rounded-full bg-slate-800 border border-slate-700 text-slate-200 font-semibold hover:bg-slate-700 transition text-sm flex items-center gap-1.5 cursor-pointer"
                      >
                        <span>View Details</span>
                        <ExternalLink className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>

                  {/* 4 Balances Grid */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-6 pt-6 border-t border-slate-850/80">
                    <div>
                      <div className="text-xs text-slate-400 font-medium">Last Statement Balance</div>
                      <div className="text-xl font-bold text-slate-300 mt-1">
                        ${(Math.abs(transactions.find(tx => tx.description === "LATE_FEE")?.amount_cents || 3500) / 100).toFixed(2)}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-slate-400 font-medium">Current Balance</div>
                      <div className="text-xl font-extrabold text-white mt-1">
                        ${((activeAccountObj?.cleared_balance_cents || 0) / 100).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-slate-400 font-medium">Available Credit</div>
                      <div className="text-xl font-bold text-emerald-400 mt-1">
                        ${((activeAccountObj?.available_credit_cents || 0) / 100).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-slate-400 font-medium">Credit Line</div>
                      <div className="text-xl font-bold text-slate-300 mt-1">
                        ${((activeAccountObj?.credit_limit_cents || 0) / 100).toLocaleString()}
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                /* DEPOSIT ACCOUNT DETAILS HEADER */
                <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
                  <div>
                    <h2 className="text-2xl font-bold text-white">{activeAccountObj?.product_name}</h2>
                    <div className="flex flex-wrap items-center gap-4 text-xs text-slate-400 mt-2">
                      <span>Account Number: <span className="text-slate-300 font-semibold">{activeAccountObj?.account_number}</span></span>
                      <span className="hidden md:inline text-slate-700">|</span>
                      <span>Routing Number: <span className="text-slate-300 font-semibold">{activeAccountObj?.routing_number || "010088889"}</span></span>
                      <span className="hidden md:inline text-slate-700">|</span>
                      <span>Status: <span className="text-emerald-400 font-semibold">{activeAccountObj?.status}</span></span>
                    </div>
                  </div>
                  <div className="text-left md:text-right">
                    <div className="text-xs text-slate-400 font-medium">Cleared Balance</div>
                    <div className="text-3xl font-black text-white mt-1">
                      ${((activeAccountObj?.cleared_balance_cents || 0) / 100).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* 2. Personalized Offers Banner (Credit Card only - between balances and blotter) */}
            {selectedAccountType === 'credit' && (
              <div className="bg-gradient-to-r from-emerald-500/10 to-teal-500/10 border border-emerald-500/25 rounded-3xl p-6 flex flex-col sm:flex-row items-center justify-between gap-4">
                <div className="flex items-center space-x-4">
                  <div className="w-12 h-12 rounded-2xl bg-emerald-500/20 flex items-center justify-center text-emerald-400 flex-shrink-0">
                    <Sparkles className="w-6 h-6 animate-pulse" />
                  </div>
                  <div>
                    <h4 className="font-bold text-white text-sm">Boost your savings yields with 4.85% APY</h4>
                    <p className="text-xs text-slate-400 mt-0.5">Maximize returns on your excess checking funds. Zero fees, zero limits.</p>
                  </div>
                </div>
                <button 
                  onClick={() => {
                    const firstSavings = accountsData?.deposit_accounts?.find(a => a.account_type === 'SAVINGS');
                    if (firstSavings) {
                      handleSelectAccount(firstSavings.account_id, 'savings');
                    }
                  }}
                  className="px-5 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 text-xs font-bold transition-all cursor-pointer flex-shrink-0"
                >
                  Boost Yield Now
                </button>
              </div>
            )}

            {/* 3. Transaction Blotter View */}
            <div className="bg-slate-900/40 border border-slate-850 rounded-3xl p-6 md:p-8">
              <h3 className="text-lg font-bold text-white mb-6">Transaction History</h3>

              {isTxsLoading ? (
                <div className="py-12 flex flex-col items-center justify-center space-y-3">
                  <div className="w-8 h-8 rounded-full border-2 border-slate-700 border-t-emerald-500 animate-spin"></div>
                  <span className="text-xs text-slate-400 font-semibold">Tailing transaction ledgers...</span>
                </div>
              ) : transactions.length === 0 ? (
                <div className="py-16 text-center space-y-2">
                  <Activity className="w-10 h-10 text-slate-600 mx-auto" />
                  <p className="text-slate-400 text-sm">No transactions found for this account.</p>
                </div>
              ) : (
                /* TABLE RENDER */
                <div className="overflow-x-auto">
                  {selectedAccountType === 'credit' ? (
                    /* CREDIT CARD BLOTTER: Pending holds list, followed by Posted ledger entries. Outgoing positive (no plus), Incoming negative (payments). */
                    <div className="space-y-8">
                      {/* PENDING TRANSACTIONS HOLD CONTAINER */}
                      {transactions.filter(t => t.pending).length > 0 && (
                        <div className="space-y-3">
                          <div className="text-xs font-bold text-amber-400 uppercase tracking-wider flex items-center gap-1.5">
                            <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse"></span>
                            <span>Pending Authorizations</span>
                          </div>
                          <div className="overflow-x-auto">
                            <table className="w-full text-left text-sm border-collapse">
                              <thead>
                                <tr className="border-b border-slate-850 text-slate-500 font-semibold text-xs">
                                  <th className="pb-2 font-semibold">Date</th>
                                  <th className="pb-2 font-semibold">Description</th>
                                  <th className="pb-2 font-semibold">Category</th>
                                  <th className="pb-2 font-semibold text-right">Amount</th>
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-slate-850/30">
                                {transactions.filter(t => t.pending).map((tx, idx) => {
                                  const isLateFee = tx.description === "LATE_FEE";
                                  const catLabel = tx.personal_finance_category?.primary 
                                    ? tx.personal_finance_category.primary.split('_').map(w => w.charAt(0) + w.slice(1).toLowerCase()).join(' ')
                                    : "Fees";
                                  return (
                                    <tr key={`pending-${idx}`} className="hover:bg-slate-900/20 transition-colors">
                                      <td className="py-3 text-xs text-slate-500 italic">Pending</td>
                                      <td className="py-3 font-medium text-slate-300 flex items-center gap-2">
                                        <span>{tx.description}</span>
                                        {isLateFee && (
                                          <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded bg-rose-500/10 border border-rose-500/20 text-rose-400">Action Required</span>
                                        )}
                                      </td>
                                      <td className="py-3 text-xs text-slate-400">{catLabel}</td>
                                      <td className={`py-3 text-right font-bold text-sm ${isLateFee ? 'text-rose-400' : 'text-slate-300'}`}>
                                        ${(tx.amount || (tx.amount_cents / 100)).toFixed(2)}
                                      </td>
                                    </tr>
                                  );
                                })}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      )}

                      {/* POSTED TRANSACTIONS LEDGER */}
                      <div className="space-y-3 pt-4">
                        <div className="text-xs font-bold text-slate-400 uppercase tracking-wider">Posted Transactions Since Last Statement</div>
                        <div className="overflow-x-auto">
                          <table className="w-full text-left text-sm border-collapse">
                            <thead>
                              <tr className="border-b border-slate-850 text-slate-400 font-semibold text-xs">
                                <th className="pb-4 font-semibold">Posting Date</th>
                                <th className="pb-4 font-semibold">Description</th>
                                <th className="pb-4 font-semibold">Category</th>
                                <th className="pb-4 font-semibold text-right">Amount</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-850/50">
                              {transactions.filter(t => !t.pending).map((tx, idx) => {
                                const isPayment = tx.transaction_type === "DIRECTDEPOSIT" || tx.amount_cents > 0;
                                const catLabel = tx.personal_finance_category?.primary 
                                  ? tx.personal_finance_category.primary.split('_').map(w => w.charAt(0) + w.slice(1).toLowerCase()).join(' ')
                                  : "General";
                                return (
                                  <tr key={`posted-${idx}`} className="hover:bg-slate-900/30 transition-colors">
                                    <td className="py-4 text-xs text-slate-400">
                                      {tx.posted_timestamp ? new Date(tx.posted_timestamp).toLocaleDateString() : "Pending"}
                                    </td>
                                    <td className="py-4 font-medium text-slate-200">{tx.description}</td>
                                    <td className="py-4">
                                      <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-slate-800 border border-slate-700/80 text-slate-300">
                                        {catLabel}
                                      </span>
                                    </td>
                                    <td className={`py-4 text-right font-bold text-sm ${isPayment ? 'text-emerald-400' : 'text-slate-200'}`}>
                                      {isPayment ? '-' : ''}${Math.abs(tx.amount || (tx.amount_cents / 100)).toFixed(2)}
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    </div>
                  ) : (
                    /* DEPOSIT BLOTTER: Traditional columns. Incoming positive (no sign), Outgoing negative. */
                    <table className="w-full text-left text-sm border-collapse">
                      <thead>
                        <tr className="border-b border-slate-850 text-slate-400 font-semibold text-xs">
                          <th className="pb-4 font-semibold">Posting Date</th>
                          <th className="pb-4 font-semibold">Description</th>
                          <th className="pb-4 font-semibold">Type</th>
                          <th className="pb-4 font-semibold text-right">Amount</th>
                          <th className="pb-4 font-semibold text-right">Available Balance</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-850/50">
                        {transactions.map((tx, idx) => {
                          const isIncoming = tx.entry_type === "DEBIT"; // DEBIT increases checking assets!
                          const amountVal = Math.abs(tx.amount_cents) / 100;
                          
                          return (
                            <tr key={idx} className="hover:bg-slate-900/30 transition-colors">
                              <td className="py-4 text-xs text-slate-400">
                                {tx.posted_at ? new Date(tx.posted_at).toLocaleDateString() : "Pending"}
                              </td>
                              <td className="py-4 font-medium text-slate-200">
                                {tx.description}
                              </td>
                              <td className="py-4 text-xs text-slate-400">
                                {isIncoming ? "Direct Deposit" : "ACH Withdrawal"}
                              </td>
                              <td className={`py-4 text-right font-bold text-sm ${isIncoming ? 'text-emerald-400' : 'text-slate-300'}`}>
                                {isIncoming ? '' : '-'}${amountVal.toFixed(2)}
                              </td>
                              <td className="py-4 text-right text-slate-300">
                                ${(tx.running_balance_cents / 100).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Bill Pay Modal Overlay */}
      {isBillPayOpen && (
        <BillPayModal 
          isOpen={isBillPayOpen}
          onClose={() => setIsBillPayOpen(false)}
          creditAccounts={creditAccounts}
          depositAccounts={checkingAccounts}
          onSuccess={fetchSummaryAndTransactions}
        />
      )}

      {/* Card Terms and Details Modal */}
      {showDocModal && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-6 z-50 animate-fade-in">
          <div className="bg-slate-900 border border-slate-800 rounded-3xl max-w-lg w-full p-8 space-y-6">
            <div className="flex justify-between items-start">
              <div>
                <h3 className="text-xl font-bold text-white">Nova Everyday Visa</h3>
                <p className="text-xs text-slate-400 mt-1">Agreement and product specifications</p>
              </div>
              <button 
                onClick={() => setShowDocModal(false)}
                className="text-slate-400 hover:text-white transition"
              >
                ✕
              </button>
            </div>
            
            <div className="space-y-4 text-sm text-slate-300 overflow-y-auto max-h-96 pr-2 leading-relaxed">
              <p>
                <strong>Interest Rates and Interest Charges:</strong> Annual Percentage Rate (APR) for Purchases is 18.99% to 24.99% variable, based on your creditworthiness.
              </p>
              <p>
                <strong>Late Payment Fee:</strong> Up to $35.00 per occurrence. Late payments may trigger internal collections workflows or supervisor audit reviews.
              </p>
              <p>
                <strong>Personalized Rebates:</strong> Reversals of Late Payment fees can be requested via our automated conversational support systems or telephone banking systems.
              </p>
            </div>

            <button 
              onClick={() => setShowDocModal(false)}
              className="w-full py-3 rounded-xl bg-slate-800 text-white font-bold hover:bg-slate-700 transition"
            >
              Close Details
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default AccountsView;
