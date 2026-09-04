/**
 * Copyright 2026 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     https://www.apache.org/licenses/LICENSE-2.0
 */

import assert from 'node:assert/strict';
import test from 'node:test';

import {
  applyRuntimeProposalStatus,
  latestProposalSignature,
  proposalActionLabel,
  proposalLifecycleSteps,
} from '../src/utils/proposalTrace.js';

test('proposal action labels are presenter friendly', () => {
  assert.equal(proposalActionLabel('TRIAGE_FRAUD_CASE'), 'Fraud remediation');
  assert.equal(proposalActionLabel('PROVISION_GOOGLE_WALLET'), 'Google Wallet provisioning');
});

test('proposal lifecycle reflects protected evidence and terminal state', () => {
  const steps = proposalLifecycleSteps({
    status: 'COMMITTED',
    presentation_verified: true,
    confirmation_verified: true,
    commit_started: true,
  });
  assert.deepEqual(steps.map(step => step.complete), [true, true, true, true, true]);
  assert.equal(steps[4].label, 'COMMITTED');
});

test('latest signature changes for a new proposal or lifecycle status', () => {
  assert.equal(latestProposalSignature([{ proposal_ref: 'proposal_a', status: 'PROPOSED' }]), 'proposal_a:PROPOSED');
  assert.equal(latestProposalSignature([{ proposal_ref: 'proposal_a', status: 'COMMITTED' }]), 'proposal_a:COMMITTED');
  assert.equal(latestProposalSignature([]), '');
});

test('runtime checkpoints advance a lagging durable proposal view', () => {
  const proposal = applyRuntimeProposalStatus({
    proposal_ref: 'proposal:a',
    status: 'PROPOSED',
    presentation_verified: false,
    confirmation_verified: false,
    commit_started: false,
  }, 'CONFIRMED');

  assert.equal(proposal.status, 'CONFIRMED');
  assert.equal(proposal.presentation_verified, true);
  assert.equal(proposal.confirmation_verified, true);
  assert.equal(proposal.commit_started, false);
});

test('runtime checkpoints never roll back durable terminal state', () => {
  const proposal = { proposal_ref: 'proposal:a', status: 'COMMITTED' };
  assert.equal(applyRuntimeProposalStatus(proposal, 'PRESENTED'), proposal);
});
