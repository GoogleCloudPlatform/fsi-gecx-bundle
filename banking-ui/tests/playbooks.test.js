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

import test from 'node:test';
import assert from 'node:assert/strict';
import { applyConfiguration, editDiscovery, playbookClient, playbookError } from '../src/utils/playbooks.js';

test('authoring sends optimistic versions and only the intended wire fields', async () => {
  const requests = [];
  const api = Object.fromEntries(['get', 'put', 'post'].map((method) => [method, async (...args) => { requests.push([method, ...args]); return { data: {} }; }]));
  const client = playbookClient(api);
  await client.clone('wallet/new', 2, 7);
  await client.save('wallet/new', 3, { discovery: {} }, 4);
  await client.validate('wallet/new', 3, 5);
  await client.publish('wallet/new', 3, 5, 7);
  assert.deepEqual(requests, [
    ['post', '/admin/playbooks/wallet%2Fnew/drafts', { source_revision: 2, expected_generation: 7 }],
    ['put', '/admin/playbooks/wallet%2Fnew/drafts/3', { document: { discovery: {} }, expected_draft_version: 4 }],
    ['post', '/admin/playbooks/wallet%2Fnew/drafts/3/validate', { expected_draft_version: 5 }],
    ['post', '/admin/playbooks/wallet%2Fnew/drafts/3/publish', { expected_draft_version: 5, expected_generation: 7 }],
  ]);
});

test('structured guidance edits leave execution configuration intact', () => {
  const original = { operation: 'registered', discovery: { when_to_use: ['old'], purpose: 'original' } };
  const edited = editDiscovery(original, 'when_to_use', 'first\nsecond');
  assert.deepEqual(edited.discovery.when_to_use, ['first', 'second']);
  assert.equal(edited.operation, 'registered');
  assert.deepEqual(original.discovery.when_to_use, ['old']);
});

test('advanced configuration cannot replace fixed draft identity or execution binding', () => {
  const current = { id: 'a', revision: 3, action_type: 'A', contract_version: 'v1', operation: 'registered' };
  const edited = applyConfiguration(JSON.stringify({ id: 'other', revision: 99, operation: 'unsafe', discovery: { title: 'new' } }), current);
  for (const field of Object.keys(current)) assert.equal(edited[field], current[field]);
  assert.equal(edited.discovery.title, 'new');
  for (const value of ['null', '[]', '{}', '{']) assert.throws(() => applyConfiguration(value, current));
});

test('conflict and access denial have useful messages without leaking raw exceptions', () => {
  assert.match(playbookError({ response: { status: 409, data: { detail: { code: 'CONFLICT', message: 'Draft changed.' } } } }), /Reload.*retained/);
  assert.match(playbookError({ response: { status: 403 } }), /Administrator access/);
  assert.equal(playbookError(new Error('secret provider exception')), 'The request failed. Please retry or reload the playbook.');
});
