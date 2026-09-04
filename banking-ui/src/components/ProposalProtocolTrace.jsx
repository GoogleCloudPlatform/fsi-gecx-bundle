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

import React, { useEffect, useMemo, useState } from 'react';
import { ChevronDown, ShieldCheck } from 'lucide-react';

import {
  latestProposalSignature,
  proposalActionLabel,
  proposalLifecycleSteps,
  TERMINAL_PROPOSAL_STATUSES,
} from '../utils/proposalTrace.js';

const AUTO_COLLAPSE_MS = 6000;

function statusTone(status) {
  if (status === 'COMMITTED') return 'text-emerald-700 dark:text-emerald-300';
  if (TERMINAL_PROPOSAL_STATUSES.has(status)) return 'text-amber-700 dark:text-amber-300';
  return 'text-violet-700 dark:text-violet-300';
}

export default function ProposalProtocolTrace({ proposals = [] }) {
  const [expanded, setExpanded] = useState(true);
  const latest = proposals[proposals.length - 1];
  const signature = latestProposalSignature(proposals);
  const latestStatus = latest?.status;
  const history = proposals.slice(0, -1);
  const steps = useMemo(() => proposalLifecycleSteps(latest), [latest]);

  useEffect(() => {
    if (!signature) return undefined;
    setExpanded(true);
    if (!TERMINAL_PROPOSAL_STATUSES.has(latestStatus)) return undefined;
    const timer = window.setTimeout(() => setExpanded(false), AUTO_COLLAPSE_MS);
    return () => window.clearTimeout(timer);
  }, [signature, latestStatus]);

  if (!latest) return null;

  return (
    <section
      aria-label="Admin-only Proposal Protocol trace"
      className="mt-4 shrink-0 overflow-hidden rounded-2xl border border-violet-200 bg-violet-50/70 dark:border-violet-800/70 dark:bg-violet-950/20"
    >
      <button
        type="button"
        onClick={() => setExpanded(value => !value)}
        aria-expanded={expanded}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
      >
        <span className="flex min-w-0 items-center gap-2">
          <ShieldCheck className="h-4 w-4 shrink-0 text-violet-600 dark:text-violet-400" />
          <span className="shrink-0 text-[9px] font-bold uppercase tracking-[0.14em] text-violet-600 dark:text-violet-400">Admin only</span>
          <span className="truncate text-xs font-semibold text-slate-800 dark:text-slate-100">Proposal Protocol trace</span>
        </span>
        <span className="flex shrink-0 items-center gap-2">
          <span className={`font-mono text-[10px] font-bold ${statusTone(latest.status)}`}>{latest.status}</span>
          <ChevronDown className={`h-4 w-4 text-slate-500 transition-transform ${expanded ? 'rotate-180' : ''}`} />
        </span>
      </button>

      {expanded && (
        <div className="border-t border-violet-200/80 px-4 pb-4 pt-3 dark:border-violet-800/60">
          {history.length > 0 && (
            <div className="mb-3 space-y-1.5" aria-label="Earlier proposals in this consultation">
              {history.map(proposal => (
                <div key={proposal.proposal_ref} className="flex items-center justify-between gap-3 text-[10px] text-slate-500 dark:text-slate-400">
                  <span className="flex min-w-0 items-center gap-1.5"><span className={`h-1.5 w-1.5 shrink-0 rounded-full ${proposal.status === 'COMMITTED' ? 'bg-emerald-500' : 'bg-amber-500'}`} /><span className="truncate">{proposalActionLabel(proposal.action_type)}</span></span>
                  <span className="shrink-0 font-mono">{proposal.status}</span>
                </div>
              ))}
            </div>
          )}

          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <div>
              <p className="text-xs font-bold text-slate-900 dark:text-white">{proposalActionLabel(latest.action_type)}</p>
              <p className="mt-0.5 font-mono text-[9px] text-slate-500 dark:text-slate-400">{latest.contract_version} · {latest.proposal_ref}</p>
            </div>
            <p className="font-mono text-[9px] text-slate-500 dark:text-slate-400">
              Policy provenance: {latest.catalog_snapshot_ref ? `Knowledge Catalog · ${latest.catalog_snapshot_ref}` : 'No catalog snapshot'}
            </p>
          </div>

          <p className="mt-3 text-[11px] leading-relaxed text-slate-700 dark:text-slate-300">{latest.customer_safe_summary}</p>

          <div className="mt-3 grid grid-cols-5 gap-1" aria-label="Proposal lifecycle">
            {steps.map(step => (
              <div key={step.label} className="min-w-0">
                <div className={`h-1 rounded-full ${step.complete ? 'bg-violet-600' : 'bg-slate-200 dark:bg-slate-700'}`} />
                <p className={`mt-1 truncate text-[8px] font-medium ${step.complete ? 'text-violet-700 dark:text-violet-300' : 'text-slate-400 dark:text-slate-500'}`}>{step.label}</p>
              </div>
            ))}
          </div>

          {latest.invalidation_reason && (
            <p className="mt-2 text-[10px] text-amber-700 dark:text-amber-300">{latest.invalidation_reason}</p>
          )}
        </div>
      )}
    </section>
  );
}
