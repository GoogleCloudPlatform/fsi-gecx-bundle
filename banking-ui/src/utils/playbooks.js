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
  const data = async (request) => (await request).data;
  return {
    list: () => data(api.get(base)),
    capabilities: () => data(api.get(`${base}/capabilities`)),
    revision: (id, revision) => data(api.get(`${path(id)}/revisions/${revision}`)),
    create: (document) => data(api.post(base, { document })),
    clone: (id, source_revision, expected_generation) => data(api.post(`${path(id)}/drafts`, { source_revision, expected_generation })),
    save: (id, revision, document, expected_draft_version) => data(api.put(draft(id, revision), { document, expected_draft_version })),
    validate: (id, revision, expected_draft_version) => data(api.post(`${draft(id, revision)}/validate`, { expected_draft_version })),
    compare: (id, from_revision, to_revision) => data(api.get(`${path(id)}/compare`, { params: { from_revision, to_revision } })),
    publish: (id, revision, expected_draft_version, expected_generation) => data(api.post(`${draft(id, revision)}/publish`, { expected_draft_version, expected_generation })),
  };
}

export function playbookError(error) {
  const status = error.response?.status;
  const detail = error.response?.data?.detail;
  if (status === 401 || status === 403) return 'Administrator access is required. Sign in with an authorized administrator account.';
  if (status === 409) return `${detail?.message || 'This playbook changed in another session.'} Reload before continuing; your unsaved edits have been retained.`;
  return detail?.message || (typeof detail === 'string' ? detail : 'The request failed. Please retry or reload the playbook.');
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
