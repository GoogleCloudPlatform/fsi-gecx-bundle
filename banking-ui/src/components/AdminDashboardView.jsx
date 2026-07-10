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

import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { FileCheck, MessageSquare, Shield, ChevronRight, LayoutDashboard, Volume2, AlertCircle, CheckCircle2, Settings, Bell, ExternalLink, Sparkles } from 'lucide-react';
import { resetDatabase, getResetDatabaseAccess, getSystemSettings, updateSystemSettings, provisionMyDemo, resetMyDemo, getCreditCardAccount } from '../utils/api.js';
import GoogleCloudIcon from './GoogleCloudIcon.jsx';
import GcpInfoModal from './GcpInfoModal.jsx';
import { showInfoModals } from '../utils/constants.js';

function AdminDashboardView() {
  const navigate = useNavigate();
  const [isResetting, setIsResetting] = useState(false);
  const [purgeAuditLogs, setPurgeAuditLogs] = useState(false);
  const [purgeDataLake, setPurgeDataLake] = useState(false);
  const [fullResetAccess, setFullResetAccess] = useState({ allowed: false, message: 'Full database reset status is loading.' });
  const [notice, setNotice] = useState({ type: '', text: '' });
  const [isInfoModalOpen, setIsInfoModalOpen] = useState(false);
  
  // Personal Demo Suite States
  const [hasSeededProfile, setHasSeededProfile] = useState(false);
  const [isProvisioning, setIsProvisioning] = useState(false);
  const [isResettingDemo, setIsResettingDemo] = useState(false);

  // Settings States
  const [hardTimeoutEnabled, setHardTimeoutEnabled] = useState(false);
  const [maxDuration, setMaxDuration] = useState(300);
  const [warningDuration, setWarningDuration] = useState(240);
  const [avatarSelection, setAvatarSelection] = useState('random');
  const [mockAvatarEnabled, setMockAvatarEnabled] = useState(false);
  const [showInfoModalsState, setShowInfoModalsState] = useState(true);
  const [isSavingSettings, setIsSavingSettings] = useState(false);

  // Load Settings on Mount
  useEffect(() => {
    async function loadSettings() {
      try {
        const settings = await getSystemSettings();
        if (settings) {
          setHardTimeoutEnabled(settings.voice_agent_hard_timeout_enabled === 'true');
          setMaxDuration(parseInt(settings.voice_agent_max_duration) || 300);
          setWarningDuration(parseInt(settings.voice_agent_warning_duration) || 240);
          setAvatarSelection(settings.voice_agent_avatar_selection || 'random');
          setMockAvatarEnabled(settings.voice_agent_mock_avatar_enabled === 'true');
          
          const showInfo = settings.show_info_modals !== undefined ? settings.show_info_modals : String(import.meta.env.VITE_SHOW_INFO_MODALS !== 'false');
          setShowInfoModalsState(showInfo === 'true');
          localStorage.setItem('show_info_modals', showInfo);
        }
      } catch (err) {
        console.error("Failed to load voice agent settings:", err);
      }
    }
    loadSettings();
  }, []);

  useEffect(() => {
    async function loadResetAccess() {
      try {
        const access = await getResetDatabaseAccess();
        setFullResetAccess(access);
      } catch (err) {
        console.error("Failed to load full reset access:", err);
        setFullResetAccess({ allowed: false, message: 'Full database reset is restricted. Use personal demo reset for presenter recovery.' });
      }
    }
    loadResetAccess();
  }, []);

  // Check if current user has a seeded profile
  useEffect(() => {
    async function checkSeededProfile() {
      try {
        await getCreditCardAccount(null, false);
        setHasSeededProfile(true);
      } catch {
        setHasSeededProfile(false);
      }
    }
    checkSeededProfile();
  }, []);

  const handleSaveSettings = async (e) => {
    e.preventDefault();
    setIsSavingSettings(true);
    setNotice({ type: '', text: '' });
    try {
      await updateSystemSettings({
        voice_agent_hard_timeout_enabled: String(hardTimeoutEnabled),
        voice_agent_max_duration: String(maxDuration),
        voice_agent_warning_duration: String(warningDuration),
        voice_agent_avatar_selection: avatarSelection,
        voice_agent_mock_avatar_enabled: String(mockAvatarEnabled),
        show_info_modals: String(showInfoModalsState)
      });
      localStorage.setItem('show_info_modals', String(showInfoModalsState));
      setNotice({ type: 'success', text: 'Voice agent settings updated successfully!' });
      setTimeout(() => setNotice({ type: '', text: '' }), 4000);
    } catch (err) {
      setNotice({ type: 'error', text: err.response?.data?.detail || 'Failed to update settings.' });
    } finally {
      setIsSavingSettings(false);
    }
  };

  const handleResetDatabase = async () => {
    if (!fullResetAccess.allowed) {
      setNotice({ type: 'error', text: fullResetAccess.message || 'Full database reset is restricted.' });
      return;
    }
    let confirmMsg = "Are you sure you want to reset the database? This will clear active applications and cards while preserving immutable audit logs and analytical lake tables.";
    if (purgeAuditLogs && purgeDataLake) {
      confirmMsg = "Are you sure you want to reset the database AND PURGE ALL BIGQUERY AUDIT LOGS & APACHE ICEBERG DATA LAKE TABLES? This cannot be undone.";
    } else if (purgeAuditLogs) {
      confirmMsg = "Are you sure you want to reset the database AND PURGE ALL BIGQUERY & POSTGRESQL AUDIT LOGS? This cannot be undone.";
    } else if (purgeDataLake) {
      confirmMsg = "Are you sure you want to reset the database AND PURGE ALL APACHE ICEBERG DATA LAKE TABLES? This cannot be undone.";
    }
    if (!window.confirm(confirmMsg)) {
      return;
    }
    setIsResetting(true);
    setNotice({ type: '', text: '' });
    try {
      const res = await resetDatabase(purgeAuditLogs, purgeDataLake);
      const warningText = Array.isArray(res.warnings) && res.warnings.length > 0
        ? ` Warnings: ${res.warnings.join(' ')}`
        : '';
      setNotice({
        type: res.status === 'PARTIAL_SUCCESS' ? 'warning' : 'success',
        text: `${res.message || 'Database successfully reset and re-seeded!'}${warningText}`,
      });
      setTimeout(() => setNotice({ type: '', text: '' }), 5000);
    } catch (err) {
      setNotice({ type: 'error', text: err.response?.data?.detail || 'Failed to reset database.' });
    } finally {
      setIsResetting(false);
    }
  };

  const handleProvisionDemo = async () => {
    setIsProvisioning(true);
    setNotice({ type: '', text: '' });
    try {
      const res = await provisionMyDemo();
      setHasSeededProfile(true);
      setNotice({ type: 'success', text: res.message || 'Demo profile provisioned successfully!' });
      setTimeout(() => setNotice({ type: '', text: '' }), 5000);
    } catch (err) {
      setNotice({ type: 'error', text: err.response?.data?.detail || 'Failed to provision demo profile.' });
    } finally {
      setIsProvisioning(false);
    }
  };

  const handleResetDemo = async () => {
    if (!window.confirm("Are you sure you want to reset your personal demo suite? This will clear your swipe history but won't impact other users.")) {
      return;
    }
    setIsResettingDemo(true);
    setNotice({ type: '', text: '' });
    try {
      const res = await resetMyDemo();
      setNotice({ type: 'success', text: res.message || 'Demo profile reset successfully!' });
      setTimeout(() => setNotice({ type: '', text: '' }), 5000);
    } catch (err) {
      setNotice({ type: 'error', text: err.response?.data?.detail || 'Failed to reset demo profile.' });
    } finally {
      setIsResettingDemo(false);
    }
  };

  const adminModules = [
    {
      title: "Underwriting Portal",
      description: "Verify low-confidence W-2 / paystub extractions, execute structural income verification checklists, and audit borrower exceptions.",
      path: "/admin/underwriting",
      icon: FileCheck,
      color: "from-emerald-500 to-teal-600"
    },
    {
      title: "Admin Secure Messaging",
      description: "Remediate customer security threads, respond to loan officer/borrower secure messaging, and audit thread trace histories.",
      path: "/admin/messaging",
      icon: MessageSquare,
      color: "from-blue-500 to-indigo-600"
    },
    {
      title: "Supervisor Voice Takeover",
      description: "Monitor active credit card voice support sessions, review customer transcripts, and accept WebRTC supervisor takeovers.",
      path: "/admin/support",
      icon: Volume2,
      color: "from-amber-500 to-orange-600"
    },
    {
      title: "FCM Messaging Debug",
      description: "Trigger simulated Firebase Cloud Messaging notifications, override thread IDs, and dispatch mock agent alerts.",
      path: "/debug",
      icon: Bell,
      color: "from-purple-500 to-pink-600"
    },
    {
      title: "Active Lakehouse & Simulation",
      description: "Monitor real-time BigQuery Data Canvas spend velocity, Datastream CDC sync status, and inject targeted fraud anomalies or activity surges.",
      path: "/admin/simulation",
      icon: Sparkles,
      color: "from-cyan-500 to-blue-600"
    }
  ];

  return (
    <section className="relative pt-24 pb-16 md:pt-28 md:pb-24 px-6 max-w-6xl mx-auto min-h-[calc(100vh-80px)] flex flex-col text-left">
      
      {/* Dynamic background glow */}
      <div className="absolute top-1/4 left-1/3 w-[400px] h-[400px] rounded-full bg-emerald-500/5 blur-[100px] pointer-events-none -z-10" />

      {/* Portal Header */}
      <div className="mb-12 pb-6 border-b border-slate-200 dark:border-slate-800 flex justify-between items-center relative w-full">
        <div className="flex items-center gap-3">
          <div className="p-3 rounded-2xl bg-slate-50 dark:bg-slate-800 text-slate-700 dark:text-slate-300 shadow-sm">
            <LayoutDashboard className="w-6 h-6" />
          </div>
          <div>
            <h1 className="text-3xl font-extrabold bg-gradient-to-r from-slate-900 via-slate-700 to-slate-500 dark:from-white dark:via-slate-200 dark:to-slate-400 bg-clip-text text-transparent">
              Nova Horizon Admin Portal
            </h1>
            <p className="text-sm text-slate-500 mt-1">
              Secure, role-gated management dashboard for employee operations, underwriting, and support audits.
            </p>
          </div>
        </div>
        {showInfoModals() && (
          <button
            onClick={() => setIsInfoModalOpen(true)}
            className="p-2.5 rounded-2xl hover:bg-slate-805/80 border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm text-slate-400 hover:text-slate-200 transition-all active:scale-95 cursor-pointer flex items-center justify-center"
            title="GCP Admin Integration Info"
          >
            <GoogleCloudIcon className="w-5 h-5 text-indigo-400" />
          </button>
        )}
      </div>

      {/* Module Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
        {adminModules.map((mod) => {
          const IconComponent = mod.icon;
          return (
            <div 
              key={mod.title}
              onClick={() => navigate(mod.path)}
              className="group relative bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800/80 rounded-3xl p-6 cursor-pointer transition-all hover:-translate-y-1 hover:shadow-lg hover:border-slate-300 dark:hover:border-slate-700 flex flex-col justify-between min-h-[220px]"
            >
              <div className="space-y-4">
                {/* Top row: Icon & Title */}
                <div className="flex items-center justify-between">
                  <div className={`w-12 h-12 rounded-2xl bg-gradient-to-br ${mod.color} text-slate-950 flex items-center justify-center shadow-md group-hover:scale-105 transition-all`}>
                    <IconComponent className="w-6 h-6" />
                  </div>
                  <Shield className="w-4 h-4 text-slate-300 dark:text-slate-700" />
                </div>
                
                {/* Text Content */}
                <div className="space-y-2">
                  <h3 className="text-lg font-bold text-slate-900 dark:text-white group-hover:text-emerald-500 dark:group-hover:text-emerald-400 transition-all">
                    {mod.title}
                  </h3>
                  <p className="text-xs text-slate-500 leading-relaxed">
                    {mod.description}
                  </p>
                </div>
              </div>

              {/* Bottom Action link */}
              <div className="pt-4 border-t border-slate-100 dark:border-slate-850 flex items-center justify-between text-[10px] font-bold uppercase tracking-wider text-slate-400 group-hover:text-emerald-500 transition-all">
                <span>Launch Module</span>
                <ChevronRight className="w-4 h-4 transform group-hover:translate-x-1 transition-all" />
              </div>
            </div>
          );
        })}
      </div>

      {/* Settings Form */}
      <form onSubmit={handleSaveSettings} className="mt-8 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl p-6 space-y-6">
        {/* Section 1: Demo & Website Settings */}
        <div className="space-y-4">
          <div className="flex items-center gap-2 pb-3 border-b border-slate-100 dark:border-slate-800/80">
            <Sparkles className="w-5 h-5 text-indigo-400" />
            <h3 className="text-sm font-bold text-slate-900 dark:text-white">Demo & Presentation Settings</h3>
          </div>
          
          <div className="flex items-center justify-between py-2">
            <div>
              <span className="text-xs font-bold text-slate-800 dark:text-slate-200 block">Enable Developer Architecture Tooltips</span>
              <p className="text-[10px] text-slate-400 mt-0.5">Displays blue Google Cloud architecture shortcuts and visual flow diagrams across page views to help walkthroughs.</p>
            </div>
            <input
              type="checkbox"
              checked={showInfoModalsState}
              onChange={(e) => setShowInfoModalsState(e.target.checked)}
              className="w-4 h-4 rounded border-slate-300 text-emerald-500 focus:ring-emerald-500"
            />
          </div>
        </div>

        {/* Section 2: Voice & Live Avatar Settings */}
        <div className="space-y-6 pt-6 border-t border-slate-100 dark:border-slate-800/80">
          <div className="flex items-center gap-2 pb-3 border-b border-slate-100 dark:border-slate-800/80">
            <Settings className="w-5 h-5 text-emerald-500" />
            <h3 className="text-sm font-bold text-slate-900 dark:text-white">Voice & Live Avatar Settings</h3>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Avatar Selection Override */}
            <div className="space-y-2">
              <label className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider block">
                Active Avatar Selection
              </label>
              <select
                value={avatarSelection}
                onChange={(e) => setAvatarSelection(e.target.value)}
                className="w-full px-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/20 text-xs font-semibold text-slate-800 dark:text-slate-200 focus:outline-none focus:border-emerald-500"
              >
                <option value="random">Randomize (Ingrid, Paul, Sam)</option>
                <option value="Ingrid">Force Ingrid</option>
                <option value="Paul">Force Paul</option>
                <option value="Sam">Force Sam</option>
                <option value="Jay">Force Jay</option>
                <option value="Vera">Force Vera</option>
              </select>
              <p className="text-[10px] text-slate-400">Controls which built-in virtual face representative joins the WebRTC session.</p>
            </div>

            {/* Call Timeout Configurations */}
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <label className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider block">
                  Enforce Hard Timeout (Watchdog)
                </label>
                <input
                  type="checkbox"
                  checked={hardTimeoutEnabled}
                  onChange={(e) => setHardTimeoutEnabled(e.target.checked)}
                  className="w-4 h-4 rounded border-slate-300 text-emerald-500 focus:ring-emerald-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-[10px] font-semibold text-slate-400 block">Max Duration (s)</label>
                  <input
                    type="number"
                    value={maxDuration}
                    onChange={(e) => setMaxDuration(parseInt(e.target.value) || 0)}
                    className="w-full px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/20 text-xs font-semibold text-slate-800 dark:text-slate-200"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-[10px] font-semibold text-slate-400 block">Warning Delay (s)</label>
                  <input
                    type="number"
                    value={warningDuration}
                    onChange={(e) => setWarningDuration(parseInt(e.target.value) || 0)}
                    className="w-full px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/20 text-xs font-semibold text-slate-800 dark:text-slate-200"
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Mock Sandbox Toggle */}
          <div className="flex items-center justify-between pt-4 border-t border-slate-100 dark:border-slate-800/80">
            <div>
              <span className="text-xs font-bold text-slate-800 dark:text-slate-200 block">Enable Mock Avatar Sandbox</span>
              <p className="text-[10px] text-slate-400 mt-0.5">Bypasses Google Vertex APIs and loops a local video file from disk to save token billing costs during testing.</p>
            </div>
            <input
              type="checkbox"
              checked={mockAvatarEnabled}
              onChange={(e) => setMockAvatarEnabled(e.target.checked)}
              className="w-4 h-4 rounded border-slate-300 text-emerald-500 focus:ring-emerald-500"
            />
          </div>
        </div>

        {/* Action Button */}
        <div className="flex justify-end pt-2">
          <button
            type="submit"
            disabled={isSavingSettings}
            className={`px-5 py-2.5 rounded-xl border text-xs font-bold transition-all shadow-sm active:scale-95 whitespace-nowrap ${
              isSavingSettings
                ? 'border-slate-200 dark:border-slate-800 bg-slate-100 dark:bg-slate-800 text-slate-400 cursor-not-allowed'
                : 'border-emerald-200 dark:border-emerald-900/30 bg-emerald-50 dark:bg-emerald-950/20 text-emerald-600 dark:text-emerald-400 hover:bg-emerald-100/50 dark:hover:bg-emerald-950/40'
            }`}
          >
            {isSavingSettings ? 'Saving Settings...' : 'Save Configuration'}
          </button>
        </div>
      </form>

      {fullResetAccess.allowed && (
        <div className="mt-8 bg-slate-50 dark:bg-slate-900/30 border border-slate-200 dark:border-slate-800 rounded-3xl p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h4 className="text-sm font-bold text-slate-800 dark:text-slate-200">System Debug Tools</h4>
            <p className="text-xs text-slate-500 mt-0.5">
              Wipe the transactional database and re-seed all test accounts with baseline configurations in one click.
            </p>
            <label className="flex items-center gap-2 mt-3 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={purgeAuditLogs}
                onChange={(e) => setPurgeAuditLogs(e.target.checked)}
                disabled={isResetting}
                className="rounded border-slate-300 dark:border-slate-700 text-rose-600 focus:ring-rose-500"
              />
              <span className="text-xs font-medium text-slate-700 dark:text-slate-300">Purge BigQuery & PostgreSQL compliance audit logs</span>
            </label>
            <label className="flex items-center gap-2 mt-2 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={purgeDataLake}
                onChange={(e) => setPurgeDataLake(e.target.checked)}
                disabled={isResetting}
                className="rounded border-slate-300 dark:border-slate-700 text-amber-600 focus:ring-amber-500"
              />
              <span className="text-xs font-medium text-slate-700 dark:text-slate-300">Purge Apache Iceberg BigLake analytical tables</span>
            </label>
          </div>
          <button
            onClick={handleResetDatabase}
            disabled={isResetting}
            className={`px-5 py-2.5 rounded-xl border text-xs font-bold transition-all shadow-sm active:scale-95 whitespace-nowrap self-start sm:self-auto ${
              isResetting
                ? 'border-slate-200 dark:border-slate-800 bg-slate-100 dark:bg-slate-800 text-slate-400 cursor-not-allowed'
                : 'border-rose-200 dark:border-rose-900/30 bg-rose-50 dark:bg-rose-950/20 text-rose-600 dark:text-rose-400 hover:bg-rose-100/50 dark:hover:bg-rose-950/40'
            }`}
          >
            {isResetting ? 'Resetting Database...' : 'Reset Database'}
          </button>
        </div>
      )}

      {/* Personal Demo Suite Management Panel */}
      <div className="mt-8 bg-slate-50 dark:bg-slate-900/30 border border-slate-200 dark:border-slate-800 rounded-3xl p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h4 className="text-sm font-bold text-slate-800 dark:text-slate-200">Personal Demo Suite Management</h4>
          <p className="text-xs text-slate-500 mt-0.5">
            {hasSeededProfile
              ? "You have an active personal demo profile. You can reset your swipe transactions and restore checking/savings default balances without impacting other concurrent presenters."
              : "You do not have a seeded personal demo profile. Click below to provision a complete suite of accounts (checking, savings, credit cards, and credit scoring profiles) with 14 days of realistic transaction history."}
          </p>
        </div>
        <div className="flex gap-3 self-start sm:self-auto">
          {!hasSeededProfile ? (
            <button
              onClick={handleProvisionDemo}
              disabled={isProvisioning}
              className={`px-5 py-2.5 rounded-xl border text-xs font-bold transition-all shadow-sm active:scale-95 whitespace-nowrap ${
                isProvisioning
                  ? 'border-slate-200 dark:border-slate-800 bg-slate-100 dark:bg-slate-800 text-slate-400 cursor-not-allowed'
                  : 'border-emerald-200 dark:border-emerald-900/30 bg-emerald-50 dark:bg-emerald-950/20 text-emerald-600 dark:text-emerald-400 hover:bg-emerald-100/50 dark:hover:bg-emerald-950/40'
              }`}
            >
              {isProvisioning ? 'Provisioning...' : 'Provision My Demo Profile'}
            </button>
          ) : (
            <button
              onClick={handleResetDemo}
              disabled={isResettingDemo}
              className={`px-5 py-2.5 rounded-xl border text-xs font-bold transition-all shadow-sm active:scale-95 whitespace-nowrap ${
                isResettingDemo
                  ? 'border-slate-200 dark:border-slate-800 bg-slate-100 dark:bg-slate-800 text-slate-400 cursor-not-allowed'
                  : 'border-blue-200 dark:border-blue-900/30 bg-blue-50 dark:bg-blue-950/20 text-blue-600 dark:text-blue-400 hover:bg-blue-100/50 dark:hover:bg-blue-950/40'
              }`}
            >
              {isResettingDemo ? 'Resetting Suite...' : 'Reset My Demo Suite'}
            </button>
          )}
        </div>
      </div>

      {/* Notice Banner */}
      {notice.text && (
        <div className={`mt-4 p-4 rounded-2xl border flex items-center gap-3 text-xs font-semibold animate-fade-in ${
          notice.type === 'success'
            ? 'bg-emerald-50 dark:bg-emerald-950/20 border-emerald-200 dark:border-emerald-800/30 text-emerald-700 dark:text-emerald-400'
            : notice.type === 'warning'
            ? 'bg-amber-50 dark:bg-amber-950/20 border-amber-200 dark:border-amber-800/30 text-amber-700 dark:text-amber-400'
            : 'bg-rose-50 dark:bg-rose-950/20 border-rose-200 dark:border-rose-800/30 text-rose-700 dark:text-rose-400'
        }`}>
          {notice.type === 'success' ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
          <span>{notice.text}</span>
        </div>
      )}

      <GcpInfoModal
        isOpen={isInfoModalOpen}
        onClose={() => setIsInfoModalOpen(false)}
        title="Google Cloud System Integration"
      >
        <div className="space-y-4 text-slate-600 dark:text-slate-400 text-sm leading-relaxed">
          <p>
            The <strong>Nova Horizon Admin Portal</strong> serves as the central control plane, orchestrating banking operations and AI settings powered by Google Cloud services.
          </p>
          <p>
            System configurations (such as session timeouts and avatar selections) are stored dynamically in the ledger database and fetched in real-time by the Voice Agent container during bootstrap.
          </p>
          <div className="bg-slate-50 dark:bg-slate-950 p-4 rounded-2xl border border-slate-100 dark:border-slate-800 space-y-3">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h4 className="font-semibold text-slate-800 dark:text-slate-200 text-xs uppercase tracking-wider">Secret Manager Console</h4>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">Manage database keys, LiveKit credentials, and Google API secrets securely.</p>
              </div>
              <a
                href="https://console.cloud.google.com/security/secret-manager"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-emerald-500 hover:text-emerald-600 font-semibold text-xs shrink-0 hover:underline"
              >
                <span>View Secrets</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            </div>
            <hr className="border-slate-100 dark:border-slate-800" />
            <div className="flex items-start justify-between gap-4">
              <div>
                <h4 className="font-semibold text-slate-800 dark:text-slate-200 text-xs uppercase tracking-wider">Cloud Run Console</h4>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">Monitor computing resources, container revisions, and backend traffic scaling.</p>
              </div>
              <a
                href="https://console.cloud.google.com/run"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-emerald-500 hover:text-emerald-600 font-semibold text-xs shrink-0 hover:underline"
              >
                <span>View Services</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            </div>
          </div>
        </div>
      </GcpInfoModal>

    </section>
  );
}

export default AdminDashboardView;
