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

import React, { useState } from 'react';
import { behindLabel, fieldLabel, lostUpdateNotice } from '../../utils/playbooks.js';
import ChangesView from './ChangesView.jsx';
import ChecksPanel from './ChecksPanel.jsx';
import DefinitionView from './DefinitionView.jsx';
import DiscoveryEditor from './DiscoveryEditor.jsx';
import { buttonStyle, inputStyle, shortDigest } from './styles.js';
import { Badge, Tabs } from './ui.jsx';

function DetailsForm({ changeRequest, busy, onSave, onCancel }) {
  const [title, setTitle] = useState(changeRequest.title);
  const [description, setDescription] = useState(changeRequest.description ?? '');
  function submit(event) {
    event.preventDefault();
    onSave({ title: title.trim(), description });
  }
  return <form onSubmit={submit} className="space-y-2 mb-4">
    <label className="block text-sm">Title<input required maxLength={200} aria-label="Change request title" className={inputStyle} value={title} disabled={busy} onChange={(event) => setTitle(event.target.value)} /></label>
    <label className="block text-sm">Description<textarea maxLength={4000} rows={3} aria-label="Change request description" className={inputStyle} value={description} disabled={busy} onChange={(event) => setDescription(event.target.value)} /></label>
    <div className="flex gap-2"><button type="submit" className={buttonStyle} disabled={busy || !title.trim()}>Save details</button><button type="button" className={buttonStyle} onClick={onCancel}>Cancel</button></div>
  </form>;
}

/** One change request: header, behind/revert warnings, editor, diffs and checks. */
export default function ChangeRequestDetail({ state, canSave }) {
  const { detail, busy, dirty, editable, accessDenied, actions } = state;
  const [tab, setTab] = useState(editable ? 'edit' : 'changes');
  const [against, setAgainst] = useState('base');
  const [editingDetails, setEditingDetails] = useState(false);
  const changeRequest = detail.change_request;
  const open = changeRequest.status === 'OPEN';
  const notice = lostUpdateNotice(detail);
  const diff = against === 'head' ? detail.diff_vs_head : detail.diff_vs_base;
  const tabs = [[open ? 'edit' : 'definition', open ? 'Edit' : 'Definition'], ['changes', 'Changes']];
  const activeTab = tabs.some(([key]) => key === tab) ? tab : tabs[0][0];

  async function saveDetails(fields) {
    if (await actions.updateDetails(fields)) setEditingDetails(false);
  }

  return <div>
    <button type="button" className={`${buttonStyle} mb-4`} onClick={actions.leaveChangeRequest}>← All change requests</button>
    <header className="mb-4">
      {editingDetails ? <DetailsForm changeRequest={changeRequest} busy={busy} onSave={saveDetails} onCancel={() => setEditingDetails(false)} /> : <>
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-lg font-semibold break-words">#{changeRequest.id} {changeRequest.title}</h3>
          <Badge tone={changeRequest.status}>{changeRequest.status}</Badge>
          {behindLabel(changeRequest) && <Badge tone="warning">{behindLabel(changeRequest)}</Badge>}
          {dirty && <Badge tone="warning">Unsaved changes</Badge>}
          {open && !accessDenied && <button type="button" className={buttonStyle} disabled={busy} onClick={() => setEditingDetails(true)}>Edit details</button>}
        </div>
        {changeRequest.description && <p className="text-sm mt-2 whitespace-pre-wrap">{changeRequest.description}</p>}
      </>}
      <p className="text-xs text-slate-500 mt-2">
        {changeRequest.base_revision ? `Revision ${changeRequest.base_revision}` : 'New playbook'} → draft revision {changeRequest.revision}
        {' '}· origin {changeRequest.origin.toLowerCase()} · opened by {changeRequest.opened_by}
        {' '}· last edited by {changeRequest.updated_by} · current published revision {detail.head.published_revision ?? 'none'} ({shortDigest(detail.head.digest)})
        {changeRequest.status === 'PUBLISHED' && ` · published as revision ${changeRequest.published_revision}`}
        {changeRequest.status === 'CLOSED' && ` · closed by ${changeRequest.closed_by}`}
      </p>
    </header>

    {open && changeRequest.behind && <div role="alert" className="mb-4 p-3 rounded-lg bg-amber-50 dark:bg-amber-950 text-amber-900 dark:text-amber-100 text-sm">
      <p>Revision {detail.head.published_revision} was published after this change request was opened from {changeRequest.base_revision ? `revision ${changeRequest.base_revision}` : 'an unpublished playbook'}. It cannot be published as is.</p>
      <p className="mt-1">Start a new change request from the current revision. Your saved draft content is copied onto it and this change request is closed. Review the changes before publishing: your draft will replace anything that changed in the meantime.</p>
      <button type="button" className={`${buttonStyle} mt-2`} disabled={busy || dirty || accessDenied} onClick={actions.recreateFromHead}>Start new change request from current</button>
      {dirty && <p className="text-xs mt-1">Save or discard your edits first.</p>}
    </div>}

    {notice && <div role="alert" className="mb-4 p-3 rounded-lg bg-amber-50 dark:bg-amber-950 text-amber-900 dark:text-amber-100 text-sm">
      <p className="font-medium">{notice.text}</p>
      {notice.kind === 'revert' && <ul className="list-disc pl-5 mt-1">{notice.paths.map((path) => <li key={path}>{fieldLabel(path)}</li>)}</ul>}
      <p className="mt-1">{notice.kind === 'legacy' ? 'This draft was created before change requests recorded where it started. Compare against the current revision before publishing.' : 'Compare against the current revision to review these fields before publishing.'}</p>
    </div>}

    <div className="grid xl:grid-cols-[1fr_280px] gap-6">
      <div className="min-w-0">
        <Tabs label="Change request views" tabs={tabs} active={activeTab} onChange={setTab} />
        {activeTab === 'edit' && <DiscoveryEditor state={state} canSave={canSave} />}
        {activeTab === 'definition' && <DefinitionView document={detail.draft.document} />}
        {activeTab === 'changes' && <div>
          {dirty && <p className="text-xs text-slate-500 mb-2">Changes reflect the saved draft. Save to include your current edits.</p>}
          <div role="group" aria-label="Compare draft against" className="flex flex-wrap gap-2 mb-3">
            <button type="button" aria-pressed={against === 'base'} className={`${buttonStyle} ${against === 'base' ? 'bg-blue-50 dark:bg-blue-950' : ''}`} onClick={() => setAgainst('base')}>Against base{changeRequest.base_revision ? ` (revision ${changeRequest.base_revision})` : ''}</button>
            <button type="button" aria-pressed={against === 'head'} className={`${buttonStyle} ${against === 'head' ? 'bg-blue-50 dark:bg-blue-950' : ''}`} onClick={() => setAgainst('head')}>Against current{detail.head.published_revision ? ` (revision ${detail.head.published_revision})` : ''}</button>
          </div>
          {diff ? <ChangesView key={against} diff={diff} /> : <p className="text-sm text-slate-500">{against === 'head' ? 'Nothing is published yet.' : 'This change request creates a new playbook; there is no base revision.'}</p>}
        </div>}
      </div>
      <ChecksPanel state={state} />
    </div>
  </div>;
}
