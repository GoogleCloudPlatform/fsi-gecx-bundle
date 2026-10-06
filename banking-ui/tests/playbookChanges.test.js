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
import {
  STALE_PLAYBOOK, behindLabel, describeChange, fieldLabel, isStaleConflict, newPlaybookDocument,
  playbookClient, playbookError, policyLabel, reviewableChanges, revertedPaths,
} from '../src/utils/playbooks.js';

function recordingClient() {
  const requests = [];
  const api = Object.fromEntries(['get', 'put', 'post', 'patch'].map((method) => [method, async (...args) => { requests.push([method, ...args]); return { data: {} }; }]));
  return { requests, client: playbookClient(api) };
}

test('change request client paths are encoded and titles are omitted unless provided', async () => {
  const { requests, client } = recordingClient();
  await client.policy();
  await client.history('wallet/new');
  await client.changeRequests('wallet/new');
  await client.changeRequest('wallet/new', 4);
  await client.updateChangeRequest('wallet/new', 4, 2, { title: 'Better title' });
  await client.closeChangeRequest('wallet/new', 4);
  await client.recreateFromHead('wallet/new', 4, 3, 9);
  await client.restore('wallet/new', 2, 9);
  await client.restore('wallet/new', 2, 9, 'Roll back');
  await client.clone('wallet/new', 2, 7, 'Tune guidance');
  await client.create({ id: 'x' });
  await client.create({ id: 'x' }, 'Create x');
  assert.deepEqual(requests, [
    ['get', '/admin/playbooks/policy'],
    ['get', '/admin/playbooks/wallet%2Fnew/history'],
    ['get', '/admin/playbooks/wallet%2Fnew/change-requests'],
    ['get', '/admin/playbooks/wallet%2Fnew/change-requests/4'],
    ['patch', '/admin/playbooks/wallet%2Fnew/change-requests/4', { expected_version: 2, title: 'Better title' }],
    ['post', '/admin/playbooks/wallet%2Fnew/change-requests/4/close'],
    ['post', '/admin/playbooks/wallet%2Fnew/change-requests/4/recreate-from-head', { expected_draft_version: 3, expected_generation: 9 }],
    ['post', '/admin/playbooks/wallet%2Fnew/revisions/2/restore', { expected_generation: 9 }],
    ['post', '/admin/playbooks/wallet%2Fnew/revisions/2/restore', { expected_generation: 9, title: 'Roll back' }],
    ['post', '/admin/playbooks/wallet%2Fnew/drafts', { source_revision: 2, expected_generation: 7, title: 'Tune guidance' }],
    ['post', '/admin/playbooks', { document: { id: 'x' } }],
    ['post', '/admin/playbooks', { document: { id: 'x' }, title: 'Create x' }],
  ]);
});

test('field labels are human readable and unescape JSON pointers', () => {
  assert.equal(fieldLabel('/discovery/when_to_use'), 'When to use');
  assert.equal(fieldLabel('/presentation/template'), 'Template');
  assert.equal(fieldLabel('/parameters/amount'), 'amount');
  assert.equal(fieldLabel('/payload/target/id'), 'Payload binding target.id');
  assert.equal(fieldLabel('/custom/a~1b/c~0d'), 'custom › a/b › c~d');
  assert.equal(fieldLabel(''), 'Definition');
});

test('describeChange summarises lists, scalars, long text, additions and removals', () => {
  assert.equal(describeChange({ path: '/discovery/when_to_use', change_type: 'CHANGED', before: ['a', 'b'], after: ['b', 'c', 'd'] }).summary, '+2 −1');
  assert.equal(describeChange({ path: '/discovery/examples', change_type: 'CHANGED', before: ['a', 'b'], after: ['b', 'a'] }).summary, 'Reordered');
  assert.equal(describeChange({ path: '/authorization_policy/step_up', change_type: 'CHANGED', before: false, after: true }).summary, 'false → true');
  assert.equal(describeChange({ path: '/presentation/template', change_type: 'CHANGED', before: 'a', after: 'b' }).summary, 'Template changed');
  assert.equal(describeChange({ path: '/discovery/purpose', change_type: 'CHANGED', before: 'x'.repeat(61), after: 'y' }).summary, 'Purpose changed');
  assert.equal(describeChange({ path: '/discovery/title', change_type: 'ADDED', after: 'New' }).summary, 'Added: New');
  const removed = describeChange({ path: '/discovery/title', change_type: 'REMOVED', before: 'Old' });
  assert.deepEqual(removed, { path: '/discovery/title', label: 'Title', summary: 'Removed' });
});

test('the revision number is not a reviewable change', () => {
  const rows = reviewableChanges([
    { path: '/revision', change_type: 'CHANGED', before: 2, after: 3 },
    { path: '/discovery/title', change_type: 'CHANGED', before: 'a', after: 'b' },
  ]);
  assert.deepEqual(rows.map((row) => row.path), ['/discovery/title']);
  assert.deepEqual(reviewableChanges(), []);
});

test('revertedPaths flags draft fields that overlap upstream publications, including nested paths', () => {
  const diffVsHead = { changes: [
    { path: '/revision' }, { path: '/discovery/title' }, { path: '/presentation' }, { path: '/discovery/examples' },
  ] };
  const upstream = { from_revision: 2, to_revision: 4, changes: [
    { path: '/revision' }, { path: '/discovery/title' }, { path: '/presentation/template' }, { path: '/discovery/purpose' },
  ] };
  assert.deepEqual(revertedPaths(diffVsHead, upstream), ['/discovery/title', '/presentation']);
  assert.deepEqual(revertedPaths({ changes: [{ path: '/discovery/title_extra' }] }, { changes: [{ path: '/discovery/title' }] }), []);
  assert.deepEqual(revertedPaths(null, upstream), []);
  assert.deepEqual(revertedPaths(diffVsHead, null), []);
});

test('policy and behind labels communicate blocked publication', () => {
  assert.deepEqual(policyLabel({ publish_mode: 'DIRECT' }), { text: 'Direct publish', blocked: false });
  assert.equal(policyLabel({ publish_mode: 'APPROVALS_NOT_IMPLEMENTED', approvals_required: 2 }).blocked, true);
  assert.match(policyLabel({ publish_mode: 'APPROVALS_NOT_IMPLEMENTED', approvals_required: 2 }).text, /2 approval/);
  assert.deepEqual(policyLabel({ publish_mode: 'INVALID' }), { text: 'Publishing blocked: invalid policy configuration', blocked: true });
  assert.equal(policyLabel(null).blocked, false);
  assert.equal(behindLabel({ behind: true, behind_by: 2 }), '2 behind');
  assert.equal(behindLabel({ behind: false, behind_by: 0 }), null);
  assert.equal(behindLabel(undefined), null);
});

test('stale generation and behind-head conflicts are distinguished', () => {
  const stale = { response: { status: 409, data: { detail: { code: 'PLAYBOOK_CONFLICT', message: 'Playbook changed.' } } } };
  const behind = { response: { status: 409, data: { detail: { code: 'BEHIND_HEAD', message: 'Start a new change request from the current revision.' } } } };
  assert.equal(isStaleConflict(stale), true);
  assert.equal(isStaleConflict(behind), false);
  assert.equal(isStaleConflict(new Error('x')), false);
  assert.ok(playbookError(stale).startsWith(STALE_PLAYBOOK));
  assert.equal(playbookError(behind), 'Start a new change request from the current revision.');
});

test('new playbook documents copy the operation template without mutating it', () => {
  const template = { id: 'template', action_type: 'T', revision: 7, discovery: { title: 't' } };
  const next = newPlaybookDocument(template, ' wallet ', ' WALLET ');
  assert.deepEqual(next, { id: 'wallet', action_type: 'WALLET', revision: 1, discovery: { title: 't' } });
  assert.equal(template.id, 'template');
  next.discovery.title = 'changed';
  assert.equal(template.discovery.title, 't');
});
