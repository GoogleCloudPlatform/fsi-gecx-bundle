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

export const TERMINAL_PROPOSAL_STATUSES = new Set([
  'COMMITTED',
  'DECLINED',
  'INVALIDATED',
  'EXPIRED',
]);

const ACTION_LABELS = {
  TRIAGE_FRAUD_CASE: 'Fraud remediation',
  REISSUE_CARD: 'Card replacement',
  PROVISION_GOOGLE_WALLET: 'Google Wallet provisioning',
};

export function proposalActionLabel(actionType) {
  return ACTION_LABELS[actionType] || String(actionType || 'Banking action')
    .toLowerCase()
    .replaceAll('_', ' ')
    .replace(/^./, value => value.toUpperCase());
}

export function proposalLifecycleSteps(proposal) {
  const status = String(proposal?.status || 'PROPOSED').toUpperCase();
  const terminal = TERMINAL_PROPOSAL_STATUSES.has(status);
  return [
    { label: 'Created', complete: true },
    { label: 'Presented', complete: Boolean(proposal?.presentation_verified) },
    { label: 'Confirmed', complete: Boolean(proposal?.confirmation_verified) },
    { label: 'Commit started', complete: Boolean(proposal?.commit_started) },
    { label: terminal ? status : 'Completed', complete: terminal },
  ];
}

export function latestProposalSignature(proposals) {
  const latest = proposals?.[proposals.length - 1];
  return latest ? `${latest.proposal_ref}:${latest.status}` : '';
}

const STATUS_RANK = {
  PROPOSED: 0,
  PRESENTED: 1,
  CONFIRMED: 2,
  COMMITTING: 3,
  COMMITTED: 4,
  DECLINED: 4,
  INVALIDATED: 4,
  EXPIRED: 4,
};

export function applyRuntimeProposalStatus(proposal, runtimeStatus) {
  const durableStatus = String(proposal?.status || 'PROPOSED').toUpperCase();
  const observedStatus = String(runtimeStatus || '').toUpperCase();
  if (STATUS_RANK[observedStatus] === undefined || STATUS_RANK[observedStatus] <= STATUS_RANK[durableStatus]) {
    return proposal;
  }
  return {
    ...proposal,
    status: observedStatus,
    presentation_verified: STATUS_RANK[observedStatus] >= STATUS_RANK.PRESENTED,
    confirmation_verified: STATUS_RANK[observedStatus] >= STATUS_RANK.CONFIRMED,
    commit_started: STATUS_RANK[observedStatus] >= STATUS_RANK.COMMITTING,
  };
}
