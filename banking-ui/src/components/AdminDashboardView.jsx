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
import { FileCheck, MessageSquare, Shield, ChevronRight, LayoutDashboard, Volume2, AlertCircle, CheckCircle2, Settings, Bell, ExternalLink } from 'lucide-react';
import { resetDatabase, getSystemSettings, updateSystemSettings } from '../utils/api.js';
import GoogleCloudIcon from './GoogleCloudIcon.jsx';
import GcpInfoModal from './GcpInfoModal.jsx';

function AdminDashboardView() {
  const navigate = useNavigate();
  const [isResetting, setIsResetting] = useState(false);
  const [notice, setNotice] = useState({ type: '', text: '' });
  const [isInfoModalOpen, setIsInfoModalOpen] = useState(false);

  // Settings States
  const [hardTimeoutEnabled, setHardTimeoutEnabled] = useState(false);
  const [maxDuration, setMaxDuration] = useState(300);
  const [warningDuration, setWarningDuration] = useState(240);
  const [avatarSelection, setAvatarSelection] = useState('random');
  const [mockAvatarEnabled, setMockAvatarEnabled] = useState(false);
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
        }
      } catch (err) {
        console.error("Failed to load voice agent settings:", err);
      }
    }
    loadSettings();
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
        voice_agent_mock_avatar_enabled: String(mockAvatarEnabled)
      });
      setNotice({ type: 'success', text: 'Voice agent settings updated successfully!' });
      setTimeout(() => setNotice({ type: '', text: '' }), 4000);
    } catch (err) {
      setNotice({ type: 'error', text: err.response?.data?.detail || 'Failed to update settings.' });
    } finally {
      setIsSavingSettings(false);
    }
  };

  const handleResetDatabase = async () => {
    if (!window.confirm("Are you sure you want to reset the database? This will clear all transactions, escalations, card block overrides, and restore the baseline configuration.")) {
      return;
    }
    setIsResetting(true);
    setNotice({ type: '', text: '' });
    try {
      await resetDatabase();
      setNotice({ type: 'success', text: 'Database successfully reset and re-seeded!' });
      // Automatically clear success toast after 4 seconds
      setTimeout(() => setNotice({ type: '', text: '' }), 4000);
    } catch (err) {
      setNotice({ type: 'error', text: err.response?.data?.detail || 'Failed to reset database.' });
    } finally {
      setIsResetting(false);
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
    }
  ];

  return (
    <section className="relative pt-32 pb-24 md:pt-44 md:pb-32 px-6 max-w-6xl mx-auto min-h-[calc(100vh-80px)] flex flex-col text-left">
      
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
        <button
          onClick={() => setIsInfoModalOpen(true)}
          className="p-2.5 rounded-2xl hover:bg-slate-805/80 border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm text-slate-400 hover:text-slate-200 transition-all active:scale-95 cursor-pointer flex items-center justify-center"
          title="GCP Admin Integration Info"
        >
          <GoogleCloudIcon className="w-5 h-5 text-indigo-400" />
        </button>
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

      {/* Notice Banner */}
      {notice.text && (
        <div className={`mt-8 p-4 rounded-2xl border flex items-center gap-3 text-xs font-semibold animate-fade-in ${
          notice.type === 'success'
            ? 'bg-emerald-50 dark:bg-emerald-950/20 border-emerald-200 dark:border-emerald-800/30 text-emerald-700 dark:text-emerald-400'
            : 'bg-rose-50 dark:bg-rose-950/20 border-rose-200 dark:border-rose-800/30 text-rose-700 dark:text-rose-400'
        }`}>
          {notice.type === 'success' ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
          <span>{notice.text}</span>
        </div>
      )}

      {/* Voice & Live Avatar Settings Panel */}
      <form onSubmit={handleSaveSettings} className="mt-8 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl p-6 space-y-6">
        <div className="flex items-center gap-2 pb-4 border-b border-slate-100 dark:border-slate-800/80">
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

      {/* System Debug Tools Panel */}
      <div className="mt-8 bg-slate-50 dark:bg-slate-900/30 border border-slate-200 dark:border-slate-800 rounded-3xl p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h4 className="text-sm font-bold text-slate-800 dark:text-slate-200">System Debug Tools</h4>
          <p className="text-xs text-slate-500 mt-0.5">Wipe the transactional database and re-seed all test accounts with baseline configurations in one click.</p>
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
