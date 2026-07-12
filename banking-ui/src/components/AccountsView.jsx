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
  AlertCircle,
  Bell,
  CalendarDays,
  ChevronDown,
  ChevronRight,
  FileText,
  Plane,
  RefreshCw,
  Search,
  ShieldAlert,
  SlidersHorizontal,
  Wallet
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
  const [activeLedgerTab, setActiveLedgerTab] = useState('ALL');
  const [expandedTransactionKey, setExpandedTransactionKey] = useState(null);
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

  const checkingAccounts = accountsData?.deposit_accounts?.filter(a => a.account_type === 'CHECKING') || [];
  const savingsAccounts = accountsData?.deposit_accounts?.filter(a => a.account_type === 'SAVINGS') || [];
  const creditAccounts = accountsData?.credit_accounts || [];
  const hasAccounts = checkingAccounts.length > 0 || savingsAccounts.length > 0 || creditAccounts.length > 0;
  let activeAccountObj = null;
  if (selectedAccountType === 'checking' || selectedAccountType === 'savings') {
    activeAccountObj = accountsData?.deposit_accounts?.find(a => String(a.account_id) === String(selectedAccountId));
  } else if (selectedAccountType === 'credit') {
    activeAccountObj = accountsData?.credit_accounts?.find(a => String(a.account_id) === String(selectedAccountId));
  }

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

  const cardFilterOptions = useMemo(() => {
    const optionMap = new Map();
    (activeAccountObj?.cards || []).forEach((card) => {
      const id = String(card.card_id || card.id || card.card_token || card.last_four);
      optionMap.set(id, {
        id,
        lastFour: card.last_four,
        label: `${card.cardholder_name || 'Cardholder'} ...${card.last_four}${card.is_virtual ? ' (Virtual Card)' : ' (Primary)'}`,
      });
    });
    transactions.forEach((tx) => {
      const lastFour = tx.last_four || tx.card_last_four;
      if (!lastFour) return;
      const id = String(tx.card_id || tx.card_token || lastFour);
      if (!optionMap.has(id)) {
        optionMap.set(id, {
          id,
          lastFour,
          label: `${tx.cardholder_name || 'Cardholder'} ...${lastFour}`,
        });
      }
    });
    return Array.from(optionMap.values()).sort((a, b) => a.label.localeCompare(b.label));
  }, [activeAccountObj, transactions]);

  const formatTransactionCardLabel = (tx) => {
    const lastFour = tx.last_four || tx.card_last_four;
    if (!lastFour) return 'Card unavailable';
    return `${tx.cardholder_name || 'Cardholder'} ...${lastFour}`;
  };

  const formatMoneyFromCents = (cents = 0) => (
    (Math.abs(cents) / 100).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  );

  const formatDateShort = (value) => {
    if (!value) return 'Not set';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return 'Not set';
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };

  const getTransactionAmountCents = (tx) => (
    tx.amount_cents !== undefined ? tx.amount_cents : Math.round((tx.amount || 0) * 100)
  );

  const getTransactionKey = (tx, idx, prefix = 'tx') => (
    tx.transaction_id || tx.authorization_id || tx.retrieval_reference_number || tx.id || `${prefix}-${idx}`
  );

  const formatCategoryLabel = (tx, fallback = 'General') => {
    const rawCat = tx.personal_finance_category?.primary || fallback;
    return rawCat.split('_').map(w => w.charAt(0) + w.slice(1).toLowerCase()).join(' ');
  };

  const isTravelTransaction = (tx) => {
    const haystack = `${tx.description || ''} ${tx.merchant_category_code || ''} ${tx.personal_finance_category?.primary || ''}`.toUpperCase();
    return haystack.includes('TRAVEL') || ['4511', '7011', '4121'].includes(String(tx.merchant_category_code || ''));
  };

  const isSubscriptionTransaction = (tx) => {
    const haystack = `${tx.description || ''} ${tx.merchant_slug || ''} ${tx.personal_finance_category?.primary || ''}`.toUpperCase();
    return haystack.includes('SUBSCRIPTION') || haystack.includes('STREAMING') || haystack.includes('NETFLIX') || haystack.includes('SPOTIFY') || haystack.includes('PEACOCK');
  };

  const isDisputeCandidate = (tx) => {
    const haystack = `${tx.status || ''} ${tx.description || ''}`.toUpperCase();
    return haystack.includes('DISPUTE') || haystack.includes('FRAUD');
  };

  const filteredTransactions = useMemo(() => {
    let result = transactions;

    if (activeLedgerTab !== 'ALL') {
      result = result.filter(tx => {
        const amountCents = Math.abs(getTransactionAmountCents(tx));
        if (activeLedgerTab === 'PENDING') return Boolean(tx.pending);
        if (activeLedgerTab === 'POSTED') return !tx.pending;
        if (activeLedgerTab === 'DISPUTES') return isDisputeCandidate(tx);
        if (activeLedgerTab === 'SUBSCRIPTIONS') return isSubscriptionTransaction(tx);
        if (activeLedgerTab === 'TRAVEL') return isTravelTransaction(tx);
        if (activeLedgerTab === 'LARGE') return amountCents >= 50000;
        return true;
      });
    }

    // 1. Search Query
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter(tx => {
        const desc = `${tx.description || ''} ${tx.merchant_slug || ''} ${tx.merchant_id || ''} ${tx.merchant_store_id || ''}`.toLowerCase();
        const cat = (tx.personal_finance_category?.primary || '').toLowerCase();
        const amount = String(Math.abs(getTransactionAmountCents(tx)) / 100);
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
          const amt = Math.abs(getTransactionAmountCents(tx)) / 100;
          return amt >= minVal;
        });
      }
    }
    if (filters.maxAmount !== '') {
      const maxVal = parseFloat(filters.maxAmount);
      if (!isNaN(maxVal)) {
        result = result.filter(tx => {
          const amt = Math.abs(getTransactionAmountCents(tx)) / 100;
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
        const selected = cardFilterOptions.find(option => option.id === filters.card);
        const txCardId = String(tx.card_id || tx.card_token || tx.last_four || tx.card_last_four || '');
        const txLastFour = String(tx.last_four || tx.card_last_four || '');
        return txCardId === filters.card || Boolean(selected?.lastFour && txLastFour === String(selected.lastFour));
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
  }, [transactions, activeLedgerTab, searchQuery, filters, cardFilterOptions]);

  const ledgerQuickTabs = useMemo(() => {
    const counts = transactions.reduce((acc, tx) => {
      acc.ALL += 1;
      if (tx.pending) acc.PENDING += 1;
      if (!tx.pending) acc.POSTED += 1;
      if (isDisputeCandidate(tx)) acc.DISPUTES += 1;
      if (isSubscriptionTransaction(tx)) acc.SUBSCRIPTIONS += 1;
      if (isTravelTransaction(tx)) acc.TRAVEL += 1;
      if (Math.abs(getTransactionAmountCents(tx)) >= 50000) acc.LARGE += 1;
      return acc;
    }, { ALL: 0, PENDING: 0, POSTED: 0, DISPUTES: 0, SUBSCRIPTIONS: 0, TRAVEL: 0, LARGE: 0 });

    return [
      { id: 'ALL', label: 'All', count: counts.ALL },
      { id: 'PENDING', label: 'Pending', count: counts.PENDING },
      { id: 'POSTED', label: 'Posted', count: counts.POSTED },
      { id: 'DISPUTES', label: 'Disputes', count: counts.DISPUTES },
      { id: 'SUBSCRIPTIONS', label: 'Subscriptions', count: counts.SUBSCRIPTIONS },
      { id: 'TRAVEL', label: 'Travel', count: counts.TRAVEL },
      { id: 'LARGE', label: 'Large purchases', count: counts.LARGE },
    ];
  }, [transactions]);

  const creditSummary = useMemo(() => {
    if (selectedAccountType !== 'credit' || !activeAccountObj) return null;
    const creditLimitCents = activeAccountObj.credit_limit_cents || 0;
    const currentBalanceCents = activeAccountObj.cleared_balance_cents || 0;
    const statementBalanceCents = activeAccountObj.statement_balance_cents ?? currentBalanceCents;
    const minimumDueCents = activeAccountObj.minimum_due_cents ?? Math.min(3500, Math.max(0, statementBalanceCents));
    const availableCreditCents = activeAccountObj.available_credit_cents || 0;
    const utilization = creditLimitCents > 0
      ? Math.min(100, Math.max(0, Math.round(((creditLimitCents - availableCreditCents) / creditLimitCents) * 100)))
      : 0;
    return {
      currentBalanceCents,
      statementBalanceCents,
      minimumDueCents,
      availableCreditCents,
      creditLimitCents,
      utilization,
      paymentDueDate: activeAccountObj.payment_due_date,
      statementCloseDate: activeAccountObj.statement_close_date,
    };
  }, [selectedAccountType, activeAccountObj]);

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
              {creditAccounts.map((acc, idx) => {
                const activeCards = (acc.cards || []).filter(card => card.status === 'ACTIVE');
                const primaryCard = activeCards.find(card => !card.is_virtual) || activeCards[0] || acc.cards?.[0];
                const virtualCards = (acc.cards || []).filter(card => card.is_virtual && card.status === 'ACTIVE');
                const walletQueued = (acc.cards || []).some(card => card.wallet_provisioning_status);
                return (
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
                    <p className="text-xs text-slate-450 dark:text-slate-500 mt-1">**** {primaryCard?.last_four || "9921"}</p>
                    {(virtualCards.length > 0 || walletQueued) && (
                      <p className="mt-2 text-[10px] font-bold text-emerald-700 dark:text-emerald-300">
                        {virtualCards.length > 0 ? `${virtualCards.length} virtual card${virtualCards.length === 1 ? '' : 's'} active` : 'Wallet provisioning queued'}
                      </p>
                    )}
                  </div>
                  <div className="border-t border-slate-200 dark:border-slate-850/80 pt-4 flex justify-between items-end">
                    <span className="text-xs text-slate-550 dark:text-slate-400">Current Balance</span>
                    <span className="text-2xl font-extrabold text-slate-900 dark:text-slate-200">${(acc.cleared_balance_cents / 100).toLocaleString('en-US', { minimumFractionDigits: 2 })}</span>
                  </div>
                </div>
                );
              })}
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
                <div className="space-y-6">
                  <div className="flex flex-col lg:flex-row justify-between items-start lg:items-center gap-5">
                    <div>
                      <h2 className="text-2xl font-bold text-slate-900 dark:text-white">Nova Everyday Visa</h2>
                      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                        <span className="rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300 px-2.5 py-1 font-bold uppercase">
                          {activeAccountObj?.status}
                        </span>
                        <span className="text-slate-500 dark:text-slate-400">
                          Statement closes {formatDateShort(creditSummary?.statementCloseDate)}
                        </span>
                      </div>
                    </div>
                    <div className="flex flex-wrap items-center gap-3">
                      <button 
                        onClick={() => setIsBillPayOpen(true)}
                        className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-emerald-500 text-slate-955 font-bold hover:bg-emerald-400 active:scale-95 transition-all text-sm cursor-pointer shadow-sm"
                      >
                        <CreditCard className="w-4 h-4" />
                        <span>Pay Bill</span>
                      </button>
                      <button 
                        onClick={() => setShowDocModal(true)}
                        className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 font-semibold hover:bg-slate-205 dark:hover:bg-slate-700 transition text-sm cursor-pointer"
                      >
                        <FileText className="w-4 h-4" />
                        <span>Statements</span>
                      </button>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-3 xl:grid-cols-6 gap-4 pt-6 border-t border-slate-205 dark:border-slate-850/80">
                    {[
                      { label: 'Current balance', value: `$${formatMoneyFromCents(creditSummary?.currentBalanceCents)}`, strong: true },
                      { label: 'Statement balance', value: `$${formatMoneyFromCents(creditSummary?.statementBalanceCents)}` },
                      { label: 'Minimum due', value: `$${formatMoneyFromCents(creditSummary?.minimumDueCents)}`, strong: true },
                      { label: 'Payment due', value: formatDateShort(creditSummary?.paymentDueDate), accent: true },
                      { label: 'Available credit', value: `$${formatMoneyFromCents(creditSummary?.availableCreditCents)}`, positive: true },
                      { label: 'Credit limit', value: `$${formatMoneyFromCents(creditSummary?.creditLimitCents)}` },
                    ].map(metric => (
                      <div key={metric.label} className="min-h-24 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950/30 p-4">
                        <div className="text-[11px] text-slate-500 dark:text-slate-400 font-bold uppercase tracking-wide">{metric.label}</div>
                        <div className={`mt-2 text-xl font-extrabold ${
                          metric.positive
                            ? 'text-emerald-600 dark:text-emerald-400'
                            : metric.accent
                              ? 'text-blue-650 dark:text-blue-300'
                              : metric.strong
                                ? 'text-slate-950 dark:text-white'
                                : 'text-slate-800 dark:text-slate-300'
                        }`}>
                          {metric.value}
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="space-y-2">
                    <div className="flex items-center justify-between text-xs font-semibold text-slate-500 dark:text-slate-400">
                      <span>Credit utilization</span>
                      <span className="text-slate-800 dark:text-slate-200">{creditSummary?.utilization || 0}%</span>
                    </div>
                    <div className="h-2.5 rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden">
                      <div
                        className="h-full rounded-full bg-emerald-500"
                        style={{ width: `${creditSummary?.utilization || 0}%` }}
                      />
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

            {selectedAccountType === 'credit' && (
              <div className="grid gap-4 lg:grid-cols-[1.1fr_1.4fr]">
                <div className="bg-white dark:bg-slate-900/40 border border-slate-200 dark:border-slate-850 rounded-2xl p-5 shadow-sm dark:shadow-none">
                  <div className="grid grid-cols-2 gap-3">
                    {[
                      { label: 'Autopay', value: 'Off', icon: RefreshCw },
                      { label: 'Statement period', value: `${formatDateShort(creditSummary?.statementCloseDate)} - ${formatDateShort(creditSummary?.paymentDueDate)}`, icon: CalendarDays },
                      { label: 'Rewards', value: '$42.18', icon: Sparkles },
                      { label: 'Pending holds', value: `${transactions.filter(tx => tx.pending).length}`, icon: Activity },
                    ].map(item => {
                      const Icon = item.icon;
                      return (
                        <div key={item.label} className="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950/30 p-3">
                          <div className="flex items-center gap-2 text-slate-500 dark:text-slate-400">
                            <Icon className="w-4 h-4" />
                            <span className="text-[11px] font-bold uppercase">{item.label}</span>
                          </div>
                          <div className="mt-2 text-sm font-extrabold text-slate-900 dark:text-white">{item.value}</div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {(activeAccountObj?.cards || []).length > 0 && (
                  <div className="bg-white dark:bg-slate-900/40 border border-slate-200 dark:border-slate-850 rounded-2xl p-5 shadow-sm dark:shadow-none">
                    <div className="flex items-center justify-between gap-3">
                      <h3 className="text-sm font-extrabold text-slate-900 dark:text-white">Card controls</h3>
                      <button
                        onClick={() => setShowDocModal(true)}
                        className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 dark:border-slate-700 px-3 py-2 text-xs font-bold text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 cursor-pointer"
                      >
                        <ExternalLink className="w-3.5 h-3.5" />
                        <span>Manage</span>
                      </button>
                    </div>
                    <div className="mt-4 grid gap-4 md:grid-cols-[0.8fr_1.2fr]">
                      <div className="min-h-32 rounded-xl bg-slate-950 text-white p-4 flex flex-col justify-between shadow-sm">
                        <div className="text-xs font-bold tracking-widest">NOVA</div>
                        <div>
                          <div className="text-xs text-slate-400">Physical card</div>
                          <div className="mt-1 text-sm font-bold">•••• •••• •••• {(activeAccountObj.cards.find(card => !card.is_virtual) || activeAccountObj.cards[0])?.last_four}</div>
                        </div>
                        <div className="text-xs font-black">VISA</div>
                      </div>
                      <div className="grid grid-cols-2 gap-2">
                        {[
                          { label: 'Lock card', icon: Lock },
                          { label: 'Replace card', icon: RefreshCw },
                          { label: 'Set alerts', icon: Bell },
                          { label: 'Travel notice', icon: Plane },
                          { label: 'Lost or stolen', icon: ShieldAlert },
                          { label: 'Wallet', icon: Wallet },
                        ].map(action => {
                          const Icon = action.icon;
                          return (
                            <button
                              key={action.label}
                              onClick={() => setShowDocModal(true)}
                              className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/30 px-3 py-2 text-xs font-bold text-slate-700 dark:text-slate-200 hover:border-blue-400 dark:hover:border-blue-500 hover:text-blue-650 dark:hover:text-blue-300 transition cursor-pointer"
                            >
                              <Icon className="w-4 h-4" />
                              <span>{action.label}</span>
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* 2. Transaction Blotter View */}
            <div className="bg-white dark:bg-slate-900/40 border border-slate-205 dark:border-slate-850 rounded-3xl p-6 md:p-8 shadow-sm dark:shadow-none">
              <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 mb-5">
                <div>
                  <h3 className="text-lg font-bold text-slate-900 dark:text-white">Transaction History</h3>
                  <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                    Pending authorizations and posted ledger entries stay separated for review.
                  </p>
                </div>
                {selectedAccountType === 'credit' && (
                  <button
                    onClick={() => setIsSpendAnalyzerOpen(true)}
                    className="inline-flex items-center justify-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-sm font-bold shadow-sm hover:shadow transition-all cursor-pointer"
                  >
                    <TrendingUp className="w-4 h-4" />
                    <span>Spend analyzer</span>
                  </button>
                )}
              </div>

              {selectedAccountType === 'credit' && (
                <div className="mb-5 flex gap-2 overflow-x-auto pb-1">
                  {ledgerQuickTabs.map(tab => (
                    <button
                      key={tab.id}
                      onClick={() => setActiveLedgerTab(tab.id)}
                      className={`inline-flex min-h-10 items-center gap-2 rounded-xl border px-3.5 py-2 text-xs font-bold transition cursor-pointer whitespace-nowrap ${
                        activeLedgerTab === tab.id
                          ? 'border-emerald-500 bg-emerald-500 text-slate-950'
                          : 'border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/30 text-slate-700 dark:text-slate-200 hover:border-slate-300 dark:hover:border-slate-700'
                      }`}
                    >
                      <span>{tab.label}</span>
                      <span className={`rounded-full px-1.5 py-0.5 text-[10px] ${
                        activeLedgerTab === tab.id
                          ? 'bg-slate-950/15 text-slate-950'
                          : 'bg-slate-200 dark:bg-slate-800 text-slate-600 dark:text-slate-300'
                      }`}>
                        {tab.count}
                      </span>
                    </button>
                  ))}
                </div>
              )}

              {/* Capital One inspired Sleek Search & Filter Top Bar */}
              <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 mb-6">
                <div className="relative flex-1">
                  <input
                    type="text"
                    placeholder="Search transactions, merchants, categories, amounts..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full pl-9 pr-4 py-2.5 bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/80 rounded-xl text-sm text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/50 dark:focus:ring-blue-400/50 transition-all shadow-sm"
                  />
                  <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
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
                    <SlidersHorizontal className="w-4 h-4" />
                    <span>Filter</span>
                    {activeFilterCount > 0 && (
                      <span className="ml-1 px-1.5 py-0.2 rounded-full bg-blue-600 text-white text-[11px] font-bold">
                        {activeFilterCount}
                      </span>
                    )}
                  </button>
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
                            ...cardFilterOptions,
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
                                  const catLabel = formatCategoryLabel(tx, "Fees");
                                  const amountVal = Math.abs(getTransactionAmountCents(tx)) / 100;
                                  const rowKey = getTransactionKey(tx, idx, 'pending');
                                  const isExpanded = expandedTransactionKey === rowKey;
                                  return (
                                    <React.Fragment key={rowKey}>
                                      <tr className="hover:bg-slate-100/50 dark:hover:bg-slate-900/20 transition-colors">
                                        <td className="py-3 text-xs text-slate-500 dark:text-slate-400 italic w-[14%]">Pending</td>
                                        <td className="py-3 font-medium text-slate-800 dark:text-slate-300 w-[32%]">
                                          <button
                                            onClick={() => setExpandedTransactionKey(isExpanded ? null : rowKey)}
                                            className="flex min-w-0 items-center gap-2 text-left cursor-pointer"
                                          >
                                            {isExpanded ? <ChevronDown className="w-4 h-4 flex-shrink-0 text-slate-400" /> : <ChevronRight className="w-4 h-4 flex-shrink-0 text-slate-400" />}
                                            <span className="truncate">{tx.description}</span>
                                            {isLateFee && (
                                              <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded bg-rose-500/10 border border-rose-500/20 text-rose-500 dark:text-rose-400">Action Required</span>
                                            )}
                                          </button>
                                        </td>
                                        <td className="py-3 w-[22%]">
                                          <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700/80 text-slate-700 dark:text-slate-300">
                                            {catLabel}
                                          </span>
                                        </td>
                                        <td className="py-3 text-xs text-slate-500 dark:text-slate-400 font-medium w-[18%]">
                                          {formatTransactionCardLabel(tx)}
                                        </td>
                                        <td className={`py-3 text-right font-bold text-sm w-[14%] ${isCredit ? 'text-emerald-600 dark:text-emerald-400 italic' : isLateFee ? 'text-rose-600 dark:text-rose-400' : 'text-slate-800 dark:text-slate-300'}`}>
                                          {isCredit ? '-' : ''}${amountVal.toFixed(2)}
                                        </td>
                                      </tr>
                                      {isExpanded && (
                                        <tr>
                                          <td colSpan={5} className="pb-4">
                                            <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/40 p-4 text-xs text-slate-600 dark:text-slate-300">
                                              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                                                <span><strong>Authorized:</strong> {formatDateShort(tx.created_at || tx.timestamp)}</span>
                                                <span><strong>Descriptor:</strong> {tx.description}</span>
                                                <span><strong>MCC:</strong> {tx.merchant_category_code || 'N/A'}</span>
                                                <span><strong>Card:</strong> {formatTransactionCardLabel(tx)}</span>
                                                <span><strong>Merchant slug:</strong> {tx.merchant_slug || 'Unresolved'}</span>
                                                <span><strong>Merchant ID:</strong> {tx.merchant_id || 'Snapshot only'}</span>
                                                <span><strong>Store ID:</strong> {tx.merchant_store_id || 'Snapshot only'}</span>
                                                <button className="text-left font-bold text-blue-650 dark:text-blue-300 hover:underline cursor-pointer">Report or dispute</button>
                                              </div>
                                            </div>
                                          </td>
                                        </tr>
                                      )}
                                    </React.Fragment>
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
                                const catLabel = formatCategoryLabel(tx, "General");
                                const amountVal = Math.abs(getTransactionAmountCents(tx)) / 100;
                                const rowKey = getTransactionKey(tx, idx, 'posted');
                                const isExpanded = expandedTransactionKey === rowKey;
                                return (
                                  <React.Fragment key={rowKey}>
                                    <tr className="hover:bg-slate-100/50 dark:hover:bg-slate-900/30 transition-colors">
                                      <td className="py-4 text-xs text-slate-500 dark:text-slate-400 w-[14%]">
                                        {tx.posted_timestamp || tx.posted_at ? new Date(tx.posted_timestamp || tx.posted_at).toLocaleDateString() : "Pending"}
                                      </td>
                                      <td className="py-4 font-medium text-slate-800 dark:text-slate-200 w-[32%]">
                                        <button
                                          onClick={() => setExpandedTransactionKey(isExpanded ? null : rowKey)}
                                          className="flex min-w-0 items-center gap-2 text-left cursor-pointer"
                                        >
                                          {isExpanded ? <ChevronDown className="w-4 h-4 flex-shrink-0 text-slate-400" /> : <ChevronRight className="w-4 h-4 flex-shrink-0 text-slate-400" />}
                                          <span className="truncate">{tx.description}</span>
                                        </button>
                                      </td>
                                      <td className="py-4 w-[22%]">
                                        <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700/80 text-slate-700 dark:text-slate-300">
                                          {catLabel}
                                        </span>
                                      </td>
                                      <td className="py-4 text-xs text-slate-500 dark:text-slate-400 font-medium w-[18%]">
                                        {formatTransactionCardLabel(tx)}
                                      </td>
                                      <td className={`py-4 text-right font-bold text-sm w-[14%] ${isPayment ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-800 dark:text-slate-200'}`}>
                                        {isPayment ? '-' : ''}${amountVal.toFixed(2)}
                                      </td>
                                    </tr>
                                    {isExpanded && (
                                      <tr>
                                        <td colSpan={5} className="pb-4">
                                          <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/40 p-4 text-xs text-slate-600 dark:text-slate-300">
                                            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                                              <span><strong>Authorized:</strong> {formatDateShort(tx.created_at || tx.timestamp)}</span>
                                              <span><strong>Posted:</strong> {formatDateShort(tx.posted_timestamp || tx.posted_at)}</span>
                                              <span><strong>MCC:</strong> {tx.merchant_category_code || 'N/A'}</span>
                                              <span><strong>Card:</strong> {formatTransactionCardLabel(tx)}</span>
                                              <span><strong>Merchant slug:</strong> {tx.merchant_slug || 'Unresolved'}</span>
                                              <span><strong>Merchant ID:</strong> {tx.merchant_id || 'Snapshot only'}</span>
                                              <span><strong>Store ID:</strong> {tx.merchant_store_id || 'Snapshot only'}</span>
                                              <button className="text-left font-bold text-blue-650 dark:text-blue-300 hover:underline cursor-pointer">Report or dispute</button>
                                            </div>
                                          </div>
                                        </td>
                                      </tr>
                                    )}
                                  </React.Fragment>
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

            {selectedAccountType === 'credit' && (
              <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/5 p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div className="flex items-center gap-4">
                  <div className="w-11 h-11 rounded-xl bg-emerald-500/15 flex items-center justify-center text-emerald-600 dark:text-emerald-300 flex-shrink-0">
                    <Sparkles className="w-5 h-5" />
                  </div>
                  <div>
                    <h4 className="font-bold text-slate-900 dark:text-white text-sm">Earn 4.85% APY on savings</h4>
                    <p className="text-xs text-slate-600 dark:text-slate-400 mt-0.5">Move idle cash when you are done reviewing this card ledger.</p>
                  </div>
                </div>
                <button
                  onClick={() => {
                    const firstSavings = accountsData?.deposit_accounts?.find(a => a.account_type === 'SAVINGS');
                    if (firstSavings) {
                      handleSelectAccount(firstSavings.account_id, 'savings');
                    }
                  }}
                  className="px-4 py-2 rounded-xl bg-white dark:bg-slate-900 border border-emerald-500/30 text-emerald-700 dark:text-emerald-300 text-xs font-bold hover:bg-emerald-50 dark:hover:bg-emerald-950/40 transition-all cursor-pointer flex-shrink-0"
                >
                  Learn More
                </button>
              </div>
            )}
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
          cards={activeAccountObj?.cards || []}
          accountName="Nova Everyday Visa"
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
