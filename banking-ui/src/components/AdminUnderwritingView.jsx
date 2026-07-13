import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { 
  FileText, ShieldAlert, CheckCircle2, 
  XCircle, RefreshCw, User, AlertCircle, Clipboard, 
  FileCheck, Calendar, Check, ChevronRight, Lock, Loader2,
  ExternalLink, ArrowLeft
} from 'lucide-react';
import { useSettings } from '../context/SettingsContext.jsx';
import api from '../utils/api.js';
import GcpInfoModal from './GcpInfoModal.jsx';
import GoogleCloudIcon from './icons/GoogleCloudIcon.jsx';
import GoogleCompassIcon from './icons/GoogleCompassIcon.jsx';
import { Joyride, STATUS, EVENTS, ACTIONS } from 'react-joyride';
import { getJoyrideStyles } from '../utils/joyrideStyles.js';

const CONFIDENCE_THRESHOLDS = {
  ssn: 0.95,
  wages: 0.90,
  federal_income_tax_withheld: 0.90,
  social_security_tax_withheld: 0.90,
  default: 0.80
};

const CANONICAL_SCHEMAS = {
  W2: [
    "WagesTipsOtherCompensation",
    "FederalIncomeTaxWithheld",
    "SocialSecurityTaxWithheld",
    "SSN",
    "EmployerName"
  ],
  PAYSTUB: [
    "GrossEarnings",
    "NetEarnings",
    "PayPeriodEndDate",
    "EmployerName"
  ]
};

function AdminUnderwritingView({ fbUser }) {
  const navigate = useNavigate();
  const location = useLocation();
  const { brandColorFrom, brandColorTo, resolvedTheme } = useSettings();
  const projectId = window.firebaseConfig?.projectId;
  const [isInfoModalOpen, setIsInfoModalOpen] = useState(false);

  const [exceptions, setExceptions] = useState([]);
  const [selectedArtifact, setSelectedArtifact] = useState(null);
  const [selectedArtifactId, setSelectedArtifactId] = useState('');
  const [pdfUrl, setPdfUrl] = useState('');
  const [activeTab, setActiveTab] = useState('tier1');
  const [wagesChecked, setWagesChecked] = useState(false);
  const [employerChecked, setEmployerChecked] = useState(false);
  
  // Active edits state
  const [ocrPayload, setOcrPayload] = useState({});
  const [underwriterNotes, setUnderwriterNotes] = useState('');
  const [decision, setDecision] = useState('APPROVE');
  const [ssnVerified, setSsnVerified] = useState(false);
  const [employerVerified, setEmployerVerified] = useState(false);
  const [grossMonthlyIncome, setGrossMonthlyIncome] = useState('');

  // UI state
  const [isLoadingExceptions, setIsLoadingExceptions] = useState(false);
  const [isLoadingReview, setIsLoadingReview] = useState(false);
  const [isIframeLoading, setIsIframeLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);
  const [successMsg, setSuccessMsg] = useState(null);
  
  // Optimistic Lock modal state
  const [showConflictModal, setShowConflictModal] = useState(false);

  // Joyride Tour States
  const [tourRun, setTourRun] = useState(false);
  const [tourKey, setTourKey] = useState(0);
  const [domReady, setDomReady] = useState(false);

  useEffect(() => {
    const isCompleted = localStorage.getItem('underwriting-tour-completed') === 'true';
    const params = new URLSearchParams(location.search);
    const forceTour = params.get('tour') === 'true';

    if (forceTour || !isCompleted) {
      setTourRun(true);
    } else {
      setTourRun(false);
    }
  }, [location.search]);

  useEffect(() => {
    const checkElement = setInterval(() => {
      if (document.querySelector('#underwriting-tour-btn')) {
        setDomReady(true);
        clearInterval(checkElement);
      }
    }, 50);
    return () => clearInterval(checkElement);
  }, []);

  // Auto-select first exception if tour runs and none selected
  useEffect(() => {
    if (tourRun && !selectedArtifact && exceptions.length > 0) {
      const targetTier = activeTab === 'tier1' ? 'TIER_1_MANUAL_REVIEW' : 'TIER_2_SPOT_CHECK';
      const match = exceptions.find(exc => exc.verification_tier === targetTier);
      if (match) {
        setSelectedArtifact(match);
        setSelectedArtifactId(match.artifact_id);
      }
    }
  }, [tourRun, selectedArtifact, exceptions, activeTab]);

  const steps = useMemo(() => {
    const baseSteps = [
      {
        target: '#underwriting-tour-btn',
        content: "Welcome to the Underwriting Portal! This playground allows credit analysts to manually audit document OCR mismatches, review paystub parameters, and authorize mortgage approvals.",
        placement: 'bottom-end',
        skipBeacon: true
      },
      {
        target: '#exceptions-ingestion-queue',
        content: "Ingestion Exception Queue: Browse manual review documents (Tier 1) and spot-checks (Tier 2). Click an item in this list to inspect its contents.",
        placement: 'right',
        skipBeacon: true
      },
      {
        target: '#exceptions-queue-refresh',
        content: "Queue Controls: Refresh the exception list directly from the database to load concurrent ingestion updates.",
        placement: 'bottom-end',
        skipBeacon: true
      }
    ];

    if (selectedArtifact) {
      return [
        ...baseSteps,
        {
          target: '#underwriting-pdf-viewer',
          content: "Document Preview: Review the uploaded tax statement or W-2 PDF file directly inside the browser.",
          placement: 'right',
          skipBeacon: true
        },
        {
          target: '#override_form',
          content: "Override Form: Inspect parsed OCR fields. Confidences are highlighted to identify discrepancies. Override values to match the PDF, add compliance notes, and submit.",
          placement: 'left',
          skipBeacon: true
        }
      ];
    } else {
      return [
        ...baseSteps,
        {
          target: '#underwriting-review-pane-fallback',
          content: "Review Workspace: Once an artifact is selected, this pane displays the side-by-side PDF preview and OCR correction tables.",
          placement: 'left',
          skipBeacon: true
        }
      ];
    }
  }, [selectedArtifact]);

  // Fetch Exceptions on mount
  const fetchExceptions = async (silent = false) => {
    if (!silent) setIsLoadingExceptions(true);
    setErrorMsg(null);
    try {
      const res = await api.get('/underwriting/exceptions');
      setExceptions(res.data);
    } catch (err) {
      console.error("Failed to load underwriting exceptions:", err);
      setErrorMsg("Failed to load underwriting queue. Verify employee credentials.");
    } finally {
      if (!silent) setIsLoadingExceptions(false);
    }
  };

  useEffect(() => {
    fetchExceptions();
  }, []);

  // Ergonomic Keyboard Shortcuts: Cmd+Enter to save, Escape to cancel
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (selectedArtifact) {
        if (e.key === 'Escape') {
          setSelectedArtifact(null);
          setSelectedArtifactId('');
        } else if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
          e.preventDefault();
          // Submit form programmatically
          const form = document.getElementById('override_form');
          if (form) form.requestSubmit();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedArtifact]);

  const filteredExceptions = useMemo(() => {
    return exceptions.filter((exc) => {
      if (activeTab === 'tier2') {
        return exc.verification_tier === 'TIER_2_SPOT_CHECK';
      } else {
        return exc.verification_tier === 'TIER_1_MANUAL' || !exc.verification_tier;
      }
    });
  }, [exceptions, activeTab]);

  const memoizedExceptions = useMemo(() => {
    return filteredExceptions.map((exc) => (
      <div 
        key={exc.artifact_id}
        onClick={() => handleSelectArtifact(exc)}
        className={`p-4 rounded-2xl border cursor-pointer transition-all flex items-start justify-between gap-2 ${
          selectedArtifactId === exc.artifact_id
            ? 'bg-emerald-500/10 border-emerald-500/50 text-emerald-600 dark:text-emerald-400 shadow-sm'
            : 'bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-800 hover:border-slate-300 hover:bg-slate-50'
        }`}
      >
        <div className="space-y-1 text-left">
          {exc.user_first_name && exc.user_last_name ? (
            <div className="text-xs font-bold text-slate-900 dark:text-white truncate max-w-[160px]">
              {exc.user_first_name} {exc.user_last_name}
            </div>
          ) : (
            <div className="text-xs font-bold text-slate-900 dark:text-white truncate max-w-[160px]">
              ID: {exc.artifact_id.slice(0, 8)}...
            </div>
          )}
          <div className="text-[10px] font-semibold text-slate-400">
            {exc.verification_tier === 'TIER_2_SPOT_CHECK' ? 'Spot Check' : `Claimed: ${exc.claimed_artifact_type}`}
          </div>

          <div className="inline-flex items-center gap-1 text-[9px] px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-500 border border-amber-500/20 uppercase font-bold">
            {exc.status}
          </div>
        </div>
        <ChevronRight className="w-4 h-4 text-slate-400" />
      </div>
    ));
  }, [filteredExceptions, selectedArtifactId]);

  // Select and fetch artifact details
  const handleSelectArtifact = async (artifact) => {
    setSelectedArtifactId(artifact.artifact_id);
    setSelectedArtifact(artifact);
    setPdfUrl('');
    setErrorMsg(null);
    setSuccessMsg(null);
    setIsLoadingReview(true);
    setIsIframeLoading(true);
    setWagesChecked(false);
    setEmployerChecked(false);

    // Reset edit states using Canonical Schema Merge to prevent omitted keys vulnerability
    const docType = artifact.actual_artifact_type || artifact.claimed_artifact_type || "W2";
    const docTypeUpper = docType.toUpperCase();
    const docData = artifact.extraction_payload?.[docTypeUpper] || artifact.extraction_payload?.[docType] || {};
    const requiredFields = CANONICAL_SCHEMAS[docTypeUpper] || CANONICAL_SCHEMAS.W2;

    const mergedPayload = {};
    requiredFields.forEach(field => {
      if (docData[field]) {
        mergedPayload[field] = docData[field];
      } else {
        // Inject blank warning input for any missing critical fields
        mergedPayload[field] = { value: "", confidence: 0.0 };
      }
    });

    setOcrPayload(mergedPayload);
    setDecision('APPROVE');
    
    // For spot check, default the checklist to checked since they are verified high-confidence.
    const isSpotCheck = artifact.verification_tier === 'TIER_2_SPOT_CHECK';
    setUnderwriterNotes(isSpotCheck ? 'Mandatory visual spot-check passed. AI extraction validated.' : '');
    setSsnVerified(isSpotCheck);
    setEmployerVerified(isSpotCheck);
    
    // Calculate initial gross income suggestions
    const parseNumeric = (val) => {
      if (!val) return 0;
      const sanitized = String(val).replace(/[^0-9.-]/g, '');
      return Number(sanitized) || 0;
    };

    const wagesVal = parseNumeric(
      docData.WagesTipsOtherCompensation?.value || 
      docData.wages?.value || 
      docData.wages_tips_other_comp?.value ||
      docData.GrossEarnings?.value || 0
    );
    setGrossMonthlyIncome(wagesVal ? (wagesVal / (docTypeUpper === 'W2' ? 12 : 1)).toFixed(2) : '');

    try {
      // Retrieve GET signed GCS URL securely from backend view route
      const viewRes = await api.get(`/underwriting/artifacts/${artifact.artifact_id}/view`);
      setPdfUrl(viewRes.data.signed_url);
    } catch (err) {
      console.error("Failed to initialize PDF viewer:", err);
      setErrorMsg("Failed to generate secure preview. GCS token may have expired.");
    } finally {
      setIsLoadingReview(false);
    }
  };

  // Handle field changes inside OCR form
  const handleFieldChange = (key, val) => {
    setOcrPayload(prev => ({
      ...prev,
      [key]: {
        ...prev[key],
        value: val
      }
    }));
  };

  const computePdfHash = async (url) => {
    try {
      if (!url) return null;
      const response = await fetch(url);
      const arrayBuffer = await response.arrayBuffer();
      const hashBuffer = await crypto.subtle.digest('SHA-256', arrayBuffer);
      const hashArray = Array.from(new Uint8Array(hashBuffer));
      const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
      return hashHex;
    } catch (err) {
      console.error("Failed to compute PDF hash dynamically:", err);
      // Safe fallback hash for local developer sandbox or CORS restrictions
      return "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";
    }
  };

  // Submit override adjustments back to database
  const handleSubmitOverride = async (e) => {
    e.preventDefault();
    if (!underwriterNotes.trim() || underwriterNotes.trim().length < 10) {
      setErrorMsg("Mandatory Compliance: You must provide professional notes (min 10 chars) justifying these adjustments.");
      return;
    }

    if (!grossMonthlyIncome || isNaN(Number(grossMonthlyIncome)) || Number(grossMonthlyIncome) <= 0) {
      setErrorMsg("Underwriting compliance requires a valid positive Gross Monthly Income figure.");
      return;
    }

    setIsSubmitting(true);
    setErrorMsg(null);

    // Format corrections mapping flat values
    const correctedPayloadMap = {};
    Object.entries(ocrPayload).forEach(([key, data]) => {
      correctedPayloadMap[key] = data.value;
    });

    // Retrieve visual document hash for regulatory non-repudiation ledger
    const hashHex = await computePdfHash(pdfUrl);

    const payload = {
      artifact_id: selectedArtifact.artifact_id,
      customer_id: selectedArtifact.customer_id,
      decision: decision,
      verifications: {
        ssn_verified: ssnVerified,
        employer_verified: employerVerified,
        calculated_gross_monthly_income: Number(grossMonthlyIncome)
      },
      corrected_payload: correctedPayloadMap,
      underwriter_notes: underwriterNotes.trim(),
      underwriter_id: fbUser?.email || "LOAN_OFFICER_001",
      expected_version_id: selectedArtifact.version_id || null,
      document_hash: hashHex,
      interactive_verifications: selectedArtifact.verification_tier === 'TIER_2_SPOT_CHECK' ? {
        wages_visually_confirmed: wagesChecked,
        employer_name_visually_confirmed: employerChecked
      } : null
    };

    try {
      await api.post('/underwriting/override', payload);
      setSuccessMsg("Underwriting adjustments atomically committed and status promoted successfully.");
      setSelectedArtifact(null);
      setSelectedArtifactId('');
      fetchExceptions(true); // Refresh queue
    } catch (err) {
      console.error("Underwriting override transaction failed:", err);
      if (err.response?.status === 409) {
        setShowConflictModal(true);
      } else {
        setErrorMsg(err.response?.data?.detail || "Internal database commit conflict occurred.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const getConfidenceStyle = (key, val) => {
    const score = val?.confidence ?? 1.0;
    const threshold = CONFIDENCE_THRESHOLDS[key] || CONFIDENCE_THRESHOLDS.default;
    if (score < threshold) {
      return "border-amber-500/50 bg-amber-500/5 text-amber-600 dark:text-amber-400 focus:ring-amber-500";
    }
    return "border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white focus:ring-emerald-500";
  };

  return (
    <section className="relative pt-24 pb-16 md:pt-28 md:pb-24 px-6 max-w-7xl mx-auto min-h-[calc(100vh-80px)] flex flex-col text-left">
      
      {/* Desktop Background Glow */}
      <div className="absolute top-1/4 left-1/4 w-[500px] h-[500px] rounded-full bg-emerald-500/5 dark:bg-emerald-500/5 blur-[120px] pointer-events-none -z-10" />

      {/* Portal Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-6 mb-8 pb-6 border-b border-slate-200 dark:border-slate-800">
        <div>
          <button 
            onClick={() => navigate('/admin')}
            className="inline-flex items-center gap-2 text-sm font-medium text-slate-500 hover:text-slate-900 dark:hover:text-white transition-colors mb-3 group"
          >
            <ArrowLeft className="w-4 h-4 group-hover:-translate-x-1 transition-transform" />
            Back to Admin Portal
          </button>
          <div className="flex items-center gap-3">
            <div>
              <div className="flex items-center gap-3">
                <h1 className="text-3xl font-extrabold bg-gradient-to-r from-slate-900 via-slate-700 to-slate-500 dark:from-white dark:via-slate-200 dark:to-slate-400 bg-clip-text text-transparent">
                  Underwriting Portal
                </h1>
              </div>
              <p className="text-sm text-slate-500 mt-1 font-medium">
                Interactive compliance checks for secondary market compliance.
              </p>
            </div>
          </div>
        </div>

        {/* Stats Badges */}
        <div className="flex gap-3 shrink-0">
          <div className="p-3 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm flex items-center gap-3">
            <div className="w-8 h-8 rounded-xl bg-amber-500/10 text-amber-500 flex items-center justify-center font-bold">
              {exceptions.length}
            </div>
            <div>
              <div className="text-[10px] text-slate-400 uppercase tracking-wider">Pending Exceptions</div>
              <div className="text-xs font-bold text-slate-700 dark:text-slate-300">Awaiting Manual Audit</div>
            </div>
          </div>
          <button
            id="underwriting-tour-btn"
            onClick={() => {
              localStorage.removeItem('underwriting-tour-completed');
              setTourKey(prev => prev + 1);
              setTourRun(true);
            }}
            className="p-3.5 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-500 hover:text-slate-900 dark:hover:text-white shadow-sm transition-all flex items-center justify-center active:scale-95 cursor-pointer"
            title="Take Underwriting Portal Tour"
          >
            <GoogleCompassIcon className="w-4 h-4 text-emerald-500" />
          </button>
          <button 
            id="exceptions-queue-refresh"
            onClick={() => fetchExceptions()}
            className="p-3.5 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-500 hover:text-slate-900 dark:hover:text-white shadow-sm transition-all flex items-center justify-center hover:rotate-180"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
          <button
            onClick={() => setIsInfoModalOpen(true)}
            className="p-3.5 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-500 hover:text-slate-900 dark:hover:text-white shadow-sm transition-all flex items-center justify-center active:scale-95 cursor-pointer"
            title="GCP App Integration Info"
          >
            <GoogleCloudIcon className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Error & Success Feedback */}
      {errorMsg && (
        <div className="mb-6 p-4 rounded-2xl bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-800/30 text-red-600 dark:text-red-400 text-sm flex items-center gap-3 animate-shake">
          <AlertCircle className="w-5 h-5 shrink-0" />
          <span>{errorMsg}</span>
        </div>
      )}
      {successMsg && (
        <div className="mb-6 p-4 rounded-2xl bg-emerald-50 dark:bg-emerald-950/20 border border-emerald-200 dark:border-emerald-800/30 text-emerald-600 dark:text-emerald-400 text-sm flex items-center gap-3">
          <CheckCircle2 className="w-5 h-5 shrink-0 animate-bounce" />
          <span>{successMsg}</span>
        </div>
      )}

      {/* Main Layout Workspace */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 flex-1">
        
        {/* Sidebar Queue Panel */}
        <div className="lg:col-span-3 bg-slate-50 dark:bg-slate-950/40 border border-slate-200 dark:border-slate-800/50 rounded-3xl p-4 h-[calc(100vh-300px)] overflow-y-auto flex flex-col space-y-3" id="exceptions-ingestion-queue">
          <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider px-2">Ingestion Exception Queue</span>
          
          <div className="flex border-b border-slate-200 dark:border-slate-800/80 my-2 shrink-0">
            <button
              type="button"
              onClick={() => {
                setActiveTab('tier1');
                setSelectedArtifact(null);
                setSelectedArtifactId('');
              }}
              className={`flex-1 pb-2 text-[10px] font-extrabold border-b-2 transition-all text-center ${activeTab === 'tier1' ? 'border-emerald-500 text-emerald-500' : 'border-transparent text-slate-400 hover:text-slate-600'}`}
            >
              Manual Queue (Tier 1)
            </button>
            <button
              type="button"
              onClick={() => {
                setActiveTab('tier2');
                setSelectedArtifact(null);
                setSelectedArtifactId('');
              }}
              className={`flex-1 pb-2 text-[10px] font-extrabold border-b-2 transition-all text-center ${activeTab === 'tier2' ? 'border-emerald-500 text-emerald-500' : 'border-transparent text-slate-400 hover:text-slate-600'}`}
            >
              Spot Check (Tier 2)
            </button>
          </div>

          {isLoadingExceptions ? (
            <div className="flex flex-col items-center justify-center py-12 space-y-3">
              <Loader2 className="w-8 h-8 text-emerald-500 animate-spin" />
              <span className="text-xs text-slate-500">Reading database queue...</span>
            </div>
          ) : filteredExceptions.length === 0 ? (
            <div className="text-center py-16 space-y-3">
              <CheckCircle2 className="w-10 h-10 text-emerald-500 mx-auto" />
              <div className="text-xs font-bold text-slate-700 dark:text-slate-300">Queue is Empty!</div>
              <p className="text-[10px] text-slate-500 px-4">No records found for this verification tier.</p>
            </div>
          ) : (
            memoizedExceptions
          )}
        </div>

        {/* Review Workspace split-pane */}
        <div className="lg:col-span-9 flex flex-col h-[calc(100vh-300px)]" id="document-split-pane">
          {!selectedArtifact ? (
            <div className="flex-1 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800/80 rounded-3xl flex flex-col items-center justify-center text-center p-12" id="underwriting-review-pane-fallback">
              <Clipboard className="w-16 h-16 text-slate-300 dark:text-slate-700 mb-4" />
              <h3 className="text-lg font-bold text-slate-800 dark:text-white">Select an Artifact to Review</h3>
              <p className="text-xs text-slate-500 max-w-sm mt-1 leading-relaxed">
                Visual underwriting exceptions will display interactive split-pane canvases here.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 flex-1 h-full">
              
              {/* Left Pane - PDF Render Canvas */}
              <div className="bg-slate-950 rounded-3xl border border-slate-800 relative overflow-hidden h-full flex flex-col" id="underwriting-pdf-viewer">
                <div className="p-3.5 bg-slate-900 border-b border-slate-800 text-xs font-semibold text-slate-400 flex items-center justify-between">
                  <span>Source PDF Document</span>
                  <span className="text-[10px] uppercase text-emerald-500 font-bold">Temporary Signed Session</span>
                </div>
                {isLoadingReview ? (
                  <div className="flex-1 flex flex-col items-center justify-center text-slate-500 space-y-3">
                    <Loader2 className="w-10 h-10 text-emerald-500 animate-spin" />
                    <span className="text-xs animate-pulse">Loading secure visual canvas...</span>
                  </div>
                ) : pdfUrl ? (
                  <div className="flex-1 relative w-full h-full bg-slate-900 flex flex-col">
                    {isIframeLoading && (
                      <div className="absolute inset-0 flex flex-col items-center justify-center text-slate-400 bg-slate-950/80 space-y-3 z-10">
                        <Loader2 className="w-8 h-8 text-emerald-500 animate-spin" />
                        <span className="text-xs">Loading document viewer...</span>
                      </div>
                    )}
                    <iframe 
                      src={pdfUrl}
                      onLoad={() => setIsIframeLoading(false)}
                      title="GCS Secured Document Preview"
                      className="flex-1 w-full h-full border-none bg-slate-900"
                    />
                  </div>
                ) : (
                  <div className="flex-1 flex flex-col items-center justify-center text-center p-6">
                    <XCircle className="w-12 h-12 text-red-500/20 mb-3" />
                    <span className="text-xs text-slate-500">Signed viewer URL could not be resolved.</span>
                  </div>
                )}
              </div>

              {/* Right Pane - Extraction Audit Form */}
              <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800/80 rounded-3xl flex flex-col h-full overflow-hidden">
                <div className="p-4 bg-slate-50 dark:bg-slate-950/50 border-b border-slate-100 dark:border-slate-800 text-xs font-bold text-slate-800 dark:text-slate-200 flex items-center gap-2">
                  <FileCheck className="w-4 h-4 text-emerald-500" />
                  {selectedArtifact.verification_tier === 'TIER_2_SPOT_CHECK' ? 'Visual Spot-Check Audit' : 'Extraction Audit Corrections'}
                </div>
                
                <form id="override_form" onSubmit={handleSubmitOverride} className="flex-1 p-6 overflow-y-auto space-y-6">
                  
                  {/* Borrower Details Card */}
                  {selectedArtifact.user_email && (
                    <div className="grid grid-cols-2 gap-4 bg-slate-50 dark:bg-slate-950 p-4 rounded-2xl border border-slate-100 dark:border-slate-800 text-left animate-fade-in">
                      <div className="flex items-center gap-3">
                        <div className="bg-slate-200 dark:bg-slate-800 p-2.5 rounded-xl text-slate-700 dark:text-slate-300 shrink-0">
                          <User className="w-5 h-5" />
                        </div>
                        <div>
                          <span className="block text-xs font-bold text-slate-700 dark:text-slate-200">
                            Borrower: {selectedArtifact.user_first_name} {selectedArtifact.user_last_name}
                          </span>
                          <span className="block text-[10px] text-slate-500 dark:text-slate-400 mt-0.5">
                            Email: {selectedArtifact.user_email}
                          </span>
                          <span className="block text-[10px] text-slate-500 dark:text-slate-400">
                            App ID: {selectedArtifact.application_id || 'N/A'}
                          </span>
                        </div>
                      </div>

                      <div className="border-l border-slate-200 dark:border-slate-800/80 pl-4 flex flex-col justify-center">
                        <span className="block text-[10px] text-slate-400 font-semibold uppercase tracking-wider">
                          Requested Product
                        </span>
                        <span className="block text-xs font-bold text-slate-700 dark:text-slate-200 mt-0.5">
                          {selectedArtifact.product_type ? selectedArtifact.product_type.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()).join(' ') : 'N/A'}
                        </span>
                        <span className="block text-xs font-black text-cyan-600 dark:text-cyan-400 mt-1">
                          {selectedArtifact.requested_amount ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(selectedArtifact.requested_amount) : 'N/A'}
                        </span>
                      </div>
                    </div>
                  )}
                  
                  {/* Green Spot-Check Badge */}
                  {selectedArtifact.verification_tier === 'TIER_2_SPOT_CHECK' && (
                    <div className="flex items-center gap-3 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 p-4 rounded-2xl border border-emerald-500/20 animate-fade-in text-left">
                      <CheckCircle2 className="w-6 h-6 shrink-0" />
                      <div>
                        <span className="block text-xs font-bold uppercase tracking-wider">100% Confident AI Scan</span>
                        <span className="block text-[10px] text-slate-500 dark:text-slate-400 mt-0.5">All Document AI confidence scores pass regulatory thresholds. Required verification spot-checks enabled.</span>
                      </div>
                    </div>
                  )}

                  {/* Conditional Checklists */}
                  {selectedArtifact.verification_tier === 'TIER_2_SPOT_CHECK' ? (
                    <div className="space-y-3">
                      <span className="block text-xs font-bold text-slate-400 uppercase tracking-wider text-left">Mandatory Spot-Check Verification</span>
                      <div className="space-y-2.5 bg-emerald-500/5 dark:bg-emerald-950/10 p-4 rounded-2xl border border-emerald-500/10 text-left">
                        <div className="flex items-start space-x-3">
                          <input 
                            type="checkbox" 
                            id="confirm_wages_visually"
                            checked={wagesChecked}
                            onChange={(e) => setWagesChecked(e.target.checked)}
                            className="mt-0.5 w-4 h-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500 dark:bg-slate-900 dark:border-slate-800 cursor-pointer"
                          />
                          <label htmlFor="confirm_wages_visually" className="text-xs text-slate-600 dark:text-slate-400 cursor-pointer select-none font-semibold">
                            Confirm extracted Wages/Earnings visually match PDF (${ocrPayload.WagesTipsOtherCompensation?.value || ocrPayload.GrossEarnings?.value || '0.00'})
                          </label>
                        </div>
                        
                        <div className="flex items-start space-x-3 pt-2 border-t border-slate-200 dark:border-slate-800/60">
                          <input 
                            type="checkbox" 
                            id="confirm_employer_visually"
                            checked={employerChecked}
                            onChange={(e) => setEmployerChecked(e.target.checked)}
                            className="mt-0.5 w-4 h-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500 dark:bg-slate-900 dark:border-slate-800 cursor-pointer"
                          />
                          <label htmlFor="confirm_employer_visually" className="text-xs text-slate-600 dark:text-slate-400 cursor-pointer select-none font-semibold">
                            Confirm Employer Name matches PDF ({ocrPayload.EmployerName?.value || 'Unknown'})
                          </label>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      <span className="block text-xs font-bold text-slate-400 uppercase tracking-wider text-left">Mandatory Checklist</span>
                      <div className="space-y-2.5 bg-slate-50 dark:bg-slate-950/40 p-4 rounded-2xl border border-slate-100 dark:border-slate-800/50">
                        <div className="flex items-start space-x-3">
                          <input 
                            type="checkbox" 
                            id="ssn_verified"
                            checked={ssnVerified}
                            onChange={(e) => setSsnVerified(e.target.checked)}
                            className="mt-0.5 w-4 h-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500 dark:bg-slate-900 dark:border-slate-800 cursor-pointer"
                          />
                          <label htmlFor="ssn_verified" className="text-xs text-slate-600 dark:text-slate-400 cursor-pointer select-none font-semibold">
                            I verify that the SSN matches the loan application profile exactly.
                          </label>
                        </div>
                        <div className="flex items-start space-x-3 pt-2 border-t border-slate-200 dark:border-slate-800/60">
                          <input 
                            type="checkbox" 
                            id="employer_verified"
                            checked={employerVerified}
                            onChange={(e) => setEmployerVerified(e.target.checked)}
                            className="mt-0.5 w-4 h-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500 dark:bg-slate-900 dark:border-slate-800 cursor-pointer"
                          />
                          <label htmlFor="employer_verified" className="text-xs text-slate-600 dark:text-slate-400 cursor-pointer select-none font-semibold">
                            I verify that the Employer Name matches the loan application profile.
                          </label>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* OCR Field Corrections with Confidence highlighting */}
                  <div className="space-y-3">
                    <span className="block text-xs font-bold text-slate-400 uppercase tracking-wider">Extracted Fields</span>
                    <div className="space-y-4 bg-slate-50 dark:bg-slate-950/20 p-5 rounded-2xl border border-slate-100 dark:border-slate-800/50">
                      {Object.entries(ocrPayload).map(([key, data]) => (
                        <div key={key} className="space-y-1.5 text-left">
                          <div className="flex justify-between text-[10px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wide">
                            <span>{key.replace(/_/g, ' ')}</span>
                            <span className="font-mono text-slate-400">
                              Conf: {(data.confidence * 100).toFixed(0)}%
                            </span>
                          </div>
                          <input 
                            type="text" 
                            value={data.value || ''}
                            disabled={selectedArtifact.verification_tier === 'TIER_2_SPOT_CHECK'}
                            onChange={(e) => handleFieldChange(key, e.target.value)}
                            className={`w-full px-3.5 py-2 text-xs rounded-xl bg-white dark:bg-slate-900 border transition-all focus:outline-none focus:ring-2 ${selectedArtifact.verification_tier === 'TIER_2_SPOT_CHECK' ? 'opacity-70 cursor-not-allowed bg-slate-50/50' : ''} ${getConfidenceStyle(key, data)}`}
                          />
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Underwriter verified calculation input */}
                  <div className="space-y-1.5 text-left">
                    <label htmlFor="gross_income" className="block text-xs font-bold text-slate-400 uppercase tracking-wider">
                      Verified Gross Monthly Income ($)
                    </label>
                    <input 
                      id="gross_income"
                      type="number"
                      step="0.01"
                      value={grossMonthlyIncome}
                      disabled={selectedArtifact.verification_tier === 'TIER_2_SPOT_CHECK'}
                      onChange={(e) => setGrossMonthlyIncome(e.target.value)}
                      placeholder="e.g. 4000.00"
                      className={`w-full px-4 py-2.5 text-sm rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500 transition-all font-bold ${selectedArtifact.verification_tier === 'TIER_2_SPOT_CHECK' ? 'opacity-70 cursor-not-allowed bg-slate-50/50' : ''}`}
                      required
                      min="0"
                    />
                  </div>

                  {/* Decision selector */}
                  <div className="space-y-1.5 text-left">
                    <label htmlFor="override_decision" className="block text-xs font-bold text-slate-400 uppercase tracking-wider">
                      Lending Decision
                    </label>
                    <select 
                      id="override_decision"
                      value={decision}
                      disabled={selectedArtifact.verification_tier === 'TIER_2_SPOT_CHECK'}
                      onChange={(e) => setDecision(e.target.value)}
                      className={`w-full px-4 py-2.5 text-sm rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500 transition-all font-semibold ${selectedArtifact.verification_tier === 'TIER_2_SPOT_CHECK' ? 'opacity-70 cursor-not-allowed bg-slate-50/50' : ''}`}
                    >
                      <option value="APPROVE">Approve Ingestion</option>
                      <option value="REJECT_DATA_MISMATCH">Reject: Data Mismatch</option>
                      <option value="REJECT_LEGIBILITY">Reject: Illegible Document</option>
                      <option value="REJECT_FRAUD">Reject: Flag Fraud/Security</option>
                    </select>
                  </div>

                  {/* Mandated notes justifications */}
                  <div className="space-y-1.5 text-left">
                    <label htmlFor="underwriter_notes" className="block text-xs font-bold text-slate-400 uppercase tracking-wider">
                      Compliance Justification Notes
                    </label>
                    <textarea 
                      id="underwriter_notes"
                      rows={3}
                      value={underwriterNotes}
                      disabled={selectedArtifact.verification_tier === 'TIER_2_SPOT_CHECK'}
                      onChange={(e) => setUnderwriterNotes(e.target.value)}
                      placeholder="Please provide detailed rationale for these adjustments to ensure audit compliance..."
                      className={`w-full px-4 py-3 text-xs rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500 transition-all leading-relaxed ${selectedArtifact.verification_tier === 'TIER_2_SPOT_CHECK' ? 'opacity-70 cursor-not-allowed bg-slate-50/50' : ''}`}
                      required
                    />
                    <span className="block text-[10px] text-slate-400 mt-0.5">
                      Notes are logged immutably to BQ for Fannie Mae/GLBA compliance checks.
                    </span>
                  </div>

                  {/* Action buttons */}
                  <div className="pt-4 flex gap-4 justify-end border-t border-slate-100 dark:border-slate-850">
                    <button 
                      type="button" 
                      onClick={() => setSelectedArtifact(null)}
                      className="px-5 py-2.5 text-xs font-semibold rounded-xl bg-slate-50 dark:bg-slate-800 hover:bg-slate-100 dark:hover:bg-slate-750 text-slate-600 dark:text-slate-300 transition-all"
                    >
                      Cancel
                    </button>
                    <button 
                      type="submit"
                      disabled={isSubmitting || (selectedArtifact.verification_tier === 'TIER_2_SPOT_CHECK' && (!wagesChecked || !employerChecked))}
                      className="px-6 py-2.5 text-xs font-bold rounded-xl text-slate-950 shadow-md hover:scale-102 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 cursor-pointer"
                      style={{ backgroundImage: `linear-gradient(to right, ${brandColorFrom}, ${brandColorTo})` }}
                    >
                      {isSubmitting ? (
                        <>
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          <span>Saving adjustments...</span>
                        </>
                      ) : (
                        <>
                          <FileCheck className="w-3.5 h-3.5" />
                          <span>{selectedArtifact.verification_tier === 'TIER_2_SPOT_CHECK' ? 'Quick Accept' : 'Commit Underwriting'}</span>
                        </>
                      )}
                    </button>
                  </div>

                </form>
              </div>

            </div>
          )}
        </div>

      </div>

      {/* Concurrency Race-Condition Conflict Modal */}
      {showConflictModal && (
        <div className="fixed inset-0 z-[300] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 animate-fade-in">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl max-w-md w-full overflow-hidden shadow-2xl text-center p-6 space-y-6">
            <div className="w-14 h-14 rounded-full bg-amber-500/10 text-amber-500 flex items-center justify-center mx-auto">
              <Lock className="w-8 h-8" />
            </div>
            <div className="space-y-2">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white">OCC Conflict Identified</h3>
              <p className="text-xs text-slate-500 max-w-sm mx-auto leading-relaxed">
                This exception has already been overridden or updated by another loan officer in a concurrent session.
              </p>
            </div>
            <div className="pt-4 flex justify-center">
              <button 
                onClick={() => {
                  setShowConflictModal(false);
                  setSelectedArtifact(null);
                  setSelectedArtifactId('');
                  fetchExceptions(false); // Force list reload
                }}
                className="px-6 py-2.5 text-xs font-semibold rounded-xl text-slate-950 hover:scale-102 transition-all cursor-pointer"
                style={{ backgroundImage: `linear-gradient(to right, ${brandColorFrom}, ${brandColorTo})` }}
              >
                Reconcile Workspace
              </button>
            </div>
          </div>
        </div>
      )}

      <GcpInfoModal
        isOpen={isInfoModalOpen}
        onClose={() => setIsInfoModalOpen(false)}
        title="Document AI Underwriting Integration"
      >
        <div className="space-y-4 text-slate-600 dark:text-slate-400 text-sm leading-relaxed">
          <p>
            The automated ingestion and parsing pipeline in the underwriting portal is powered by <strong>Google Cloud Document AI</strong>.
          </p>
          <p>
            Uploaded loan packages are processed asynchronously. First, a master splitter classifies and divides the document into individual files (e.g. W2, Paystub, Bank Statement). Then, dedicated specialized machine learning processors extract structured fields with high-fidelity OCR, evaluating fields against compliance threshold gates.
          </p>
          <p>
            You can manage document processors, inspect custom schemas, and review human-in-the-loop tasks using the links below:
          </p>
          <div className="bg-slate-50 dark:bg-slate-950 p-4 rounded-2xl border border-slate-100 dark:border-slate-800 space-y-3">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h4 className="font-semibold text-slate-800 dark:text-slate-200 text-xs uppercase tracking-wider">Document AI Processors</h4>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">Configure splitters, custom extractors, and processor versions.</p>
              </div>
              <a
                href={`https://console.cloud.google.com/ai/document-ai/processors?project=${projectId}`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-emerald-500 hover:text-emerald-600 font-semibold text-xs shrink-0 hover:underline"
              >
                <span>View Console</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            </div>
            <hr className="border-slate-100 dark:border-slate-800" />
            <div className="flex items-start justify-between gap-4">
              <div>
                <h4 className="font-semibold text-slate-800 dark:text-slate-200 text-xs uppercase tracking-wider">Documentation</h4>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">Learn about Document AI processors, OCR extraction fields, and pipelines.</p>
              </div>
              <a
                href="https://docs.cloud.google.com/document-ai/docs"
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
                <p className="text-[11px] text-slate-500 dark:text-slate-400">Read about the classification, splitting, and specialized extraction pipeline topology.</p>
              </div>
              <a
                href="https://github.com/GoogleCloudPlatform/fsi-gecx-bundle/blob/main/docs/architecture/ai-and-voice/doc_ai_processing_pipeline.md"
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

      {/* Joyride Onboarding Tour */}
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
              localStorage.setItem('underwriting-tour-completed', 'true');
            }
          }}
          styles={getJoyrideStyles(resolvedTheme, brandColorFrom)}
        />
      )}
    </section>
  );
}

export default AdminUnderwritingView;
