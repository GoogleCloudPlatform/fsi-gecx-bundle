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
import { 
  Sparkles, Activity, ShieldAlert, Zap, Database, RefreshCw, 
  ArrowLeft, CheckCircle2, AlertTriangle, TrendingUp, Globe, Clock, 
  Layers, ChevronRight, Play, Info, ExternalLink
} from 'lucide-react';
import { triggerSpendSurge, injectFraudAnomaly, injectLateFee, getGlobalStream, getLakehouseStream, getCdcStatus } from '../utils/api.js';
import GoogleCloudIcon from './GoogleCloudIcon.jsx';
import GcpInfoModal from './GcpInfoModal.jsx';
import { showInfoModals } from '../utils/constants.js';

function AdminSimulationView() {
  const navigate = useNavigate();
  const [isSurgeLoading, setIsSurgeLoading] = useState(false);
  const [isAnomalyLoading, setIsAnomalyLoading] = useState(false);
  const [isFeeLoading, setIsFeeLoading] = useState(false);
  const [isStreamLoading, setIsStreamLoading] = useState(false);
  const [isGcpInfoModalOpen, setIsGcpInfoModalOpen] = useState(false);
  const [streamData, setStreamData] = useState([]);
  const [lakehouseData, setLakehouseData] = useState([]);
  const [cdcStatus, setCdcStatus] = useState(null);
  const [lakehouseError, setLakehouseError] = useState('');
  const [feedback, setFeedback] = useState({ type: '', title: '', message: '', data: null });
  const [cdcStats, setCdcStats] = useState({
    systemLag: 0,
    dataFreshness: 0,
    totalThroughputMb: 0,
    activeAnomalies: 0,
    lastSyncTime: new Date().toLocaleTimeString()
  });

  const fetchGlobalStream = async () => {
    setIsStreamLoading(true);
    try {
      const [operationalRes, lakehouseRes, statusRes] = await Promise.all([
        getGlobalStream(),
        getLakehouseStream(),
        getCdcStatus(),
      ]);
      if (operationalRes && operationalRes.stream) {
        setStreamData(operationalRes.stream);
      }
      if (lakehouseRes && lakehouseRes.stream) {
        setLakehouseData(lakehouseRes.stream);
        setLakehouseError(lakehouseRes.bigquery_error || '');
      }
      if (statusRes) {
        setCdcStatus(statusRes);
      }
    } catch (e) {
      console.error("Failed to fetch global stream:", e);
    } finally {
      setIsStreamLoading(false);
    }
  };

  useEffect(() => {
    fetchGlobalStream();
    
    // Replace manual polling with SSE Push
    const eventSource = new EventSource('/api/v1/simulation/stream-sse', { withCredentials: true });
    
    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.status === 'SUCCESS') {
          if (data.operational_stream) setStreamData(data.operational_stream);
          if (data.lakehouse_stream) setLakehouseData(data.lakehouse_stream);
          
          if (data.cdc_metrics) {
            setCdcStats({
              systemLag: data.cdc_metrics.system_lag ?? 0,
              dataFreshness: data.cdc_metrics.data_freshness ?? 0,
              totalThroughputMb: data.cdc_metrics.total_bytes_processed 
                ? (data.cdc_metrics.total_bytes_processed / (1024 * 1024)).toFixed(2)
                : 0,
              activeAnomalies: data.cdc_metrics.active_anomalies ?? 0,
              lastSyncTime: new Date().toLocaleTimeString()
            });
            setCdcStatus(prev => ({
               ...prev, 
               lakehouse_error: data.cdc_metrics.status === 'DEGRADED' ? 'Monitoring degraded' : '' 
            }));
          }
        }
      } catch (err) {
        console.error("Error parsing SSE data", err);
      }
    };

    return () => eventSource.close();
  }, []);

  useEffect(() => {
    if (feedback.message) {
      const timer = setTimeout(() => {
        setFeedback({ type: '', title: '', message: '', data: null });
      }, 5000);
      return () => clearTimeout(timer);
    }
  }, [feedback]);

  const handleSpendSurge = async () => {
    setIsSurgeLoading(true);
    setFeedback({ type: '', title: '', message: '', data: null });
    try {
      const res = await triggerSpendSurge();
      setFeedback({
        type: 'success',
        title: 'Spend Surge Dispatch Initiated',
        message: res.message || 'Successfully triggered 50 rapid-fire swipes across the active card pool.',
        data: res
      });
      fetchGlobalStream();
    } catch (err) {
      setFeedback({
        type: 'error',
        title: 'Surge Injection Failed',
        message: err.response?.data?.detail || err.message || 'Unable to connect to simulation gateway.',
        data: null
      });
    } finally {
      setIsSurgeLoading(false);
    }
  };

  const handleFraudAnomaly = async () => {
    setIsAnomalyLoading(true);
    setFeedback({ type: '', title: '', message: '', data: null });
    try {
      const res = await injectFraudAnomaly();
      setFeedback({
        type: 'warning',
        title: 'Targeted Fraud Anomaly Injected',
        message: res.message || `Injected ${res.injected_swipes_count || 4} high-risk Mexico/Cancun transactions against presenter card.`,
        data: res
      });
      setCdcStats(prev => ({
        ...prev,
        activeAnomalies: prev.activeAnomalies + (res.injected_swipes_count || 4)
      }));
      fetchGlobalStream();
    } catch (err) {
      setFeedback({
        type: 'error',
        title: 'Anomaly Injection Failed',
        message: err.response?.data?.detail || err.message || 'Unable to execute targeted anomaly injection.',
        data: null
      });
    } finally {
      setIsAnomalyLoading(false);
    }
  };

  const handleLateFee = async () => {
    setIsFeeLoading(true);
    setFeedback({ type: '', title: '', message: '', data: null });
    try {
      const res = await injectLateFee();
      setFeedback({
        type: 'warning',
        title: 'Late Fee Injected',
        message: res.message || 'Injected $35.00 Late Fee against presenter card.',
        data: res
      });
      fetchGlobalStream();
    } catch (err) {
      setFeedback({
        type: 'error',
        title: 'Late Fee Injection Failed',
        message: err.response?.data?.detail || err.message || 'Unable to execute late fee injection.',
        data: null
      });
    } finally {
      setIsFeeLoading(false);
    }
  };

  return (
    <section className="relative pt-32 pb-24 md:pt-40 md:pb-32 px-6 max-w-6xl mx-auto min-h-[calc(100vh-80px)] flex flex-col text-left">
      
      {/* Background ambient lighting */}
      <div className="absolute top-1/3 left-1/4 w-[450px] h-[450px] rounded-full bg-cyan-500/10 blur-[120px] pointer-events-none -z-10 animate-pulse" />
      <div className="absolute top-1/2 right-1/4 w-[400px] h-[400px] rounded-full bg-blue-600/10 blur-[100px] pointer-events-none -z-10" />

      {/* Header Navigation */}
      <div className="mb-10 flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-200 dark:border-slate-800 pb-6">
        <div>
          <button 
            onClick={() => navigate('/admin')}
            className="inline-flex items-center gap-2 text-sm font-medium text-slate-500 hover:text-slate-900 dark:hover:text-white transition-colors mb-3 group"
          >
            <ArrowLeft className="w-4 h-4 group-hover:-translate-x-1 transition-transform" />
            Back to Admin Portal
          </button>
          <div className="flex items-center gap-3">
            <div className="p-3 rounded-2xl bg-gradient-to-br from-cyan-500 to-blue-600 text-white shadow-lg shadow-cyan-500/20">
              <Sparkles className="w-7 h-7" />
            </div>
            <div>
              <h1 className="text-3xl font-extrabold bg-gradient-to-r from-slate-900 via-slate-700 to-slate-500 dark:from-white dark:via-slate-200 dark:to-slate-400 bg-clip-text text-transparent">
                Active Lakehouse & Simulation Studio
              </h1>
              <p className="text-sm text-slate-500 mt-1">
                Real-time WAL Change Data Capture replication monitor and synthetic event injection controller.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Section 1: Datastream & WAL CDC Replication Status */}
      <div className="mb-10 p-6 rounded-3xl bg-white/80 dark:bg-slate-900/80 border border-slate-200/80 dark:border-slate-800/80 backdrop-blur-xl shadow-xl shadow-slate-950/5">
        <div className="flex items-center justify-between mb-6 pb-4 border-b border-slate-200/60 dark:border-slate-800/60">
          <div className="flex items-center gap-3">
            <Database className="w-6 h-6 text-cyan-500" />
            <div>
              <h2 className="text-lg font-bold text-slate-900 dark:text-white">
                Datastream WAL Replication Engine
              </h2>
              <p className="text-xs text-slate-500">
                PostgreSQL Outbox WAL &rarr; Cloud Storage &rarr; BigQuery Active Lakehouse (`fsi_lakehouse`)
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-600 dark:text-emerald-400 text-xs font-semibold">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-ping" />
            <span className="w-2 h-2 rounded-full bg-emerald-500 -ml-4" />
            STREAMING ACTIVE
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="p-4 rounded-2xl bg-slate-50 dark:bg-slate-950/50 border border-slate-100 dark:border-slate-800">
            <div className="flex items-center justify-between text-xs text-slate-500 mb-1">
              <span>System Lag</span>
              <Clock className="w-4 h-4 text-cyan-500" />
            </div>
            <div className="text-2xl font-black text-slate-900 dark:text-white font-mono">
              {cdcStats.systemLag} <span className="text-sm font-normal text-slate-500">sec</span>
            </div>
            <div className="text-[10px] text-emerald-500 font-medium mt-1">Datastream ingestion delay</div>
          </div>

          <div className="p-4 rounded-2xl bg-slate-50 dark:bg-slate-950/50 border border-slate-100 dark:border-slate-800">
            <div className="flex items-center justify-between text-xs text-slate-500 mb-1">
              <span>Data Freshness</span>
              <Activity className="w-4 h-4 text-emerald-500" />
            </div>
            <div className="text-2xl font-black text-slate-900 dark:text-white font-mono">
              {cdcStats.dataFreshness} <span className="text-sm font-normal text-slate-500">sec</span>
            </div>
            <div className="text-[10px] text-slate-400 mt-1">End-to-end CDC latency</div>
          </div>

          <div className="p-4 rounded-2xl bg-slate-50 dark:bg-slate-950/50 border border-slate-100 dark:border-slate-800">
            <div className="flex items-center justify-between text-xs text-slate-500 mb-1">
              <span>Total Throughput</span>
              <Layers className="w-4 h-4 text-blue-500" />
            </div>
            <div className="text-2xl font-black text-slate-900 dark:text-white font-mono">
              {cdcStats.totalThroughputMb} <span className="text-sm font-normal text-slate-500">MB</span>
            </div>
            <div className="text-[10px] text-slate-400 mt-1">Bytes processed via Datastream</div>
          </div>

          <div className="p-4 rounded-2xl bg-slate-50 dark:bg-slate-950/50 border border-slate-100 dark:border-slate-800">
            <div className="flex items-center justify-between text-xs text-slate-500 mb-1">
              <span>Active Anomalies</span>
              <ShieldAlert className="w-4 h-4 text-rose-500" />
            </div>
            <div className="text-2xl font-black text-rose-600 dark:text-rose-400 font-mono">
              {cdcStats.activeAnomalies}
            </div>
            <div className="text-[10px] text-rose-500 font-medium mt-1">Risk score &gt; 20 flagged</div>
          </div>
        </div>
      </div>

      {/* Section 2: Interactive Simulation Command Center */}
      <h3 className="text-xl font-extrabold text-slate-900 dark:text-white mb-6 flex items-center gap-2">
        <Zap className="w-6 h-6 text-amber-500" />
        Simulation Event Command Center
      </h3>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-12">
        
        {/* Card 1: Spend Surge */}
        <div className="relative group p-7 rounded-3xl bg-gradient-to-br from-white to-slate-50 dark:from-slate-900 dark:to-slate-950 border border-slate-200 dark:border-slate-800 hover:border-cyan-500/50 dark:hover:border-cyan-500/50 transition-all duration-300 shadow-xl hover:shadow-2xl hover:shadow-cyan-500/10 flex flex-col justify-between overflow-hidden">
          <div className="absolute top-0 right-0 w-32 h-32 bg-cyan-500/10 rounded-full blur-2xl group-hover:scale-150 transition-transform duration-500" />
          
          <div>
            <div className="flex items-center gap-3 mb-4">
              <div className="p-3 rounded-2xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-600 dark:text-cyan-400">
                <TrendingUp className="w-6 h-6" />
              </div>
              <div>
                <h4 className="text-lg font-bold text-slate-900 dark:text-white">
                  Spend Velocity Surge
                </h4>
                <span className="text-xs font-semibold text-cyan-600 dark:text-cyan-400">
                  50 SWIPES / 10 SECONDS
                </span>
              </div>
            </div>
            <p className="text-sm text-slate-600 dark:text-slate-400 leading-relaxed mb-6">
              Triggers a rapid-fire synthetic activity surge across the active card pool. Simulates realistic domestic purchases across coffee shops, restaurants, grocers, and airlines to hydrate BigQuery real-time spend velocity views.
            </p>
          </div>

          <button
            onClick={handleSpendSurge}
            disabled={isSurgeLoading}
            className="w-full py-4 px-6 rounded-2xl bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white font-bold shadow-lg shadow-cyan-500/25 hover:shadow-cyan-500/40 active:scale-[0.99] transition-all disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {isSurgeLoading ? (
              <>
                <RefreshCw className="w-5 h-5 animate-spin" />
                Dispatching Surge...
              </>
            ) : (
              <>
                <Play className="w-5 h-5 fill-current" />
                Trigger Spend Surge
              </>
            )}
          </button>
        </div>

        {/* Card 2: Targeted Fraud Anomaly */}
        <div className="relative group p-7 rounded-3xl bg-gradient-to-br from-white to-slate-50 dark:from-slate-900 dark:to-slate-950 border border-slate-200 dark:border-slate-800 hover:border-rose-500/50 dark:hover:border-rose-500/50 transition-all duration-300 shadow-xl hover:shadow-2xl hover:shadow-rose-500/10 flex flex-col justify-between overflow-hidden">
          <div className="absolute top-0 right-0 w-32 h-32 bg-rose-500/10 rounded-full blur-2xl group-hover:scale-150 transition-transform duration-500" />
          
          <div>
            <div className="flex items-center gap-3 mb-4">
              <div className="p-3 rounded-2xl bg-rose-500/10 border border-rose-500/20 text-rose-600 dark:text-rose-400">
                <Globe className="w-6 h-6" />
              </div>
              <div>
                <h4 className="text-lg font-bold text-slate-900 dark:text-white">
                  Targeted Fraud Anomaly
                </h4>
                <span className="text-xs font-semibold text-rose-600 dark:text-rose-400">
                  RIVIERA MAYA HIGH-RISK SWIPES
                </span>
              </div>
            </div>
            <p className="text-sm text-slate-600 dark:text-slate-400 leading-relaxed mb-6">
              Injects 4 rapid-fire card-present transactions in Riviera Maya, Mexico against the presenter card. Instantly flags foreign anomaly alerts (`risk_score &gt; 20`) in BigQuery `v_international_fraud_anomalies` to demonstrate real-time fraud intervention.
            </p>
          </div>

          <button
            onClick={handleFraudAnomaly}
            disabled={isAnomalyLoading}
            className="w-full py-4 px-6 rounded-2xl bg-gradient-to-r from-rose-500 to-red-600 hover:from-rose-400 hover:to-red-500 text-white font-bold shadow-lg shadow-rose-500/25 hover:shadow-rose-500/40 active:scale-[0.99] transition-all disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {isAnomalyLoading ? (
              <>
                <RefreshCw className="w-5 h-5 animate-spin" />
                Injecting Anomaly...
              </>
            ) : (
              <>
                <ShieldAlert className="w-5 h-5" />
                Inject Targeted Anomaly
              </>
            )}
          </button>
        </div>

        {/* Card 3: Inject Late Fee */}
        <div className="relative group p-7 rounded-3xl bg-gradient-to-br from-white to-slate-50 dark:from-slate-900 dark:to-slate-950 border border-slate-200 dark:border-slate-800 hover:border-amber-500/50 dark:hover:border-amber-500/50 transition-all duration-300 shadow-xl hover:shadow-2xl hover:shadow-amber-500/10 flex flex-col justify-between overflow-hidden">
          <div className="absolute top-0 right-0 w-32 h-32 bg-amber-500/10 rounded-full blur-2xl group-hover:scale-150 transition-transform duration-500" />
          
          <div>
            <div className="flex items-center gap-3 mb-4">
              <div className="p-3 rounded-2xl bg-amber-500/10 border border-amber-500/20 text-amber-600 dark:text-amber-400">
                <Clock className="w-6 h-6" />
              </div>
              <div>
                <h4 className="text-lg font-bold text-slate-900 dark:text-white">
                  Inject Late Fee
                </h4>
                <span className="text-xs font-semibold text-amber-600 dark:text-amber-400">
                  $35.00 POSTED CHARGE
                </span>
              </div>
            </div>
            <p className="text-sm text-slate-600 dark:text-slate-400 leading-relaxed mb-6">
              Posts a standalone $35.00 Late Fee to the presenter card ledger. Enables live voice demos or standalone script executions of automated fee waiver and reversal workflows.
            </p>
          </div>

          <button
            onClick={handleLateFee}
            disabled={isFeeLoading}
            className="w-full py-4 px-6 rounded-2xl bg-gradient-to-r from-amber-500 to-orange-600 hover:from-amber-400 hover:to-orange-500 text-white font-bold shadow-lg shadow-amber-500/25 hover:shadow-amber-500/40 active:scale-[0.99] transition-all disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {isFeeLoading ? (
              <>
                <RefreshCw className="w-5 h-5 animate-spin" />
                Injecting Fee...
              </>
            ) : (
              <>
                <Zap className="w-5 h-5" />
                Inject Late Fee
              </>
            )}
          </button>
        </div>
      </div>

      {/* Feedback Alert Box (Pop-up above live streaming ledger) */}
      {feedback.message && (
        <div className={`mb-8 p-5 rounded-2xl border backdrop-blur-md flex items-start gap-4 transition-all duration-300 shadow-xl animate-fade-in ${
          feedback.type === 'success' 
            ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-900 dark:text-emerald-200 shadow-emerald-500/5' 
            : feedback.type === 'warning'
            ? 'bg-amber-500/15 border-amber-500/40 text-amber-900 dark:text-amber-200 shadow-amber-500/5'
            : 'bg-rose-500/15 border-rose-500/40 text-rose-900 dark:text-rose-200 shadow-rose-500/5'
        }`}>
          <div className="p-2 rounded-xl bg-white/20 dark:bg-black/20 mt-0.5 shrink-0">
            {feedback.type === 'success' && <CheckCircle2 className="w-6 h-6 text-emerald-500 animate-bounce" />}
            {feedback.type === 'warning' && <AlertTriangle className="w-6 h-6 text-amber-500 animate-pulse" />}
            {feedback.type === 'error' && <ShieldAlert className="w-6 h-6 text-rose-500 animate-pulse" />}
          </div>
          <div className="flex-1 overflow-hidden">
            <div className="flex items-center justify-between">
              <h4 className="font-bold text-base">{feedback.title}</h4>
              <span className="text-[10px] font-mono opacity-60 uppercase tracking-wider">Auto-dismissing in 5s...</span>
            </div>
            <p className="text-sm mt-1 opacity-90">{feedback.message}</p>
            {feedback.data && (
              <div className="mt-3 p-3 rounded-xl bg-slate-900/80 text-slate-200 font-mono text-xs overflow-x-auto border border-slate-700/50">
                <pre>{JSON.stringify(feedback.data, null, 2)}</pre>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Section 3: Live Transaction Activity Streams */}
      <div className="p-7 rounded-3xl bg-slate-900 text-slate-300 border border-slate-800 shadow-2xl">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
          <div>
            <h4 className="text-white font-extrabold text-lg flex items-center gap-2 flex-wrap">
              <Database className="w-5 h-5 text-cyan-400 animate-pulse" />
              Live Transaction Replication Monitor
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 shadow-sm">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-ping" />
                AUTH POLLING ACTIVE
              </span>
            </h4>
            <p className="text-xs text-slate-400 mt-1">
              Authenticated monitor comparing operational card-network writes with BigQuery lakehouse rows replicated by Datastream.
            </p>
            {cdcStatus && (
              <p className="text-[11px] text-slate-500 mt-1">
                Operational latest: {cdcStatus.operational_latest_timestamp || 'N/A'} | Lakehouse latest: {cdcStatus.lakehouse_latest_timestamp || 'N/A'}
              </p>
            )}
          </div>

          <div className="flex items-center gap-3 self-start md:self-auto">
            <button
              onClick={fetchGlobalStream}
              disabled={isStreamLoading}
              className="py-2 px-4 rounded-xl bg-slate-800 hover:bg-slate-700 active:scale-95 text-slate-300 hover:text-white text-xs font-semibold flex items-center gap-2 transition-all border border-slate-700 disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isStreamLoading ? 'animate-spin' : ''}`} />
              {isStreamLoading ? 'Refreshing...' : 'Refresh Stream'}
            </button>

            {showInfoModals() && (
              <button
                onClick={() => setIsGcpInfoModalOpen(true)}
                className="p-2.5 rounded-2xl hover:bg-slate-800 border border-slate-700 bg-slate-900 shadow-sm text-slate-400 hover:text-slate-200 transition-all active:scale-95 cursor-pointer flex items-center justify-center"
                title="GCP Admin Integration Info"
              >
                <GoogleCloudIcon className="w-5 h-5 text-indigo-400" />
              </button>
            )}
          </div>
        </div>

        <h5 className="text-xs uppercase tracking-wider text-slate-500 font-bold mb-3">Operational Source of Truth</h5>
        <div className="overflow-x-auto rounded-2xl border border-slate-800 bg-slate-950/70 mb-7">
          <table className="w-full text-left border-collapse font-mono text-xs">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400 bg-slate-900/50">
                <th className="p-3.5 font-semibold">Timestamp</th>
                <th className="p-3.5 font-semibold">RRN / Event ID</th>
                <th className="p-3.5 font-semibold">Merchant / Descriptor</th>
                <th className="p-3.5 font-semibold text-right">Amount</th>
                <th className="p-3.5 font-semibold">Status / Replication Target</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {streamData.length === 0 ? (
                <tr>
                  <td colSpan="5" className="p-8 text-center text-slate-500 font-sans">
                    Waiting for operational transaction activity... Trigger a surge, anomaly, or late fee above.
                  </td>
                </tr>
              ) : (
                streamData.map((item, idx) => (
                  <tr key={item.id + idx} className="hover:bg-slate-900/60 transition-colors">
                    <td className="p-3.5 text-slate-400 whitespace-nowrap flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                      {item.timestamp}
                    </td>
                    <td className="p-3.5 text-slate-300 font-bold whitespace-nowrap">{item.rrn}</td>
                    <td className="p-3.5 text-white font-sans font-medium truncate max-w-xs">{item.merchant_name}</td>
                    <td className="p-3.5 text-right font-bold whitespace-nowrap">
                      ${(item.amount_cents / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </td>
                    <td className="p-3.5 whitespace-nowrap">
                      <div className="flex flex-col gap-0.5">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold w-fit ${
                          item.status.includes('FLAGGED') 
                            ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30' 
                            : item.status.includes('HOLD') 
                            ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30' 
                            : 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                        }`}>
                          {item.status}
                        </span>
                        <span className="text-[10px] text-slate-500">{item.bq_view}</span>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <div className="flex items-center justify-between mb-3">
          <h5 className="text-xs uppercase tracking-wider text-slate-500 font-bold">BigQuery Lakehouse CDC Destination</h5>
          {lakehouseError && <span className="text-[10px] text-amber-400 font-mono">BigQuery degraded</span>}
        </div>
        {lakehouseError && (
          <div className="mb-3 p-3 rounded-xl border border-amber-500/30 bg-amber-500/10 text-amber-200 text-xs font-mono overflow-x-auto">
            {lakehouseError}
          </div>
        )}
        <div className="overflow-x-auto rounded-2xl border border-slate-800 bg-slate-950/70">
          <table className="w-full text-left border-collapse font-mono text-xs">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400 bg-slate-900/50">
                <th className="p-3.5 font-semibold">Timestamp</th>
                <th className="p-3.5 font-semibold">RRN / Event ID</th>
                <th className="p-3.5 font-semibold">Merchant / Descriptor</th>
                <th className="p-3.5 font-semibold text-right">Amount</th>
                <th className="p-3.5 font-semibold">Status / Source Table</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {lakehouseData.length === 0 ? (
                <tr>
                  <td colSpan="5" className="p-8 text-center text-slate-500 font-sans">
                    Waiting for replicated BigQuery rows from Datastream.
                  </td>
                </tr>
              ) : (
                lakehouseData.map((item, idx) => (
                  <tr key={item.id + idx} className="hover:bg-slate-900/60 transition-colors">
                    <td className="p-3.5 text-slate-400 whitespace-nowrap flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-cyan-500 animate-pulse" />
                      {item.timestamp}
                    </td>
                    <td className="p-3.5 text-slate-300 font-bold whitespace-nowrap">{item.rrn}</td>
                    <td className="p-3.5 text-white font-sans font-medium truncate max-w-xs">{item.merchant_name}</td>
                    <td className="p-3.5 text-right font-bold whitespace-nowrap">
                      ${(Math.abs(item.amount_cents || 0) / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </td>
                    <td className="p-3.5 whitespace-nowrap">
                      <div className="flex flex-col gap-0.5">
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold w-fit bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">
                          {item.status}
                        </span>
                        <span className="text-[10px] text-slate-500">{item.bq_view}</span>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <GcpInfoModal
        isOpen={isGcpInfoModalOpen}
        onClose={() => setIsGcpInfoModalOpen(false)}
        title="Lakehouse CDC Replication & Global Ledger"
      >
        <div className="space-y-4 text-slate-600 dark:text-slate-400 text-sm leading-relaxed">
          <p>
            The <strong>Transaction Replication Monitor</strong> compares recent operational card-network writes with BigQuery rows replicated by Datastream.
          </p>
          <p>
            Each event is simultaneously recorded in an append-only PostgreSQL outbox table and streamed through Google Cloud Datastream and Pub/Sub into BigQuery lakehouse tables. Looker semantic models structure this data into specialized real-time views:
          </p>
          <div className="bg-slate-50 dark:bg-slate-950 p-4 rounded-2xl border border-slate-100 dark:border-slate-800 space-y-3 font-sans text-xs">
            <div className="p-2.5 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
              <div className="text-cyan-500 dark:text-cyan-400 font-mono font-bold">fsi_lakehouse.v_realtime_spend_velocity</div>
              <p className="text-slate-500 dark:text-slate-400 mt-1">Aggregates CDC transaction volume and ticket size by FDX spend category &amp; home metro area in real time.</p>
            </div>
            <div className="p-2.5 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
              <div className="text-rose-500 dark:text-rose-400 font-mono font-bold">fsi_lakehouse.v_international_fraud_anomalies</div>
              <p className="text-slate-500 dark:text-slate-400 mt-1">Isolates foreign card-present transactions where risk_score &gt; 20 for immediate automated intervention and Looker alerts.</p>
            </div>
          </div>
          <div className="bg-slate-50 dark:bg-slate-950 p-4 rounded-2xl border border-slate-100 dark:border-slate-800 space-y-3">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h4 className="font-semibold text-slate-800 dark:text-slate-200 text-xs uppercase tracking-wider">BigQuery Studio Console</h4>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">Query streaming Datastream tables, examine CDC latency, and inspect SQL view schemas.</p>
              </div>
              <a
                href="https://console.cloud.google.com/bigquery"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-emerald-500 hover:text-emerald-600 font-semibold text-xs shrink-0 hover:underline"
              >
                <span>View BigQuery</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            </div>
            <hr className="border-slate-100 dark:border-slate-800" />
            <div className="flex items-start justify-between gap-4">
              <div>
                <h4 className="font-semibold text-slate-800 dark:text-slate-200 text-xs uppercase tracking-wider">Cloud Run Architecture</h4>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">Monitor microservice telemetry, SSE stream connections, and automated scaling.</p>
              </div>
              <a
                href="https://console.cloud.google.com/run"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-emerald-500 hover:text-emerald-600 font-semibold text-xs shrink-0 hover:underline"
              >
                <span>View Cloud Run</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            </div>
          </div>
        </div>
      </GcpInfoModal>

    </section>
  );
}

export default AdminSimulationView;
