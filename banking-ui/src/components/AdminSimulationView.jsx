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
import { fetchEventSource } from '@microsoft/fetch-event-source';
import { useNavigate } from 'react-router-dom';
import { 
  Sparkles, Activity, ShieldAlert, Zap, Database, RefreshCw, 
  ArrowLeft, CheckCircle2, AlertTriangle, TrendingUp, Clock,
  Layers, ExternalLink
} from 'lucide-react';
import {
  triggerSpendSurge,
  injectFraudAnomaly,
  injectLateFee,
  getGlobalStream,
  getBackendApiUrl,
  getBackendAuthHeaders,
} from '../utils/api.js';
import GoogleCloudIcon from './GoogleCloudIcon.jsx';
import GcpInfoModal from './GcpInfoModal.jsx';
import { showInfoModals } from '../utils/constants.js';

function formatLatency(ms) {
  if (ms == null) return 'N/A';
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(ms < 10_000 ? 1 : 0)} s`;
}

function formatEventAge(ms) {
  if (ms == null) return 'Awaiting events';
  if (ms < 1000) return `${ms} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)} s`;
  return `${Math.round(ms / 60_000)} min`;
}

function formatCurrencyFromCents(cents) {
  return `$${(Math.abs(cents ?? 0) / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatFraudReason(reason) {
  return String(reason || '')
    .replaceAll('_', ' ')
    .toLowerCase()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function parseFraudRiskScore(item) {
  const explicitScore = Number(item?.fraud_risk_score);
  if (Number.isFinite(explicitScore)) {
    return explicitScore;
  }
  const match = String(item?.status || '').match(/RISK\s+(\d+)/i);
  return match ? Number(match[1]) : null;
}

function AdminSimulationView() {
  const navigate = useNavigate();
  const projectId = window.firebaseConfig?.projectId;
  const [isSurgeLoading, setIsSurgeLoading] = useState(false);
  const [isAnomalyLoading, setIsAnomalyLoading] = useState(false);
  const [isFeeLoading, setIsFeeLoading] = useState(false);
  const [isStreamLoading, setIsStreamLoading] = useState(false);
  const [infoModal, setInfoModal] = useState(null);
  const [streamData, setStreamData] = useState([]);
  const [feedback, setFeedback] = useState({ type: '', title: '', message: '', data: null });
  const [streamConnection, setStreamConnection] = useState({ state: 'connecting', message: 'Negotiating secure stream...' });
  const [cdcStats, setCdcStats] = useState({
    systemLagMs: null,
    dataFreshnessMs: null,
    activeAnomalies: 0,
    eventsPerMinute: 0,
    authorizationEventsPerMinute: 0,
    postedEventsPerMinute: 0,
    flaggedEventsPerMinute: 0,
    latestEventAgeMs: null,
    recentBufferedEvents: 0,
    lastSyncTime: new Date().toLocaleTimeString()
  });

  const walStatus = streamConnection.state === 'error'
    ? {
        label: 'STREAM RETRYING',
        className: 'bg-amber-500/10 border-amber-500/20 text-amber-600 dark:text-amber-400',
        dotClassName: 'bg-amber-500',
        animate: false,
      }
    : streamConnection.state === 'live' && cdcStats.latestEventAgeMs != null && cdcStats.latestEventAgeMs > 120000
    ? {
        label: 'STREAM STALE',
        className: 'bg-amber-500/10 border-amber-500/20 text-amber-600 dark:text-amber-400',
        dotClassName: 'bg-amber-500',
        animate: false,
      }
    : streamConnection.state === 'live'
    ? {
        label: 'STREAMING ACTIVE',
        className: 'bg-emerald-500/10 border-emerald-500/20 text-emerald-600 dark:text-emerald-400',
        dotClassName: 'bg-emerald-500',
        animate: true,
      }
    : {
        label: 'CONNECTING',
        className: 'bg-cyan-500/10 border-cyan-500/20 text-cyan-600 dark:text-cyan-400',
        dotClassName: 'bg-cyan-500',
        animate: true,
      };

  const creditRiskMetrics = streamData.reduce(
    (acc, item) => {
      const status = String(item.status || '');
      const amount = Math.abs(item.amount_cents ?? 0);
      const riskScore = parseFraudRiskScore(item);
      const fraudReasons = Array.isArray(item.fraud_reason_codes) ? item.fraud_reason_codes : [];
      if (status.includes('FLAGGED')) {
        acc.flaggedCount += 1;
        acc.flaggedAmountCents += amount;
        if (riskScore != null) {
          acc.flaggedRiskScoreTotal += riskScore;
        }
      }
      if (status.includes('HOLD') || status.includes('FLAGGED')) {
        acc.pendingCount += 1;
        acc.pendingAmountCents += amount;
      }
      if (status.includes('SETTLE')) {
        acc.postedCount += 1;
        acc.postedAmountCents += amount;
      }
      if (riskScore != null) {
        acc.scoredCount += 1;
        acc.riskScoreTotal += riskScore;
        if (acc.peakRiskScore == null || riskScore > acc.peakRiskScore) {
          acc.peakRiskScore = riskScore;
          acc.peakRiskMerchant = item.merchant_name || 'Recent authorization';
        }
      }
      if (item.fraud_model_version) {
        acc.latestModelVersion = item.fraud_model_version;
      }
      fraudReasons.forEach((reason) => {
        acc.reasonCounts[reason] = (acc.reasonCounts[reason] || 0) + 1;
      });
      return acc;
    },
    {
      flaggedCount: 0,
      flaggedAmountCents: 0,
      flaggedRiskScoreTotal: 0,
      pendingCount: 0,
      pendingAmountCents: 0,
      postedCount: 0,
      postedAmountCents: 0,
      scoredCount: 0,
      riskScoreTotal: 0,
      peakRiskScore: null,
      peakRiskMerchant: null,
      latestModelVersion: null,
      reasonCounts: {},
    },
  );
  creditRiskMetrics.averageRiskScore = creditRiskMetrics.scoredCount
    ? Math.round(creditRiskMetrics.riskScoreTotal / creditRiskMetrics.scoredCount)
    : null;
  creditRiskMetrics.averageFlaggedRiskScore = creditRiskMetrics.flaggedCount
    ? Math.round(creditRiskMetrics.flaggedRiskScoreTotal / creditRiskMetrics.flaggedCount)
    : null;
  creditRiskMetrics.topReason = Object.entries(creditRiskMetrics.reasonCounts)
    .sort((a, b) => b[1] - a[1])[0] || null;

  const anomalySeverity = cdcStats.activeAnomalies >= 5
    ? {
        cardClass: 'bg-rose-50 dark:bg-rose-950/10 border-rose-100 dark:border-rose-900/40',
        textClass: 'text-rose-700 dark:text-rose-300',
        iconClass: 'text-rose-500',
      }
    : cdcStats.activeAnomalies > 0
    ? {
        cardClass: 'bg-amber-50 dark:bg-amber-950/10 border-amber-100 dark:border-amber-900/40',
        textClass: 'text-amber-700 dark:text-amber-300',
        iconClass: 'text-amber-500',
      }
    : {
        cardClass: 'bg-emerald-50 dark:bg-emerald-950/10 border-emerald-100 dark:border-emerald-900/40',
        textClass: 'text-emerald-700 dark:text-emerald-300',
        iconClass: 'text-emerald-500',
      };

  const applyMonitorSnapshot = (streamSnapshot) => {
    if (streamSnapshot?.stream) {
      setStreamData(streamSnapshot.stream);
    }

    if (streamSnapshot?.cdc_metrics || streamSnapshot?.stream_metrics) {
      setCdcStats({
        systemLagMs: streamSnapshot.cdc_metrics?.system_lag_ms ?? null,
        dataFreshnessMs: streamSnapshot.cdc_metrics?.data_freshness_ms ?? null,
        activeAnomalies: streamSnapshot.cdc_metrics?.active_anomalies ?? 0,
        eventsPerMinute: streamSnapshot.stream_metrics?.events_per_minute ?? 0,
        authorizationEventsPerMinute: streamSnapshot.stream_metrics?.authorization_events_per_minute ?? 0,
        postedEventsPerMinute: streamSnapshot.stream_metrics?.posted_events_per_minute ?? 0,
        flaggedEventsPerMinute: streamSnapshot.stream_metrics?.flagged_events_per_minute ?? 0,
        latestEventAgeMs: streamSnapshot.stream_metrics?.latest_event_age_ms ?? null,
        recentBufferedEvents: streamSnapshot.stream_metrics?.recent_buffered_events ?? 0,
        lastSyncTime: new Date().toLocaleTimeString(),
      });
    }
  };

  const fetchGlobalStream = async () => {
    setIsStreamLoading(true);
    try {
      const streamRes = await getGlobalStream();
      applyMonitorSnapshot(streamRes);
    } catch (e) {
      console.error("Failed to fetch global stream:", e);
    } finally {
      setIsStreamLoading(false);
    }
  };

  useEffect(() => {
    const loadInitialSnapshot = async () => {
      try {
        const streamRes = await getGlobalStream();
        applyMonitorSnapshot(streamRes);
      } catch (error) {
        console.error('Failed to fetch initial simulation snapshot:', error);
      }
    };

    loadInitialSnapshot();

    const controller = new AbortController();
    let isMounted = true;

    const reconnectDelay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

    const startStream = async () => {
      while (!controller.signal.aborted) {
        try {
          const headers = await getBackendAuthHeaders({ Accept: 'text/event-stream' });
          await fetchEventSource(`${getBackendApiUrl()}/v1/simulation/stream-sse`, {
            method: 'GET',
            headers,
            credentials: 'include',
            signal: controller.signal,
            openWhenHidden: true,
            async onopen(response) {
              if (!response.ok) {
                const detail = await response.text();
                throw new Error(`SSE auth failed (${response.status}): ${detail}`);
              }
              if (isMounted) {
                setStreamConnection({ state: 'live', message: 'Authenticated SSE stream active.' });
              }
            },
            onmessage(event) {
              try {
                const data = JSON.parse(event.data);
                if (data.status === 'SUCCESS') {
                  applyMonitorSnapshot(
                    {
                      stream: data.operational_stream,
                      stream_metrics: data.stream_metrics,
                      cdc_metrics: data.cdc_metrics,
                      cdc_status: data.cdc_status,
                    },
                  );
                  if (isMounted) {
                    setStreamConnection({
                      state: 'live',
                      message: data.event_kind === 'heartbeat' ? 'Heartbeat received.' : 'Event stream flowing.',
                    });
                  }
                }
              } catch (err) {
                console.error('Error parsing SSE data', err);
              }
            },
            onclose() {
              throw new Error('SSE connection closed.');
            },
            onerror(error) {
              throw error;
            },
          });
        } catch (error) {
          if (controller.signal.aborted) {
            return;
          }
          console.error('Simulation stream error', error);
          if (isMounted) {
            setStreamConnection({
              state: 'error',
              message: 'Secure stream interrupted. Retrying with a fresh token...',
            });
          }
          await reconnectDelay(2000);
        }
      }
    };

    startStream();

    return () => {
      isMounted = false;
      controller.abort();
    };
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
        message: res.message || `Injected ${res.injected_swipes_count || 5} high-risk digital gift-card transactions against the active demo card.`,
        data: res
      });
      setCdcStats(prev => ({
        ...prev,
        activeAnomalies: Math.max(prev.activeAnomalies, 1),
        flaggedEventsPerMinute: Math.max(prev.flaggedEventsPerMinute, 1),
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
        message: res.message || 'Injected $35.00 Late Fee against the active demo card.',
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
    <section className="relative pt-24 pb-16 md:pt-28 md:pb-24 px-6 max-w-6xl mx-auto min-h-[calc(100vh-80px)] flex flex-col text-left">
      
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
                Replication Monitor & Simulation Studio
              </h1>
              <p className="text-sm text-slate-500 mt-1">
                Live Redis event streaming, Datastream health, and synthetic transaction controls for the banking service.
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
                PostgreSQL Outbox WAL &rarr; Datastream CDC tables in `iceberg_catalog` &rarr; curated views in `analytics_curated`
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full border text-xs font-semibold ${walStatus.className}`}>
              <span className={`w-2 h-2 rounded-full ${walStatus.dotClassName} ${walStatus.animate ? 'animate-ping' : ''}`} />
              <span className={`w-2 h-2 rounded-full ${walStatus.dotClassName} ${walStatus.animate ? '-ml-4' : ''}`} />
              {walStatus.label}
            </div>
            {showInfoModals() && (
              <button
                onClick={() => setInfoModal('wal')}
                className="p-2.5 rounded-2xl hover:bg-slate-100 dark:hover:bg-slate-800 border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-sm text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200 transition-all active:scale-95 cursor-pointer flex items-center justify-center"
                title="Datastream replication info"
              >
                <GoogleCloudIcon className="w-5 h-5 text-indigo-400" />
              </button>
            )}
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="p-4 rounded-2xl bg-slate-50 dark:bg-slate-950/50 border border-slate-100 dark:border-slate-800">
            <div className="flex items-center justify-between text-xs text-slate-500 mb-1">
              <span>SSE Connection</span>
              <Clock className="w-4 h-4 text-cyan-500" />
            </div>
            <div className={`text-2xl font-black font-mono ${
              streamConnection.state === 'live'
                ? 'text-emerald-600 dark:text-emerald-400'
                : streamConnection.state === 'error'
                ? 'text-amber-600 dark:text-amber-400'
                : 'text-slate-900 dark:text-white'
            }`}>
              {streamConnection.state === 'live' ? 'LIVE' : streamConnection.state === 'error' ? 'RETRY' : 'SYNC'}
            </div>
            <div className="text-[10px] text-slate-500 mt-1">Browser connection to the live Redis-backed event feed</div>
          </div>

          <div className="p-4 rounded-2xl bg-slate-50 dark:bg-slate-950/50 border border-slate-100 dark:border-slate-800">
            <div className="flex items-center justify-between text-xs text-slate-500 mb-1">
              <span>Last Event Age</span>
              <Activity className="w-4 h-4 text-emerald-500" />
            </div>
            <div className="text-2xl font-black text-slate-900 dark:text-white font-mono">
              {formatEventAge(cdcStats.latestEventAgeMs)}
            </div>
            <div className="text-[10px] text-slate-400 mt-1">Age of the newest Redis event</div>
          </div>

          <div className="p-4 rounded-2xl bg-slate-50 dark:bg-slate-950/50 border border-slate-100 dark:border-slate-800">
            <div className="flex items-center justify-between text-xs text-slate-500 mb-1">
              <span>Event Throughput</span>
              <Layers className="w-4 h-4 text-blue-500" />
            </div>
            <div className="text-2xl font-black text-slate-900 dark:text-white font-mono">
              {cdcStats.eventsPerMinute} <span className="text-sm font-normal text-slate-500">/ min</span>
            </div>
            <div className="text-[10px] text-slate-400 mt-1">
              {cdcStats.authorizationEventsPerMinute} auth, {cdcStats.postedEventsPerMinute} posted, {cdcStats.flaggedEventsPerMinute} flagged
            </div>
          </div>

          <div className="p-4 rounded-2xl bg-slate-50 dark:bg-slate-950/50 border border-slate-100 dark:border-slate-800">
            <div className="flex items-center justify-between text-xs text-slate-500 mb-1">
              <span>Datastream Freshness</span>
              <ShieldAlert className="w-4 h-4 text-rose-500" />
            </div>
            <div className="text-2xl font-black text-slate-900 dark:text-white font-mono">
              {formatLatency(cdcStats.dataFreshnessMs)}
            </div>
            <div className="text-[10px] text-slate-400 mt-1">Managed CDC destination freshness</div>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-2 text-[11px] text-slate-500">
          <span className="px-2.5 py-1 rounded-full bg-slate-100 dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
            System lag: <span className="font-mono text-slate-700 dark:text-slate-300">{formatLatency(cdcStats.systemLagMs)}</span>
          </span>
          <span className="px-2.5 py-1 rounded-full bg-slate-100 dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
            Buffered events: <span className="font-mono text-slate-700 dark:text-slate-300">{cdcStats.recentBufferedEvents}</span>
          </span>
          <span className="px-2.5 py-1 rounded-full bg-slate-100 dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
            Last sync: <span className="font-mono text-slate-700 dark:text-slate-300">{cdcStats.lastSyncTime}</span>
          </span>
        </div>
      </div>

      {/* Section 2: Credit Risk Metrics */}
      <div className="mb-10 p-6 rounded-3xl bg-white/80 dark:bg-slate-900/80 border border-slate-200/80 dark:border-slate-800/80 backdrop-blur-xl shadow-xl shadow-slate-950/5">
        <div className="flex items-center justify-between mb-6 pb-4 border-b border-slate-200/60 dark:border-slate-800/60">
          <div className="flex items-center gap-3">
            <ShieldAlert className="w-6 h-6 text-rose-500" />
            <div>
              <h2 className="text-lg font-bold text-slate-900 dark:text-white">
                Credit Risk Metrics
              </h2>
              <p className="text-xs text-slate-500">
                Fraud anomaly posture, pending exposure, and authorization-to-posting flow from the live card stream.
              </p>
            </div>
          </div>
          {showInfoModals() && (
            <button
              onClick={() => setInfoModal('credit-risk')}
              className="p-2.5 rounded-2xl hover:bg-slate-100 dark:hover:bg-slate-800 border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-sm text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200 transition-all active:scale-95 cursor-pointer flex items-center justify-center"
              title="Credit risk metrics info"
            >
              <GoogleCloudIcon className="w-5 h-5 text-indigo-400" />
            </button>
          )}
        </div>

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div className={`p-4 rounded-2xl border ${anomalySeverity.cardClass}`}>
            <div className={`flex items-center justify-between text-xs mb-1 ${anomalySeverity.textClass}`}>
              <span>Open Fraud Alerts</span>
              <ShieldAlert className={`w-4 h-4 ${anomalySeverity.iconClass}`} />
            </div>
            <div className={`text-2xl font-black font-mono ${anomalySeverity.textClass}`}>{cdcStats.activeAnomalies}</div>
            <div className={`text-[10px] mt-1 ${anomalySeverity.textClass}`}>Customer-facing cases awaiting review</div>
          </div>

          <div className="p-4 rounded-2xl bg-slate-50 dark:bg-slate-950/50 border border-slate-100 dark:border-slate-800">
            <div className="flex items-center justify-between text-xs text-slate-500 mb-1">
              <span>Peak Model Score</span>
              <AlertTriangle className="w-4 h-4 text-amber-500" />
            </div>
            <div className="text-2xl font-black text-slate-900 dark:text-white font-mono">
              {creditRiskMetrics.peakRiskScore ?? 'N/A'}
            </div>
            <div className="text-[10px] text-slate-400 mt-1 truncate">
              {creditRiskMetrics.peakRiskMerchant || 'Awaiting scored authorizations'}
            </div>
          </div>

          <div className="p-4 rounded-2xl bg-slate-50 dark:bg-slate-950/50 border border-slate-100 dark:border-slate-800">
            <div className="flex items-center justify-between text-xs text-slate-500 mb-1">
              <span>Top Reason Code</span>
              <ShieldAlert className="w-4 h-4 text-rose-500" />
            </div>
            <div className="text-xl font-black text-slate-900 dark:text-white font-mono truncate">
              {creditRiskMetrics.topReason ? formatFraudReason(creditRiskMetrics.topReason[0]) : 'None'}
            </div>
            <div className="text-[10px] text-slate-400 mt-1">
              {creditRiskMetrics.topReason ? `${creditRiskMetrics.topReason[1]} hit${creditRiskMetrics.topReason[1] === 1 ? '' : 's'} in current wall` : 'No flagged reason codes visible'}
            </div>
          </div>

          <div className="p-4 rounded-2xl bg-slate-50 dark:bg-slate-950/50 border border-slate-100 dark:border-slate-800">
            <div className="flex items-center justify-between text-xs text-slate-500 mb-1">
              <span>Flagged Exposure</span>
              <Clock className="w-4 h-4 text-amber-500" />
            </div>
            <div className="text-2xl font-black text-slate-900 dark:text-white font-mono">
              {formatCurrencyFromCents(creditRiskMetrics.flaggedAmountCents)}
            </div>
            <div className="text-[10px] text-slate-400 mt-1">
              {creditRiskMetrics.flaggedCount} flagged auth{creditRiskMetrics.flaggedCount === 1 ? '' : 's'}
              {creditRiskMetrics.averageFlaggedRiskScore != null ? `, avg score ${creditRiskMetrics.averageFlaggedRiskScore}` : ''}
            </div>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="px-3 py-2 rounded-2xl bg-slate-50 dark:bg-slate-950/50 border border-slate-100 dark:border-slate-800">
            <div className="flex items-center justify-between gap-3 text-[11px]">
              <span className="text-slate-500">Live event mix</span>
              <span className="font-mono font-bold text-slate-800 dark:text-slate-200">
                {cdcStats.authorizationEventsPerMinute} auth / {cdcStats.postedEventsPerMinute} posted / {cdcStats.flaggedEventsPerMinute} flagged
              </span>
            </div>
          </div>
          <div className="px-3 py-2 rounded-2xl bg-slate-50 dark:bg-slate-950/50 border border-slate-100 dark:border-slate-800">
            <div className="flex items-center justify-between gap-3 text-[11px]">
              <span className="text-slate-500">Pending exposure</span>
              <span className="font-mono font-bold text-slate-800 dark:text-slate-200">
                {formatCurrencyFromCents(creditRiskMetrics.pendingAmountCents)} across {creditRiskMetrics.pendingCount} hold{creditRiskMetrics.pendingCount === 1 ? '' : 's'}
              </span>
            </div>
          </div>
          <div className="px-3 py-2 rounded-2xl bg-slate-50 dark:bg-slate-950/50 border border-slate-100 dark:border-slate-800">
            <div className="flex items-center justify-between gap-3 text-[11px]">
              <span className="text-slate-500">Model signal</span>
              <span className="font-mono font-bold text-slate-800 dark:text-slate-200 truncate">
                {creditRiskMetrics.latestModelVersion || 'Awaiting model events'}
                {creditRiskMetrics.averageRiskScore != null ? `, avg ${creditRiskMetrics.averageRiskScore}` : ''}
              </span>
            </div>
          </div>
        </div>
      </div>

      <div className="mb-10">
        <div className="mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
          <Zap className="w-4 h-4 text-amber-500" />
          Synthetic Transaction Controls
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="p-4 rounded-2xl bg-white/80 dark:bg-slate-900/80 border border-slate-200/80 dark:border-slate-800/80 shadow-lg shadow-slate-950/5 transition-all hover:-translate-y-0.5 hover:shadow-xl hover:shadow-slate-950/10">
            <div className="flex items-start gap-3">
              <div className="p-2.5 rounded-xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-600 dark:text-cyan-400 shrink-0">
                <TrendingUp className="w-5 h-5" />
              </div>
              <div className="min-w-0">
                <div className="text-sm font-bold text-slate-900 dark:text-white">Spend Velocity Surge</div>
                <div className="text-[11px] text-slate-500">50 synthetic swipes</div>
                <div className="text-[11px] text-slate-500 dark:text-slate-400 mt-1 leading-snug">Rapid domestic card activity to exercise stream throughput and replication freshness.</div>
              </div>
            </div>
            <button
              onClick={handleSpendSurge}
              disabled={isSurgeLoading}
              className="mt-4 w-full py-2.5 px-3 rounded-xl bg-cyan-600 hover:bg-cyan-500 active:scale-[0.98] text-white text-xs font-bold flex items-center justify-center gap-2 transition-all disabled:opacity-60 disabled:hover:bg-cyan-600"
            >
              {isSurgeLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <TrendingUp className="w-4 h-4" />}
              {isSurgeLoading ? 'Injecting Surge...' : 'Run Surge'}
            </button>
          </div>

          <div className="p-4 rounded-2xl bg-white/80 dark:bg-slate-900/80 border border-slate-200/80 dark:border-slate-800/80 shadow-lg shadow-slate-950/5 transition-all hover:-translate-y-0.5 hover:shadow-xl hover:shadow-slate-950/10">
            <div className="flex items-start gap-3">
              <div className="p-2.5 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-600 dark:text-rose-400 shrink-0">
                <ShieldAlert className="w-5 h-5" />
              </div>
              <div className="min-w-0">
                <div className="text-sm font-bold text-slate-900 dark:text-white">Targeted Fraud Anomaly</div>
                <div className="text-[11px] text-slate-500">High-risk gift cards</div>
                <div className="text-[11px] text-slate-500 dark:text-slate-400 mt-1 leading-snug">Creates a customer fraud alert, secure message, and flagged risk stream activity.</div>
              </div>
            </div>
            <button
              onClick={handleFraudAnomaly}
              disabled={isAnomalyLoading}
              className="mt-4 w-full py-2.5 px-3 rounded-xl bg-rose-600 hover:bg-rose-500 active:scale-[0.98] text-white text-xs font-bold flex items-center justify-center gap-2 transition-all disabled:opacity-60 disabled:hover:bg-rose-600"
            >
              {isAnomalyLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <ShieldAlert className="w-4 h-4" />}
              {isAnomalyLoading ? 'Creating Alert...' : 'Inject Anomaly'}
            </button>
          </div>

          <div className="p-4 rounded-2xl bg-white/80 dark:bg-slate-900/80 border border-slate-200/80 dark:border-slate-800/80 shadow-lg shadow-slate-950/5 transition-all hover:-translate-y-0.5 hover:shadow-xl hover:shadow-slate-950/10">
            <div className="flex items-start gap-3">
              <div className="p-2.5 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-600 dark:text-amber-400 shrink-0">
                <Zap className="w-5 h-5" />
              </div>
              <div className="min-w-0">
                <div className="text-sm font-bold text-slate-900 dark:text-white">Inject Late Fee</div>
                <div className="text-[11px] text-slate-500">$35 posted charge flow</div>
                <div className="text-[11px] text-slate-500 dark:text-slate-400 mt-1 leading-snug">Adds a standalone fee event for ledger, support, and voice-agent demonstrations.</div>
              </div>
            </div>
            <button
              onClick={handleLateFee}
              disabled={isFeeLoading}
              className="mt-4 w-full py-2.5 px-3 rounded-xl bg-amber-600 hover:bg-amber-500 active:scale-[0.98] text-white text-xs font-bold flex items-center justify-center gap-2 transition-all disabled:opacity-60 disabled:hover:bg-amber-600"
            >
              {isFeeLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
              {isFeeLoading ? 'Injecting Fee...' : 'Inject Fee'}
            </button>
          </div>
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

      {/* Section 4: Live Transaction Activity Streams */}
      <div className="p-7 rounded-3xl bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-800 shadow-2xl shadow-slate-950/5">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
          <div>
            <h4 className="text-slate-900 dark:text-white font-extrabold text-lg flex items-center gap-2 flex-wrap">
              <Database className="w-5 h-5 text-cyan-500 dark:text-cyan-400 animate-pulse" />
              Live Transaction Replication Monitor
              <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-bold border shadow-sm ${
                streamConnection.state === 'live'
                  ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20'
                  : streamConnection.state === 'error'
                  ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20'
                  : 'bg-cyan-500/10 text-cyan-600 dark:text-cyan-300 border-cyan-500/20'
              }`}>
                <span className={`w-1.5 h-1.5 rounded-full ${
                  streamConnection.state === 'live'
                    ? 'bg-emerald-500 animate-ping'
                  : streamConnection.state === 'error'
                    ? 'bg-amber-500'
                    : 'bg-cyan-500 dark:bg-cyan-300 animate-pulse'
                }`} />
                {streamConnection.state === 'live' ? 'AUTHENTICATED SSE LIVE' : streamConnection.state === 'error' ? 'STREAM RETRYING' : 'CONNECTING'}
              </span>
            </h4>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
              Shows the newest transaction activity as it is published by the banking service, streamed through Redis, and delivered to this view over authenticated server-sent events.
            </p>
          </div>

          <div className="flex items-center gap-3 self-start md:self-auto">
            <button
              onClick={fetchGlobalStream}
              disabled={isStreamLoading}
              className="py-2 px-4 rounded-xl bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 active:scale-95 text-slate-700 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white text-xs font-semibold flex items-center gap-2 transition-all border border-slate-200 dark:border-slate-700 disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isStreamLoading ? 'animate-spin' : ''}`} />
              {isStreamLoading ? 'Refreshing...' : 'Refresh Stream'}
            </button>

            {showInfoModals() && (
              <button
                onClick={() => setInfoModal('monitor')}
                className="p-2.5 rounded-2xl hover:bg-slate-100 dark:hover:bg-slate-800 border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-sm text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 transition-all active:scale-95 cursor-pointer flex items-center justify-center"
                title="Live monitor info"
              >
                <GoogleCloudIcon className="w-5 h-5 text-indigo-400" />
              </button>
            )}
          </div>
        </div>

        <h5 className="text-xs uppercase tracking-wider text-slate-500 dark:text-slate-500 font-bold mb-3">Live Unified Event Stream (Redis Bus)</h5>
        <div className="overflow-x-auto rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/70 mb-7">
          <table className="w-full text-left border-collapse font-mono text-xs">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-500 dark:text-slate-400 bg-white/80 dark:bg-slate-900/50">
                <th className="p-3.5 font-semibold">Timestamp</th>
                <th className="p-3.5 font-semibold">RRN / Event ID</th>
                <th className="p-3.5 font-semibold">Merchant / Descriptor</th>
                <th className="p-3.5 font-semibold text-right">Amount</th>
                <th className="p-3.5 font-semibold">Status / Replication Target</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-800/60">
              {streamData.length === 0 ? (
                <tr>
                  <td colSpan="5" className="p-8 text-center text-slate-500 dark:text-slate-500 font-sans">
                    Waiting for operational transaction activity... Trigger a surge, anomaly, or late fee above.
                  </td>
                </tr>
              ) : (
                streamData.map((item, idx) => {
                  const fraudReasons = Array.isArray(item.fraud_reason_codes) ? item.fraud_reason_codes : [];
                  return (
                    <tr key={item.id + idx} className="hover:bg-slate-100 dark:hover:bg-slate-900/60 transition-colors">
                      <td className="p-3.5 text-slate-500 dark:text-slate-400 whitespace-nowrap flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                        {item.timestamp}
                      </td>
                      <td className="p-3.5 text-slate-800 dark:text-slate-300 font-bold whitespace-nowrap">{item.rrn}</td>
                      <td className="p-3.5 text-slate-900 dark:text-white font-sans font-medium truncate max-w-xs">{item.merchant_name}</td>
                      <td className="p-3.5 text-right text-slate-900 dark:text-slate-100 font-bold whitespace-nowrap">
                        {formatCurrencyFromCents(item.amount_cents)}
                      </td>
                      <td className="p-3.5 whitespace-nowrap">
                        <div className="flex flex-col gap-1">
                          <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold w-fit ${
                            item.status.includes('FLAGGED')
                              ? 'bg-rose-500/15 text-rose-700 dark:text-rose-400 border border-rose-500/30'
                              : item.status.includes('HOLD')
                              ? 'bg-amber-500/15 text-amber-700 dark:text-amber-400 border border-amber-500/30'
                              : 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border border-emerald-500/30'
                          }`}>
                            {item.status}
                          </span>
                          {fraudReasons.length > 0 && (
                            <div className="flex flex-wrap gap-1 max-w-md">
                              {fraudReasons.slice(0, 3).map((reason) => (
                                <span
                                  key={reason}
                                  className="inline-flex items-center px-1.5 py-0.5 rounded border border-rose-500/20 bg-rose-500/10 text-[9px] font-bold text-rose-700 dark:text-rose-300"
                                >
                                  {formatFraudReason(reason)}
                                </span>
                              ))}
                            </div>
                          )}
                          <span className="text-[10px] text-slate-500 dark:text-slate-500">{item.bq_view}</span>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

      </div>

      <GcpInfoModal
        isOpen={infoModal === 'monitor'}
        onClose={() => setInfoModal(null)}
        title="Live Transaction Monitor"
      >
        <div className="space-y-4 text-slate-600 dark:text-slate-400 text-sm leading-relaxed">
          <p>
            The <strong>Live Transaction Replication Monitor</strong> shows recent card activity as it is created by the banking service. Authorizations, settlements, reversals, and flagged events are published to Redis and streamed directly into the admin UI over authenticated server-sent events.
          </p>
          <p>
            This panel is meant to answer a simple operational question: what is happening right now in the transaction flow? It is a live event wall, ordered with the newest activity first, and every connected admin session sees the same shared stream.
          </p>
          <div className="bg-slate-50 dark:bg-slate-950 p-4 rounded-2xl border border-slate-100 dark:border-slate-800 space-y-3 font-sans text-xs">
            <div className="p-2.5 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
              <div className="text-cyan-500 dark:text-cyan-400 font-mono font-bold">Redis recent_transactions + channel:transactions:live</div>
              <p className="text-slate-500 dark:text-slate-400 mt-1">Card authorizations and settlements are published once and fanned out to every connected admin GUI without consumers competing for events.</p>
            </div>
            <div className="p-2.5 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
              <div className="text-rose-500 dark:text-rose-400 font-mono font-bold">Cloud Monitoring Datastream metrics</div>
              <p className="text-slate-500 dark:text-slate-400 mt-1">System lag and freshness are still sourced from managed Datastream metrics so the page can distinguish live event flow from downstream replication health.</p>
            </div>
          </div>
          <div className="bg-slate-50 dark:bg-slate-950 p-4 rounded-2xl border border-slate-100 dark:border-slate-800 space-y-3">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h4 className="font-semibold text-slate-800 dark:text-slate-200 text-xs uppercase tracking-wider">BigQuery Studio Console</h4>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">Inspect the analytical lakehouse destination, CDC-derived views, and anomaly datasets after replication lands.</p>
              </div>
              <a
                href={`https://console.cloud.google.com/bigquery?project=${projectId}&ws=!1m5!1m4!3m2!1s${projectId}!2siceberg_catalog!23sTREE_NODE_SELECTION`}
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
                <h4 className="font-semibold text-slate-800 dark:text-slate-200 text-xs uppercase tracking-wider">Cloud Run + Memorystore</h4>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">Track the banking-service SSE connections, the data-generator pulse worker, and the Redis event bus that powers the live wall.</p>
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

      <GcpInfoModal
        isOpen={infoModal === 'wal'}
        onClose={() => setInfoModal(null)}
        title="Datastream Replication Engine"
      >
        <div className="space-y-4 text-slate-600 dark:text-slate-400 text-sm leading-relaxed">
          <p>
            The <strong>Datastream WAL Replication Engine</strong> panel summarizes operational stream health and downstream CDC freshness for transaction writes.
          </p>
          <p>
            In practical terms, this panel helps confirm that new transaction events are reaching the admin console and that writes are moving from PostgreSQL WAL into Datastream CDC tables and curated analytical views.
          </p>
          <div className="bg-slate-50 dark:bg-slate-950 p-4 rounded-2xl border border-slate-100 dark:border-slate-800 space-y-3 font-sans text-xs">
            <div className="p-2.5 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
              <div className="text-cyan-500 dark:text-cyan-400 font-mono font-bold">SSE Connection</div>
              <p className="text-slate-500 dark:text-slate-400 mt-1">Shows whether this browser has an authenticated server-sent-events connection to the banking-service live stream. LIVE means the admin UI is connected; RETRY means the client is reconnecting.</p>
            </div>
            <div className="p-2.5 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
              <div className="text-emerald-500 dark:text-emerald-400 font-mono font-bold">Last Event Age</div>
              <p className="text-slate-500 dark:text-slate-400 mt-1">Measures how long it has been since the newest transaction event in the Redis-backed stream. A high value can mean the system is quiet or that live event publishing has stalled.</p>
            </div>
            <div className="p-2.5 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
              <div className="text-blue-500 dark:text-blue-400 font-mono font-bold">Event Throughput</div>
              <p className="text-slate-500 dark:text-slate-400 mt-1">Counts recent live events per minute and breaks them into authorization, posted, and flagged activity so the wall can distinguish holds from settled ledger events.</p>
            </div>
            <div className="p-2.5 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
              <div className="text-rose-500 dark:text-rose-400 font-mono font-bold">Datastream Freshness</div>
              <p className="text-slate-500 dark:text-slate-400 mt-1">Reports managed CDC freshness from Cloud Monitoring. This is downstream replication health, separate from the browser's live SSE connection.</p>
            </div>
            <div className="p-2.5 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
              <div className="text-cyan-500 dark:text-cyan-400 font-mono font-bold">PostgreSQL WAL to Datastream</div>
              <p className="text-slate-500 dark:text-slate-400 mt-1">Operational writes are replicated into lakehouse CDC tables before curated analytics views consume them.</p>
            </div>
            <div className="p-2.5 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
              <div className="text-rose-500 dark:text-rose-400 font-mono font-bold">Managed replication health</div>
              <p className="text-slate-500 dark:text-slate-400 mt-1">System lag and freshness come from managed cloud metrics so you can distinguish a quiet system from a replication problem.</p>
            </div>
          </div>
          <div className="bg-slate-50 dark:bg-slate-950 p-4 rounded-2xl border border-slate-100 dark:border-slate-800 space-y-3">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h4 className="font-semibold text-slate-800 dark:text-slate-200 text-xs uppercase tracking-wider">BigQuery Studio Console</h4>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">Inspect the analytical lakehouse destination, CDC-derived views, and anomaly datasets after replication lands.</p>
              </div>
              <a
                href={`https://console.cloud.google.com/bigquery?project=${projectId}&ws=!1m5!1m4!3m2!1s${projectId}!2siceberg_catalog!23sTREE_NODE_SELECTION`}
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
                <h4 className="font-semibold text-slate-800 dark:text-slate-200 text-xs uppercase tracking-wider">Cloud Run + Memorystore</h4>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">Track the banking-service stream endpoints, the data-generator worker, and the Redis event bus that feeds the monitor.</p>
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

      <GcpInfoModal
        isOpen={infoModal === 'credit-risk'}
        onClose={() => setInfoModal(null)}
        title="Credit Risk Metrics"
      >
        <div className="space-y-4 text-slate-600 dark:text-slate-400 text-sm leading-relaxed">
          <p>
            The <strong>Credit Risk Metrics</strong> tile tracks open fraud-case outcomes, live model scores, reason-code activity, and unsettled exposure separately from replication transport health. A non-zero alert count means the demo has suspicious card activity available for secure-message review and the voice agent flow.
          </p>
          <div className="bg-slate-50 dark:bg-slate-950 p-4 rounded-2xl border border-slate-100 dark:border-slate-800 space-y-3 font-sans text-xs">
            <div className="p-2.5 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
              <div className="text-rose-500 dark:text-rose-400 font-mono font-bold">Open Fraud Alerts</div>
              <p className="text-slate-500 dark:text-slate-400 mt-1">Open alerts represent operational fraud cases that have been enriched, messaged to the customer, and made available to support workflows.</p>
            </div>
            <div className="p-2.5 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
              <div className="text-amber-500 dark:text-amber-400 font-mono font-bold">Peak Model Score + Reason Codes</div>
              <p className="text-slate-500 dark:text-slate-400 mt-1">The score and reason-code fields come directly from the authorization fraud decision payload, making the tile reflect the current model rather than a separate hard-coded anomaly counter.</p>
            </div>
            <div className="p-2.5 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
              <div className="text-blue-500 dark:text-blue-400 font-mono font-bold">Exposure + Event Mix</div>
              <p className="text-slate-500 dark:text-slate-400 mt-1">Flagged exposure sums suspicious authorizations in the current wall, while the event mix compares authorization, posting, and flagged activity per minute.</p>
            </div>
          </div>
        </div>
      </GcpInfoModal>

    </section>
  );
}

export default AdminSimulationView;
