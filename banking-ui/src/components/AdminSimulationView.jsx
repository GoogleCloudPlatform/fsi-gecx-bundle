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

import React, { useCallback, useState, useEffect } from 'react';
import { fetchEventSource } from '@microsoft/fetch-event-source';
import { useNavigate } from 'react-router-dom';
import { 
  Sparkles, Activity, ShieldAlert, Zap, Database, RefreshCw, 
  ArrowLeft, CheckCircle2, AlertTriangle, TrendingUp, Clock,
  Layers, ExternalLink, ClipboardList, Play, RotateCcw, CalendarClock,
  Eye, ChevronDown, MoreHorizontal, RadioTower, HeartPulse
} from 'lucide-react';
import {
  triggerSpendSurge,
  planGenerationScenario,
  executeGenerationScenario,
  enqueueScheduledScenario,
  listScheduledEvents,
  getDataGeneratorStatus,
  getOperationsMonitorSummary,
  injectFraudAnomaly,
  injectLateFee,
  getGlobalStream,
  getBackendApiUrl,
  getBackendAuthHeaders,
} from '../utils/api.js';
import GoogleCloudIcon from './icons/GoogleCloudIcon.jsx';
import GcpInfoModal from './GcpInfoModal.jsx';
import { showInfoModals } from '../utils/constants.js';

const MIN_RISK_CONDITION_SCORED_EVENTS = 5;
const ELEVATED_AVERAGE_RISK_SCORE = 25;
const SURGING_AVERAGE_RISK_SCORE = 70;
const FEEDBACK_DISMISS_MS = 30000;
const MONITOR_WINDOW_OPTIONS = [
  { label: 'Last 15 minutes', value: 15 },
  { label: 'Last 1 hour', value: 60 },
  { label: 'Last 4 hours', value: 240 },
  { label: 'Last 8 hours', value: 480 },
  { label: 'Last 12 hours', value: 720 },
  { label: 'Last 24 hours', value: 1440 },
];

const SCENARIO_OPTIONS = [
  {
    value: 'cnp_gift_card_campaign',
    label: 'Gift Card CNP Campaign',
    goal: 'Create a coordinated card-not-present gift card fraud campaign.',
  },
  {
    value: 'digital_card_testing_campaign',
    label: 'Digital Card Testing',
    goal: 'Create a digital goods card testing campaign with small probes and follow-up activity.',
  },
  {
    value: 'impossible_travel_campaign',
    label: 'Impossible Travel',
    goal: 'Create rapid card-present geography jumps that should surface impossible-travel risk.',
  },
  {
    value: 'travel_false_positive_story',
    label: 'Legitimate Travel Review',
    goal: 'Create a legitimate Mexico travel story with false-positive review and confirmed customer outcome.',
  },
  {
    value: 'lakehouse_spend_velocity_surge',
    label: 'Spend Velocity Surge',
    goal: 'Run a scenario-backed active lakehouse spend velocity surge.',
  },
];

const SCENARIO_INTENSITIES = ['low', 'medium', 'high'];

function uniqueValues(values, fallback = 'None') {
  const unique = [...new Set(values.filter(Boolean))];
  if (!unique.length) return fallback;
  return unique.slice(0, 3).join(', ') + (unique.length > 3 ? ` +${unique.length - 3}` : '');
}

function buildScenarioIdempotencyKey(prefix, plan) {
  return `${prefix}:${plan?.scenario_id || 'scenario'}:${Date.now()}`;
}

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

function formatCompactNumber(value) {
  return Number(value || 0).toLocaleString();
}

function formatShortTimestamp(value) {
  if (!value) return 'N/A';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'N/A';
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function formatWindowLabel(minutes) {
  return MONITOR_WINDOW_OPTIONS.find((option) => option.value === Number(minutes))?.label || `Last ${minutes} minutes`;
}

function formatScheduleTime(value) {
  if (!value) return 'N/A';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'N/A';
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function formatScheduledEventType(value) {
  return String(value || 'event')
    .replaceAll('_', ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function getScheduledEventMerchant(event) {
  return event?.payload?.authorization_payload?.merchant_name
    || event?.payload?.merchant_name
    || event?.payload?.outcome_label
    || event?.event_id
    || 'Synthetic event';
}

function summarizeScheduledEvents(events) {
  const summary = {
    upcoming: 0,
    dispatching: 0,
    succeeded: 0,
    failed: 0,
  };
  events.forEach((event) => {
    const status = String(event.status || '').toUpperCase();
    if (status === 'SCHEDULED') summary.upcoming += 1;
    if (status === 'DISPATCHING') summary.dispatching += 1;
    if (status === 'SUCCEEDED') summary.succeeded += 1;
    if (status === 'FAILED') summary.failed += 1;
  });
  return summary;
}

function formatCompactDateTime(value) {
  if (!value) return 'N/A';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'N/A';
  return date.toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function toDatetimeLocalValue(date) {
  const offsetMs = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
}

function fromDatetimeLocalValue(value) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function getScheduledStatusClass(status) {
  const statusLabel = String(status || 'SCHEDULED').toUpperCase();
  if (statusLabel === 'FAILED') return 'bg-rose-500/10 border-rose-500/20 text-rose-700 dark:text-rose-300';
  if (statusLabel === 'SUCCEEDED') return 'bg-emerald-500/10 border-emerald-500/20 text-emerald-700 dark:text-emerald-300';
  if (statusLabel === 'DISPATCHING') return 'bg-cyan-500/10 border-cyan-500/20 text-cyan-700 dark:text-cyan-300';
  if (statusLabel === 'CANCELED') return 'bg-slate-500/10 border-slate-500/20 text-slate-600 dark:text-slate-300';
  return 'bg-amber-500/10 border-amber-500/20 text-amber-700 dark:text-amber-300';
}

function buildSparklinePath(values, width = 156, height = 52) {
  if (!values.length) return '';
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = Math.max(1, max - min);
  return values.map((value, index) => {
    const x = values.length === 1 ? width : (index / (values.length - 1)) * width;
    const y = height - ((value - min) / span) * height;
    return `${index === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`;
  }).join(' ');
}

function buildAreaPath(values, width = 640, height = 160) {
  const line = buildSparklinePath(values, width, height);
  if (!line) return '';
  return `${line} L ${width} ${height} L 0 ${height} Z`;
}

function buildSeriesValues(series, key = 'events') {
  const values = (series || []).map((point) => Number(point?.[key] || 0));
  return values.length ? values : [0, 0, 0, 0, 0, 0];
}

function buildThroughputSparkline(streamData) {
  const seed = streamData.slice(0, 18).reverse().map((item, index) => {
    const base = Math.abs(item?.amount_cents || 0) / 100;
    const risk = parseFraudRiskScore(item) || 0;
    return Math.max(8, Math.min(180, Math.round((base % 120) + risk + index * 3)));
  });
  return seed.length >= 4 ? seed : [1, 1, 1, 1, 1, 1, 1, 1];
}

function groupScheduledRuns(events) {
  const groups = new Map();
  events.forEach((event) => {
    const scheduleId = event.schedule_id || 'unscheduled';
    if (!groups.has(scheduleId)) {
      groups.set(scheduleId, {
        scheduleId,
        scenarioId: event.scenario_id || scheduleId,
        events: [],
        firstTime: event.scheduled_for,
        lastTime: event.scheduled_for,
      });
    }
    const group = groups.get(scheduleId);
    group.events.push(event);
    if (new Date(event.scheduled_for) < new Date(group.firstTime)) group.firstTime = event.scheduled_for;
    if (new Date(event.scheduled_for) > new Date(group.lastTime)) group.lastTime = event.scheduled_for;
  });

  return [...groups.values()]
    .map((group) => {
      const counts = summarizeScheduledEvents(group.events);
      const completed = counts.succeeded + counts.failed;
      const total = group.events.length;
      const status = counts.dispatching > 0
        ? 'IN FLIGHT'
        : counts.failed > 0
        ? 'ATTENTION'
        : total > 0 && completed === total
        ? 'COMPLETED'
        : 'SCHEDULED';
      const nextEvent = group.events
        .filter((event) => String(event.status || '').toUpperCase() === 'SCHEDULED')
        .sort((a, b) => new Date(a.scheduled_for) - new Date(b.scheduled_for))[0];
      return {
        ...group,
        counts,
        completed,
        total,
        status,
        nextEvent,
        progress: total ? Math.round((completed / total) * 100) : 0,
        opsImpact: counts.failed + counts.dispatching,
      };
    })
    .sort((a, b) => new Date(a.firstTime) - new Date(b.firstTime));
}

function titleFromScenarioId(value) {
  return String(value || 'Synthetic Scenario')
    .replace(/^schedule-/, '')
    .replaceAll('_', ' ')
    .replaceAll('-', ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase())
    .slice(0, 48);
}

function getRiskState(score, status = '') {
  const statusText = String(status || '').toUpperCase();
  if (statusText.includes('FLAGGED') && (score == null || score < 70)) {
    return {
      label: 'High',
      className: 'bg-rose-500/15 text-rose-700 dark:text-rose-400 border border-rose-500/30',
    };
  }
  if (score == null) {
    return {
      label: 'Not scored',
      className: 'bg-slate-500/10 text-slate-500 dark:text-slate-400 border border-slate-500/20',
    };
  }
  if (score >= 90) {
    return {
      label: 'Critical',
      className: 'bg-rose-600/15 text-rose-800 dark:text-rose-300 border border-rose-600/30',
    };
  }
  if (score >= 70) {
    return {
      label: 'High',
      className: 'bg-rose-500/15 text-rose-700 dark:text-rose-400 border border-rose-500/30',
    };
  }
  if (score >= 25) {
    return {
      label: 'Medium',
      className: 'bg-amber-500/15 text-amber-700 dark:text-amber-400 border border-amber-500/30',
    };
  }
  return {
    label: 'Low',
    className: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border border-emerald-500/30',
  };
}

function getRiskBandStyle(label) {
  const normalized = String(label || '').toLowerCase();
  if (normalized.includes('critical')) {
    return {
      dot: 'bg-rose-600',
      text: 'text-rose-700 dark:text-rose-300',
      bg: 'bg-rose-500/10 border-rose-500/20',
      bar: 'bg-rose-600',
    };
  }
  if (normalized.includes('high')) {
    return {
      dot: 'bg-rose-500',
      text: 'text-rose-600 dark:text-rose-300',
      bg: 'bg-rose-500/10 border-rose-500/20',
      bar: 'bg-rose-500',
    };
  }
  if (normalized.includes('medium')) {
    return {
      dot: 'bg-amber-500',
      text: 'text-amber-600 dark:text-amber-300',
      bg: 'bg-amber-500/10 border-amber-500/20',
      bar: 'bg-amber-500',
    };
  }
  if (normalized.includes('low')) {
    return {
      dot: 'bg-emerald-500',
      text: 'text-emerald-600 dark:text-emerald-300',
      bg: 'bg-emerald-500/10 border-emerald-500/20',
      bar: 'bg-emerald-500',
    };
  }
  return {
    dot: 'bg-slate-400',
    text: 'text-slate-500 dark:text-slate-400',
    bg: 'bg-slate-500/10 border-slate-500/20',
    bar: 'bg-slate-400',
  };
}

function getRiskBandStroke(label) {
  const normalized = String(label || '').toLowerCase();
  if (normalized.includes('critical')) return '#e11d48';
  if (normalized.includes('high')) return '#f43f5e';
  if (normalized.includes('medium')) return '#f59e0b';
  if (normalized.includes('low')) return '#10b981';
  return '#94a3b8';
}

function getTransactionStatusDisplay(status = '') {
  const normalized = String(status || '').toUpperCase();
  if (normalized.includes('FAILED') || normalized.includes('DECLINED')) {
    return {
      label: 'Failed',
      lifecycle: 'Authorization failed',
      className: 'bg-rose-500/15 text-rose-700 dark:text-rose-400 border border-rose-500/30',
    };
  }
  if (normalized.includes('FLAGGED')) {
    return {
      label: 'Flagged',
      lifecycle: 'Authorization → Review',
      className: 'bg-rose-500/15 text-rose-700 dark:text-rose-400 border border-rose-500/30',
    };
  }
  if (normalized.includes('HOLD') || normalized.includes('PENDING')) {
    return {
      label: 'Pending',
      lifecycle: 'Authorization received',
      className: 'bg-amber-500/15 text-amber-700 dark:text-amber-400 border border-amber-500/30',
    };
  }
  if (normalized.includes('SETTLE') || normalized.includes('POSTED')) {
    return {
      label: 'Posted',
      lifecycle: 'Authorization → Settlement',
      className: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border border-emerald-500/30',
    };
  }
  return {
    label: 'Posted',
    lifecycle: 'Replicated record',
    className: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border border-emerald-500/30',
  };
}

function summarizeScenarioPlan(plan) {
  const events = plan?.timeline || [];
  return {
    eventCount: events.length,
    personaCount: plan?.personas?.length || 0,
    geography: uniqueValues(events.map((event) => event.merchant_context?.country_code), 'Local'),
    categories: uniqueValues(events.map((event) => event.merchant_context?.category || event.merchant_context?.mcc), 'Mixed'),
    validations: plan?.expected_validations?.length || 0,
    warnings: plan?.warnings?.length || 0,
  };
}

function summarizeScenarioResult(result) {
  if (!result) {
    return {
      status: 'None',
      attempted: 0,
      succeeded: 0,
      authorizations: 0,
      settlements: 0,
      reversals: 0,
      pending: 0,
      outcomes: 0,
      failures: 0,
      skipped: 0,
    };
  }
  return {
    status: result.status || 'None',
    attempted: result.attempted_events || 0,
    succeeded: result.succeeded_events || 0,
    authorizations: result.authorizations_created || 0,
    settlements: result.settlements_created || 0,
    reversals: result.reversals_created || 0,
    pending: result.pending_holds_created || 0,
    outcomes: result.outcomes?.length || 0,
    failures: result.failed_events || 0,
    skipped: result.skipped_events || 0,
  };
}

function parseFraudRiskScore(item) {
  const explicitScore = Number(item?.fraud_risk_score);
  if (Number.isFinite(explicitScore)) {
    return explicitScore;
  }
  const match = String(item?.status || '').match(/RISK\s+(\d+)/i);
  return match ? Number(match[1]) : null;
}

function AdminSimulationView({ mode = 'studio' }) {
  const navigate = useNavigate();
  const projectId = window.firebaseConfig?.projectId;
  const isMonitoring = mode === 'monitoring';
  const PageIcon = isMonitoring ? Activity : Sparkles;
  const pageIconGradient = isMonitoring ? 'from-emerald-500 to-cyan-600' : 'from-cyan-500 to-blue-600';
  const pageTitle = isMonitoring ? 'Operations Monitor' : 'Simulation Studio';
  const pageSubtitle = isMonitoring
    ? 'Tracks source authorization events as they are enriched, risk-scored, and posted to the replicated ledger.'
    : 'Plan, dry-run, and execute synthetic banking scenarios with data-generator controls.';
  const [isSurgeLoading, setIsSurgeLoading] = useState(false);
  const [isAnomalyLoading, setIsAnomalyLoading] = useState(false);
  const [isFeeLoading, setIsFeeLoading] = useState(false);
  const [isScenarioLoading, setIsScenarioLoading] = useState(false);
  const [isScheduleLoading, setIsScheduleLoading] = useState(false);
  const [selectedScenarioType, setSelectedScenarioType] = useState(SCENARIO_OPTIONS[0].value);
  const [scenarioIntensity, setScenarioIntensity] = useState('medium');
  const [scenarioSeed, setScenarioSeed] = useState('1841');
  const [scenarioMaxEvents, setScenarioMaxEvents] = useState('8');
  const [scenarioStartAt, setScenarioStartAt] = useState(() => toDatetimeLocalValue(new Date(Date.now() + 30_000)));
  const [scenarioEndAt, setScenarioEndAt] = useState(() => toDatetimeLocalValue(new Date(Date.now() + 60 * 60_000)));
  const [scenarioPlan, setScenarioPlan] = useState(null);
  const [scenarioResult, setScenarioResult] = useState(null);
  const [scheduledEvents, setScheduledEvents] = useState([]);
  const [scheduleError, setScheduleError] = useState('');
  const [dispatchReceipt, setDispatchReceipt] = useState(null);
  const [dataGeneratorStatus, setDataGeneratorStatus] = useState(null);
  const [infoModal, setInfoModal] = useState(null);
  const [streamData, setStreamData] = useState([]);
  const [monitorWindowMinutes, setMonitorWindowMinutes] = useState(15);
  const [operationsSummary, setOperationsSummary] = useState(null);
  const [operationsSummaryError, setOperationsSummaryError] = useState('');
  const [feedback, setFeedback] = useState({ type: '', title: '', message: '', data: null });
  const [streamConnection, setStreamConnection] = useState({ state: 'connecting', message: 'Negotiating secure stream...' });
  const [cdcStats, setCdcStats] = useState({
    systemLagMs: null,
    dataFreshnessMs: null,
    activeAnomalies: 0,
    operationalActiveFraudAlerts: 0,
    lakehouseFraudAnomalies: 0,
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
        if (riskScore >= 70) {
          acc.highRiskTransactionCount += 1;
        }
        if (acc.peakRiskScore == null || riskScore > acc.peakRiskScore) {
          acc.peakRiskScore = riskScore;
          acc.peakRiskMerchant = item.merchant_name || 'Recent authorization';
        }
      }
      if (item.fraud_model_version) {
        acc.latestModelVersion = item.fraud_model_version;
      }
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
      highRiskTransactionCount: 0,
      peakRiskScore: null,
      peakRiskMerchant: null,
      latestModelVersion: null,
    },
  );
  creditRiskMetrics.averageRiskScore = creditRiskMetrics.scoredCount
    ? Math.round(creditRiskMetrics.riskScoreTotal / creditRiskMetrics.scoredCount)
    : null;
  creditRiskMetrics.averageFlaggedRiskScore = creditRiskMetrics.flaggedCount
    ? Math.round(creditRiskMetrics.flaggedRiskScoreTotal / creditRiskMetrics.flaggedCount)
    : null;
  const hasSustainedElevatedRisk =
    creditRiskMetrics.scoredCount >= MIN_RISK_CONDITION_SCORED_EVENTS
    && creditRiskMetrics.averageRiskScore >= ELEVATED_AVERAGE_RISK_SCORE;
  const hasSustainedSurgingRisk =
    creditRiskMetrics.scoredCount >= MIN_RISK_CONDITION_SCORED_EVENTS
    && creditRiskMetrics.averageRiskScore >= SURGING_AVERAGE_RISK_SCORE;

  const riskCondition = (() => {
    if (cdcStats.flaggedEventsPerMinute >= 3 || hasSustainedSurgingRisk) {
      return {
        label: 'Surging',
        className: 'bg-rose-50 dark:bg-rose-950/10 border-rose-100 dark:border-rose-900/40',
        textClass: 'text-rose-700 dark:text-rose-300',
        iconClass: 'text-rose-500',
      };
    }
    if (
      cdcStats.flaggedEventsPerMinute > 0
      || cdcStats.operationalActiveFraudAlerts > 0
      || hasSustainedElevatedRisk
    ) {
      return {
        label: 'Elevated',
        className: 'bg-amber-50 dark:bg-amber-950/10 border-amber-100 dark:border-amber-900/40',
        textClass: 'text-amber-700 dark:text-amber-300',
        iconClass: 'text-amber-500',
      };
    }
    return {
      label: 'Normal',
      className: 'bg-emerald-50 dark:bg-emerald-950/10 border-emerald-100 dark:border-emerald-900/40',
      textClass: 'text-emerald-700 dark:text-emerald-300',
      iconClass: 'text-emerald-500',
    };
  })();

  const scenarioPlanSummary = summarizeScenarioPlan(scenarioPlan);
  const scenarioResultSummary = summarizeScenarioResult(scenarioResult);
  const scheduleSummary = summarizeScheduledEvents(scheduledEvents);
  const scheduledRuns = groupScheduledRuns(scheduledEvents);
  const ambientProfile = dataGeneratorStatus?.ambient_profile || null;
  const observedReceiptEvents = dispatchReceipt
    ? streamData.filter((item) => Number(item.raw_time || 0) >= dispatchReceipt.submittedAtSeconds)
    : [];
  const latestObservedEvent = observedReceiptEvents[0] || null;
  const throughputSparkline = buildThroughputSparkline(streamData);
  const throughputPath = buildSparklinePath(throughputSparkline);
  const mostRecentDispatchTitle = dispatchReceipt?.action || 'Ambient Baseline';
  const mostRecentDispatchStatus = dispatchReceipt ? 'DISPATCHED' : 'RUNNING';
  const scenarioOverlayCount = scheduledRuns.filter((run) => run.status !== 'COMPLETED').length;
  const scheduledEventsInFlight = scheduledEvents.filter((event) => ['SCHEDULED', 'DISPATCHING'].includes(String(event.status || '').toUpperCase())).length;
  const systemHealthRows = [
    ['Data Stream', streamConnection.state === 'live' ? 'Live' : streamConnection.state === 'error' ? 'Retrying' : 'Connecting'],
    ['Risk Engine', riskCondition.label === 'Surging' ? 'Surging' : 'Healthy'],
    ['Rules Engine', 'Healthy'],
    ['Notifications', cdcStats.operationalActiveFraudAlerts > 0 ? `${cdcStats.operationalActiveFraudAlerts} alerts` : 'No alerts'],
  ];
  const summaryHealth = operationsSummary?.replication_health || {};
  const summaryImpact = operationsSummary?.impact || {};
  const summaryTransactions = operationsSummary?.transactions || [];
  const summaryRiskSignals = operationsSummary?.risk_signals || [];
  const summaryScenarioImpact = operationsSummary?.scenario_impact || [];
  const summaryEventMix = operationsSummary?.event_mix || [];
  const summarySystemHealth = operationsSummary?.system_health || [];
  const summaryRiskDistribution = operationsSummary?.risk_distribution || [];
  const summarySeriesValues = buildSeriesValues(operationsSummary?.activity_series, 'events');
  const summaryLinePath = buildSparklinePath(summarySeriesValues, 640, 160);
  const summaryAreaPath = buildAreaPath(summarySeriesValues, 640, 160);
  const activeRiskDistribution = summaryRiskDistribution.filter((item) => Number(item.count || 0) > 0);
  const scoredRiskTotal = activeRiskDistribution.reduce((sum, item) => sum + Number(item.count || 0), 0);
  const highPlusRiskTotal = activeRiskDistribution
    .filter((item) => ['critical', 'high'].includes(String(item.label || '').toLowerCase()))
    .reduce((sum, item) => sum + Number(item.count || 0), 0);
  const riskPieSegments = activeRiskDistribution.reduce((segments, item) => {
    const percent = scoredRiskTotal ? (Number(item.count || 0) / scoredRiskTotal) * 100 : 0;
    const offset = segments.reduce((sum, segment) => sum + segment.percent, 0);
    return [
      ...segments,
      {
      ...item,
      percent,
      offset,
      stroke: getRiskBandStroke(item.label),
      },
    ];
  }, []);
  const replicationHealthCards = [
    {
      label: 'Stream Status',
      value: streamConnection.state === 'live' ? 'LIVE' : streamConnection.state === 'error' ? 'RETRY' : 'SYNC',
      detail: streamConnection.state === 'live' ? 'Connected to Redis event feed' : streamConnection.message,
      icon: Activity,
      className: streamConnection.state === 'live'
        ? 'text-emerald-600 dark:text-emerald-300'
        : 'text-amber-600 dark:text-amber-300',
    },
    {
      label: 'Last Event Age',
      value: formatEventAge(summaryHealth.latest_event_age_ms ?? cdcStats.latestEventAgeMs),
      detail: 'Age of newest event',
      icon: Clock,
      className: 'text-slate-900 dark:text-white',
    },
    {
      label: 'Event Throughput',
      value: `${formatCompactNumber(summaryHealth.events_per_minute ?? cdcStats.eventsPerMinute)} / min`,
      detail: formatWindowLabel(monitorWindowMinutes),
      icon: Layers,
      className: 'text-slate-900 dark:text-white',
    },
    {
      label: 'Replication Lag',
      value: formatLatency(summaryHealth.replication_lag_ms ?? cdcStats.systemLagMs),
      detail: 'Operational to lakehouse',
      icon: Database,
      className: 'text-slate-900 dark:text-white',
    },
    {
      label: 'Datastream Freshness',
      value: formatLatency(summaryHealth.data_freshness_ms ?? cdcStats.dataFreshnessMs),
      detail: 'Managed CDC destination',
      icon: ShieldAlert,
      className: 'text-slate-900 dark:text-white',
    },
  ];
  const riskOverviewCards = [
    {
      label: 'Open Fraud Alerts',
      value: formatCompactNumber(summaryImpact.open_fraud_alerts ?? cdcStats.operationalActiveFraudAlerts),
      detail: 'Cases awaiting review',
      className: 'bg-emerald-50 dark:bg-emerald-950/10 border-emerald-200 dark:border-emerald-900/40 text-emerald-700 dark:text-emerald-300',
    },
    {
      label: 'High Risk Transactions',
      value: formatCompactNumber(summaryImpact.high_risk_transactions ?? creditRiskMetrics.highRiskTransactionCount),
      detail: formatWindowLabel(monitorWindowMinutes),
      className: 'bg-rose-50 dark:bg-rose-950/10 border-rose-200 dark:border-rose-900/40 text-rose-700 dark:text-rose-300',
    },
    {
      label: 'Accounts Impacted',
      value: formatCompactNumber(summaryImpact.accounts_impacted),
      detail: 'Unique account IDs',
      className: 'bg-cyan-50 dark:bg-cyan-950/10 border-cyan-200 dark:border-cyan-900/40 text-cyan-700 dark:text-cyan-300',
    },
    {
      label: 'Pending Exposure',
      value: formatCurrencyFromCents(summaryImpact.pending_exposure_cents),
      detail: 'Pending or flagged holds',
      className: 'bg-amber-50 dark:bg-amber-950/10 border-amber-200 dark:border-amber-900/40 text-amber-700 dark:text-amber-300',
    },
    {
      label: 'Active Scenarios',
      value: formatCompactNumber(summaryImpact.active_scenarios ?? scenarioOverlayCount),
      detail: 'Windowed synthetic overlays',
      className: 'bg-slate-50 dark:bg-slate-950/50 border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-300',
    },
    {
      label: 'Peak Risk Score',
      value: summaryImpact.peak_risk_score ?? creditRiskMetrics.peakRiskScore ?? 'N/A',
      detail: 'Highest scored event',
      className: 'bg-slate-50 dark:bg-slate-950/50 border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-300',
    },
    {
      label: 'Rules Triggered',
      value: formatCompactNumber(summaryImpact.rules_triggered),
      detail: 'Distinct reason codes',
      className: 'bg-slate-50 dark:bg-slate-950/50 border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-300',
    },
    {
      label: 'Alerts Generated',
      value: formatCompactNumber(summaryImpact.alerts_generated),
      detail: formatWindowLabel(monitorWindowMinutes),
      className: 'bg-slate-50 dark:bg-slate-950/50 border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-300',
    },
  ];

  const applyMonitorSnapshot = (streamSnapshot) => {
    if (streamSnapshot?.stream) {
      setStreamData(streamSnapshot.stream);
    }

    if (streamSnapshot?.cdc_metrics || streamSnapshot?.stream_metrics) {
      setCdcStats({
        systemLagMs: streamSnapshot.cdc_metrics?.system_lag_ms ?? null,
        dataFreshnessMs: streamSnapshot.cdc_metrics?.data_freshness_ms ?? null,
        activeAnomalies: streamSnapshot.cdc_metrics?.active_anomalies ?? 0,
        operationalActiveFraudAlerts: streamSnapshot.cdc_metrics?.operational_active_fraud_alerts ?? streamSnapshot.cdc_metrics?.active_anomalies ?? 0,
        lakehouseFraudAnomalies: streamSnapshot.cdc_metrics?.lakehouse_fraud_anomalies ?? 0,
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
    try {
      const streamRes = await getGlobalStream();
      applyMonitorSnapshot(streamRes);
    } catch (e) {
      console.error("Failed to fetch global stream:", e);
    }
  };

  const refreshOperationsSummary = useCallback(async (windowMinutes) => {
    try {
      const summary = await getOperationsMonitorSummary({ windowMinutes });
      setOperationsSummary(summary);
      setOperationsSummaryError('');
    } catch (error) {
      console.error('Failed to fetch operations monitor summary:', error);
      setOperationsSummaryError(error.response?.data?.detail || error.message || 'Operations summary is unavailable.');
    }
  }, []);

  const refreshScheduledEvents = async () => {
    try {
      const scheduled = await listScheduledEvents({ limit: 20 });
      setScheduledEvents(Array.isArray(scheduled.events) ? scheduled.events : []);
      setScheduleError('');
    } catch (error) {
      console.error('Failed to fetch scheduled data-generator events:', error);
      setScheduleError(error.response?.data?.detail || error.message || 'Scheduled events are unavailable.');
    }
  };

  const beginDispatchReceipt = (action, expectedEvents = null, message = '') => {
    setDispatchReceipt({
      action,
      expectedEvents,
      message,
      submittedAt: new Date().toLocaleTimeString(),
      submittedAtSeconds: Date.now() / 1000,
    });
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

    const loadDataGeneratorStatus = async () => {
      try {
        const status = await getDataGeneratorStatus();
        setDataGeneratorStatus(status);
      } catch (error) {
        console.error('Failed to fetch data-generator status:', error);
      }
    };

    loadDataGeneratorStatus();

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
    if (!isMonitoring) {
      return undefined;
    }

    refreshOperationsSummary(monitorWindowMinutes);
    const intervalId = window.setInterval(
      () => refreshOperationsSummary(monitorWindowMinutes),
      15000,
    );
    return () => window.clearInterval(intervalId);
  }, [isMonitoring, monitorWindowMinutes, refreshOperationsSummary]);

  useEffect(() => {
    if (isMonitoring) {
      return undefined;
    }

    refreshScheduledEvents();
    const intervalId = window.setInterval(refreshScheduledEvents, 8000);
    return () => window.clearInterval(intervalId);
  }, [isMonitoring]);

  useEffect(() => {
    if (feedback.message) {
      const timer = setTimeout(() => {
        setFeedback({ type: '', title: '', message: '', data: null });
      }, FEEDBACK_DISMISS_MS);
      return () => clearTimeout(timer);
    }
  }, [feedback]);

  const handleSpendSurge = async () => {
    setIsSurgeLoading(true);
    setFeedback({ type: '', title: '', message: '', data: null });
    beginDispatchReceipt('Spend Velocity Surge', 50, 'Waiting for transaction stream activity...');
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
    beginDispatchReceipt('Targeted Fraud Anomaly', 5, 'Waiting for flagged authorization events...');
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
        operationalActiveFraudAlerts: Math.max(prev.operationalActiveFraudAlerts, 1),
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
    beginDispatchReceipt('Late Fee Injection', 1, 'Waiting for fee event activity...');
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

  const selectedScenario = SCENARIO_OPTIONS.find((option) => option.value === selectedScenarioType) || SCENARIO_OPTIONS[0];

  const buildScenarioRequest = (mode = 'dry_run') => ({
    goal: selectedScenario.goal,
    scenario_type: selectedScenario.value,
    mode,
    intensity: scenarioIntensity,
    seed: Number(scenarioSeed) || 1841,
    max_events: Number(scenarioMaxEvents) || 8,
    target_cohort_size: Math.max(1, Math.min(Number(scenarioMaxEvents) || 8, 25)),
  });

  const handleScenarioDryRun = async () => {
    setIsScenarioLoading(true);
    setFeedback({ type: '', title: '', message: '', data: null });
    try {
      const plan = await planGenerationScenario(buildScenarioRequest('dry_run'));
      setScenarioPlan(plan);
      setScenarioResult(null);
      setFeedback({
        type: 'success',
        title: 'Scenario Dry Run Planned',
        message: `${plan.scenario_type} prepared ${plan.timeline?.length || 0} planned events with ${plan.expected_validations?.length || 0} validation hint${(plan.expected_validations?.length || 0) === 1 ? '' : 's'}.`,
        data: plan,
      });
    } catch (err) {
      setFeedback({
        type: 'error',
        title: 'Scenario Planning Failed',
        message: err.response?.data?.detail || err.message || 'Unable to plan the synthetic scenario.',
        data: null,
      });
    } finally {
      setIsScenarioLoading(false);
    }
  };

  const executeScenarioPlan = async (plan, mode = 'execute') => {
    beginDispatchReceipt(
      mode === 'replay' ? 'Scenario Replay' : 'Scenario Execution',
      plan?.timeline?.length || null,
      'Waiting for scenario-backed stream activity...',
    );
    const result = await executeGenerationScenario({
      plan,
      mode,
      idempotency_key: buildScenarioIdempotencyKey(`ui-${mode}`, plan),
      operator: window.firebaseAuth?.getCurrentUser?.()?.email || 'admin-simulation-ui',
    });
    setScenarioResult(result);
    setFeedback({
      type: result.status === 'failed' ? 'error' : result.status === 'partial' ? 'warning' : 'success',
      title: mode === 'replay' ? 'Scenario Replay Submitted' : 'Scenario Execution Submitted',
      message: `${result.status || 'submitted'}: ${result.succeeded_events || 0}/${result.planned_events || 0} events succeeded, ${result.outcomes?.length || 0} outcome labels captured.`,
      data: result,
    });
    fetchGlobalStream();
  };

  const handleScenarioSchedule = async () => {
    setIsScheduleLoading(true);
    setFeedback({ type: '', title: '', message: '', data: null });
    try {
      const plan = scenarioPlan?.scenario_type === selectedScenario.value
        ? scenarioPlan
        : await planGenerationScenario(buildScenarioRequest('dry_run'));
      setScenarioPlan(plan);
      const scheduleStart = fromDatetimeLocalValue(scenarioStartAt) || new Date(Date.now() + 30_000);
      const scheduleEnd = fromDatetimeLocalValue(scenarioEndAt);
      const scheduleResult = await enqueueScheduledScenario({
        execution_request: {
          plan,
          mode: 'execute',
          idempotency_key: buildScenarioIdempotencyKey('ui-schedule', plan),
          operator: window.firebaseAuth?.getCurrentUser?.()?.email || 'admin-simulation-ui',
        },
        start_at: scheduleStart.toISOString(),
        ...(scheduleEnd ? { end_at: scheduleEnd.toISOString() } : {}),
      });
      beginDispatchReceipt(
        'Scheduled Scenario',
        scheduleResult.created_events?.length || plan.timeline?.length || null,
        `Queued ${scheduleResult.created_events?.length || 0} durable event${(scheduleResult.created_events?.length || 0) === 1 ? '' : 's'} from ${formatScheduleTime(scheduleStart.toISOString())}${scheduleEnd ? ` to ${formatScheduleTime(scheduleEnd.toISOString())}` : ''}.`,
      );
      setFeedback({
        type: scheduleResult.warnings?.length ? 'warning' : 'success',
        title: 'Scenario Scheduled',
        message: `${scheduleResult.schedule_id} queued ${scheduleResult.created_events?.length || 0} event${(scheduleResult.created_events?.length || 0) === 1 ? '' : 's'} via ${scheduleResult.dispatch_transport}.`,
        data: scheduleResult,
      });
      refreshScheduledEvents();
    } catch (err) {
      setFeedback({
        type: 'error',
        title: 'Scenario Scheduling Failed',
        message: err.response?.data?.detail || err.message || 'Unable to schedule the synthetic scenario.',
        data: null,
      });
    } finally {
      setIsScheduleLoading(false);
    }
  };

  const handleScenarioExecute = async () => {
    setIsScenarioLoading(true);
    setFeedback({ type: '', title: '', message: '', data: null });
    try {
      const plan = scenarioPlan?.scenario_type === selectedScenario.value
        ? scenarioPlan
        : await planGenerationScenario(buildScenarioRequest('dry_run'));
      setScenarioPlan(plan);
      await executeScenarioPlan(plan, 'execute');
    } catch (err) {
      setFeedback({
        type: 'error',
        title: 'Scenario Execution Failed',
        message: err.response?.data?.detail || err.message || 'Unable to execute the synthetic scenario.',
        data: null,
      });
    } finally {
      setIsScenarioLoading(false);
    }
  };

  const handleScenarioReplay = async () => {
    if (!scenarioPlan) {
      setFeedback({
        type: 'warning',
        title: 'No Scenario To Replay',
        message: 'Run a dry run or execute a scenario before replaying it.',
        data: null,
      });
      return;
    }
    setIsScenarioLoading(true);
    setFeedback({ type: '', title: '', message: '', data: null });
    try {
      await executeScenarioPlan(scenarioPlan, 'replay');
    } catch (err) {
      setFeedback({
        type: 'error',
        title: 'Scenario Replay Failed',
        message: err.response?.data?.detail || err.message || 'Unable to replay the synthetic scenario.',
        data: null,
      });
    } finally {
      setIsScenarioLoading(false);
    }
  };

  return (
    <section className="relative pt-24 pb-16 md:pt-28 md:pb-24 px-6 max-w-7xl mx-auto min-h-[calc(100vh-80px)] flex flex-col text-left">

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
            <div className={`p-3 rounded-2xl bg-gradient-to-br ${pageIconGradient} text-white shadow-lg shadow-cyan-500/20`}>
              <PageIcon className="w-7 h-7" />
            </div>
            <div>
              <h1 className="text-3xl font-extrabold bg-gradient-to-r from-slate-900 via-slate-700 to-slate-500 dark:from-white dark:via-slate-200 dark:to-slate-400 bg-clip-text text-transparent">
                {pageTitle}
              </h1>
              <p className="text-sm text-slate-500 mt-1">
                {pageSubtitle}
              </p>
            </div>
          </div>
        </div>
        {isMonitoring && (
          <div className="flex items-center gap-2 self-start md:self-end">
            <select
              value={monitorWindowMinutes}
              onChange={(event) => setMonitorWindowMinutes(Number(event.target.value))}
              className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 px-3 py-2 text-xs font-bold text-slate-700 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-cyan-500"
              title="Operations monitor time window"
            >
              {MONITOR_WINDOW_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
            <button
              onClick={() => refreshOperationsSummary(monitorWindowMinutes)}
              className="p-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-500 hover:text-slate-900 dark:hover:text-white transition-colors"
              title="Refresh operations summary"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>

      {isMonitoring && (
        <>
          <div className="mb-6 p-5 rounded-3xl bg-white/80 dark:bg-slate-900/80 border border-slate-200/80 dark:border-slate-800/80 backdrop-blur-xl shadow-xl shadow-slate-950/5">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <div className="text-[11px] uppercase tracking-wider font-black text-slate-500 dark:text-slate-400">Replication Engine Health</div>
                <p className="text-xs text-slate-500 mt-1">Authenticated event stream, operational write freshness, and lakehouse replication posture.</p>
              </div>
              <div className="flex items-center gap-2">
                <span className={`px-3 py-1 rounded-full border text-[10px] font-black ${walStatus.className}`}>{walStatus.label}</span>
                {showInfoModals() && (
                  <button
                    onClick={() => setInfoModal('wal')}
                    className="p-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-500 hover:text-slate-900 dark:hover:text-white transition-colors"
                    title="Replication engine health info"
                  >
                    <GoogleCloudIcon className="w-4 h-4 text-indigo-400" />
                  </button>
                )}
              </div>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
              {replicationHealthCards.map((card) => {
                const CardIcon = card.icon;
                return (
                  <div key={card.label} className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/50 p-4 min-h-[116px]">
                    <div className="flex items-center justify-between text-xs text-slate-500 mb-3">
                      <span>{card.label}</span>
                      <CardIcon className="w-4 h-4 text-cyan-500" />
                    </div>
                    <div className={`font-mono text-2xl font-black ${card.className}`}>{card.value}</div>
                    <div className="mt-1 text-[10px] text-slate-500 truncate">{card.detail}</div>
                  </div>
                );
              })}
            </div>
            <div className="mt-4 flex flex-wrap gap-2 text-[11px] text-slate-500">
              <span className="px-2.5 py-1 rounded-full bg-slate-100 dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
                Buffered events: <span className="font-mono text-slate-700 dark:text-slate-300">{formatCompactNumber(summaryHealth.backlog_depth ?? cdcStats.recentBufferedEvents)}</span>
              </span>
              <span className="px-2.5 py-1 rounded-full bg-slate-100 dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
                System lag: <span className="font-mono text-slate-700 dark:text-slate-300">{formatLatency(summaryHealth.system_lag_ms ?? cdcStats.systemLagMs)}</span>
              </span>
              <span className="px-2.5 py-1 rounded-full bg-slate-100 dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
                Error rate: <span className="font-mono text-slate-700 dark:text-slate-300">{summaryHealth.error_rate ? `${summaryHealth.error_rate}.00%` : '0.00%'}</span>
              </span>
              <span className="px-2.5 py-1 rounded-full bg-slate-100 dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
                Last sync: <span className="font-mono text-slate-700 dark:text-slate-300">{cdcStats.lastSyncTime}</span>
              </span>
            </div>
            {operationsSummaryError && (
              <div className="mt-4 rounded-2xl border border-amber-200 dark:border-amber-900/40 bg-amber-50 dark:bg-amber-950/10 px-4 py-3 text-xs font-semibold text-amber-700 dark:text-amber-300">
                {operationsSummaryError}
              </div>
            )}
          </div>

          <div className="mb-6 grid grid-cols-1 xl:grid-cols-[1.2fr_0.8fr] gap-5">
            <div className="p-5 rounded-3xl bg-white/80 dark:bg-slate-900/80 border border-slate-200/80 dark:border-slate-800/80 shadow-xl shadow-slate-950/5">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <div className="text-[11px] uppercase tracking-wider font-black text-slate-500 dark:text-slate-400">Risk & Alerts Overview</div>
                  <p className="text-xs text-slate-500 mt-1">{formatWindowLabel(monitorWindowMinutes)} operational risk posture.</p>
                </div>
                {showInfoModals() && (
                  <button
                    onClick={() => setInfoModal('credit-risk')}
                    className="p-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-500 hover:text-slate-900 dark:hover:text-white transition-colors"
                    title="Credit risk metrics info"
                  >
                    <GoogleCloudIcon className="w-4 h-4 text-indigo-400" />
                  </button>
                )}
              </div>
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                {riskOverviewCards.map((card) => (
                  <div key={card.label} className={`rounded-2xl border p-4 ${card.className}`}>
                    <div className="text-[11px] font-bold">{card.label}</div>
                    <div className="mt-2 font-mono text-2xl font-black">{card.value}</div>
                    <div className="mt-1 text-[10px] opacity-80 truncate">{card.detail}</div>
                  </div>
                ))}
              </div>
            </div>

            <div className="p-5 rounded-3xl bg-white/80 dark:bg-slate-900/80 border border-slate-200/80 dark:border-slate-800/80 shadow-xl shadow-slate-950/5">
              <div className="mb-4">
                <div className="text-[11px] uppercase tracking-wider font-black text-slate-500 dark:text-slate-400">Impact At A Glance</div>
                <p className="text-xs text-slate-500 mt-1">Risk-band distribution for scored decisions in this window.</p>
              </div>
              <div>
                {activeRiskDistribution.length === 0 ? (
                  <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/50 p-4 text-xs text-slate-500">
                    No scored risk distribution yet for this window.
                  </div>
                ) : (
                  <div className="grid grid-cols-1 sm:grid-cols-[176px_1fr] gap-5 items-center">
                    <div className="relative mx-auto w-44 h-44">
                      <svg viewBox="0 0 120 120" className="w-44 h-44 -rotate-90" aria-label="Risk distribution pie chart">
                        <circle cx="60" cy="60" r="44" fill="none" stroke="currentColor" strokeWidth="18" className="text-slate-100 dark:text-slate-800" />
                        {riskPieSegments.map((segment) => (
                          <circle
                            key={segment.label}
                            cx="60"
                            cy="60"
                            r="44"
                            fill="none"
                            stroke={segment.stroke}
                            strokeWidth="18"
                            strokeLinecap="butt"
                            pathLength="100"
                            strokeDasharray={`${segment.percent} ${100 - segment.percent}`}
                            strokeDashoffset={-segment.offset}
                          />
                        ))}
                      </svg>
                      <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
                        <div className="font-mono text-3xl font-black text-slate-900 dark:text-white">{formatCompactNumber(highPlusRiskTotal)}</div>
                        <div className="text-[10px] uppercase tracking-wider font-bold text-slate-500">High+</div>
                        <div className="text-[10px] text-slate-400">{formatCompactNumber(scoredRiskTotal)} scored</div>
                      </div>
                    </div>
                    <div className="space-y-3">
                      {activeRiskDistribution.map((item) => {
                        const style = getRiskBandStyle(item.label);
                        return (
                          <div key={item.label} className="flex items-center justify-between gap-3 text-xs">
                            <span className={`font-bold flex items-center gap-2 ${style.text}`}>
                              <span className={`w-2 h-2 rounded-full ${style.dot}`} />
                              {item.label}
                            </span>
                            <span className="font-mono font-black text-slate-900 dark:text-white">
                              {item.count} <span className="text-slate-400 font-normal">{item.percentage}%</span>
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="mb-10 grid grid-cols-1 xl:grid-cols-[1fr_300px] gap-5">
            <div className="p-5 rounded-3xl bg-white/80 dark:bg-slate-900/80 border border-slate-200/80 dark:border-slate-800/80 shadow-xl shadow-slate-950/5">
              <div className="mb-4 flex items-center justify-between gap-3">
                <div>
                  <div className="text-[11px] uppercase tracking-wider font-black text-slate-500 dark:text-slate-400">Live Activity</div>
                  <p className="text-xs text-slate-500 mt-1">Windowed activity from authorizations and posted transactions.</p>
                </div>
                <span className="px-2.5 py-1 rounded-full bg-cyan-500/10 text-cyan-700 dark:text-cyan-300 text-[10px] font-black border border-cyan-500/20">Event Throughput</span>
              </div>
              <svg viewBox="0 0 640 160" className="w-full h-44 text-cyan-500" aria-hidden="true">
                {summaryAreaPath && <path d={summaryAreaPath} fill="currentColor" opacity="0.10" />}
                {summaryLinePath && <path d={summaryLinePath} fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />}
              </svg>
            </div>

            <div className="p-5 rounded-3xl bg-white/80 dark:bg-slate-900/80 border border-slate-200/80 dark:border-slate-800/80 shadow-xl shadow-slate-950/5">
              <div className="mb-4 text-[11px] uppercase tracking-wider font-black text-slate-500 dark:text-slate-400">Stream Event Mix</div>
              <div className="space-y-3">
                {summaryEventMix.map((item) => (
                  <div key={item.label}>
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-semibold text-slate-700 dark:text-slate-300">{item.label}</span>
                      <span className="font-mono font-bold text-slate-900 dark:text-white">{item.percentage}%</span>
                    </div>
                    <div className="mt-1 h-1.5 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                      <div className="h-full rounded-full bg-cyan-500" style={{ width: `${Math.max(3, item.percentage)}%` }} />
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-5 pt-4 border-t border-slate-200 dark:border-slate-800 flex items-center justify-between text-xs">
                <span className="text-slate-500">Total Events</span>
                <span className="font-mono font-black text-slate-900 dark:text-white">{formatCompactNumber(summaryEventMix.reduce((sum, item) => sum + Number(item.count || 0), 0))}</span>
              </div>
            </div>
          </div>

        </>
      )}

      {!isMonitoring && (
        <>
      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_280px] gap-5 items-start">
      <div className="min-w-0">
      <div className="mb-10 p-5 rounded-3xl bg-white/80 dark:bg-slate-900/80 border border-slate-200/80 dark:border-slate-800/80 shadow-xl shadow-slate-950/5">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-extrabold text-slate-900 dark:text-white">Active Dispatch & Feedback</h2>
            <span className={`px-2.5 py-1 rounded-full text-[10px] font-black ${
              streamConnection.state === 'live'
                ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300'
                : 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300'
            }`}>
              {streamConnection.state === 'live' ? 'LIVE' : 'SYNC'}
            </span>
          </div>
          <span className="text-[11px] font-mono text-slate-400">{new Date().toLocaleTimeString()}</span>
        </div>
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              <Activity className="w-4 h-4 text-emerald-500" />
              Most Recent Dispatch
            </div>
            <h3 className="text-sm font-bold text-slate-900 dark:text-white">
              {dispatchReceipt?.action || 'No simulation action submitted yet'}
            </h3>
            <p className="text-xs text-slate-500 mt-1">
              {dispatchReceipt
                ? `${dispatchReceipt.message || 'Watching the live stream for activity after submission.'} Submitted at ${dispatchReceipt.submittedAt}.`
                : 'Run or schedule a simulation action to see immediate confirmation here.'}
            </p>
          </div>
          <div className="grid grid-cols-3 gap-2 text-[11px] min-w-full md:min-w-[360px]">
            <div className="px-3 py-2 rounded-2xl bg-slate-50 dark:bg-slate-950/50 border border-slate-100 dark:border-slate-800">
              <div className="text-slate-400">Events Dispatched</div>
              <div className="font-mono font-black text-slate-900 dark:text-white">{dispatchReceipt?.expectedEvents ?? 0}</div>
            </div>
            <div className="px-3 py-2 rounded-2xl bg-slate-50 dark:bg-slate-950/50 border border-slate-100 dark:border-slate-800">
              <div className="text-slate-400">Observed</div>
              <div className="font-mono font-black text-slate-900 dark:text-white">{dispatchReceipt ? observedReceiptEvents.length : 0}</div>
            </div>
            <div className="px-3 py-2 rounded-2xl bg-slate-50 dark:bg-slate-950/50 border border-slate-100 dark:border-slate-800">
              <div className="text-slate-400">Pending</div>
              <div className="font-mono font-black text-amber-600 dark:text-amber-300 truncate">
                {dispatchReceipt?.expectedEvents == null ? 0 : Math.max(0, dispatchReceipt.expectedEvents - observedReceiptEvents.length)}
              </div>
            </div>
          </div>
        </div>
        <div className="mt-4 grid grid-cols-1 lg:grid-cols-[1fr_220px] gap-3">
          <div className="rounded-2xl border border-emerald-200 dark:border-emerald-900/40 bg-emerald-50 dark:bg-emerald-950/10 px-4 py-3 flex items-center gap-3">
            <div className="p-2 rounded-xl bg-white/70 dark:bg-slate-900/70 text-emerald-600 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-900/40">
              <TrendingUp className="w-5 h-5" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-extrabold text-slate-900 dark:text-white truncate">{mostRecentDispatchTitle}</span>
                <span className="px-2 py-0.5 rounded-full bg-emerald-100 dark:bg-emerald-900/30 text-[10px] font-bold text-emerald-700 dark:text-emerald-300">{mostRecentDispatchStatus}</span>
              </div>
              <div className="text-xs text-slate-500 truncate">{dispatchReceipt?.message || 'Background baseline traffic is active.'}</div>
            </div>
          </div>
          <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/50 p-3">
            <div className="flex items-center justify-between text-[10px] uppercase tracking-wider text-slate-400 font-bold">
              <span>Recent Stream Activity</span>
              <span className="text-emerald-500">{streamData.length >= 4 ? 'Live' : 'Quiet'}</span>
            </div>
            <div className="mt-1 flex items-end justify-between gap-3">
              <div className="font-mono text-2xl font-black text-slate-900 dark:text-white">{cdcStats.eventsPerMinute}</div>
              <svg viewBox="0 0 156 52" className="w-28 h-10 text-emerald-500" aria-hidden="true">
                <path d={throughputPath} fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
              </svg>
            </div>
          </div>
        </div>
        {latestObservedEvent && (
          <div className="mt-4 rounded-2xl border border-emerald-200 dark:border-emerald-900/40 bg-emerald-50 dark:bg-emerald-950/10 px-4 py-3 text-xs text-emerald-700 dark:text-emerald-300 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <span className="font-semibold truncate">{latestObservedEvent.merchant_name || 'Recent stream event'}</span>
            <span className="font-mono">{formatCurrencyFromCents(latestObservedEvent.amount_cents)} · {latestObservedEvent.status || 'STREAM EVENT'}</span>
          </div>
        )}
      </div>

      <div className="mb-10">
        <div className="mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
          <Zap className="w-4 h-4 text-amber-500" />
          Immediate Actions
        </div>
        <p className="text-xs text-slate-500 mb-3">
          These controls fire direct simulation requests now. They are useful for quick demos, but they do not create durable scheduled records.
        </p>
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

      <div className="mb-10 p-6 rounded-3xl bg-white/80 dark:bg-slate-900/80 border border-slate-200/80 dark:border-slate-800/80 backdrop-blur-xl shadow-xl shadow-slate-950/5">
        <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-5">
          <div className="min-w-0">
            <div className="mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              <ClipboardList className="w-4 h-4 text-violet-500" />
              Scenario Composer
            </div>
            <div className="flex items-center gap-3">
              <h2 className="text-lg font-bold text-slate-900 dark:text-white">Scenario Composer</h2>
              {showInfoModals() && (
                <button
                  onClick={() => setInfoModal('scenario-studio')}
                  className="p-2 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-sm text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200 transition-all active:scale-95 cursor-pointer flex items-center justify-center"
                  title="Scenario Studio info"
                >
                  <GoogleCloudIcon className="w-4 h-4 text-indigo-400" />
                </button>
              )}
            </div>
            <p className="text-xs text-slate-500 mt-1 max-w-2xl">
              Dry-run a scenario plan, launch it now, or schedule the run into a start/end operating window.
            </p>
          </div>
          <div className="grid grid-cols-2 gap-3 text-xs min-w-[220px]">
            <div className="px-3 py-2 rounded-2xl bg-slate-50 dark:bg-slate-950/50 border border-slate-100 dark:border-slate-800">
              <div className="text-slate-500">Last Plan</div>
              <div className="font-mono font-bold text-slate-900 dark:text-white truncate">{scenarioPlan?.scenario_id || 'None'}</div>
            </div>
            <div className="px-3 py-2 rounded-2xl bg-slate-50 dark:bg-slate-950/50 border border-slate-100 dark:border-slate-800">
              <div className="text-slate-500">Last Result</div>
              <div className="font-mono font-bold text-slate-900 dark:text-white">{scenarioResult?.status || 'None'}</div>
            </div>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3">
          <div className="rounded-2xl border border-violet-200 dark:border-violet-900/40 bg-violet-50 dark:bg-violet-950/10 px-4 py-3">
            <div className="text-[11px] font-bold uppercase tracking-wider text-violet-600 dark:text-violet-300">Launch Now</div>
            <p className="text-xs text-slate-600 dark:text-slate-400 mt-1">Runs the scenario immediately through the card-network APIs and confirms activity through the live stream.</p>
          </div>
          <div className="rounded-2xl border border-emerald-200 dark:border-emerald-900/40 bg-emerald-50 dark:bg-emerald-950/10 px-4 py-3">
            <div className="text-[11px] font-bold uppercase tracking-wider text-emerald-600 dark:text-emerald-300">Schedule Run</div>
            <p className="text-xs text-slate-600 dark:text-slate-400 mt-1">Persists planned events into the data-generator schedule so Cloud Tasks can dispatch them over time.</p>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-2 text-[11px]">
          <div className="px-3 py-2 rounded-xl bg-slate-50 dark:bg-slate-950/50 border border-slate-100 dark:border-slate-800">
            <div className="text-slate-400">Ambient Profile</div>
            <div className="font-mono font-bold text-slate-900 dark:text-white truncate">{ambientProfile?.profile_name || 'steady'}</div>
          </div>
          <div className="px-3 py-2 rounded-xl bg-slate-50 dark:bg-slate-950/50 border border-slate-100 dark:border-slate-800">
            <div className="text-slate-400">Pulse Events</div>
            <div className="font-mono font-bold text-slate-900 dark:text-white">
              {ambientProfile ? `${ambientProfile.pulse_min_events}-${ambientProfile.pulse_max_events}` : 'Default'}
            </div>
          </div>
          <div className="px-3 py-2 rounded-xl bg-slate-50 dark:bg-slate-950/50 border border-slate-100 dark:border-slate-800">
            <div className="text-slate-400">Travel / Digital</div>
            <div className="font-mono font-bold text-slate-900 dark:text-white">
              {ambientProfile ? `${ambientProfile.travel_multiplier}x / ${ambientProfile.ecommerce_multiplier}x` : '1x / 1x'}
            </div>
          </div>
          <div className="px-3 py-2 rounded-xl bg-slate-50 dark:bg-slate-950/50 border border-slate-100 dark:border-slate-800">
            <div className="text-slate-400">Fraud Pattern</div>
            <div className="font-mono font-bold text-slate-900 dark:text-white">
              {ambientProfile?.fraud_pattern_enabled ? `${Math.round((ambientProfile.fraud_pattern_rate || 0) * 100)}%` : 'Off'}
            </div>
          </div>
        </div>

        <div className="mt-5 grid grid-cols-1 lg:grid-cols-[1.2fr_0.8fr] gap-5">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label className="block">
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Template</span>
              <select
                value={selectedScenarioType}
                onChange={(event) => {
                  setSelectedScenarioType(event.target.value);
                  setScenarioPlan(null);
                  setScenarioResult(null);
                }}
                className="mt-1 w-full rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 px-3 py-2 text-sm font-semibold text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-violet-500"
              >
                {SCENARIO_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>

            <label className="block">
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Intensity</span>
              <select
                value={scenarioIntensity}
                onChange={(event) => setScenarioIntensity(event.target.value)}
                className="mt-1 w-full rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 px-3 py-2 text-sm font-semibold text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-violet-500"
              >
                {SCENARIO_INTENSITIES.map((intensity) => (
                  <option key={intensity} value={intensity}>{intensity.toUpperCase()}</option>
                ))}
              </select>
            </label>

            <label className="block">
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Start Time</span>
              <input
                type="datetime-local"
                value={scenarioStartAt}
                onChange={(event) => setScenarioStartAt(event.target.value)}
                className="mt-1 w-full rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 px-3 py-2 text-sm font-semibold text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-violet-500"
              />
            </label>

            <label className="block">
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">End Time</span>
              <input
                type="datetime-local"
                value={scenarioEndAt}
                onChange={(event) => setScenarioEndAt(event.target.value)}
                className="mt-1 w-full rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 px-3 py-2 text-sm font-semibold text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-violet-500"
              />
            </label>

            <label className="block">
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Seed</span>
              <input
                type="number"
                min="0"
                value={scenarioSeed}
                onChange={(event) => setScenarioSeed(event.target.value)}
                className="mt-1 w-full rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 px-3 py-2 text-sm font-semibold text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-violet-500"
              />
            </label>

            <label className="block">
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Max Events</span>
              <input
                type="number"
                min="1"
                max="100"
                value={scenarioMaxEvents}
                onChange={(event) => setScenarioMaxEvents(event.target.value)}
                className="mt-1 w-full rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 px-3 py-2 text-sm font-semibold text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-violet-500"
              />
            </label>
          </div>

          <div className="flex flex-col gap-3">
            <div className="rounded-2xl bg-slate-50 dark:bg-slate-950/50 border border-slate-100 dark:border-slate-800 p-4">
              <div className="text-sm font-bold text-slate-900 dark:text-white">{selectedScenario.label}</div>
              <div className="text-[11px] text-slate-500 dark:text-slate-400 mt-1 leading-snug">{selectedScenario.goal}</div>
              <div className="mt-3 grid grid-cols-3 gap-2 text-[11px]">
                <div>
                  <div className="text-slate-400">Events</div>
                  <div className="font-mono font-bold text-slate-800 dark:text-slate-200">{scenarioPlanSummary.eventCount}</div>
                </div>
                <div>
                  <div className="text-slate-400">Personas</div>
                  <div className="font-mono font-bold text-slate-800 dark:text-slate-200">{scenarioPlanSummary.personaCount}</div>
                </div>
                <div>
                  <div className="text-slate-400">Checks</div>
                  <div className="font-mono font-bold text-slate-800 dark:text-slate-200">{scenarioPlanSummary.validations}</div>
                </div>
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2 text-[11px]">
                <div>
                  <div className="text-slate-400">Geography</div>
                  <div className="font-semibold text-slate-700 dark:text-slate-200 truncate">{scenarioPlanSummary.geography}</div>
                </div>
                <div>
                  <div className="text-slate-400">Categories</div>
                  <div className="font-semibold text-slate-700 dark:text-slate-200 truncate">{scenarioPlanSummary.categories}</div>
                </div>
              </div>
              {scenarioPlanSummary.warnings > 0 && (
                <div className="mt-3 rounded-xl border border-amber-200 dark:border-amber-900/50 bg-amber-50 dark:bg-amber-950/20 px-3 py-2 text-[11px] font-semibold text-amber-700 dark:text-amber-300">
                  {scenarioPlanSummary.warnings} planning warning{scenarioPlanSummary.warnings === 1 ? '' : 's'} attached.
                </div>
              )}
            </div>

            <div className="rounded-2xl bg-slate-50 dark:bg-slate-950/50 border border-slate-100 dark:border-slate-800 p-4">
              <div className="text-sm font-bold text-slate-900 dark:text-white">Execution Result</div>
              <div className="mt-3 grid grid-cols-4 gap-2 text-[11px]">
                <div>
                  <div className="text-slate-400">Status</div>
                  <div className="font-mono font-bold text-slate-800 dark:text-slate-200 truncate">{scenarioResultSummary.status}</div>
                </div>
                <div>
                  <div className="text-slate-400">Success</div>
                  <div className="font-mono font-bold text-slate-800 dark:text-slate-200">{scenarioResultSummary.succeeded}/{scenarioResultSummary.attempted}</div>
                </div>
                <div>
                  <div className="text-slate-400">Auths</div>
                  <div className="font-mono font-bold text-slate-800 dark:text-slate-200">{scenarioResultSummary.authorizations}</div>
                </div>
                <div>
                  <div className="text-slate-400">Labels</div>
                  <div className="font-mono font-bold text-slate-800 dark:text-slate-200">{scenarioResultSummary.outcomes}</div>
                </div>
              </div>
              <div className="mt-3 grid grid-cols-4 gap-2 text-[11px]">
                <div>
                  <div className="text-slate-400">Settle</div>
                  <div className="font-mono font-bold text-slate-800 dark:text-slate-200">{scenarioResultSummary.settlements}</div>
                </div>
                <div>
                  <div className="text-slate-400">Reverse</div>
                  <div className="font-mono font-bold text-slate-800 dark:text-slate-200">{scenarioResultSummary.reversals}</div>
                </div>
                <div>
                  <div className="text-slate-400">Holds</div>
                  <div className="font-mono font-bold text-slate-800 dark:text-slate-200">{scenarioResultSummary.pending}</div>
                </div>
                <div>
                  <div className="text-slate-400">Issues</div>
                  <div className="font-mono font-bold text-slate-800 dark:text-slate-200">{scenarioResultSummary.failures + scenarioResultSummary.skipped}</div>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={handleScenarioDryRun}
                disabled={isScenarioLoading}
                className="py-2.5 px-2 rounded-xl bg-slate-800 hover:bg-slate-700 active:scale-[0.98] text-white text-xs font-bold flex items-center justify-center gap-2 transition-all disabled:opacity-60 disabled:hover:bg-slate-800"
                title="Plan scenario"
              >
                {isScenarioLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Eye className="w-4 h-4" />}
                Dry Run
              </button>
              <button
                onClick={handleScenarioExecute}
                disabled={isScenarioLoading}
                className="py-2.5 px-2 rounded-xl bg-violet-600 hover:bg-violet-500 active:scale-[0.98] text-white text-xs font-bold flex items-center justify-center gap-2 transition-all disabled:opacity-60 disabled:hover:bg-violet-600"
                title="Execute scenario immediately"
              >
                {isScenarioLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                Launch Now
              </button>
              <button
                onClick={handleScenarioReplay}
                disabled={isScenarioLoading || !scenarioPlan}
                className="py-2.5 px-2 rounded-xl bg-cyan-600 hover:bg-cyan-500 active:scale-[0.98] text-white text-xs font-bold flex items-center justify-center gap-2 transition-all disabled:opacity-60 disabled:hover:bg-cyan-600"
                title="Replay last plan"
              >
                {isScenarioLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <RotateCcw className="w-4 h-4" />}
                Replay
              </button>
              <button
                onClick={handleScenarioSchedule}
                disabled={isScenarioLoading || isScheduleLoading}
                className="py-2.5 px-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 active:scale-[0.98] text-white text-xs font-bold flex items-center justify-center gap-2 transition-all disabled:opacity-60 disabled:hover:bg-emerald-600"
                title="Schedule durable scenario"
              >
                {isScheduleLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <CalendarClock className="w-4 h-4" />}
                Schedule Run
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="mb-10 p-6 rounded-3xl bg-white/80 dark:bg-slate-900/80 border border-slate-200/80 dark:border-slate-800/80 shadow-xl shadow-slate-950/5">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 mb-5 pb-4 border-b border-slate-200/60 dark:border-slate-800/60">
          <div>
            <div className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              <Clock className="w-4 h-4 text-emerald-500" />
              Scheduled Event Queue
            </div>
            <h2 className="text-lg font-bold text-slate-900 dark:text-white">Scenario Runs & Scheduled Event Queue</h2>
            <p className="text-xs text-slate-500 mt-1">Synthetic scenario runs created by Schedule Run and dispatched by Cloud Tasks over time.</p>
          </div>
          <button
            onClick={refreshScheduledEvents}
            className="self-start lg:self-auto px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-xs font-bold text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition-all active:scale-95 flex items-center gap-2"
          >
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5 text-[11px]">
          <div className="px-3 py-2 rounded-2xl bg-slate-50 dark:bg-slate-950/50 border border-slate-100 dark:border-slate-800">
            <div className="text-slate-400">Scheduled</div>
            <div className="font-mono font-black text-slate-900 dark:text-white">{scheduleSummary.upcoming}</div>
          </div>
          <div className="px-3 py-2 rounded-2xl bg-slate-50 dark:bg-slate-950/50 border border-slate-100 dark:border-slate-800">
            <div className="text-slate-400">Dispatching</div>
            <div className="font-mono font-black text-slate-900 dark:text-white">{scheduleSummary.dispatching}</div>
          </div>
          <div className="px-3 py-2 rounded-2xl bg-slate-50 dark:bg-slate-950/50 border border-slate-100 dark:border-slate-800">
            <div className="text-slate-400">Succeeded</div>
            <div className="font-mono font-black text-slate-900 dark:text-white">{scheduleSummary.succeeded}</div>
          </div>
          <div className="px-3 py-2 rounded-2xl bg-slate-50 dark:bg-slate-950/50 border border-slate-100 dark:border-slate-800">
            <div className="text-slate-400">Failed</div>
            <div className={`font-mono font-black ${scheduleSummary.failed ? 'text-rose-600 dark:text-rose-400' : 'text-slate-900 dark:text-white'}`}>{scheduleSummary.failed}</div>
          </div>
        </div>

        {scheduleError ? (
          <div className="rounded-2xl border border-amber-200 dark:border-amber-900/40 bg-amber-50 dark:bg-amber-950/10 px-4 py-3 text-xs font-semibold text-amber-700 dark:text-amber-300">
            {scheduleError}
          </div>
        ) : scheduledRuns.length === 0 ? (
          <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/50 px-4 py-6 text-center text-xs text-slate-500">
            No durable synthetic runs are queued yet. Use Schedule Run to place a scenario on the Cloud Tasks-backed timeline.
          </div>
        ) : (
          <div className="space-y-3">
            {scheduledRuns.slice(0, 6).map((run, runIndex) => {
              const runStatusClass = getScheduledStatusClass(run.status);
              return (
                <div key={run.scheduleId} className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950/40 overflow-hidden">
                  <div className="px-4 py-3 flex flex-col lg:flex-row lg:items-center justify-between gap-3">
                    <div className="min-w-0 flex items-start gap-3">
                      <div className="mt-0.5 w-7 h-7 rounded-full bg-cyan-600 text-white text-xs font-black flex items-center justify-center shrink-0">
                        {runIndex + 1}
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <h3 className="text-sm font-extrabold text-slate-900 dark:text-white truncate">{titleFromScenarioId(run.scenarioId)}</h3>
                          <span className={`px-2 py-0.5 rounded-full border text-[10px] font-bold ${runStatusClass}`}>{run.status}</span>
                        </div>
                        <p className="mt-0.5 text-[11px] text-slate-500">
                          Start: {formatCompactDateTime(run.firstTime)} <span className="mx-1">•</span> Est. End: {formatCompactDateTime(run.lastTime)}
                        </p>
                      </div>
                    </div>
                    <div className="grid grid-cols-3 gap-4 text-[11px] text-slate-500 min-w-full lg:min-w-[360px]">
                      <div>
                        <div className="text-slate-400">Progress</div>
                        <div className="mt-1 h-1.5 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                          <div className="h-full rounded-full bg-cyan-600" style={{ width: `${run.progress}%` }} />
                        </div>
                        <div className="mt-1 font-mono font-bold text-slate-800 dark:text-slate-200">{run.progress}%</div>
                      </div>
                      <div>
                        <div className="text-slate-400">Events</div>
                        <div className="font-mono font-black text-slate-900 dark:text-white">{run.completed} / {run.total}</div>
                      </div>
                      <div>
                        <div className="text-slate-400">Next Event</div>
                        <div className="font-mono font-black text-slate-900 dark:text-white">{run.nextEvent ? formatScheduleTime(run.nextEvent.scheduled_for) : 'Done'}</div>
                      </div>
                    </div>
                  </div>
                  <div className="border-t border-slate-200 dark:border-slate-800 overflow-x-auto">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-slate-50 dark:bg-slate-900/60 text-[10px] uppercase tracking-wider text-slate-400">
                        <tr>
                          <th className="px-4 py-2 font-bold">Event</th>
                          <th className="px-4 py-2 font-bold">Type</th>
                          <th className="px-4 py-2 font-bold">Scheduled</th>
                          <th className="px-4 py-2 font-bold">Status</th>
                          <th className="px-4 py-2 font-bold">Details</th>
                          <th className="px-4 py-2 font-bold text-right">More</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80">
                        {run.events.slice(0, 5).map((event) => {
                          const statusLabel = String(event.status || 'SCHEDULED').toUpperCase();
                          return (
                            <tr key={event.id} className="text-slate-600 dark:text-slate-300">
                              <td className="px-4 py-2 font-semibold max-w-[180px] truncate">{getScheduledEventMerchant(event)}</td>
                              <td className="px-4 py-2">{formatScheduledEventType(event.event_type)}</td>
                              <td className="px-4 py-2 font-mono">{formatScheduleTime(event.scheduled_for)}</td>
                              <td className="px-4 py-2">
                                <span className={`px-2 py-0.5 rounded-full border text-[10px] font-bold ${getScheduledStatusClass(statusLabel)}`}>{statusLabel}</span>
                              </td>
                              <td className="px-4 py-2 max-w-[220px] truncate">{event.last_error || event.persona_id || event.scenario_id || 'Ready'}</td>
                              <td className="px-4 py-2 text-right text-slate-400"><MoreHorizontal className="w-4 h-4 inline" /></td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
      </div>
      <aside className="space-y-4 xl:sticky xl:top-24">
        <div className="rounded-3xl bg-white/80 dark:bg-slate-900/80 border border-slate-200/80 dark:border-slate-800/80 shadow-xl shadow-slate-950/5 p-4">
          <h2 className="text-sm font-extrabold text-slate-900 dark:text-white mb-3">Environment Overview</h2>
          <div className="rounded-2xl border border-emerald-100 dark:border-emerald-900/40 bg-emerald-50/70 dark:bg-emerald-950/10 p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-2">
                <RadioTower className="w-4 h-4 text-emerald-500" />
                <span className="text-xs font-extrabold text-slate-900 dark:text-white">Ambient Baseline</span>
              </div>
              <span className="px-2 py-0.5 rounded-full bg-emerald-100 dark:bg-emerald-900/30 text-[10px] font-bold text-emerald-700 dark:text-emerald-300">
                {streamConnection.state === 'live' ? 'Running' : 'Connecting'}
              </span>
            </div>
            <p className="mt-2 text-[11px] text-slate-500">Background traffic remains active to simulate normal operation.</p>
            <div className="mt-4 space-y-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-slate-400 font-bold">Throughput</div>
                  <div className="font-mono text-xl font-black text-slate-900 dark:text-white">{cdcStats.eventsPerMinute}</div>
                  <div className="text-[10px] text-slate-500">events/min</div>
                </div>
                <svg viewBox="0 0 156 52" className="w-28 h-10 text-emerald-500" aria-hidden="true">
                  <path d={throughputPath} fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
                </svg>
              </div>
              <div className="text-[10px] text-slate-500">Sparkline reflects recent stream rows, not a backend time-series.</div>
              <div>
                <div className="text-[10px] uppercase tracking-wider text-slate-400 font-bold">Error Rate</div>
                <div className="font-mono text-xl font-black text-slate-900 dark:text-white">{scheduleSummary.failed > 0 ? '1.00%' : '0.00%'}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wider text-slate-400 font-bold">Accounts Active</div>
                <div className="font-mono text-xl font-black text-slate-900 dark:text-white">{dataGeneratorStatus?.active_cards_count || '1,997'}</div>
              </div>
            </div>
          </div>
        </div>

        <div className="rounded-3xl bg-white/80 dark:bg-slate-900/80 border border-slate-200/80 dark:border-slate-800/80 shadow-xl shadow-slate-950/5 p-4">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Layers className="w-4 h-4 text-amber-500" />
              <h2 className="text-sm font-extrabold text-slate-900 dark:text-white">Scenario Overlays</h2>
            </div>
            <span className="px-2 py-0.5 rounded-full bg-amber-100 dark:bg-amber-900/30 text-[10px] font-bold text-amber-700 dark:text-amber-300">
              {scenarioOverlayCount} Active
            </span>
          </div>
          <p className="mt-2 text-[11px] text-slate-500">Manual scenarios layered over active baseline traffic.</p>
          <div className="mt-4 grid grid-cols-3 gap-3 text-[11px]">
            <div>
              <div className="text-slate-400">Overlays</div>
              <div className="font-mono font-black text-slate-900 dark:text-white">{scenarioOverlayCount}</div>
            </div>
            <div>
              <div className="text-slate-400">In Flight</div>
              <div className="font-mono font-black text-slate-900 dark:text-white">{scheduledEventsInFlight}</div>
            </div>
            <div>
              <div className="text-slate-400">Ops Impact</div>
              <div className="font-mono font-black text-rose-600 dark:text-rose-400">{cdcStats.operationalActiveFraudAlerts}</div>
            </div>
          </div>
          <button
            onClick={refreshScheduledEvents}
            className="mt-4 text-xs font-bold text-cyan-700 dark:text-cyan-300 inline-flex items-center gap-1"
          >
            View details <ChevronDown className="w-3.5 h-3.5 -rotate-90" />
          </button>
        </div>

        <div className="rounded-3xl bg-white/80 dark:bg-slate-900/80 border border-slate-200/80 dark:border-slate-800/80 shadow-xl shadow-slate-950/5 p-4">
          <div className="flex items-center gap-2 mb-3">
            <HeartPulse className="w-4 h-4 text-emerald-500" />
            <h2 className="text-sm font-extrabold text-slate-900 dark:text-white">System Health</h2>
          </div>
          <div className="space-y-2">
            {systemHealthRows.map(([label, value]) => (
              <div key={label} className="flex items-center justify-between gap-3 text-[11px]">
                <span className="text-slate-500">{label}</span>
                <span className={`font-bold ${String(value).includes('Retry') || String(value).includes('alerts') ? 'text-amber-600 dark:text-amber-300' : 'text-emerald-600 dark:text-emerald-300'}`}>
                  {value}
                </span>
              </div>
            ))}
          </div>
        </div>
      </aside>
      </div>

        </>
      )}

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
              <button
                onClick={() => setFeedback({ type: '', title: '', message: '', data: null })}
                className="px-2.5 py-1 rounded-lg bg-white/30 dark:bg-black/20 hover:bg-white/50 dark:hover:bg-black/30 text-[10px] font-bold uppercase tracking-wider transition-colors"
              >
                Hide
              </button>
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

      {isMonitoring && (
        <>
          <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_300px] gap-5">
            <div className="p-6 rounded-3xl bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-800 shadow-2xl shadow-slate-950/5 min-w-0">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-5">
                <div>
                  <h4 className="text-slate-900 dark:text-white font-extrabold text-lg flex items-center gap-2 flex-wrap">
                    <Database className="w-5 h-5 text-cyan-500 dark:text-cyan-400" />
                    Live Transaction Stream
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
                      {streamConnection.state === 'live' ? 'LIVE' : streamConnection.state === 'error' ? 'RETRYING' : 'CONNECTING'}
                    </span>
                  </h4>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                    Compact one-line stream of recent authorizations and postings for the selected window.
                  </p>
                </div>
                <div className="text-[11px] text-slate-500 font-mono">
                  Auto-refresh: 15s
                </div>
              </div>

              <div className="overflow-x-auto rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/70">
                <table className="w-full text-left border-collapse font-mono text-xs">
                  <thead>
                    <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-500 dark:text-slate-400 bg-white/80 dark:bg-slate-900/50">
                      <th className="px-3 py-3 font-semibold">Time</th>
                      <th className="px-3 py-3 font-semibold">Event</th>
                      <th className="px-3 py-3 font-semibold">Merchant / Descriptor</th>
                      <th className="px-3 py-3 font-semibold text-right">Amount</th>
                      <th className="px-3 py-3 font-semibold">Risk</th>
                      <th className="px-3 py-3 font-semibold">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200 dark:divide-slate-800/60">
                    {summaryTransactions.length === 0 ? (
                      <tr>
                        <td colSpan="6" className="p-8 text-center text-slate-500 dark:text-slate-500 font-sans">
                          Waiting for operational transaction activity. Use Simulation Studio to generate scenario activity.
                        </td>
                      </tr>
                    ) : (
                      summaryTransactions.map((item, idx) => {
                        const isSettlement = item.event_type === 'settlement';
                        const riskState = getRiskState(isSettlement ? null : item.risk_score, item.status);
                        const statusDisplay = getTransactionStatusDisplay(item.status);
                        return (
                          <tr key={`${item.id}-${item.event_type}-${idx}`} className="hover:bg-slate-100 dark:hover:bg-slate-900/60 transition-colors">
                            <td className="px-3 py-3 text-slate-500 dark:text-slate-400 whitespace-nowrap">{formatShortTimestamp(item.timestamp)}</td>
                            <td className="px-3 py-3 whitespace-nowrap">
                              <span className="font-bold text-slate-800 dark:text-slate-200">{item.event_type === 'settlement' ? 'SETTLE' : 'AUTH'}</span>
                              <span className="ml-2 text-slate-400">{item.rrn || item.id}</span>
                            </td>
                            <td className="px-3 py-3 text-slate-900 dark:text-white font-sans font-semibold max-w-[260px] truncate" title={item.raw_descriptor || item.merchant_name}>
                              {item.merchant_name || 'Unknown merchant'}
                            </td>
                            <td className="px-3 py-3 text-right text-slate-900 dark:text-slate-100 font-bold whitespace-nowrap">
                              {formatCurrencyFromCents(item.amount_cents)}
                            </td>
                            <td className="px-3 py-3 whitespace-nowrap">
                              {isSettlement ? (
                                <span className="text-slate-400">-</span>
                              ) : (
                                <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold ${riskState.className}`}>
                                  {item.risk_score != null && riskState.label !== 'Not scored' ? `${riskState.label} ${item.risk_score}` : riskState.label}
                                </span>
                              )}
                            </td>
                            <td className="px-3 py-3 whitespace-nowrap">
                              <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold ${statusDisplay.className}`}>
                                {statusDisplay.label}
                              </span>
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            <aside className="space-y-5">
              <div className="p-5 rounded-3xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-xl shadow-slate-950/5">
                <div className="mb-4 text-[11px] uppercase tracking-wider font-black text-slate-500 dark:text-slate-400">Top Risk Signals</div>
                <div className="space-y-3">
                  {summaryRiskSignals.length === 0 ? (
                    <div className="text-xs text-slate-500">No elevated risk signals in this window.</div>
                  ) : (
                    summaryRiskSignals.map((signal, index) => (
                      <div key={signal.label} className="flex items-center justify-between gap-3 text-xs">
                        <span className="min-w-0 flex items-center gap-2 font-semibold text-slate-700 dark:text-slate-300">
                          <span className="w-5 h-5 rounded-full bg-slate-100 dark:bg-slate-800 text-[10px] font-black flex items-center justify-center shrink-0">{index + 1}</span>
                          <span className="truncate">{signal.label}</span>
                        </span>
                        <span className="font-mono font-black text-slate-900 dark:text-white">{signal.count}</span>
                      </div>
                    ))
                  )}
                </div>
              </div>

              <div className="p-5 rounded-3xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-xl shadow-slate-950/5">
                <div className="mb-4 text-[11px] uppercase tracking-wider font-black text-slate-500 dark:text-slate-400">Scenario Impact</div>
                <div className="space-y-3">
                  {summaryScenarioImpact.length === 0 ? (
                    <div className="text-xs text-slate-500">No scenario-linked outcomes in this window.</div>
                  ) : (
                    summaryScenarioImpact.map((scenario) => (
                      <div key={scenario.label} className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/50 p-3">
                        <div className="text-xs font-bold text-slate-900 dark:text-white truncate">{scenario.label}</div>
                        <div className="mt-2 grid grid-cols-2 gap-2 text-[11px]">
                          <div>
                            <div className="text-slate-400">Events</div>
                            <div className="font-mono font-black text-slate-900 dark:text-white">{scenario.events}</div>
                          </div>
                          <div>
                            <div className="text-slate-400">High Risk</div>
                            <div className="font-mono font-black text-rose-600 dark:text-rose-300">{scenario.high_risk}</div>
                          </div>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </aside>
          </div>

          <div className="mt-5 p-5 rounded-3xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-xl shadow-slate-950/5">
            <div className="mb-4 text-[11px] uppercase tracking-wider font-black text-slate-500 dark:text-slate-400">System Health</div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-3">
              {summarySystemHealth.map((item) => (
                <div key={item.label} className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/50 p-3">
                  <div className="text-xs font-bold text-slate-700 dark:text-slate-300 truncate">{item.label}</div>
                  <div className={`mt-2 text-sm font-black ${String(item.status).toUpperCase() === 'SUCCESS' || String(item.status).toUpperCase() === 'HEALTHY' ? 'text-emerald-600 dark:text-emerald-300' : 'text-amber-600 dark:text-amber-300'}`}>
                    {item.status}
                  </div>
                  <div className="mt-1 text-[10px] text-slate-500 truncate">{item.detail}</div>
                </div>
              ))}
            </div>
          </div>

        </>
      )}

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
            This panel is meant to answer a simple operational question: what is happening right now in the transaction flow? It is a live event stream, ordered with the newest activity first, and every connected admin session sees the same shared stream.
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
                <p className="text-[11px] text-slate-500 dark:text-slate-400">Track the banking-service SSE connections, the data-generator pulse worker, and the Redis event bus that powers the live monitor.</p>
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
        title="Replication Engine Health"
      >
        <div className="space-y-4 text-slate-600 dark:text-slate-400 text-sm leading-relaxed">
          <p>
            The <strong>Replication Engine Health</strong> monitor shows recent card activity, live stream status, and downstream CDC freshness for transaction writes.
          </p>
          <p>
            In practical terms, this tile helps confirm that new authorization and settlement events are reaching the admin console while writes continue moving from PostgreSQL WAL into Datastream CDC tables and curated analytical views.
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
              <p className="text-slate-500 dark:text-slate-400 mt-1">Counts recent live events per minute and breaks them into authorization, posted, and flagged activity so the stream can distinguish holds from settled ledger events.</p>
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
            The <strong>Credit Risk Metrics</strong> tile tracks open fraud cases, recent model scores, risk condition, and unsettled exposure separately from replication transport health. A non-zero alert count means the demo has suspicious card activity available for secure-message review and the voice agent flow.
          </p>
          <div className="bg-slate-50 dark:bg-slate-950 p-4 rounded-2xl border border-slate-100 dark:border-slate-800 space-y-3 font-sans text-xs">
            <div className="p-2.5 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
              <div className="text-rose-500 dark:text-rose-400 font-mono font-bold">Open Fraud Alerts</div>
              <p className="text-slate-500 dark:text-slate-400 mt-1">Open alerts represent operational fraud cases that have been enriched, messaged to the customer, and made available to support workflows.</p>
            </div>
            <div className="p-2.5 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
              <div className="text-amber-500 dark:text-amber-400 font-mono font-bold">Risk Condition</div>
              <p className="text-slate-500 dark:text-slate-400 mt-1">Normal means the visible stream has low model scores and no active alert pressure. Elevated means the stream has flagged activity, open alerts, or an average model score above the operating threshold. Surging is reserved for multiple flagged authorizations per minute or a sustained high average model score.</p>
            </div>
            <div className="p-2.5 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
              <div className="text-amber-500 dark:text-amber-400 font-mono font-bold">Peak Model Score</div>
              <p className="text-slate-500 dark:text-slate-400 mt-1">The score comes directly from authorization fraud decision payloads, making the tile reflect the current model rather than a separate hard-coded anomaly counter.</p>
            </div>
            <div className="p-2.5 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
              <div className="text-blue-500 dark:text-blue-400 font-mono font-bold">Exposure + Event Mix</div>
              <p className="text-slate-500 dark:text-slate-400 mt-1">Flagged exposure sums suspicious authorizations in the visible stream, while the event mix compares authorization, posting, and flagged activity per minute.</p>
            </div>
          </div>
        </div>
      </GcpInfoModal>

      <GcpInfoModal
        isOpen={infoModal === 'scenario-studio'}
        onClose={() => setInfoModal(null)}
        title="Scenario Studio"
      >
        <div className="space-y-4 text-slate-600 dark:text-slate-400 text-sm leading-relaxed">
          <p>
            <strong>Scenario Studio</strong> sends bounded scenario planning and execution requests directly to the data-generator Cloud Run service. Dry runs only return a validated plan, Launch Now uses the immediate card-network path, and Schedule Run persists future synthetic events for Cloud Tasks dispatch.
          </p>
          <div className="bg-slate-50 dark:bg-slate-950 p-4 rounded-2xl border border-slate-100 dark:border-slate-800 space-y-3 font-sans text-xs">
            <div className="p-2.5 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
              <div className="text-violet-500 dark:text-violet-400 font-mono font-bold">banking-ui /data-generator/scenarios</div>
              <p className="text-slate-500 dark:text-slate-400 mt-1">The UI calls the Data Generator control surface through the same IAP-protected load balancer used by the banking app.</p>
            </div>
            <div className="p-2.5 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
              <div className="text-cyan-500 dark:text-cyan-400 font-mono font-bold">data-generator ScenarioPlan + schedule</div>
              <p className="text-slate-500 dark:text-slate-400 mt-1">The generator owns the Pydantic scenario contract, canned templates, idempotency keys, synthetic outcome labels, durable scheduled events, and future agentic control tools.</p>
            </div>
            <div className="p-2.5 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
              <div className="text-emerald-500 dark:text-emerald-400 font-mono font-bold">banking-service card-network APIs</div>
              <p className="text-slate-500 dark:text-slate-400 mt-1">Immediate and scheduled scenarios still use banking-service for authorizations, settlement, reversal, fraud scoring, Redis stream events, and CDC into the lakehouse.</p>
            </div>
          </div>
          <div className="bg-slate-50 dark:bg-slate-950 p-4 rounded-2xl border border-slate-100 dark:border-slate-800 flex items-start justify-between gap-4">
            <div>
              <h4 className="font-semibold text-slate-800 dark:text-slate-200 text-xs uppercase tracking-wider">Cloud Run Services</h4>
              <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-1">Inspect revisions for banking-service, data-generator, and banking-ui after a scenario-control deployment.</p>
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
      </GcpInfoModal>

    </section>
  );
}

export default AdminSimulationView;
