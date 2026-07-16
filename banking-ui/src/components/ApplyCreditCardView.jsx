import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams, useLocation } from 'react-router-dom';
import { 
  ArrowLeft, 
  CreditCard, 
  User, 
  Mail, 
  Phone, 
  DollarSign, 
  Landmark, 
  Shield, 
  FileText, 
  AlertCircle, 
  CheckCircle2, 
  Loader2,
  ExternalLink
} from 'lucide-react';
import { useSettings } from '../context/SettingsContext.jsx';
import { createApplication } from '../utils/api.js';
import { formatPhoneNumber } from '../utils/formatters.js';
import GcpInfoModal from './GcpInfoModal.jsx';
import GoogleCloudIcon from './icons/GoogleCloudIcon.jsx';
import AnalyticsButton from './AnalyticsButton.jsx';

const CARDS_MAP = {
  'aura-elite-reserve': {
    id: 'AURA_ELITE_RESERVE',
    name: 'Aura Elite Reserve',
    color: 'from-slate-900 via-slate-800 to-slate-950 text-amber-400 border-amber-500/30',
    tag: 'Premium Travel & Lifestyle'
  },
  'velocity-cash-preferred': {
    id: 'VELOCITY_CASH_PREFERRED',
    name: 'Velocity Cash Preferred',
    color: 'from-emerald-900 via-teal-900 to-cyan-950 text-emerald-400 border-emerald-500/30',
    tag: 'Maximum Cash Back'
  },
  'equinox-horizon': {
    id: 'EQUINOX_HORIZON',
    name: 'Equinox Horizon',
    color: 'from-sky-900 via-blue-950 to-slate-900 text-sky-400 border-sky-500/30',
    tag: 'Low APR & Balance Transfers'
  },
  'vanguard-builder': {
    id: 'VANGUARD_BUILDER',
    name: 'Vanguard Builder',
    color: 'from-indigo-950 via-slate-900 to-indigo-900 text-indigo-400 border-indigo-500/30',
    tag: 'Secured Rebuilding'
  }
};

const cleanNumericValue = (val) => {
  if (val === undefined || val === null) return '';
  return val.toString().replace(/[^\d.]/g, '');
};

const formatNumberWithCommas = (val) => {
  if (val === undefined || val === null || val === '') return '';
  const clean = val.toString().replace(/\D/g, '');
  if (!clean) return '';
  const num = parseInt(clean, 10);
  return new Intl.NumberFormat('en-US').format(num);
};

function ApplyCreditCardView({ customerProfile, fbUser }) {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const location = useLocation();
  const prefill = location.state?.prefill;
  const { brandColorFrom, brandColorTo, bankName } = useSettings();
  const projectId = window.firebaseConfig?.projectId;
  const cxParts = (window.env?.CX_AGENT_STUDIO_DEPLOYMENT_NAME || '').split('/');
  const cxProjectId = cxParts.includes('projects') ? cxParts[cxParts.indexOf('projects') + 1] : '';
  const appId = cxParts.includes('apps') ? cxParts[cxParts.indexOf('apps') + 1] : '';
  const [isInfoModalOpen, setIsInfoModalOpen] = useState(false);

  // Get initial card parameter
  const getInitialCard = () => {
    if (prefill?.product) {
      const formatted = prefill.product.toLowerCase().replace(/\s+/g, '-');
      if (CARDS_MAP[formatted]) return formatted;
    }
    const cardParam = searchParams.get('card') || 'aura-elite-reserve';
    return CARDS_MAP[cardParam] ? cardParam : 'aura-elite-reserve';
  };

  const [selectedCardKey, setSelectedCardKey] = useState(getInitialCard());
  const [annualIncome, setAnnualIncome] = useState('');
  const [housingPayment, setHousingPayment] = useState('');
  const [employmentStatus, setEmploymentStatus] = useState('EMPLOYED');
  const [agreeTerms, setAgreeTerms] = useState(false);
  const [authorizeCredit, setAuthorizeCredit] = useState(false);

  // Profile data (pre-filled but editable)
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);
  const [successMsg, setSuccessMsg] = useState(null);
  const [applicationId, setApplicationId] = useState(null);

  useEffect(() => {
    if (prefill) {
      if (prefill.first_name) setFirstName(prefill.first_name);
      if (prefill.last_name) setLastName(prefill.last_name);
      if (prefill.email) setEmail(prefill.email);
      if (prefill.phone) setPhone(formatPhoneNumber(prefill.phone));
      if (prefill.annual_gross_income) setAnnualIncome(cleanNumericValue(prefill.annual_gross_income));
      if (prefill.monthly_housing_payment) setHousingPayment(cleanNumericValue(prefill.monthly_housing_payment));
      if (prefill.employment_status) {
        const statusMap = {
          'Employed': 'EMPLOYED',
          'Self-Employed': 'SELF_EMPLOYED',
          'Retired': 'RETIRED',
          'Student': 'STUDENT',
          'Unemployed': 'UNEMPLOYED'
        };
        const mapped = statusMap[prefill.employment_status] || prefill.employment_status.toUpperCase();
        setEmploymentStatus(mapped);
      }
    } else if (customerProfile) {
      setFirstName(customerProfile.first_name || '');
      setLastName(customerProfile.last_name || '');
      setEmail(customerProfile.email || fbUser?.email || '');
      setPhone(formatPhoneNumber(customerProfile.phone_number || ''));
    } else if (fbUser) {
      setEmail(fbUser.email || '');
      if (fbUser.displayName) {
        const parts = fbUser.displayName.split(' ');
        setFirstName(parts[0] || '');
        setLastName(parts.slice(1).join(' ') || '');
      }
    }
  }, [customerProfile, fbUser, prefill]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMsg(null);
    setSuccessMsg(null);

    if (!agreeTerms || !authorizeCredit) {
      setErrorMsg('You must agree to the terms and authorize the credit inquiry.');
      return;
    }

    if (!annualIncome || isNaN(Number(annualIncome)) || Number(annualIncome) <= 0) {
      setErrorMsg('Please enter a valid annual income.');
      return;
    }

    if (!housingPayment || isNaN(Number(housingPayment)) || Number(housingPayment) <= 0) {
      setErrorMsg('Please enter a valid monthly housing payment.');
      return;
    }

    setIsSubmitting(true);

    try {
      const cardDetail = CARDS_MAP[selectedCardKey];
      const payload = {
        product_category: 'CARD',
        product_type: cardDetail.id,
        requested_amount: Number(annualIncome) // Log requested amount as annual income / requested limit
      };

      const result = await createApplication(payload);
      setApplicationId(result.application_id);
      setSuccessMsg('Your credit card application has been submitted successfully!');
    } catch (err) {
      console.error('Error submitting credit card application:', err);
      setErrorMsg(err.response?.data?.detail || err.message || 'An unexpected error occurred. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const currentCard = CARDS_MAP[selectedCardKey];

  return (
    <section className="relative pt-24 pb-16 md:pt-28 md:pb-24 px-6 max-w-6xl mx-auto min-h-[calc(100vh-80px)] flex flex-col text-left w-full">
      {/* Background Glows */}
      <div className="absolute top-1/4 left-1/3 w-[400px] h-[400px] rounded-full bg-emerald-500/5 blur-[100px] pointer-events-none -z-10" />

      {/* Portal Header */}
      <div className="mb-8 pb-4 border-b border-slate-200 dark:border-slate-800 flex justify-between items-center relative w-full">
        <div className="flex items-center gap-3">
          <AnalyticsButton analyticsId="apply_credit_card_view_back"
            onClick={() => navigate('/credit-cards')}
            className="p-3 rounded-2xl bg-slate-50 dark:bg-slate-800 text-slate-550 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white transition-all hover:scale-105 shadow-sm cursor-pointer"
            aria-label="Back"
          >
            <ArrowLeft className="w-6 h-6" />
          </AnalyticsButton>
          <div className="p-3 rounded-2xl bg-slate-50 dark:bg-slate-800 text-slate-700 dark:text-slate-300 shadow-sm">
            <CreditCard className="w-6 h-6 text-emerald-500" />
          </div>
          <div>
            <h1 className="text-3xl font-extrabold bg-gradient-to-r from-slate-900 via-slate-700 to-slate-500 dark:from-white dark:via-slate-200 dark:to-slate-400 bg-clip-text text-transparent">
              Apply for a Credit Card
            </h1>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
              Complete the secure form below to submit your application.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <AnalyticsButton analyticsId="apply_credit_card_view_gcp_app_integration_info_modal"
            onClick={() => setIsInfoModalOpen(true)}
            className="p-2.5 rounded-2xl hover:bg-slate-100 dark:hover:bg-slate-850 transition-all active:scale-95 cursor-pointer flex items-center justify-center border border-slate-200/60 dark:border-slate-800/60 bg-white dark:bg-slate-900 shadow-sm text-slate-550 hover:text-slate-850 dark:hover:text-white"
            title="GCP App Integration Info"
          >
            <GoogleCloudIcon className="w-5 h-5" />
          </AnalyticsButton>
        </div>
      </div>

      <div className="max-w-4xl mx-auto w-full bg-white dark:bg-slate-900 rounded-3xl p-8 border border-slate-200 dark:border-slate-800/80 shadow-2xl relative overflow-hidden">

        {/* Alerts */}
        {errorMsg && (
          <div className="mb-6 p-4 rounded-2xl bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800/30 text-red-600 dark:text-red-400 text-sm flex items-center gap-2.5 animate-shake">
            <AlertCircle className="w-5 h-5 shrink-0" />
            <span>{errorMsg}</span>
          </div>
        )}

        {successMsg ? (
          <div className="text-center py-12 space-y-6">
            <div className="w-20 h-20 rounded-full bg-emerald-500/10 text-emerald-500 flex items-center justify-center mx-auto">
              <CheckCircle2 className="w-12 h-12 animate-bounce" />
            </div>
            <div className="space-y-2">
              <h2 className="text-2xl font-bold text-slate-900 dark:text-white">{successMsg}</h2>
              <p className="text-sm text-slate-600 dark:text-slate-400 max-w-md mx-auto">
                Thank you for applying for the <strong>{currentCard?.name}</strong>. Your application ID is:
              </p>
              <div className="inline-block bg-slate-100 dark:bg-slate-800 px-4 py-2 rounded-xl font-mono text-sm text-slate-950 dark:text-emerald-400 select-all border border-slate-200 dark:border-slate-700">
                {applicationId}
              </div>
            </div>
            <div className="pt-6">
              <AnalyticsButton analyticsId="apply_credit_card_view_go_to_credit_cards"
                onClick={() => navigate('/credit-cards')}
                className="px-6 py-2.5 text-sm font-semibold rounded-full bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 transition-all cursor-pointer"
              >
                Go to Credit Cards
              </AnalyticsButton>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-8">
            
            {/* Card Selector section */}
            <div className="bg-slate-50 dark:bg-slate-950/50 p-6 rounded-2xl border border-slate-100 dark:border-slate-800/50 space-y-4">
              <h2 className="text-sm font-bold text-slate-800 dark:text-slate-200 uppercase tracking-wider flex items-center gap-2">
                <CreditCard className="w-4 h-4 text-emerald-500" />
                Selected Credit Card
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-12 gap-6 items-center">
                <div className="md:col-span-6">
                  <label htmlFor="card_select" className="block text-xs text-slate-400 mb-1">
                    Card Product
                  </label>
                  <select
                    id="card_select"
                    value={selectedCardKey}
                    onChange={(e) => setSelectedCardKey(e.target.value)}
                    className="w-full px-4 py-3 text-sm rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500 transition-all font-semibold"
                  >
                    {Object.entries(CARDS_MAP).map(([key, value]) => (
                      <option key={key} value={key}>
                        {value.name}
                      </option>
                    ))}
                  </select>
                </div>
                {/* Visual Card Preview */}
                <div className="md:col-span-6 flex justify-center">
                  <div className={`w-full max-w-[280px] aspect-[1.58] rounded-xl p-4 shadow-lg border bg-gradient-to-tr text-white flex flex-col justify-between overflow-hidden transition-all duration-300 ${currentCard?.color}`}>
                    <div className="flex justify-between items-center">
                      <span className="font-bold text-[10px] tracking-wider opacity-95">{bankName}</span>
                      <div className="w-2.5 h-2.5 rounded-full bg-white/20"></div>
                    </div>
                    <div className="my-auto">
                      <div className="text-[9px] uppercase tracking-wider opacity-60">Visa Signature</div>
                      <div className="text-sm font-extrabold tracking-tight mt-0.5 truncate">
                        {currentCard?.name}
                      </div>
                    </div>
                    <div className="flex justify-between items-end border-t border-white/10 pt-2">
                      <span className="text-[8px] opacity-70 tracking-widest uppercase">VALUED MEMBER</span>
                      <span className="italic font-black text-xs">VISA</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Personal Details Section */}
            <div className="space-y-4">
              <h2 className="text-sm font-bold text-slate-800 dark:text-slate-200 uppercase tracking-wider flex items-center gap-2">
                <User className="w-4 h-4 text-emerald-500" />
                Personal Information
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="p-4 bg-slate-50 dark:bg-slate-950 rounded-2xl border border-slate-100 dark:border-slate-800/50">
                  <label htmlFor="first_name" className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1.5">
                    First Name
                  </label>
                  <div className="relative">
                    <span className="absolute left-3 top-2.5 text-slate-400">
                      <User className="w-4 h-4" />
                    </span>
                    <input
                      id="first_name"
                      type="text"
                      value={firstName}
                      onChange={(e) => setFirstName(e.target.value)}
                      placeholder="First Name"
                      className="w-full pl-10 pr-4 py-2 text-sm rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500 transition-all"
                      required
                    />
                  </div>
                </div>

                <div className="p-4 bg-slate-50 dark:bg-slate-950 rounded-2xl border border-slate-100 dark:border-slate-800/50">
                  <label htmlFor="last_name" className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1.5">
                    Last Name
                  </label>
                  <div className="relative">
                    <span className="absolute left-3 top-2.5 text-slate-400">
                      <User className="w-4 h-4" />
                    </span>
                    <input
                      id="last_name"
                      type="text"
                      value={lastName}
                      onChange={(e) => setLastName(e.target.value)}
                      placeholder="Last Name"
                      className="w-full pl-10 pr-4 py-2 text-sm rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500 transition-all"
                      required
                    />
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="p-4 bg-slate-50 dark:bg-slate-950 rounded-2xl border border-slate-100 dark:border-slate-800/50">
                  <label htmlFor="email" className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1.5">
                    Email Address
                  </label>
                  <div className="relative">
                    <span className="absolute left-3 top-2.5 text-slate-400">
                      <Mail className="w-4 h-4" />
                    </span>
                    <input
                      id="email"
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="email@example.com"
                      className="w-full pl-10 pr-4 py-2 text-sm rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500 transition-all"
                      required
                    />
                  </div>
                </div>

                <div className="p-4 bg-slate-50 dark:bg-slate-950 rounded-2xl border border-slate-100 dark:border-slate-800/50">
                  <label htmlFor="phone" className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1.5">
                    Phone Number
                  </label>
                  <div className="relative">
                    <span className="absolute left-3 top-2.5 text-slate-400">
                      <Phone className="w-4 h-4" />
                    </span>
                    <input
                      id="phone"
                      type="tel"
                      value={phone}
                      onChange={(e) => setPhone(formatPhoneNumber(e.target.value))}
                      placeholder="(555) 555-5555"
                      className="w-full pl-10 pr-4 py-2 text-sm rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500 transition-all"
                      required
                    />
                  </div>
                </div>
              </div>
            </div>

            {/* Financial Details Section */}
            <div className="space-y-4">
              <h2 className="text-sm font-bold text-slate-800 dark:text-slate-200 uppercase tracking-wider flex items-center gap-2">
                <Landmark className="w-4 h-4 text-emerald-500" />
                Financial Information
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div className="p-4 bg-slate-50 dark:bg-slate-950 rounded-2xl border border-slate-100 dark:border-slate-800/50">
                  <label htmlFor="employment_status" className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1.5">
                    Employment Status
                  </label>
                  <select
                    id="employment_status"
                    value={employmentStatus}
                    onChange={(e) => setEmploymentStatus(e.target.value)}
                    className="w-full px-3 py-2 text-sm rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500 transition-all"
                  >
                    <option value="EMPLOYED">Employed</option>
                    <option value="SELF_EMPLOYED">Self-Employed</option>
                    <option value="RETIRED">Retired</option>
                    <option value="STUDENT">Student</option>
                    <option value="UNEMPLOYED">Unemployed</option>
                  </select>
                </div>

                <div className="p-4 bg-slate-50 dark:bg-slate-950 rounded-2xl border border-slate-100 dark:border-slate-800/50">
                  <label htmlFor="annual_income" className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1.5">
                    Annual Gross Income
                  </label>
                  <div className="relative">
                    <span className="absolute left-3 top-2 text-slate-400">
                      <DollarSign className="w-4 h-4" />
                    </span>
                    <input
                      id="annual_income"
                        type="text"
                        value={formatNumberWithCommas(annualIncome)}
                        onChange={(e) => setAnnualIncome(e.target.value.replace(/\D/g, ''))}
                        placeholder="e.g. 75,000"
                      className="w-full pl-10 pr-4 py-2 text-sm rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500 transition-all font-semibold"
                        required
                    />
                  </div>
                </div>

                <div className="p-4 bg-slate-50 dark:bg-slate-950 rounded-2xl border border-slate-100 dark:border-slate-800/50">
                  <label htmlFor="housing_payment" className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1.5">
                    Monthly Housing Payment
                  </label>
                  <div className="relative">
                    <span className="absolute left-3 top-2 text-slate-400">
                      <DollarSign className="w-4 h-4" />
                    </span>
                    <input
                      id="housing_payment"
                        type="text"
                        value={formatNumberWithCommas(housingPayment)}
                        onChange={(e) => setHousingPayment(e.target.value.replace(/\D/g, ''))}
                        placeholder="e.g. 1,200"
                      className="w-full pl-10 pr-4 py-2 text-sm rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500 transition-all font-semibold"
                        required
                    />
                  </div>
                </div>
              </div>
            </div>

            {/* Terms and Consents */}
            <div className="space-y-4 pt-2">
              <h2 className="text-sm font-bold text-slate-800 dark:text-slate-200 uppercase tracking-wider flex items-center gap-2">
                <Shield className="w-4 h-4 text-emerald-500" />
                Agreements & Disclosures
              </h2>
              
              <div className="space-y-3 bg-slate-50 dark:bg-slate-950/60 rounded-2xl p-6 border border-slate-200 dark:border-slate-800/60 text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
                <div className="flex items-start space-x-3">
                  <input
                    type="checkbox"
                    id="agree_terms"
                    checked={agreeTerms}
                    onChange={(e) => setAgreeTerms(e.target.checked)}
                    className="mt-1 w-4 h-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500 dark:bg-slate-900 dark:border-slate-800 cursor-pointer"
                  />
                  <label htmlFor="agree_terms" className="cursor-pointer select-none">
                    I agree to the electronic communications disclosure, terms of use, cardholder agreement, and certify that all information provided is accurate and true.
                  </label>
                </div>

                <div className="flex items-start space-x-3 pt-2 border-t border-slate-200 dark:border-slate-800">
                  <input
                    type="checkbox"
                    id="auth_credit"
                    checked={authorizeCredit}
                    onChange={(e) => setAuthorizeCredit(e.target.checked)}
                    className="mt-1 w-4 h-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500 dark:bg-slate-900 dark:border-slate-800 cursor-pointer"
                  />
                  <label htmlFor="auth_credit" className="cursor-pointer select-none">
                    I authorize {bankName} to obtain my consumer credit report to evaluate my eligibility for this credit card. I understand that this soft inquiry will not affect my credit score.
                  </label>
                </div>
              </div>
            </div>

            {/* Form Actions */}
            <div className="flex items-center justify-end gap-4 pt-6 border-t border-slate-100 dark:border-slate-800/50">
              <AnalyticsButton analyticsId="apply_credit_card_view_cancel"
                type="button"
                onClick={() => navigate('/credit-cards')}
                className="px-6 py-2.5 text-sm font-semibold rounded-full bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 transition-all cursor-pointer"
              >
                Cancel
              </AnalyticsButton>
              <AnalyticsButton analyticsId="apply_credit_card_view_05"
                type="submit"
                disabled={isSubmitting}
                className="px-6 py-2.5 text-sm font-semibold rounded-full text-slate-950 hover:scale-102 active:scale-98 transition-all flex items-center justify-center gap-2 shadow-lg cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                style={{
                  backgroundImage: `linear-gradient(to right, ${brandColorFrom}, ${brandColorTo})`,
                  boxShadow: `0 10px 15px -3px ${brandColorFrom}30`
                }}
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Submitting Application...</span>
                  </>
                ) : (
                  <>
                    <FileText className="w-4 h-4" />
                    <span>Submit Application</span>
                  </>
                )}
              </AnalyticsButton>
            </div>

          </form>
        )}
      </div>

      <GcpInfoModal
        isOpen={isInfoModalOpen}
        onClose={() => setIsInfoModalOpen(false)}
        title="Credit Card Application Prefill Integration"
      >
        <div className="space-y-4 text-slate-600 dark:text-slate-400 text-sm leading-relaxed">
          <p>
            To apply for a credit card, you can fill out this application form manually or leverage the <strong>Home Loan Assistant</strong> conversational agent to prefill it for you automatically.
          </p>
          <p>
            When talking to the agent, asking to apply for a card (e.g., <em>"I want to apply for the Aura Elite Reserve card"</em>) triggers a client extension action. The agent gathers required information from the context, generates structured parameters, and redirects you to this page with secure pre-filled form values.
          </p>
          <p>
            The agent extension configurations, dialog flows, and prompt boundaries are managed in <strong>CX Agent Studio</strong>:
          </p>
          <div className="bg-slate-50 dark:bg-slate-950 p-4 rounded-2xl border border-slate-100 dark:border-slate-800 space-y-3">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h4 className="font-semibold text-slate-800 dark:text-slate-200 text-xs uppercase tracking-wider">CX Agent Studio Console</h4>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">Inspect agent intents, parameters, and form-fill extension routes.</p>
              </div>
              <div className="flex flex-col items-end gap-1.5 shrink-0">
                <a
                  href={`https://ces.cloud.google.com/projects/${projectId}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-emerald-500 hover:text-emerald-600 font-semibold text-xs hover:underline"
                >
                  <span>View Console</span>
                  <ExternalLink className="w-3.5 h-3.5" />
                </a>
                {appId && (
                  <a
                    href={`https://ces.cloud.google.com/projects/${cxProjectId || projectId}/locations/us/apps/${appId}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-emerald-500 hover:text-emerald-600 font-semibold text-xs hover:underline"
                  >
                    <span>View Agent</span>
                    <ExternalLink className="w-3.5 h-3.5" />
                  </a>
                )}
              </div>
            </div>
            <hr className="border-slate-100 dark:border-slate-800" />
            <div className="flex items-start justify-between gap-4">
              <div>
                <h4 className="font-semibold text-slate-800 dark:text-slate-200 text-xs uppercase tracking-wider">Documentation</h4>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">Learn about conversational agents, toolsets, and extension flows.</p>
              </div>
              <a
                href="https://docs.cloud.google.com/customer-engagement-ai/conversational-agents/ps"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-emerald-500 hover:text-emerald-600 font-semibold text-xs shrink-0 hover:underline"
              >
                <span>View Docs</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            </div>
            <hr className="border-slate-100 dark:border-slate-800" />
            <div className="flex items-start justify-between gap-4">
              <div>
                <h4 className="font-semibold text-slate-800 dark:text-slate-200 text-xs uppercase tracking-wider">Architecture Guide</h4>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">Read about the GECX client-side function callbacks, React Router prefill mapping, and schemas.</p>
              </div>
              <a
                href="https://github.com/GoogleCloudPlatform/fsi-gecx-bundle/blob/main/docs/architecture/domain-workflows/origination/credit_card_prefill_integration.md"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-emerald-500 hover:text-emerald-600 font-semibold text-xs shrink-0 hover:underline"
              >
                <span>View Design</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            </div>
          </div>
        </div>
      </GcpInfoModal>

    </section>
  );
}

export default ApplyCreditCardView;
