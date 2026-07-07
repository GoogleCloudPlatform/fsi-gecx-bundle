import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
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
import { 
  getAccountsSummary, 
  getDepositTransactions, 
  getCreditCardTransactions,
  provisionMyDemo
} from '../utils/api.js';
import BillPayModal from './BillPayModal.jsx';
import SpendAnalyzerModal from './SpendAnalyzerModal.jsx';

function AccountsView({ fbUser, customerProfile }) {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const [accountsData, setAccountsData] = useState(null);
  const [selectedAccountId, setSelectedAccountId] = useState(null);
  const [selectedAccountType, setSelectedAccountType] = useState(null); // 'checking' | 'savings' | 'credit'
  const [transactions, setTransactions] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isTxsLoading, setIsTxsLoading] = useState(false);
  const [isBillPayOpen, setIsBillPayOpen] = useState(false);
  const [showDocModal, setShowDocModal] = useState(false);
  const [isSpendAnalyzerOpen, setIsSpendAnalyzerOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [isFilterMenuOpen, setIsFilterMenuOpen] = useState(false);
  const [activeFilterTab, setActiveFilterTab] = useState('category');
  const [filters, setFilters] = useState({
    category: 'ALL',
    minAmount: '',
    maxAmount: '',
    dateRange: 'ALL',
    card: 'ALL',
    statement: 'ALL'
  });

  const idParam = searchParams.get('id');
  const typeParam = searchParams.get('type');

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

  useEffect(() => {
    if (fbUser) {
      fetchSummaryAndTransactions();
    }
  }, [fbUser, fetchSummaryAndTransactions]);

  // Synchronize dynamic routing query param selectors
  useEffect(() => {
    if (idParam && typeParam && accountsData) {
      setSelectedAccountId(idParam);
      setSelectedAccountType(typeParam);
      loadTransactions(idParam, typeParam);
    } else {
      setSelectedAccountId(null);
      setSelectedAccountType(null);
      setTransactions([]);
    }
  }, [idParam, typeParam, accountsData, loadTransactions]);

  const handleSelectAccount = (accountId, type) => {
    setSearchParams({ id: accountId, type: type });
  };

  const activeFilterCount = useMemo(() => {
    let count = 0;
    if (filters.category !== 'ALL') count++;
    if (filters.minAmount !== '' || filters.maxAmount !== '') count++;
    if (filters.dateRange !== 'ALL') count++;
    if (filters.card !== 'ALL') count++;
    if (filters.statement !== 'ALL') count++;
    return count;
  }, [filters]);

  const resetFilters = () => {
    setFilters({
      category: 'ALL',
      minAmount: '',
      maxAmount: '',
      dateRange: 'ALL',
      card: 'ALL',
      statement: 'ALL'
    });
  };

  const filteredTransactions = useMemo(() => {
    let result = transactions;

    // 1. Search Query
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter(tx => {
        const desc = (tx.description || '').toLowerCase();
        const cat = (tx.personal_finance_category?.primary || '').toLowerCase();
        const amount = String(tx.amount || (tx.amount_cents ? Math.abs(tx.amount_cents)/100 : ''));
        return desc.includes(q) || cat.includes(q) || amount.includes(q);
      });
    }

    // 2. Category Filter
    if (filters.category !== 'ALL') {
      result = result.filter(tx => {
        const rawCat = (tx.personal_finance_category?.primary || 'GENERAL').toUpperCase();
        return rawCat === filters.category;
      });
    }

    // 3. Amount Filter (Min/Max in dollars)
    if (filters.minAmount !== '') {
      const minVal = parseFloat(filters.minAmount);
      if (!isNaN(minVal)) {
        result = result.filter(tx => {
          const amt = tx.amount_cents !== undefined ? Math.abs(tx.amount_cents)/100 : Math.abs(tx.amount || 0);
          return amt >= minVal;
        });
      }
    }
    if (filters.maxAmount !== '') {
      const maxVal = parseFloat(filters.maxAmount);
      if (!isNaN(maxVal)) {
        result = result.filter(tx => {
          const amt = tx.amount_cents !== undefined ? Math.abs(tx.amount_cents)/100 : Math.abs(tx.amount || 0);
          return amt <= maxVal;
        });
      }
    }

    // 4. Date Range Filter
    if (filters.dateRange !== 'ALL') {
      const now = new Date();
      result = result.filter(tx => {
        const txDateStr = tx.posted_at || tx.created_at || tx.timestamp;
        if (!txDateStr) return true;
        const txDate = new Date(txDateStr);
        if (filters.dateRange === '30D') {
          const thirtyDaysAgo = new Date();
          thirtyDaysAgo.setDate(now.getDate() - 30);
          return txDate >= thirtyDaysAgo;
        } else if (filters.dateRange === '60D') {
          const sixtyDaysAgo = new Date();
          sixtyDaysAgo.setDate(now.getDate() - 60);
          return txDate >= sixtyDaysAgo;
        } else if (filters.dateRange === 'YTD') {
          const startOfYear = new Date(now.getFullYear(), 0, 1);
          return txDate >= startOfYear;
        }
        return true;
      });
    }

    // 5. Card Filter
    if (filters.card !== 'ALL') {
      result = result.filter(tx => {
        const cardStr = tx.last_four ? `...${tx.last_four}` : (tx.card_last_four ? `...${tx.card_last_four}` : '');
        if (!cardStr) return true;
        return cardStr.includes(filters.card) || (filters.card === '2304' && cardStr.includes('2304')) || (filters.card === '2344' && cardStr.includes('2344'));
      });
    }

    // 6. Statement Period Filter
    if (filters.statement !== 'ALL') {
      result = result.filter(tx => {
        if (filters.statement === 'CURRENT') {
          return tx.pending || !tx.description?.includes('Statement');
        } else if (filters.statement === 'JUNE_2026') {
          const txDateStr = tx.posted_at || tx.created_at;
          if (!txDateStr) return true;
          return txDateStr.includes('-06-') || txDateStr.includes('/06/');
        } else if (filters.statement === 'MAY_2026') {
          const txDateStr = tx.posted_at || tx.created_at;
          if (!txDateStr) return true;
          return txDateStr.includes('-05-') || txDateStr.includes('/05/');
        }
        return true;
      });
    }

    return result;
  }, [transactions, searchQuery, filters]);

  const handleBackToMaster = () => {
    setSearchParams({});
  };

  if (!fbUser) {
    return (
      <div className="min-h-screen bg-slate-50 dark:bg-slate-950 flex items-center justify-center p-6 text-center text-slate-900 dark:text-white">
        <div className="max-w-md space-y-6">
          <Lock className="w-16 h-16 text-rose-550 dark:text-rose-500 mx-auto animate-pulse" />
          <h2 className="text-3xl font-extrabold text-slate-900 dark:text-white">Access Denied</h2>
          <p className="text-slate-600 dark:text-slate-400">Please sign in via your identity provider to access secure bank accounts.</p>
          <button 
            onClick={() => navigate('/')}
            className="px-6 py-3 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 font-semibold hover:bg-slate-200 dark:hover:bg-slate-700 transition cursor-pointer"
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
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 pt-28 pb-12 px-6 md:pt-36 md:pb-20 md:px-12">
      <div className="max-w-6xl mx-auto space-y-12">
        {/* Header bar */}
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-6 pb-6 border-b border-slate-200 dark:border-slate-900">
          <div>
            <span className="text-emerald-600 dark:text-emerald-400 font-semibold text-xs uppercase tracking-wider">Member Dashboard</span>
            <h1 className="text-3xl md:text-5xl font-black text-slate-900 dark:text-white mt-1">
              {selectedAccountId ? "Account Ledger" : "My Accounts"}
            </h1>
            <p className="text-slate-600 dark:text-slate-400 text-sm mt-1">
              Hello, <span className="text-emerald-600 dark:text-emerald-400 font-bold">{customerProfile?.first_name || fbUser.email.split('@')[0]}</span>
            </p>
          </div>

          {selectedAccountId && (
            <button 
              onClick={handleBackToMaster}
              className="flex items-center space-x-2 px-5 py-2.5 rounded-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-850 hover:text-slate-900 dark:hover:text-white transition-all cursor-pointer font-semibold text-sm shadow-sm"
            >
              <ArrowLeft className="w-4 h-4" />
              <span>Back to Accounts</span>
            </button>
          )}
        </div>

        {isLoading ? (
          <div className="py-24 flex flex-col items-center justify-center space-y-4">
            <div className="w-12 h-12 rounded-full border-4 border-slate-200 dark:border-slate-800 border-t-emerald-500 animate-spin"></div>
            <span className="text-slate-500 dark:text-slate-400 font-medium">Decrypting account ledgers...</span>
          </div>
        ) : !hasAccounts ? (
          <div className="max-w-md mx-auto bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-slate-850 rounded-3xl p-8 text-center space-y-6 shadow-xl dark:shadow-none">
            <Shield className="w-16 h-16 text-emerald-600 dark:text-emerald-400 mx-auto animate-pulse" />
            <h2 className="text-2xl font-bold text-slate-900 dark:text-white">Setup Your Sandbox</h2>
            <p className="text-slate-605 dark:text-slate-400 text-sm leading-relaxed">
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
                  className="bg-white dark:bg-slate-900/40 backdrop-blur-md border border-slate-200 dark:border-slate-800/60 hover:border-teal-500/40 rounded-3xl p-8 hover:-translate-y-1 transition-all duration-300 cursor-pointer flex flex-col justify-between group h-64 shadow-sm dark:shadow-none hover:shadow-teal-500/5"
                >
                  <div className="flex justify-between items-start">
                    <div className="w-12 h-12 rounded-2xl bg-teal-500/10 border border-teal-500/20 flex items-center justify-center text-teal-600 dark:text-teal-400">
                      <CreditCard className="w-6 h-6" />
                    </div>
                    <span className="text-[10px] font-bold text-teal-600 dark:text-teal-400 bg-teal-500/10 border border-teal-500/20 px-2.5 py-1 rounded-full uppercase">Checking</span>
                  </div>
                  <div>
                    <h3 className="text-lg font-bold text-slate-900 dark:text-white group-hover:text-teal-600 dark:group-hover:text-teal-300 transition-colors">{acc.product_name}</h3>
                    <p className="text-xs text-slate-450 dark:text-slate-500 mt-1">**** {acc.account_number.slice(-4)}</p>
                  </div>
                  <div className="border-t border-slate-200 dark:border-slate-850/80 pt-4 flex justify-between items-end">
                    <span className="text-xs text-slate-500 dark:text-slate-400">Balance</span>
                    <span className="text-2xl font-extrabold text-slate-900 dark:text-white">${(acc.cleared_balance_cents / 100).toLocaleString('en-US', { minimumFractionDigits: 2 })}</span>
                  </div>
                </div>
              ))}

              {/* Savings Account Card */}
              {savingsAccounts.map((acc, idx) => (
                <div 
                  key={`sav-${idx}`} 
                  onClick={() => handleSelectAccount(acc.account_id, 'savings')}
                  className="bg-white dark:bg-slate-900/40 backdrop-blur-md border border-slate-200 dark:border-slate-800/60 hover:border-emerald-500/40 rounded-3xl p-8 hover:-translate-y-1 transition-all duration-300 cursor-pointer flex flex-col justify-between group h-64 shadow-sm dark:shadow-none hover:shadow-emerald-500/5"
                >
                  <div className="flex justify-between items-start">
                    <div className="w-12 h-12 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-600 dark:text-emerald-400">
                      <Percent className="w-6 h-6" />
                    </div>
                    <span className="text-[10px] font-bold text-emerald-650 dark:text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2.5 py-1 rounded-full uppercase">Savings</span>
                  </div>
                  <div>
                    <h3 className="text-lg font-bold text-slate-900 dark:text-white group-hover:text-emerald-650 dark:group-hover:text-emerald-300 transition-colors">{acc.product_name}</h3>
                    <p className="text-xs text-slate-450 dark:text-slate-500 mt-1">Active High-Yield Growth</p>
                  </div>
                  <div className="border-t border-slate-200 dark:border-slate-850/80 pt-4 flex justify-between items-end">
                    <span className="text-xs text-slate-550 dark:text-slate-400">Balance</span>
                    <span className="text-2xl font-extrabold text-slate-900 dark:text-white">${(acc.cleared_balance_cents / 100).toLocaleString('en-US', { minimumFractionDigits: 2 })}</span>
                  </div>
                </div>
              ))}

              {/* Credit Card Account Card */}
              {creditAccounts.map((acc, idx) => (
                <div 
                  key={`cred-${idx}`} 
                  onClick={() => handleSelectAccount(acc.account_id, 'credit')}
                  className="bg-white dark:bg-slate-900/40 backdrop-blur-md border border-slate-200 dark:border-slate-800/60 hover:border-indigo-500/40 rounded-3xl p-8 hover:-translate-y-1 transition-all duration-300 cursor-pointer flex flex-col justify-between group h-64 shadow-sm dark:shadow-none hover:shadow-indigo-500/5"
                >
                  <div className="flex justify-between items-start">
                    <div className="w-12 h-12 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-650 dark:text-indigo-400">
                      <CreditCard className="w-6 h-6" />
                    </div>
                    <span className="text-[10px] font-bold text-indigo-650 dark:text-indigo-400 bg-indigo-500/10 border border-indigo-500/20 px-2.5 py-1 rounded-full uppercase">Credit Card</span>
                  </div>
                  <div>
                    <h3 className="text-lg font-bold text-slate-900 dark:text-white group-hover:text-indigo-650 dark:group-hover:text-indigo-300 transition-colors">Nova Everyday Visa</h3>
                    <p className="text-xs text-slate-450 dark:text-slate-500 mt-1">**** {acc.cards?.[0]?.last_four || "9921"}</p>
                  </div>
                  <div className="border-t border-slate-200 dark:border-slate-850/80 pt-4 flex justify-between items-end">
                    <span className="text-xs text-slate-550 dark:text-slate-400">Current Balance</span>
                    <span className="text-2xl font-extrabold text-slate-900 dark:text-slate-200">${(acc.cleared_balance_cents / 100).toLocaleString('en-US', { minimumFractionDigits: 2 })}</span>
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
            <div className="bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-slate-850 rounded-3xl p-8 shadow-sm dark:shadow-none">
              {selectedAccountType === 'credit' ? (
                /* CREDIT ACCOUNT DETAILS HEADER */
                <div className="space-y-8">
                  <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                    <div>
                      <h2 className="text-2xl font-bold text-slate-900 dark:text-white">Nova Everyday Visa</h2>
                      <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">Status: <span className="text-emerald-600 dark:text-emerald-400 font-semibold">{activeAccountObj?.status}</span></p>
                    </div>
                    <div className="flex items-center gap-3">
                      <button 
                        onClick={() => setIsBillPayOpen(true)}
                        className="px-6 py-2.5 rounded-full bg-emerald-500 text-slate-955 font-bold hover:scale-[1.02] active:scale-95 transition-all text-sm cursor-pointer"
                      >
                        Pay Bill
                      </button>
                      <button 
                        onClick={() => setShowDocModal(true)}
                        className="px-6 py-2.5 rounded-full bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 font-semibold hover:bg-slate-205 dark:hover:bg-slate-700 transition text-sm flex items-center gap-1.5 cursor-pointer"
                      >
                        <span>View Details</span>
                        <ExternalLink className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>

                  {/* 4 Balances Grid */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-6 pt-6 border-t border-slate-205 dark:border-slate-850/80">
                    <div>
                      <div className="text-xs text-slate-500 dark:text-slate-400 font-medium">Last Statement Balance</div>
                      <div className="text-xl font-bold text-slate-800 dark:text-slate-350 mt-1">
                        ${(Math.abs(transactions.find(tx => tx.description === "LATE_FEE")?.amount_cents || 3500) / 100).toFixed(2)}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-slate-500 dark:text-slate-400 font-medium">Current Balance</div>
                      <div className="text-xl font-extrabold text-slate-900 dark:text-white mt-1">
                        ${((activeAccountObj?.cleared_balance_cents || 0) / 100).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-slate-500 dark:text-slate-400 font-medium">Available Credit</div>
                      <div className="text-xl font-bold text-emerald-600 dark:text-emerald-400 mt-1">
                        ${((activeAccountObj?.available_credit_cents || 0) / 100).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-slate-500 dark:text-slate-400 font-medium">Credit Line</div>
                      <div className="text-xl font-bold text-slate-800 dark:text-slate-300 mt-1">
                        ${((activeAccountObj?.credit_limit_cents || 0) / 100).toLocaleString()}
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                /* DEPOSIT ACCOUNT DETAILS HEADER */
                <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
                  <div>
                    <h2 className="text-2xl font-bold text-slate-900 dark:text-white">{activeAccountObj?.product_name}</h2>
                    <div className="flex flex-wrap items-center gap-4 text-xs text-slate-500 dark:text-slate-400 mt-2">
                      <span>Account Number: <span className="text-slate-805 dark:text-slate-300 font-semibold">{activeAccountObj?.account_number}</span></span>
                      <span className="hidden md:inline text-slate-300 dark:text-slate-700">|</span>
                      <span>Routing Number: <span className="text-slate-805 dark:text-slate-300 font-semibold">{activeAccountObj?.routing_number || "010088889"}</span></span>
                      <span className="hidden md:inline text-slate-300 dark:text-slate-700">|</span>
                      <span>Status: <span className="text-emerald-605 dark:text-emerald-400 font-semibold">{activeAccountObj?.status}</span></span>
                    </div>
                  </div>
                  <div className="text-left md:text-right">
                    <div className="text-xs text-slate-505 dark:text-slate-400 font-medium">Cleared Balance</div>
                    <div className="text-3xl font-black text-slate-900 dark:text-white mt-1">
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
                    <h4 className="font-bold text-slate-900 dark:text-white text-sm">Boost your savings yields with 4.85% APY</h4>
                    <p className="text-xs text-slate-600 dark:text-slate-400 mt-0.5">Maximize returns on your excess checking funds. Zero fees, zero limits.</p>
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
            <div className="bg-white dark:bg-slate-900/40 border border-slate-205 dark:border-slate-850 rounded-3xl p-6 md:p-8 shadow-sm dark:shadow-none">
              <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-6">Transaction History</h3>

              {/* Capital One inspired Sleek Search & Filter Top Bar */}
              <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 mb-6">
                <div className="relative flex-1">
                  <input
                    type="text"
                    placeholder="Search/filter transactions..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full pl-9 pr-4 py-2.5 bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/80 rounded-xl text-sm text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/50 dark:focus:ring-blue-400/50 transition-all shadow-sm"
                  />
                  <svg className="w-4 h-4 text-slate-400 absolute left-3 top-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                  {searchQuery && (
                    <button
                      onClick={() => setSearchQuery('')}
                      className="absolute right-3 top-2.5 text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors cursor-pointer"
                    >
                      Clear
                    </button>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setIsFilterMenuOpen(!isFilterMenuOpen)}
                    className={`flex items-center gap-1.5 px-4 py-2.5 rounded-xl text-sm font-semibold transition-all shadow-sm cursor-pointer border ${
                      isFilterMenuOpen || activeFilterCount > 0
                        ? 'bg-blue-50 dark:bg-blue-900/30 border-blue-500 text-blue-600 dark:text-blue-400'
                        : 'bg-slate-50 dark:bg-slate-800/60 border-slate-200 dark:border-slate-700/80 text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700'
                    }`}
                  >
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
                    </svg>
                    <span>Filter</span>
                    {activeFilterCount > 0 && (
                      <span className="ml-1 px-1.5 py-0.2 rounded-full bg-blue-600 text-white text-[11px] font-bold">
                        {activeFilterCount}
                      </span>
                    )}
                  </button>

                  {selectedAccountType === 'credit' && (
                    <button
                      onClick={() => setIsSpendAnalyzerOpen(true)}
                      className="flex items-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-sm font-bold shadow-sm hover:shadow transition-all cursor-pointer"
                    >
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 3.055A9.001 9.001 0 1020.945 13H11V3.055z" />
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M20.488 9H15V3.512A9.025 9.025 0 0120.488 9z" />
                      </svg>
                      <span>View spend analyzer</span>
                    </button>
                  )}
                </div>
              </div>

              {/* Capital One Inspired Interactive Filter Submenu Panel */}
              {isFilterMenuOpen && (
                <div className="mb-8 p-6 bg-slate-50/95 dark:bg-slate-900/95 border border-slate-200 dark:border-slate-800 rounded-3xl shadow-xl animate-fadeIn space-y-6">
                  {/* Filter Submenu Tabs Bar */}
                  <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 dark:border-slate-800 pb-4">
                    <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0">
                      {[
                        { id: 'category', label: 'Category', icon: '🏷️' },
                        { id: 'amount', label: 'Amount', icon: '💰' },
                        { id: 'date', label: 'Custom Dates', icon: '📅' },
                        { id: 'card', label: 'Cardholder', icon: '💳' },
                        { id: 'statement', label: 'Statement Period', icon: '📄' }
                      ].map(tab => (
                        <button
                          key={tab.id}
                          onClick={() => setActiveFilterTab(tab.id)}
                          className={`flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-bold transition-all cursor-pointer ${
                            activeFilterTab === tab.id
                              ? 'bg-blue-600 text-white shadow-sm'
                              : 'bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700'
                          }`}
                        >
                          <span>{tab.icon}</span>
                          <span>{tab.label}</span>
                          {((tab.id === 'category' && filters.category !== 'ALL') ||
                            (tab.id === 'amount' && (filters.minAmount !== '' || filters.maxAmount !== '')) ||
                            (tab.id === 'date' && filters.dateRange !== 'ALL') ||
                            (tab.id === 'card' && filters.card !== 'ALL') ||
                            (tab.id === 'statement' && filters.statement !== 'ALL')) && (
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
                          )}
                        </button>
                      ))}
                    </div>
                    {activeFilterCount > 0 && (
                      <button
                        onClick={resetFilters}
                        className="text-xs font-bold text-rose-600 dark:text-rose-400 hover:underline cursor-pointer flex items-center gap-1"
                      >
                        <span>Reset All Filters ({activeFilterCount})</span>
                      </button>
                    )}
                  </div>

                  {/* Active Tab Control Content */}
                  <div className="pt-1">
                    {activeFilterTab === 'category' && (
                      <div className="space-y-3">
                        <label className="block text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                          Filter by Spending Category
                        </label>
                        <div className="flex flex-wrap gap-2">
                          {[
                            { id: 'ALL', label: 'All Categories' },
                            { id: 'GROCERY', label: 'Grocery' },
                            { id: 'DINING', label: 'Dining' },
                            { id: 'OTHER_TRAVEL', label: 'Travel & Flights' },
                            { id: 'GAS_AUTOMOTIVE', label: 'Gas / Automotive' },
                            { id: 'MERCHANDISE', label: 'Merchandise & Stores' },
                            { id: 'HEALTHCARE', label: 'Healthcare' },
                            { id: 'FEES', label: 'Fees & Interest' },
                            { id: 'OTHER', label: 'Other & Entertainment' }
                          ].map(cat => (
                            <button
                              key={cat.id}
                              onClick={() => setFilters(prev => ({ ...prev, category: cat.id }))}
                              className={`px-4 py-2 rounded-xl text-xs font-bold border transition-all cursor-pointer ${
                                filters.category === cat.id
                                  ? 'bg-blue-500/10 dark:bg-blue-500/20 border-blue-500 text-blue-600 dark:text-blue-400 shadow-sm'
                                  : 'bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:border-slate-300 dark:hover:border-slate-600'
                              }`}
                            >
                              {cat.label}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}

                    {activeFilterTab === 'amount' && (
                      <div className="space-y-4 max-w-lg">
                        <label className="block text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                          Filter by Transaction Amount Range ($)
                        </label>
                        <div className="flex items-center gap-3">
                          <div className="flex-1">
                            <span className="block text-[11px] font-semibold text-slate-500 mb-1">Min Amount ($)</span>
                            <input
                              type="number"
                              placeholder="0.00"
                              value={filters.minAmount}
                              onChange={(e) => setFilters(prev => ({ ...prev, minAmount: e.target.value }))}
                              className="w-full bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-xl px-3 py-2 text-sm font-semibold text-slate-900 dark:text-white"
                            />
                          </div>
                          <span className="text-slate-400 font-bold mt-5">—</span>
                          <div className="flex-1">
                            <span className="block text-[11px] font-semibold text-slate-500 mb-1">Max Amount ($)</span>
                            <input
                              type="number"
                              placeholder="1000.00"
                              value={filters.maxAmount}
                              onChange={(e) => setFilters(prev => ({ ...prev, maxAmount: e.target.value }))}
                              className="w-full bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-xl px-3 py-2 text-sm font-semibold text-slate-900 dark:text-white"
                            />
                          </div>
                        </div>
                        <div className="flex flex-wrap gap-2 pt-1">
                          <button
                            onClick={() => setFilters(prev => ({ ...prev, minAmount: '', maxAmount: '25' }))}
                            className="px-3.5 py-1.5 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-xs font-semibold text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 cursor-pointer"
                          >
                            Under $25
                          </button>
                          <button
                            onClick={() => setFilters(prev => ({ ...prev, minAmount: '25', maxAmount: '100' }))}
                            className="px-3.5 py-1.5 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-xs font-semibold text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 cursor-pointer"
                          >
                            $25 - $100
                          </button>
                          <button
                            onClick={() => setFilters(prev => ({ ...prev, minAmount: '100', maxAmount: '' }))}
                            className="px-3.5 py-1.5 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-xs font-semibold text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 cursor-pointer"
                          >
                            Over $100
                          </button>
                          <button
                            onClick={() => setFilters(prev => ({ ...prev, minAmount: '', maxAmount: '' }))}
                            className="px-3.5 py-1.5 bg-slate-200 dark:bg-slate-700 rounded-xl text-xs font-bold text-slate-700 dark:text-slate-200 hover:bg-slate-300 dark:hover:bg-slate-600 cursor-pointer"
                          >
                            Clear Amount
                          </button>
                        </div>
                      </div>
                    )}

                    {activeFilterTab === 'date' && (
                      <div className="space-y-3">
                        <label className="block text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                          Filter by Custom Date Range
                        </label>
                        <div className="flex flex-wrap gap-2">
                          {[
                            { id: 'ALL', label: 'All Time' },
                            { id: '30D', label: 'Last 30 Days' },
                            { id: '60D', label: 'Last 60 Days' },
                            { id: 'YTD', label: 'Year to Date (YTD)' }
                          ].map(d => (
                            <button
                              key={d.id}
                              onClick={() => setFilters(prev => ({ ...prev, dateRange: d.id }))}
                              className={`px-4 py-2 rounded-xl text-xs font-bold border transition-all cursor-pointer ${
                                filters.dateRange === d.id
                                  ? 'bg-blue-500/10 dark:bg-blue-500/20 border-blue-500 text-blue-600 dark:text-blue-400 shadow-sm'
                                  : 'bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:border-slate-300 dark:hover:border-slate-600'
                              }`}
                            >
                              {d.label}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}

                    {activeFilterTab === 'card' && (
                      <div className="space-y-3">
                        <label className="block text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                          Filter by Authorized Cardholder
                        </label>
                        <div className="flex flex-wrap gap-2">
                          {[
                            { id: 'ALL', label: 'All Cards & Account Users' },
                            { id: '2304', label: 'Erik V. ...2304 (Primary)' },
                            { id: '2344', label: 'Erik V. ...2344 (Virtual Card)' },
                            { id: '8234', label: 'Jane D. ...8234 (Authorized User)' }
                          ].map(c => (
                            <button
                              key={c.id}
                              onClick={() => setFilters(prev => ({ ...prev, card: c.id }))}
                              className={`px-4 py-2 rounded-xl text-xs font-bold border transition-all cursor-pointer ${
                                filters.card === c.id
                                  ? 'bg-blue-500/10 dark:bg-blue-500/20 border-blue-500 text-blue-600 dark:text-blue-400 shadow-sm'
                                  : 'bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:border-slate-300 dark:hover:border-slate-600'
                              }`}
                            >
                              {c.label}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}

                    {activeFilterTab === 'statement' && (
                      <div className="space-y-3">
                        <label className="block text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                          Filter by Billing Statement Period
                        </label>
                        <div className="flex flex-wrap gap-2">
                          {[
                            { id: 'ALL', label: 'All Statements' },
                            { id: 'CURRENT', label: 'Current Open Statement (Since Last Statement)' },
                            { id: 'JUNE_2026', label: 'June 2026 Statement (Closed)' },
                            { id: 'MAY_2026', label: 'May 2026 Statement (Closed)' }
                          ].map(s => (
                            <button
                              key={s.id}
                              onClick={() => setFilters(prev => ({ ...prev, statement: s.id }))}
                              className={`px-4 py-2 rounded-xl text-xs font-bold border transition-all cursor-pointer ${
                                filters.statement === s.id
                                  ? 'bg-blue-500/10 dark:bg-blue-500/20 border-blue-500 text-blue-600 dark:text-blue-400 shadow-sm'
                                  : 'bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:border-slate-300 dark:hover:border-slate-600'
                              }`}
                            >
                              {s.label}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Filter Submenu Footer */}
                  <div className="flex items-center justify-between pt-4 border-t border-slate-200 dark:border-slate-800 text-xs">
                    <span className="text-slate-600 dark:text-slate-300 font-semibold">
                      Showing <strong className="text-slate-900 dark:text-white font-bold">{filteredTransactions.length}</strong> matching transactions
                    </span>
                    <button
                      onClick={() => setIsFilterMenuOpen(false)}
                      className="px-5 py-2.5 rounded-xl bg-slate-900 dark:bg-slate-700 hover:bg-slate-800 dark:hover:bg-slate-600 text-white font-bold transition-all cursor-pointer shadow-sm"
                    >
                      Apply & Close Panel
                    </button>
                  </div>
                </div>
              )}

              {isTxsLoading ? (
                <div className="py-12 flex flex-col items-center justify-center space-y-3">
                  <div className="w-8 h-8 rounded-full border-2 border-slate-200 dark:border-slate-700 border-t-emerald-500 animate-spin"></div>
                  <span className="text-xs text-slate-500 dark:text-slate-400 font-semibold">Tailing transaction ledgers...</span>
                </div>
              ) : filteredTransactions.length === 0 ? (
                <div className="py-16 text-center space-y-2">
                  <Activity className="w-10 h-10 text-slate-405 dark:text-slate-600 mx-auto" />
                  <p className="text-slate-500 dark:text-slate-400 text-sm">No transactions found matching your criteria.</p>
                </div>
              ) : (
                /* TABLE RENDER */
                <div className="overflow-x-auto">
                  {selectedAccountType === 'credit' ? (
                    /* CREDIT CARD BLOTTER: Pending holds list, followed by Posted ledger entries. */
                    <div className="space-y-8">
                      {/* PENDING TRANSACTIONS HOLD CONTAINER */}
                      {filteredTransactions.filter(t => t.pending).length > 0 && (
                        <div className="space-y-3">
                          <div className="text-xs font-bold text-amber-600 dark:text-amber-400 uppercase tracking-wider flex items-center gap-1.5">
                            <span className="w-2 h-2 rounded-full bg-amber-500 dark:bg-amber-400 animate-pulse"></span>
                            <span>Pending Authorizations</span>
                          </div>
                          <div className="overflow-x-auto">
                            <table className="w-full text-left text-sm border-collapse table-fixed">
                              <thead>
                                <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-500 dark:text-slate-400 font-semibold text-xs">
                                  <th className="pb-2 font-semibold w-[14%]">Date</th>
                                  <th className="pb-2 font-semibold w-[32%]">Description</th>
                                  <th className="pb-2 font-semibold w-[22%]">Category</th>
                                  <th className="pb-2 font-semibold w-[18%]">Card</th>
                                  <th className="pb-2 font-semibold text-right w-[14%]">Amount</th>
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-slate-200 dark:divide-slate-800/50">
                                {filteredTransactions.filter(t => t.pending).map((tx, idx) => {
                                  const isLateFee = tx.description === "LATE_FEE" || tx.merchant_name === "LATE_FEE";
                                  const isCredit = (tx.amount_cents !== undefined && tx.amount_cents < 0) || tx.description?.toUpperCase().includes('OFFER');
                                  const catLabel = tx.personal_finance_category?.primary 
                                    ? tx.personal_finance_category.primary.split('_').map(w => w.charAt(0) + w.slice(1).toLowerCase()).join(' ')
                                    : "Fees";
                                  const amountVal = Math.abs(tx.amount || (tx.amount_cents ? tx.amount_cents / 100 : 0));
                                  return (
                                    <tr key={`pending-${idx}`} className="hover:bg-slate-100/50 dark:hover:bg-slate-900/20 transition-colors">
                                      <td className="py-3 text-xs text-slate-500 dark:text-slate-400 italic w-[14%]">Pending</td>
                                      <td className="py-3 font-medium text-slate-800 dark:text-slate-300 flex items-center gap-2 w-[32%]">
                                        <span>{tx.description}</span>
                                        {isLateFee && (
                                          <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded bg-rose-500/10 border border-rose-500/20 text-rose-500 dark:text-rose-400">Action Required</span>
                                        )}
                                      </td>
                                      <td className="py-3 w-[22%]">
                                        <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700/80 text-slate-700 dark:text-slate-300">
                                          {catLabel}
                                        </span>
                                      </td>
                                      <td className="py-3 text-xs text-slate-500 dark:text-slate-400 font-medium w-[18%]">
                                        {tx.cardholder_name || "Erik V."} ...{tx.last_four || "2304"}
                                      </td>
                                      <td className={`py-3 text-right font-bold text-sm w-[14%] ${isCredit ? 'text-emerald-600 dark:text-emerald-400 italic' : isLateFee ? 'text-rose-600 dark:text-rose-400' : 'text-slate-800 dark:text-slate-300'}`}>
                                        {isCredit ? '-' : ''}${amountVal.toFixed(2)}
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
                        <div className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Posted Transactions Since Last Statement</div>
                        <div className="overflow-x-auto">
                          <table className="w-full text-left text-sm border-collapse table-fixed">
                            <thead>
                              <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-500 dark:text-slate-400 font-semibold text-xs">
                                <th className="pb-4 font-semibold w-[14%]">Posting Date</th>
                                <th className="pb-4 font-semibold w-[32%]">Description</th>
                                <th className="pb-4 font-semibold w-[22%]">Category</th>
                                <th className="pb-4 font-semibold w-[18%]">Card</th>
                                <th className="pb-4 font-semibold text-right w-[14%]">Amount</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-200 dark:divide-slate-800/50">
                              {filteredTransactions.filter(t => !t.pending).map((tx, idx) => {
                                const isPayment = tx.transaction_type === "DIRECTDEPOSIT" || (tx.amount_cents !== undefined ? tx.amount_cents > 0 : tx.amount < 0) || tx.description?.toUpperCase().includes('PAYMENT');
                                const catLabel = tx.personal_finance_category?.primary 
                                  ? tx.personal_finance_category.primary.split('_').map(w => w.charAt(0) + w.slice(1).toLowerCase()).join(' ')
                                  : "General";
                                const amountVal = Math.abs(tx.amount || (tx.amount_cents ? tx.amount_cents / 100 : 0));
                                return (
                                  <tr key={`posted-${idx}`} className="hover:bg-slate-100/50 dark:hover:bg-slate-900/30 transition-colors">
                                    <td className="py-4 text-xs text-slate-500 dark:text-slate-400 w-[14%]">
                                      {tx.posted_timestamp || tx.posted_at ? new Date(tx.posted_timestamp || tx.posted_at).toLocaleDateString() : "Pending"}
                                    </td>
                                    <td className="py-4 font-medium text-slate-800 dark:text-slate-200 w-[32%]">{tx.description}</td>
                                    <td className="py-4 w-[22%]">
                                      <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700/80 text-slate-700 dark:text-slate-300">
                                        {catLabel}
                                      </span>
                                    </td>
                                    <td className="py-4 text-xs text-slate-500 dark:text-slate-400 font-medium w-[18%]">
                                      {tx.cardholder_name || "Erik V."} ...{tx.last_four || "2304"}
                                    </td>
                                    <td className={`py-4 text-right font-bold text-sm w-[14%] ${isPayment ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-800 dark:text-slate-200'}`}>
                                      {isPayment ? '-' : ''}${amountVal.toFixed(2)}
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
                    /* DEPOSIT BLOTTER: Separated by Pending vs Posted with search & filter */
                    <div className="space-y-8">
                      {filteredTransactions.filter(t => t.pending).length > 0 && (
                        <div className="space-y-3">
                          <div className="text-xs font-bold text-amber-600 dark:text-amber-400 uppercase tracking-wider flex items-center gap-1.5">
                            <span className="w-2 h-2 rounded-full bg-amber-500 dark:bg-amber-400 animate-pulse"></span>
                            <span>Pending Authorizations</span>
                          </div>
                          <table className="w-full text-left text-sm border-collapse">
                            <thead>
                              <tr className="border-b border-slate-200 dark:border-slate-850 text-slate-500 dark:text-slate-400 font-semibold text-xs">
                                <th className="pb-4 font-semibold">Date</th>
                                <th className="pb-4 font-semibold">Description</th>
                                <th className="pb-4 font-semibold">Type</th>
                                <th className="pb-4 font-semibold text-right">Amount</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-200 dark:divide-slate-850/50">
                              {filteredTransactions.filter(t => t.pending).map((tx, idx) => {
                                const isIncoming = tx.entry_type === "DEBIT";
                                const amountVal = Math.abs(tx.amount || (tx.amount_cents ? tx.amount_cents / 100 : 0));
                                return (
                                  <tr key={`dep-pen-${idx}`} className="hover:bg-slate-100/50 dark:hover:bg-slate-900/30 transition-colors">
                                    <td className="py-4 text-xs text-slate-450 dark:text-slate-500 italic">Pending</td>
                                    <td className="py-4 font-medium text-slate-800 dark:text-slate-200">{tx.description}</td>
                                    <td className="py-4 text-xs text-slate-500 dark:text-slate-400">Hold</td>
                                    <td className={`py-4 text-right font-bold text-sm ${isIncoming ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-850 dark:text-slate-300'}`}>
                                      {isIncoming ? '' : '-'}${amountVal.toFixed(2)}
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      )}

                      <div className="space-y-3 pt-2">
                        <div className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Posted Transactions</div>
                        <table className="w-full text-left text-sm border-collapse">
                          <thead>
                            <tr className="border-b border-slate-200 dark:border-slate-850 text-slate-500 dark:text-slate-400 font-semibold text-xs">
                              <th className="pb-4 font-semibold">Posting Date</th>
                              <th className="pb-4 font-semibold">Description</th>
                              <th className="pb-4 font-semibold">Type</th>
                              <th className="pb-4 font-semibold text-right">Amount</th>
                              <th className="pb-4 font-semibold text-right">Available Balance</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-200 dark:divide-slate-850/50">
                            {filteredTransactions.filter(t => !t.pending).map((tx, idx) => {
                              const isIncoming = tx.entry_type === "DEBIT";
                              const amountVal = Math.abs(tx.amount || (tx.amount_cents ? tx.amount_cents / 100 : 0));
                              return (
                                <tr key={`dep-pos-${idx}`} className="hover:bg-slate-100/50 dark:hover:bg-slate-900/30 transition-colors">
                                  <td className="py-4 text-xs text-slate-500 dark:text-slate-400">
                                    {tx.posted_at ? new Date(tx.posted_at).toLocaleDateString() : "Pending"}
                                  </td>
                                  <td className="py-4 font-medium text-slate-800 dark:text-slate-200">{tx.description}</td>
                                  <td className="py-4 text-xs text-slate-500 dark:text-slate-400">
                                    {isIncoming ? "Direct Deposit" : "ACH Withdrawal"}
                                  </td>
                                  <td className={`py-4 text-right font-bold text-sm ${isIncoming ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-850 dark:text-slate-300'}`}>
                                    {isIncoming ? '' : '-'}${amountVal.toFixed(2)}
                                  </td>
                                  <td className="py-4 text-right text-slate-800 dark:text-slate-300">
                                    ${(tx.running_balance_cents !== undefined ? tx.running_balance_cents / 100 : 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>
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

      {/* Spend Analyzer Modal Overlay */}
      {isSpendAnalyzerOpen && (
        <SpendAnalyzerModal 
          isOpen={isSpendAnalyzerOpen}
          onClose={() => setIsSpendAnalyzerOpen(false)}
          transactions={transactions}
        />
      )}

      {/* Card Terms and Details Modal */}
      {showDocModal && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-6 z-50 animate-fade-in">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl max-w-lg w-full p-8 space-y-6 shadow-2xl">
            <div className="flex justify-between items-start">
              <div>
                <h3 className="text-xl font-bold text-slate-900 dark:text-white">Nova Everyday Visa</h3>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">Agreement and product specifications</p>
              </div>
              <button 
                onClick={() => setShowDocModal(false)}
                className="text-slate-400 hover:text-slate-700 dark:hover:text-white transition"
              >
                ✕
              </button>
            </div>
            
            <div className="space-y-4 text-sm text-slate-655 dark:text-slate-300 overflow-y-auto max-h-96 pr-2 leading-relaxed">
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
              className="w-full py-3 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-white font-bold hover:bg-slate-200 dark:hover:bg-slate-700 transition cursor-pointer"
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
