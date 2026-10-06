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

export function playbookClient(api) {
  const base = '/admin/playbooks';
  const path = (id) => `${base}/${encodeURIComponent(id)}`;
  const draft = (id, revision) => `${path(id)}/drafts/${revision}`;
  const request = (id, changeRequest) => `${path(id)}/change-requests/${changeRequest}`;
  const data = async (call) => (await call).data;
  const titled = (body, title) => (title ? { ...body, title } : body);
  return {
    list: () => data(api.get(base)),
    capabilities: () => data(api.get(`${base}/capabilities`)),
    policy: () => data(api.get(`${base}/policy`)),
    revision: (id, revision) => data(api.get(`${path(id)}/revisions/${revision}`)),
    history: (id) => data(api.get(`${path(id)}/history`)),
    create: (document, title) => data(api.post(base, titled({ document }, title))),
    clone: (id, source_revision, expected_generation, title) => data(api.post(`${path(id)}/drafts`, titled({ source_revision, expected_generation }, title))),
    restore: (id, revision, expected_generation, title) => data(api.post(`${path(id)}/revisions/${revision}/restore`, titled({ expected_generation }, title))),
    save: (id, revision, document, expected_draft_version) => data(api.put(draft(id, revision), { document, expected_draft_version })),
    validate: (id, revision, expected_draft_version) => data(api.post(`${draft(id, revision)}/validate`, { expected_draft_version })),
    compare: (id, from_revision, to_revision) => data(api.get(`${path(id)}/compare`, { params: { from_revision, to_revision } })),
    publish: (id, revision, expected_draft_version, expected_generation) => data(api.post(`${draft(id, revision)}/publish`, { expected_draft_version, expected_generation })),
    changeRequests: (id) => data(api.get(`${path(id)}/change-requests`)),
    changeRequest: (id, changeRequest) => data(api.get(request(id, changeRequest))),
    updateChangeRequest: (id, changeRequest, expected_version, fields) => data(api.patch(request(id, changeRequest), { expected_version, ...fields })),
    closeChangeRequest: (id, changeRequest) => data(api.post(`${request(id, changeRequest)}/close`)),
    recreateFromHead: (id, changeRequest, expected_draft_version, expected_generation) => data(api.post(`${request(id, changeRequest)}/recreate-from-head`, { expected_draft_version, expected_generation })),
  };
}

export const STALE_PLAYBOOK = 'Playbook changed since you loaded it — review and publish again.';

export function playbookError(error) {
  const status = error.response?.status;
  const detail = error.response?.data?.detail;
  if (status === 401 || status === 403) return 'Administrator access is required. Sign in with an authorized administrator account.';
  if (status === 409 && detail?.code === 'PLAYBOOK_CONFLICT') return `${STALE_PLAYBOOK} Your unsaved edits have been retained.`;
  if (status === 409 && detail?.code === 'BEHIND_HEAD') return `${detail.message}`;
  if (status === 409) return `${detail?.message || 'This playbook changed in another session.'} Reload before continuing; your unsaved edits have been retained.`;
  return detail?.message || (typeof detail === 'string' ? detail : 'The request failed. Please retry or reload the playbook.');
}

export function isStaleConflict(error) {
  return error.response?.status === 409 && error.response?.data?.detail?.code === 'PLAYBOOK_CONFLICT';
}

export function editDiscovery(document, field, value) {
  const lists = new Set(['when_to_use', 'when_not_to_use', 'prerequisites', 'examples']);
  return { ...document, discovery: { ...document.discovery, [field]: lists.has(field) ? value.split('\n') : value } };
}

export function validationMessages(errors = []) {
  return errors.map((error) => typeof error === 'string' ? error : error.message || error.msg || JSON.stringify(error));
}

export function applyConfiguration(text, current) {
  const parsed = JSON.parse(text);
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed) || !parsed.discovery || typeof parsed.discovery !== 'object' || Array.isArray(parsed.discovery)) {
    throw new Error('Configuration must be a definition object with discovery guidance.');
  }
  for (const field of ['id', 'revision', 'action_type', 'contract_version', 'operation']) parsed[field] = current[field];
  return parsed;
}

export const DISCOVERY_FIELDS = [
  ['title', 'Title'], ['purpose', 'Purpose'], ['when_to_use', 'When to use'],
  ['when_not_to_use', 'When not to use'], ['prerequisites', 'Prerequisites'],
  ['input_guidance', 'Input guidance'], ['examples', 'Examples'],
];

const LABELS = new Map([
  ...DISCOVERY_FIELDS.map(([field, label]) => [`/discovery/${field}`, label]),
  ['/discovery', 'Discovery guidance'],
  ['/presentation/template', 'Template'],
  ['/presentation/required_facts', 'Required facts'],
  ['/presentation/display_selection', 'Displayed fields'],
  ['/presentation/public_payload_fields', 'Public payload fields'],
  ['/authorization_policy', 'Authorization policy'],
  ['/schema_version', 'Schema version'],
]);

function unescapePointer(segment) {
  return segment.replace(/~1/g, '/').replace(/~0/g, '~');
}

export function fieldLabel(path) {
  if (LABELS.has(path)) return LABELS.get(path);
  const segments = path.split('/').slice(1).map(unescapePointer);
  if (segments[0] === 'parameters' && segments.length === 2) return segments[1];
  if (segments[0] === 'payload' && segments.length >= 2) return `Payload binding ${segments.slice(1).join('.')}`;
  return segments.join(' › ') || 'Definition';
}

function formatValue(value) {
  if (value === undefined) return '(missing)';
  return typeof value === 'string' ? value : JSON.stringify(value);
}

const isPrimitive = (value) => value === null || ['string', 'number', 'boolean'].includes(typeof value);

/** Human-readable summary of one structural change from the server diff. */
export function describeChange(change) {
  const label = fieldLabel(change.path);
  const { before, after } = change;
  if (change.change_type === 'ADDED') return { path: change.path, label, summary: `Added: ${formatValue(after)}` };
  if (change.change_type === 'REMOVED') return { path: change.path, label, summary: 'Removed' };
  if (Array.isArray(before) && Array.isArray(after) && [...before, ...after].every(isPrimitive)) {
    const added = after.filter((item) => !before.includes(item)).length;
    const removed = before.filter((item) => !after.includes(item)).length;
    const parts = [added && `+${added}`, removed && `−${removed}`].filter(Boolean);
    return { path: change.path, label, summary: parts.length ? parts.join(' ') : 'Reordered' };
  }
  const long = (value) => typeof value === 'string' && (value.length > 60 || value.includes('\n'));
  if (long(before) || long(after) || change.path === '/presentation/template') {
    return { path: change.path, label, summary: `${label} changed` };
  }
  return { path: change.path, label, summary: `${formatValue(before)} → ${formatValue(after)}` };
}

/** The revision number always differs between revisions; it is not a reviewable change. */
export function reviewableChanges(changes = []) {
  return changes.filter((change) => change.path !== '/revision').map(describeChange);
}

function overlaps(left, right) {
  return left === right || left.startsWith(`${right}/`) || right.startsWith(`${left}/`);
}

/**
 * Paths that were changed by publications after this draft's content was derived
 * and that the draft would set to a different value: publishing would revert them.
 */
export function revertedPaths(diffVsHead, upstreamChanges) {
  if (!diffVsHead || !upstreamChanges) return [];
  const upstream = upstreamChanges.changes.map((change) => change.path).filter((path) => path !== '/revision');
  return diffVsHead.changes
    .map((change) => change.path)
    .filter((path) => path !== '/revision' && upstream.some((other) => overlaps(path, other)));
}

export function policyLabel(policy) {
  if (!policy) return { text: 'Policy loading', blocked: false };
  if (policy.publish_mode === 'DIRECT') return { text: 'Direct publish', blocked: false };
  if (policy.publish_mode === 'APPROVALS_NOT_IMPLEMENTED') {
    return { text: `Publishing blocked: ${policy.approvals_required} approval(s) required`, blocked: true };
  }
  return { text: 'Publishing blocked: invalid policy configuration', blocked: true };
}

export function behindLabel(changeRequest) {
  return changeRequest?.behind ? `${changeRequest.behind_by} behind` : null;
}

export function newPlaybookDocument(template, id, actionType) {
  const next = structuredClone(template);
  next.id = id.trim(); next.action_type = actionType.trim(); next.revision = 1;
  return next;
}
