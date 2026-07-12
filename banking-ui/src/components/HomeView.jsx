import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { 
  Shield, 
  ArrowRight, 
  TrendingUp, 
  CreditCard, 
  Percent, 
  Lock, 
  Smartphone, 
  Globe, 
  Check,
  ExternalLink,
  X,
  Wallet
} from 'lucide-react';
import { useSettings } from '../context/SettingsContext.jsx';
import { getAccountsSummary, provisionMyDemo, getCreditCardTransactions } from '../utils/api.js';
import { useNavigate, Link } from 'react-router-dom';
import BillPayModal from './BillPayModal.jsx';
import GoogleCloudIcon from './icons/GoogleCloudIcon.jsx';
import GoogleCompassIcon from './icons/GoogleCompassIcon.jsx';
import { Joyride, STATUS, EVENTS, ACTIONS } from 'react-joyride';
import { getJoyrideStyles } from '../utils/joyrideStyles.js';

function HomeView({
  fbUser,
  customerProfile,
  loanAmount,
  setLoanAmount,
  loanTerm,
  setLoanTerm,
  activeBot,
  setActiveBot,
  calculateMonthlyPayment,
  interestRate
}) {
  const { 
    bankName,
    brandColorFrom,
    brandColorTo,
    resolvedTheme
  } = useSettings();

  const navigate = useNavigate();

  const [accountsData, setAccountsData] = useState(null);
  const [, setTransactions] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isBillPayOpen, setIsBillPayOpen] = useState(false);
  const [isProvisioning, setIsProvisioning] = useState(false);
  const [isSchemaModalOpen, setIsSchemaModalOpen] = useState(false);
  const [isMemberModalOpen, setIsMemberModalOpen] = useState(false);
  const [isLoanModalOpen, setIsLoanModalOpen] = useState(false);

  const [tourRun, setTourRun] = useState(false);
  const [tourKey, setTourKey] = useState(0);
  const [domReady, setDomReady] = useState(false);

  useEffect(() => {
    const isCompleted = fbUser 
      ? localStorage.getItem('home-tour-auth-completed') === 'true'
      : localStorage.getItem('home-tour-completed') === 'true';
    
    const params = new URLSearchParams(window.location.search);
    const forceTour = params.get('tour') === 'true';

    if (forceTour || !isCompleted) {
      setTourRun(true);
    } else {
      setTourRun(false);
    }
  }, [fbUser]);

  useEffect(() => {
    const checkElement = setInterval(() => {
      const targetId = fbUser ? '#home-tour-btn-auth' : '#become-member-btn';
      if (document.querySelector(targetId)) {
        setDomReady(true);
        clearInterval(checkElement);
      }
    }, 50);
    return () => clearInterval(checkElement);
  }, [fbUser]);

  const fetchAccounts = useCallback(async () => {
    if (!fbUser) {
      setAccountsData(null);
      setTransactions([]);
      return;
    }
    try {
      setIsLoading(true);
      const data = await getAccountsSummary();
      setAccountsData(data);
      
      try {
        const txs = await getCreditCardTransactions();
        const sorted = (txs || []).sort((a, b) => new Date(b.posted_at) - new Date(a.posted_at));
        setTransactions(sorted.slice(0, 4));
      } catch (txErr) {
        console.error("Failed to load transactions for blotter:", txErr);
      }
    } catch (err) {
      console.error("Failed to load accounts summary:", err);
    } finally {
      setIsLoading(false);
    }
  }, [fbUser]);

  const handleProvision = async () => {
    setIsProvisioning(true);
    try {
      await provisionMyDemo();
      await fetchAccounts();
    } catch (err) {
      console.error("Failed to provision demo sandbox:", err);
      alert(err.response?.data?.detail || "Failed to provision demo sandbox.");
    } finally {
      setIsProvisioning(false);
    }
  };

  useEffect(() => {
    fetchAccounts();
  }, [fetchAccounts]);

  const hasAccounts = accountsData && (
    (accountsData.deposit_accounts && accountsData.deposit_accounts.length > 0) ||
    (accountsData.credit_accounts && accountsData.credit_accounts.length > 0)
  );

  const steps = useMemo(() => {
    if (!fbUser) {
      return [
        {
          target: '#home-tour-btn',
          content: "Welcome to Nova Horizon Bank! Let's take a quick tour of how to get started.",
          placement: 'top',
          skipBeacon: true
        },
        {
          target: '#become-member-btn',
          content: 'Click here to learn about how you can become a member and provision your sandbox demo suite.',
          placement: 'bottom',
          skipBeacon: true
        },
        {
          target: '#compare-products-link',
          content: 'Explore credit card features, rates, and benefits in our product comparison portal.',
          placement: 'bottom',
          skipBeacon: true
        },
        {
          target: '#header-signin-btn',
          content: 'To access your secure dashboard, view balances, get support, and apply for products, click the Sign In button here!',
          placement: 'bottom-end',
          skipBeacon: true
        }
      ];
    } else {
      const authSteps = [
        {
          target: '#home-tour-btn-auth',
          content: "Welcome to your personal dashboard! Let's tour the tools available to you as an active member.",
          placement: 'top',
          skipBeacon: true
        },
        {
          target: '#view-accounts-link',
          content: 'Click here to navigate to your accounts page where you can check balances, transaction histories, and transfer funds.',
          placement: 'bottom',
          skipBeacon: true
        },
        {
          target: '#header-search-input',
          content: 'Use this search bar to search the entire banking web site content using Agent Search.',
          placement: 'bottom',
          skipBeacon: true
        }
      ];

      if (hasAccounts) {
        authSteps.push({
          target: '#dashboard-schema-btn',
          content: 'Click this cloud button to inspect the active Cloud SQL database schema definitions and examine operation queries.',
          placement: 'left',
          skipBeacon: true
        });
      } else {
        authSteps.push({
          target: '#provision-demo-btn',
          content: "It looks like you don't have active accounts yet. Click here to instantly seed your sandbox database with checking, savings, and credit cards.",
          placement: 'left',
          skipBeacon: true
        });
      }

      authSteps.push({
        target: '#help-support-link',
        content: 'Have any questions? Access our documentation, user guides, and FAQs here.',
        placement: 'bottom',
        skipBeacon: true
      });

      return authSteps;
    }
  }, [fbUser, hasAccounts]);

  return (
    <>
      {/* Hero Section */}
      <section className="relative pt-32 pb-12 md:pt-36 md:pb-16 px-6">
        <div className="absolute inset-0 -z-10 overflow-hidden">
          <img 
            src="/hero_bg.png" 
            alt="Abstract background" 
            className="w-full h-full object-cover opacity-40 mix-blend-screen"
          />
          <div className="absolute inset-0 bg-gradient-to-b from-slate-50/50 via-slate-50/80 to-slate-50 dark:from-slate-950/50 dark:via-slate-950/80 dark:to-slate-950"></div>
        </div>

        <div className={`max-w-7xl mx-auto grid grid-cols-1 ${fbUser ? 'lg:grid-cols-2' : ''} gap-16 items-start`}>
          <div className={`space-y-8 ${!fbUser ? 'max-w-4xl mx-auto text-center' : ''}`}>
            {fbUser ? (
              <>
                <h1 className="text-3xl md:text-4xl lg:text-5xl font-extrabold tracking-tight leading-tight">
                  Welcome back, <span className="bg-gradient-to-r from-emerald-400 via-teal-300 to-cyan-400 bg-clip-text text-transparent">
                    {customerProfile?.first_name ? `${customerProfile.first_name}` : (() => {
                      const name = accountsData?.user_profile?.first_name || fbUser.email.split('@')[0];
                      return name.charAt(0).toUpperCase() + name.slice(1).toLowerCase();
                    })()}
                  </span>
                </h1>
                
                <p className="text-lg text-slate-600 dark:text-slate-400 max-w-xl leading-relaxed">
                  Take control of your financial future. Manage daily accounts, build long-term deposits, and explore premium credit offers designed just for you.
                </p>

                <div className="flex flex-wrap gap-x-6 gap-y-2 text-xs font-semibold text-slate-500 dark:text-slate-400 py-2">
                  <div className="flex items-center gap-1.5">
                    <Check className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                    <span>High-Yield Deposits</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Check className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                    <span>Zero Account Fees</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Check className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                    <span>256-Bit Security</span>
                  </div>
                </div>

                <div className="flex flex-col sm:flex-row gap-4 items-center">
                  <Link 
                    to="/accounts"
                    id="view-accounts-link"
                    className="flex items-center justify-center space-x-2 px-8 py-4 rounded-full text-slate-950 font-bold text-base shadow-xl hover:scale-[1.02] transition-all duration-300 cursor-pointer w-full sm:w-auto text-center"
                    style={{ backgroundImage: `linear-gradient(to right, ${brandColorFrom}, ${brandColorTo})`, boxShadow: `0 20px 25px -5px ${brandColorFrom}33` }}
                  >
                    <span>View My Accounts</span>
                    <ArrowRight className="w-5 h-5" />
                  </Link>
                  <div className="flex items-center gap-2 w-full sm:w-auto justify-center">
                    <Link 
                      to="/help-center"
                      id="help-support-link"
                      className="flex-1 sm:flex-initial flex items-center justify-center px-8 py-4 rounded-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-200 font-semibold hover:bg-slate-50 dark:hover:bg-slate-800 hover:scale-[1.02] active:scale-95 transition-all duration-300 cursor-pointer shadow-sm text-center"
                    >
                      Help & Support
                    </Link>
                    <button
                      id="home-tour-btn-auth"
                      onClick={() => {
                        localStorage.removeItem('home-tour-auth-completed');
                        setTourKey(prev => prev + 1);
                        setTourRun(true);
                      }}
                      className="p-4 rounded-full hover:bg-slate-100 dark:hover:bg-slate-800 transition-all active:scale-95 cursor-pointer flex items-center justify-center border border-slate-200/60 dark:border-slate-800/60 bg-white dark:bg-slate-900 shadow-sm text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white shrink-0"
                      title="Take the Tour"
                    >
                      <GoogleCompassIcon className="w-5 h-5" />
                    </button>
                  </div>
                </div>
              </>
            ) : (
              <>
                <h1 className="text-5xl md:text-7xl font-extrabold tracking-tight leading-tight">
                  Banking that works <br />
                  <span className="bg-gradient-to-r from-emerald-400 via-teal-300 to-cyan-400 bg-clip-text text-transparent">
                    in your best interest.
                  </span>
                </h1>
                
                <p className="text-lg text-slate-600 dark:text-slate-400 max-w-xl mx-auto leading-relaxed">
                  Experience next-generation retail banking combined with the trusted values of a member-owned credit union. Higher yields, lower rates, zero hidden fees.
                </p>

                  <div className="flex flex-col sm:flex-row justify-center gap-4 items-center">
                  <button 
                      id="become-member-btn"
                    onClick={() => setIsMemberModalOpen(true)}
                      className="flex items-center justify-center space-x-2 px-8 py-4 rounded-full text-slate-950 font-bold text-base shadow-xl hover:scale-[1.02] transition-all duration-300 cursor-pointer w-full sm:w-auto"
                    style={{ backgroundImage: `linear-gradient(to right, ${brandColorFrom}, ${brandColorTo})`, boxShadow: `0 20px 25px -5px ${brandColorFrom}33` }}
                  >
                    <span>Become a Member</span>
                    <ArrowRight className="w-5 h-5" />
                  </button>
                    <div className="flex items-center gap-2 w-full sm:w-auto justify-center">
                      <Link
                        to="/compare-products"
                        id="compare-products-link"
                        className="flex-1 sm:flex-initial flex items-center justify-center px-8 py-4 rounded-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-200 font-semibold hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors cursor-pointer shadow-sm"
                      >
                        Compare Products
                      </Link>
                      <button
                        id="home-tour-btn"
                        onClick={() => {
                          localStorage.removeItem('home-tour-completed');
                          setTourKey(prev => prev + 1);
                          setTourRun(true);
                        }}
                        className="p-4 rounded-full hover:bg-slate-100 dark:hover:bg-slate-800 transition-all active:scale-95 cursor-pointer flex items-center justify-center border border-slate-200/60 dark:border-slate-800/60 bg-white dark:bg-slate-900 shadow-sm text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white shrink-0"
                        title="Take the Tour"
                      >
                        <GoogleCompassIcon className="w-5 h-5" />
                      </button>
                    </div>
                </div>
              </>
            )}

            {/* Stats copy removed from here to features section */}
          </div>

          {/* Interactive Glassmorphism Dashboard Preview */}
          {fbUser && (
          <div className="relative block mt-12 lg:mt-0">
            <div className="absolute -inset-4 bg-gradient-to-tr from-emerald-500/20 to-cyan-500/20 rounded-3xl blur-3xl -z-10"></div>
            <div className="relative bg-white dark:bg-slate-900/40 border border-slate-200 dark:border-slate-800/80 rounded-2xl p-8 shadow-xl dark:shadow-black/50">
              {isLoading ? (
                <div className="flex flex-col items-center justify-center py-12 text-slate-400 space-y-3">
                  <div className="w-8 h-8 rounded-full border-2 border-slate-700 border-t-emerald-500 animate-spin"></div>
                  <span className="text-xs font-semibold">Synchronizing secure balances...</span>
                </div>
              ) : hasAccounts ? (
                // Authenticated User with Accounts
                <>
                  <div className="flex items-start justify-between mb-8">
                    <div>
                      <div className="text-sm text-slate-500 dark:text-slate-400">Total Liquid Deposits</div>
                      <div className="text-4xl font-bold text-slate-900 dark:text-white mt-1">
                        ${((accountsData.deposit_accounts?.reduce((sum, acc) => sum + acc.cleared_balance_cents, 0) || 0) / 100).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </div>
                    </div>
                    {/* Schema trigger button on top right */}
                    <button 
                      id="dashboard-schema-btn"
                      onClick={() => setIsSchemaModalOpen(true)}
                      className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors p-1 cursor-pointer flex items-center justify-center shrink-0"
                      title="View Schema Details"
                    >
                      <GoogleCloudIcon className="w-4 h-4" />
                    </button>
                  </div>

                  <div className="space-y-4 mb-8">
                    {accountsData.deposit_accounts?.filter(a => a.account_type === 'CHECKING').map((acc, idx) => (
                      <div 
                        key={`chk-${idx}`} 
                        onClick={() => navigate(`/accounts?id=${acc.account_id}&type=checking`)}
                        className="bg-slate-50 dark:bg-slate-950/50 rounded-xl p-4 border border-slate-200/40 dark:border-slate-800/50 flex items-center justify-between transition-all duration-300 hover:bg-slate-100/50 dark:hover:bg-slate-900/30 hover:scale-[1.008] will-change-transform hover:shadow-md hover:border-emerald-500/20 cursor-pointer"
                      >
                        <div className="flex items-center space-x-4">
                          <div className="w-10 h-10 rounded-lg bg-teal-500/20 flex items-center justify-center text-teal-500 dark:text-teal-400">
                            <Wallet className="w-5 h-5" />
                          </div>
                          <div>
                            <div className="font-medium text-slate-900 dark:text-white">{acc.product_name}</div>
                            <div className="text-xs text-slate-500 dark:text-slate-400">**** {acc.account_number.slice(-4)}</div>
                          </div>
                        </div>
                        <div className="font-semibold text-slate-900 dark:text-white">
                          ${(acc.cleared_balance_cents / 100).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                        </div>
                      </div>
                    ))}

                    {accountsData.deposit_accounts?.filter(a => a.account_type === 'SAVINGS').map((acc, idx) => (
                      <div 
                        key={`sav-${idx}`} 
                        onClick={() => navigate(`/accounts?id=${acc.account_id}&type=savings`)}
                        className="bg-slate-50 dark:bg-slate-950/50 rounded-xl p-4 border border-slate-200/40 dark:border-slate-800/50 flex items-center justify-between transition-all duration-300 hover:bg-slate-100/50 dark:hover:bg-slate-900/30 hover:scale-[1.008] will-change-transform hover:shadow-md hover:border-emerald-500/20 cursor-pointer"
                      >
                        <div className="flex items-center space-x-4">
                          <div className="w-10 h-10 rounded-lg bg-emerald-500/20 flex items-center justify-center text-emerald-500 dark:text-emerald-400">
                            <Percent className="w-5 h-5" />
                          </div>
                          <div>
                            <div className="font-medium text-slate-900 dark:text-white">{acc.product_name}</div>
                            <div className="text-xs text-slate-500 dark:text-slate-400">Active Savings Tier</div>
                          </div>
                        </div>
                        <div className="font-semibold text-slate-900 dark:text-white">
                          ${(acc.cleared_balance_cents / 100).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                        </div>
                      </div>
                    ))}

                    {accountsData.credit_accounts?.map((acc, idx) => (
                      <div 
                        key={`cred-${idx}`} 
                        onClick={() => navigate(`/accounts?id=${acc.account_id}&type=credit`)}
                        className="bg-slate-50 dark:bg-slate-950/50 rounded-xl p-4 border border-slate-200/40 dark:border-slate-800/50 flex items-center justify-between transition-all duration-300 hover:bg-slate-100/50 dark:hover:bg-slate-900/30 hover:scale-[1.008] will-change-transform hover:shadow-md hover:border-emerald-500/20 cursor-pointer"
                      >
                        <div className="flex items-center space-x-4">
                          <div className="w-10 h-10 rounded-lg bg-indigo-500/10 dark:bg-indigo-500/20 flex items-center justify-center text-indigo-600 dark:text-indigo-400">
                            <CreditCard className="w-5 h-5" />
                          </div>
                          <div>
                            <div className="font-medium text-slate-900 dark:text-white">Nova Credit Card</div>
                            <div className="text-xs text-slate-500 dark:text-slate-400">Outstanding Balance</div>
                          </div>
                        </div>
                        <div className="font-semibold text-slate-900 dark:text-white text-right">
                          ${(acc.cleared_balance_cents / 100).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                          <div className="text-[10px] font-normal text-slate-400 dark:text-slate-500">Limit: ${(acc.credit_limit_cents / 100).toLocaleString()}</div>
                        </div>
                      </div>
                    ))}

                    
                  </div>

                  <div className="flex justify-end text-xs text-slate-400 dark:text-slate-500">
                    <div className="flex items-center space-x-1 text-emerald-400">
                      <Lock className="w-3 h-3" />
                      <span>End-to-End Encrypted</span>
                    </div>
                  </div>
                </>
              ) : (
                // Authenticated User with NO Accounts (Provision Sandbox CTA)
                <div className="flex flex-col items-center text-center py-8 space-y-6">
                  <div className="w-16 h-16 rounded-2xl bg-emerald-500/10 flex items-center justify-center border border-emerald-500/20 text-emerald-400">
                    <Shield className="w-8 h-8 animate-pulse" />
                  </div>
                  <div className="space-y-2">
                    <h3 className="text-lg font-bold text-slate-900 dark:text-white">Set up your Sandbox</h3>
                    <p className="text-xs leading-relaxed text-slate-500 dark:text-slate-400 max-w-sm">
                      A database profile has been provisioned for <span className="text-emerald-400 font-semibold">{fbUser?.email}</span>, but you don't have any active accounts. 
                      Provision your isolated personal demo suite to test live payments, statements, and agent calls.
                    </p>
                  </div>
                  <button
                    id="provision-demo-btn"
                    onClick={handleProvision}
                    disabled={isProvisioning}
                    className="w-full py-3.5 rounded-xl text-slate-950 font-bold text-sm bg-gradient-to-r from-emerald-400 to-cyan-400 hover:scale-[1.02] active:scale-95 disabled:opacity-50 disabled:scale-100 transition-all duration-300 shadow-lg shadow-emerald-500/10"
                  >
                    {isProvisioning ? "Seeding accounts & transaction history..." : "Provision Demo Suite"}
                  </button>
                </div>
              )}
            </div>
          </div>
          )}
        </div>
      </section>

      {/* Personalized Offers or CTA Section (moved below Hero) */}
      <section className="py-12 px-6 relative overflow-hidden border-y border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] bg-emerald-500/5 rounded-full blur-3xl -z-10"></div>
        <div className="max-w-7xl mx-auto relative z-10">
          {fbUser ? (
            <div>
              <div className="text-center max-w-2xl mx-auto mb-16">
                <span className="text-emerald-500 dark:text-emerald-400 font-semibold text-sm tracking-wider uppercase">Exclusive Benefits</span>
                <h2 className="text-3xl md:text-5xl font-black mt-3 mb-6 text-slate-900 dark:text-white">
                  Personalized offers for you
                </h2>
                <p className="text-slate-650 dark:text-slate-400 text-sm">
                  Maximize your wealth with active member benefits tailored to your credit profile and account history.
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                {/* Offer 1 */}
                <div className="bg-white dark:bg-slate-900/80 border border-slate-200 dark:border-slate-850 rounded-3xl p-8 hover:border-emerald-500/40 hover:-translate-y-1 transition-all duration-300 flex flex-col justify-between shadow-sm dark:shadow-none">
                  <div>
                    <div className="w-12 h-12 rounded-2xl bg-teal-500/10 border border-teal-500/20 flex items-center justify-center text-teal-500 dark:text-teal-400 mb-6">
                      <TrendingUp className="w-6 h-6" />
                    </div>
                    <span className="text-xs font-semibold text-teal-600 dark:text-teal-400 bg-teal-500/10 px-3 py-1 rounded-full">High-Yield Special</span>
                    <h3 className="text-2xl font-bold text-slate-900 dark:text-white mt-4 mb-3">4.85% APY Savings</h3>
                    <p className="text-slate-600 dark:text-slate-400 text-sm leading-relaxed mb-8">
                      Earn interest rates 10x higher than the national average with zero minimum deposit rules and zero monthly maintenance fees.
                    </p>
                  </div>
                  <Link 
                    to="/checking-accounts"
                    className="w-full text-center block py-3.5 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 font-semibold hover:bg-slate-200 dark:hover:bg-slate-700 transition-all duration-200 cursor-pointer no-underline"
                  >
                    Deposit Funds
                  </Link>
                </div>

                {/* Offer 2 */}
                <div className="bg-white dark:bg-slate-900/80 border border-slate-200 dark:border-slate-850 rounded-3xl p-8 hover:border-cyan-500/40 hover:-translate-y-1 transition-all duration-300 flex flex-col justify-between shadow-sm dark:shadow-none">
                  <div>
                    <div className="w-12 h-12 rounded-2xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-500 dark:text-cyan-400 mb-6">
                      <CreditCard className="w-6 h-6" />
                    </div>
                    <span className="text-xs font-semibold text-cyan-600 dark:text-cyan-400 bg-cyan-500/10 px-3 py-1 rounded-full">1.5% Unlimited Cash</span>
                    <h3 className="text-2xl font-bold text-slate-900 dark:text-white mt-4 mb-3">Nova Everyday Card</h3>
                    <p className="text-slate-600 dark:text-slate-400 text-sm leading-relaxed mb-8">
                      Enjoy unlimited cash back on gas, groceries, and dining with a prime credit limit up to $10,000 and no annual fees.
                    </p>
                  </div>
                  <Link 
                    to="/credit-cards"
                    className="w-full text-center block py-3.5 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 font-semibold hover:bg-slate-200 dark:hover:bg-slate-700 transition-all duration-200 cursor-pointer no-underline"
                  >
                    Apply Instantly
                  </Link>
                </div>

                {/* Offer 3 */}
                <div className="bg-white dark:bg-slate-900/80 border border-slate-200 dark:border-slate-850 rounded-3xl p-8 hover:border-emerald-500/40 hover:-translate-y-1 transition-all duration-300 flex flex-col justify-between shadow-sm dark:shadow-none">
                  <div>
                    <div className="w-12 h-12 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-500 dark:text-emerald-400 mb-6">
                      <Percent className="w-6 h-6" />
                    </div>
                    <span className="text-xs font-semibold text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 px-3 py-1 rounded-full">Low Fixed Rates</span>
                    <h3 className="text-2xl font-bold text-slate-900 dark:text-white mt-4 mb-3">5.99% Personal Loan</h3>
                    <p className="text-slate-600 dark:text-slate-400 text-sm leading-relaxed mb-8">
                      Estimate, customize, and submit loan requests with instant approval decisions and check deposits within 24 hours.
                    </p>
                  </div>
                  <button 
                    onClick={() => {
                      const calcSection = document.getElementById('calculator');
                      if (calcSection) calcSection.scrollIntoView({ behavior: 'smooth' });
                    }}
                    className="w-full py-3.5 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 font-semibold hover:bg-slate-200 dark:hover:bg-slate-700 transition-all duration-200 cursor-pointer"
                  >
                    Calculate Payments
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <div className="max-w-4xl mx-auto text-center">
              <h2 className="text-3xl md:text-5xl font-black mb-6 text-slate-900 dark:text-white">
                Ready to take control of your wealth?
              </h2>
              <p className="text-slate-650 dark:text-slate-400 max-w-xl mx-auto mb-8">
                Join thousands of members who are earning more and paying less with {bankName} Credit Union.
              </p>
              <button
                onClick={() => setIsMemberModalOpen(true)}
                className="px-8 py-4 rounded-full text-slate-950 font-bold text-base shadow-xl hover:scale-105 transition-all duration-300 cursor-pointer"
                style={{ backgroundImage: `linear-gradient(to right, ${brandColorFrom}, ${brandColorTo})`, boxShadow: `0 20px 25px -5px ${brandColorFrom}33` }}
              >
                Open an Account in 5 Minutes
              </button>
            </div>
          )}
        </div>
      </section>

      {/* Interactive Loan Calculator Section (moved up above features) */}
      <section id="calculator" className="py-12 px-6">
        <div className="max-width-7xl mx-auto grid grid-cols-1 lg:grid-cols-2 gap-16 items-center">
          <div>
            <span className="text-emerald-600 dark:text-emerald-400 font-medium text-sm tracking-wider uppercase">Smart Planning</span>
            <h2 className="text-4xl font-bold tracking-tight mt-3 mb-6 text-slate-900 dark:text-white">
              Calculate your loan with transparent rates.
            </h2>
            <p className="text-slate-600 dark:text-slate-400 mb-8 leading-relaxed">
              No hidden fees, no origination costs. Slide to adjust your desired amount and term to see exactly what you'll pay each month.
            </p>

            <div className="space-y-4">
              {[
                "Same-day approval for personal and auto loans",
                "Fixed rates so your payment never changes",
                "No prepayment penalties—pay off anytime"
              ].map((text, i) => (
                <div key={i} className="flex items-center space-x-3">
                  <div className="w-5 h-5 rounded-full bg-emerald-500/20 flex items-center justify-center text-emerald-600 dark:text-emerald-400 flex-shrink-0">
                    <Check className="w-3 h-3" />
                  </div>
                  <span className="text-sm text-slate-600 dark:text-slate-300">{text}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="bg-white dark:bg-slate-900/40 border border-slate-200 dark:border-slate-800/80 rounded-3xl p-8 shadow-2xl">
            <h3 className="text-xl font-semibold mb-8 text-slate-900 dark:text-white">Personal Loan Estimator</h3>
            
            {/* Loan Amount Slider */}
            <div className="mb-8">
              <div className="flex justify-between items-center mb-3">
                <label className="text-sm font-medium text-slate-500 dark:text-slate-400">Loan Amount</label>
                <span className="text-xl font-bold text-slate-900 dark:text-white">${loanAmount.toLocaleString()}</span>
              </div>
              <input 
                type="range" 
                min="1000" 
                max="100000" 
                step="1000"
                value={loanAmount}
                onChange={(e) => setLoanAmount(Number(e.target.value))}
                className="w-full h-2 bg-slate-100 dark:bg-slate-800 rounded-lg appearance-none cursor-pointer accent-emerald-500"
              />
              <div className="flex justify-between text-xs text-slate-400 dark:text-slate-600 mt-2">
                <span>$1,000</span>
                <span>$100,000</span>
              </div>
            </div>

            {/* Loan Term Slider */}
            <div className="mb-12">
              <div className="flex justify-between items-center mb-3">
                <label className="text-sm font-medium text-slate-500 dark:text-slate-400">Loan Term (Months)</label>
                <span className="text-xl font-bold text-slate-900 dark:text-white">{loanTerm} Months</span>
              </div>
              <input 
                type="range" 
                min="12" 
                max="84" 
                step="12"
                value={loanTerm}
                onChange={(e) => setLoanTerm(Number(e.target.value))}
                className="w-full h-2 bg-slate-100 dark:bg-slate-800 rounded-lg appearance-none cursor-pointer accent-emerald-500"
              />
              <div className="flex justify-between text-xs text-slate-400 dark:text-slate-600 mt-2">
                <span>12 months</span>
                <span>84 months</span>
              </div>

              {/* Result Display */}
              <div className="bg-sky-50 dark:bg-slate-950 rounded-xl p-6 border border-sky-200 dark:border-slate-800 flex items-center justify-between mt-6 mb-6">
                <div>
                  <div className="text-xs text-slate-500 mb-1">Estimated Monthly Payment</div>
                  <div className="text-4xl font-black text-emerald-600 dark:text-emerald-400">${calculateMonthlyPayment()}</div>
                </div>
                <div className="text-right">
                  <div className="text-xs text-slate-500 mb-1">Fixed APR</div>
                  <div className="text-2xl font-bold text-slate-900 dark:text-white">{interestRate}%</div>
                </div>
              </div>
            </div>

            <button 
              onClick={() => setIsLoanModalOpen(true)}
              className="w-full py-4 rounded-xl text-slate-950 font-bold shadow-lg hover:scale-[1.02] transition-all duration-300 cursor-pointer"
              style={{ backgroundImage: `linear-gradient(to right, ${brandColorFrom}, ${brandColorTo})`, boxShadow: `0 10px 15px -3px ${brandColorFrom}33` }}
            >
              Apply for Loan Now
            </button>
          </div>
        </div>
      </section>

      {/* Features Section (moved down below calculator) */}
      <section id="features" className="py-12 px-6 bg-slate-50 dark:bg-slate-900/30 border-y border-slate-200 dark:border-slate-900">
        <div className="max-w-7xl mx-auto">
          <div className="text-center max-w-2xl mx-auto mb-16">
            <h2 className="text-3xl md:text-5xl font-bold tracking-tight mb-4 text-slate-900 dark:text-white">
              Designed for your financial freedom
            </h2>
            <p className="text-slate-600 dark:text-slate-400">
              We provide the tools, rates, and security you need to grow your wealth effortlessly.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {[
              {
                icon: Smartphone,
                title: "Modern Digital Experience",
                desc: "Manage everything from our lightning-fast mobile app with biometric login and instant transfers."
              },
              {
                icon: Shield,
                title: "NCUA Insured Security",
                desc: "Your deposits are federally insured up to $250,000 by the National Credit Union Administration."
              },
              {
                icon: Globe,
                title: "Global ATM Access",
                desc: "Access your cash anywhere with zero ATM fees worldwide. We automatically reimburse all charges.",
                to: '/locator'
              }
            ].map((item, idx) => {
              const CardContent = (
                <>
                  <div className="w-12 h-12 rounded-xl bg-slate-100 dark:bg-slate-900 flex items-center justify-center mb-6 group-hover:scale-110 transition-transform duration-300 border border-slate-200 dark:border-slate-700/50">
                    <item.icon className="w-6 h-6 text-emerald-500" />
                  </div>
                  <h3 className="text-xl font-semibold mb-3 text-theme-main">{item.title}</h3>
                  <p className="text-theme-muted text-sm leading-relaxed">{item.desc}</p>
                </>
              );

              if (item.to) {
                return (
                  <Link
                    key={idx}
                    to={item.to}
                    className="card-themeable hover:border-emerald-500/50 transition-all duration-300 group hover:-translate-y-1 block text-left no-underline cursor-pointer"
                  >
                    {CardContent}
                  </Link>
                );
              }

              return (
                <div 
                  key={idx} 
                  className="card-themeable hover:border-emerald-500/50 transition-all duration-300 group hover:-translate-y-1"
                >
                  {CardContent}
                </div>
              );
            })}
          </div>

          {/* APY Stats centered at the bottom of Features section */}
          <div className="mt-16 pt-12 border-t border-slate-200 dark:border-slate-800 flex flex-col sm:flex-row items-center justify-center gap-12 sm:gap-24 text-center">
            <div>
              <div className="text-4xl font-extrabold text-emerald-500">4.85%</div>
              <div className="text-xs text-slate-600 dark:text-slate-400 mt-1">APY on High-Yield Savings</div>
            </div>
            <div className="hidden sm:block w-px h-12 bg-slate-250 dark:bg-slate-800"></div>
            <div>
              <div className="text-4xl font-extrabold text-emerald-500">0.00%</div>
              <div className="text-xs text-slate-600 dark:text-slate-400 mt-1">Maintenance Fees</div>
            </div>
            <div className="hidden sm:block w-px h-12 bg-slate-250 dark:bg-slate-800"></div>
            <div>
              <div className="text-4xl font-extrabold text-emerald-500">150k+</div>
              <div className="text-xs text-slate-600 dark:text-slate-400 mt-1">Active Members</div>
            </div>
          </div>
        </div>
      </section>

      {/* Help Center & AI Support */}
      <section id="help" className="py-12 px-6 bg-slate-50 dark:bg-slate-950">
        <div className="max-width-7xl mx-auto">
          <div className="text-center max-w-2xl mx-auto mb-16">
            <span className="text-teal-600 dark:text-teal-400 font-medium text-sm tracking-wider uppercase">Automated Assistance</span>
            <h2 className="text-3xl md:text-5xl font-bold tracking-tight mt-3 mb-4 text-slate-900 dark:text-white">
              How can we help you today?
            </h2>
            <p className="text-slate-600 dark:text-slate-400">
              Select an inquiry below to instantly launch a specialized AI support agent trained to resolve your specific request.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {[
              {
                title: "Account & Login",
                desc: "Unlock your account, reset passwords, or troubleshoot two-factor authentication issues.",
                botName: "Account Support Bot"
              },
              {
                title: "Loan Applications",
                desc: "Check pre-approval status, calculate customized rates, or upload pending documents.",
                botName: "Loan Advisor Bot"
              },
              {
                title: "Fraud & Security",
                desc: "Report unauthorized charges, freeze debit/credit cards instantly, or dispute a transaction.",
                botName: "Security & Fraud Bot"
              },
              {
                title: "Rates & Yields",
                desc: "Learn about high-yield savings tiers, certificate of deposit (CD) rates, and IRA structures.",
                botName: "Wealth Management Bot"
              },
              {
                title: "Lost Credit Card",
                desc: "Instantly freeze a missing card, report it lost or stolen, and request an expedited replacement.",
                botName: "Lost Card Agent"
              }
            ].map((inquiry, idx) => (
              <div key={idx} className="bg-white dark:bg-slate-900/40 border border-slate-200 dark:border-slate-800/80 rounded-3xl p-6 flex flex-col justify-between hover:border-teal-500/50 hover:bg-slate-50 dark:hover:bg-slate-800/60 transition-all duration-300 group shadow-sm dark:shadow-none">
                <div>
                  <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-2 group-hover:text-teal-600 dark:group-hover:text-teal-400 transition-colors">
                    {inquiry.title}
                  </h3>
                  <p className="text-slate-650 dark:text-slate-400 text-sm leading-relaxed mb-6">
                    {inquiry.desc}
                  </p>
                </div>
                <button 
                  onClick={() => {
                    setActiveBot(inquiry.botName);
                    setTimeout(() => setActiveBot(null), 3500);
                  }}
                  className="w-full py-3 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 text-sm font-semibold hover:bg-teal-500 hover:text-slate-950 dark:hover:bg-teal-500 dark:hover:text-slate-950 transition-all duration-300 shadow-sm hover:shadow-teal-500/20"
                >
                  Launch {inquiry.botName}
                </button>
              </div>
            ))}
          </div>

          {/* Interactive Bot Launch Modal/Toast */}
          {activeBot && (
            <div className="fixed bottom-8 right-8 z-50 bg-white dark:bg-slate-900 border border-teal-500/50 rounded-2xl p-4 shadow-2xl shadow-teal-500/20 flex items-center space-x-4 animate-bounce">
              <div className="w-10 h-10 rounded-xl bg-teal-500/20 flex items-center justify-center text-teal-400">
                <div className="w-2 h-2 bg-teal-400 rounded-full animate-ping"></div>
              </div>
              <div>
                <div className="text-xs text-teal-500 dark:text-teal-400 font-semibold uppercase tracking-wider">Connecting...</div>
                <div className="text-sm font-medium text-slate-900 dark:text-white">Initializing {activeBot}</div>
              </div>
            </div>
          )}

          {isSchemaModalOpen && (
            <div className="fixed inset-0 z-[200] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 animate-fade-in">
              <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl max-w-lg w-full overflow-hidden shadow-2xl flex flex-col animate-scale-up">
                {/* Header bar */}
                <div className="p-6 border-b border-slate-200 dark:border-slate-800 flex justify-between items-center bg-slate-50 dark:bg-slate-950/50 flex-shrink-0">
                  <div className="flex items-center gap-2">
                    <GoogleCloudIcon className="w-5 h-5 text-emerald-500" />
                    <h3 className="font-bold text-slate-900 dark:text-white text-base">Enterprise Data Layer Architecture</h3>
                  </div>
                  <button 
                    onClick={() => setIsSchemaModalOpen(false)}
                    className="p-1.5 rounded-full hover:bg-slate-200 dark:hover:bg-slate-800 text-slate-500 dark:text-slate-400 transition-colors cursor-pointer"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>

                {/* Content body */}
                <div className="p-6 space-y-4 text-sm text-slate-600 dark:text-slate-300 leading-relaxed text-left font-normal">
                  <p>
                    Our cloud-native banking platform utilizes a multi-schema relational data architecture designed for real-time transaction processing, high-concurrency simulation, and regulatory compliance.
                  </p>
                  <div className="space-y-2.5 pt-1 text-xs">
                    <div className="flex items-start gap-2.5">
                      <span className="w-2 h-2 rounded-full bg-emerald-500 mt-1.5 shrink-0"></span>
                      <div>
                        <strong className="text-slate-900 dark:text-white font-bold">Transactional Ledgers:</strong> Event-driven outbox pattern recording append-only cryptographic audit logs and double-entry accounting for pending holds and posted transactions.
                      </div>
                    </div>
                    <div className="flex items-start gap-2.5">
                      <span className="w-2 h-2 rounded-full bg-blue-500 mt-1.5 shrink-0"></span>
                      <div>
                        <strong className="text-slate-900 dark:text-white font-bold">CDC Iceberg Pipeline:</strong> Real-time Write-Ahead Log (WAL) streaming via Google Cloud Datastream into Apache Iceberg tables and BigQuery Medallion Materialized Views for sub-second OLAP compliance analytics.
                      </div>
                    </div>
                    <div className="flex items-start gap-2.5">
                      <span className="w-2 h-2 rounded-full bg-purple-500 mt-1.5 shrink-0"></span>
                      <div>
                        <strong className="text-slate-900 dark:text-white font-bold">Sandbox Isolation:</strong> Automated persona provisioning with multi-layered KYC credit profile isolation and real-time surge data generators.
                      </div>
                    </div>
                  </div>
                  <div className="pt-4 border-t border-slate-200 dark:border-slate-800 flex justify-between items-center text-xs">
                    <span className="text-slate-500 font-mono">Enterprise Data Platform</span>
                    <a 
                      href="https://github.com/GoogleCloudPlatform/fsi-gecx-bundle/tree/main/docs/architecture/data-platform" 
                      target="_blank" 
                      rel="noreferrer" 
                      className="text-teal-600 dark:text-teal-400 hover:underline flex items-center gap-1 font-bold"
                    >
                      View Architecture Docs
                      <ExternalLink className="w-3.5 h-3.5" />
                    </a>
                  </div>
                </div>

                {/* Footer */}
                <div className="p-4 bg-slate-50 dark:bg-slate-950/30 border-t border-slate-200 dark:border-slate-800 flex justify-end">
                  <button 
                    onClick={() => setIsSchemaModalOpen(false)}
                    className="px-5 py-2 rounded-xl bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-white font-bold text-xs transition cursor-pointer"
                  >
                    Close Details
                  </button>
                </div>
              </div>
            </div>
          )}

          <BillPayModal
            isOpen={isBillPayOpen}
            onClose={() => setIsBillPayOpen(false)}
            accountsData={accountsData}
            onPaymentSuccess={fetchAccounts}
          />

          {isMemberModalOpen && (
            <div className="fixed inset-0 z-[250] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 animate-fade-in">
              <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl max-w-md w-full overflow-hidden shadow-2xl p-6 text-center space-y-4">
                <div className="w-12 h-12 rounded-full bg-emerald-500/10 text-emerald-500 flex items-center justify-center mx-auto">
                  <Shield className="w-6 h-6" />
                </div>
                <h3 className="text-xl font-bold text-slate-900 dark:text-white">Become a Member</h3>
                <p className="text-sm text-slate-600 dark:text-slate-400 leading-relaxed">
                  To join Nova Horizon, please sign in using the top-right profile controls and then click <strong>Provision Demo Suite</strong> on the home dashboard to initialize your sandbox member profile.
                </p>
                <button
                  onClick={() => setIsMemberModalOpen(false)}
                  className="w-full py-2.5 rounded-xl text-slate-950 font-bold text-sm shadow-lg hover:scale-[1.02] transition-all duration-300 cursor-pointer"
                  style={{ backgroundImage: `linear-gradient(to right, ${brandColorFrom}, ${brandColorTo})` }}
                >
                  Acknowledge
                </button>
              </div>
            </div>
          )}

          {isLoanModalOpen && (
            <div className="fixed inset-0 z-[250] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 animate-fade-in">
              <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl max-w-md w-full overflow-hidden shadow-2xl p-6 text-center space-y-4">
                <div className="w-12 h-12 rounded-full bg-sky-500/10 text-sky-500 flex items-center justify-center mx-auto">
                  <Shield className="w-6 h-6" />
                </div>
                <h3 className="text-xl font-bold text-slate-900 dark:text-white">Apply for a Loan</h3>
                <p className="text-sm text-slate-600 dark:text-slate-400 leading-relaxed">
                  To apply, please sign in using the top-right profile button and then click the chat icon on the bottom right of the page to launch the CX Agent Studio mortgage preapproval flow.
                </p>
                <button
                  onClick={() => setIsLoanModalOpen(false)}
                  className="w-full py-2.5 rounded-xl text-slate-950 font-bold text-sm shadow-lg hover:scale-[1.02] transition-all duration-300 cursor-pointer"
                  style={{ backgroundImage: `linear-gradient(to right, ${brandColorFrom}, ${brandColorTo})` }}
                >
                  Acknowledge
                </button>
              </div>
            </div>
          )}

        </div>
      </section>

      {/* Joyride Landing Page Onboarding Tour */}
      {tourRun && domReady && steps.length > 0 && (
        <Joyride
          key={tourKey}
          run={tourRun}
          options={{
            scrollOffset: 120
          }}
          steps={steps}
          continuous={true}
          showSkipButton={true}
          showCloseButton={true}
          onEvent={(data) => {
            const { status, type, action } = data;
            if (
              [STATUS.FINISHED, STATUS.SKIPPED].includes(status) ||
              type === EVENTS.TOUR_END ||
              action === ACTIONS.CLOSE ||
              action === ACTIONS.SKIP
            ) {
              setTourRun(false);
              const key = fbUser ? 'home-tour-auth-completed' : 'home-tour-completed';
              localStorage.setItem(key, 'true');
            }
          }}
          styles={getJoyrideStyles(resolvedTheme, brandColorFrom)}
        />
      )}
    </>
  );
}

export default HomeView;
