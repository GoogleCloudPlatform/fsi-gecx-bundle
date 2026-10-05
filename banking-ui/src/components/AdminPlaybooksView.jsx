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
import { useNavigate } from 'react-router-dom';
import usePlaybookAdministration from '../hooks/usePlaybookAdministration.js';
import { editDiscovery, validationMessages } from '../utils/playbooks.js';

const fields = [
  ['title', 'Title'], ['purpose', 'Purpose'], ['when_to_use', 'When to use'],
  ['when_not_to_use', 'When not to use'], ['prerequisites', 'Prerequisites'],
  ['input_guidance', 'Input guidance'], ['examples', 'Examples'],
];
const inputStyle = 'w-full border border-slate-300 dark:border-slate-600 rounded-lg p-2 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 disabled:bg-slate-100 dark:disabled:bg-slate-800';
const buttonStyle = 'rounded-lg border border-slate-300 dark:border-slate-600 px-3 py-2 text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-100 dark:hover:bg-slate-800';

export default function AdminPlaybooksView() {
  const state = usePlaybookAdministration();
  const navigate = useNavigate();
  const [operation, setOperation] = useState('');
  const [newId, setNewId] = useState('');
  const [newAction, setNewAction] = useState('');
  const [comparisonBases, setComparisonBases] = useState({});
  const { catalog, capabilities, selected, document, editable, dirty, busy, error, notice, validation, comparison, head, actions } = state;
  const chosen = capabilities.find((capability) => capability.operation === operation);
  const canSave = editable && dirty && state.advancedText === null && !busy;
  const comparisonBase = comparisonBases[selected?.id] ?? head?.published_revision ?? head?.revisions[0]?.revision;
  const displayRevision = (playbook) => playbook.published_revision ?? playbook.revisions.at(-1)?.revision;

  function create(event) {
    event.preventDefault();
    if (dirty && !window.confirm('Discard unsaved playbook changes?')) return;
    const next = structuredClone(chosen.template);
    next.id = newId.trim(); next.action_type = newAction.trim(); next.revision = 1;
    actions.create(next);
  }

  return <section className="pt-24 pb-16 px-6 max-w-7xl mx-auto text-left text-slate-900 dark:text-slate-100">
    <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
      <div><h1 className="text-3xl font-semibold">Playbook administration</h1><p className="mt-2 text-slate-500">Manage versioned definitions for banking action proposals.</p></div>
      <div className="flex gap-2">
        <button className={buttonStyle} disabled={busy} onClick={() => { if (!dirty || window.confirm('Discard unsaved playbook changes?')) navigate('/admin'); }}>Back to administration</button>
        <button className={buttonStyle} disabled={busy} onClick={actions.reload}>Reload</button>
      </div>
    </div>
    {error && <div role="alert" className="mb-4 p-4 rounded-lg bg-red-50 text-red-800">{error}</div>}
    {notice && <div role="status" className="mb-4 p-4 rounded-lg bg-emerald-50 text-emerald-800">{notice}</div>}
    {busy && <p role="status" className="mb-3">Working…</p>}
    <div className="grid lg:grid-cols-[280px_1fr] gap-6">
      <aside className="space-y-6">
        <div className="border rounded-xl p-4"><h2 className="font-semibold mb-3">Playbooks</h2>
          {!busy && !catalog.length && <p className="text-sm text-slate-500">No playbooks available.</p>}
          <ul className="space-y-2">{catalog.map((playbook) => <li key={playbook.id}>
            <button className={`${buttonStyle} w-full text-left ${selected?.id === playbook.id ? 'bg-blue-50 dark:bg-blue-950' : ''}`} disabled={busy} onClick={() => actions.select(playbook.id, displayRevision(playbook))}>
              <span className="block break-words">{playbook.id}</span><span className="text-xs text-slate-500">{playbook.published_revision ? `Published revision ${playbook.published_revision}` : 'Unpublished'}</span>
            </button>
          </li>)}</ul>
        </div>
        <form onSubmit={create} className="border rounded-xl p-4 space-y-3">
          <h2 className="font-semibold">Create a playbook</h2><p className="text-xs text-slate-500">Use a registered banking operation. Eligibility and execution remain bank-owned.</p>
          <label className="block text-sm">Operation<select required aria-label="Operation" className={inputStyle} disabled={busy || !capabilities.length} value={operation} onChange={(event) => setOperation(event.target.value)}>
            <option value="">Choose an operation</option>{capabilities.map((capability) => <option key={capability.operation} value={capability.operation}>{capability.operation}</option>)}
          </select></label>
          <label className="block text-sm">Playbook ID<input required maxLength={128} aria-label="Playbook ID" className={inputStyle} disabled={busy} value={newId} onChange={(event) => setNewId(event.target.value)} /></label>
          <label className="block text-sm">Action type<input required maxLength={64} aria-label="Action type" className={inputStyle} disabled={busy} value={newAction} onChange={(event) => setNewAction(event.target.value)} /></label>
          <button type="submit" className={buttonStyle} disabled={busy || state.accessDenied || !chosen || !newId.trim() || !newAction.trim()}>Create draft</button>
        </form>
      </aside>
      <main className="border rounded-xl p-5 min-w-0">
        {!selected ? <p>Select a playbook to view its definition and revision history.</p> : <>
          <div className="flex flex-wrap justify-between gap-3 mb-5">
            <div><h2 className="text-xl font-semibold break-words">{selected.id}</h2><p className="text-sm">Revision {selected.revision} · {selected.status}{dirty ? ' · Unsaved changes' : ''}</p></div>
            <label className="text-sm">Revision history<select aria-label="Revision history" className={inputStyle} disabled={busy} value={selected.revision} onChange={(event) => actions.select(selected.id, Number(event.target.value))}>
              {head?.revisions.map((revision) => <option key={revision.revision} value={revision.revision}>{revision.revision} · {revision.status}{revision.revision === head.published_revision ? ' · Current' : ''}</option>)}
            </select></label>
          </div>
          <dl className="text-sm space-y-1 mb-5 break-all">
            <div><dt className="inline font-semibold">Operation: </dt><dd className="inline">{document.operation}</dd></div>
            <div><dt className="inline font-semibold">Action: </dt><dd className="inline">{document.action_type} · {document.contract_version}</dd></div>
            <div><dt className="inline font-semibold">Digest: </dt><dd className="inline">{selected.digest || 'Assigned on publication'}</dd></div>
            <div><dt className="inline font-semibold">Updated by: </dt><dd className="inline">{selected.updated_by || selected.created_by} · {selected.updated_at}</dd></div>
          </dl>
          {selected.status === 'PUBLISHED' && <p className="p-3 mb-4 rounded bg-blue-50 dark:bg-blue-950 text-sm">Published definitions are immutable. Clone a revision to edit a draft.</p>}
          <div className="grid md:grid-cols-2 gap-4">
            {fields.map(([field, label]) => { const value = document.discovery?.[field] ?? ''; const isList = Array.isArray(value); return <label key={field} className={`block text-sm ${field === 'purpose' || field === 'input_guidance' ? 'md:col-span-2' : ''}`}>
              <span className="font-medium">{label}</span>{isList && <span className="text-xs text-slate-500"> · One item per line</span>}
              <textarea aria-label={label} rows={field === 'title' ? 2 : 4} className={inputStyle} disabled={!editable || busy || state.advancedText !== null} value={isList ? value.join('\n') : value} onChange={(event) => state.edit(editDiscovery(document, field, event.target.value))} />
            </label>; })}
          </div>
          <details className="mt-5 border rounded-lg p-3"><summary className="cursor-pointer font-medium">Advanced configuration</summary>
            <p className="text-sm my-2 text-slate-500">The server validates operation bindings, required facts, and authorization policy. Identity and revision stay fixed when editing a draft.</p>
            <textarea aria-label="Advanced configuration JSON" rows={16} className={`${inputStyle} font-mono text-xs`} disabled={!editable || busy} value={state.advancedText ?? JSON.stringify(document, null, 2)} onChange={(event) => state.editAdvanced(event.target.value)} />
            {editable && <button className={`${buttonStyle} mt-2`} disabled={busy || state.advancedText === null} onClick={state.applyAdvanced}>Apply configuration</button>}
          </details>
          <div className="flex flex-wrap gap-2 mt-5">
            <button className={buttonStyle} disabled={busy || dirty || state.accessDenied} onClick={actions.clone}>Clone revision to draft</button>
            {editable && <>
              <button className={buttonStyle} disabled={!canSave} onClick={actions.save}>Save draft</button>
              <button className={buttonStyle} disabled={busy || dirty} onClick={actions.validate}>Validate draft</button>
              <button className={`${buttonStyle} bg-emerald-600 text-white hover:bg-emerald-700`} disabled={busy || dirty || !validation?.valid} onClick={actions.publish}>Publish revision</button>
            </>}
          </div>
          {head?.revisions.length > 1 && <div className="flex flex-wrap gap-2 items-end mt-4">
            <label className="text-sm">Compare from revision<select aria-label="Compare from revision" className={inputStyle} value={comparisonBase} disabled={busy} onChange={(event) => setComparisonBases({ ...comparisonBases, [selected.id]: Number(event.target.value) })}>
              {head.revisions.map((revision) => <option key={revision.revision} value={revision.revision}>{revision.revision} · {revision.status}</option>)}
            </select></label>
            <button className={buttonStyle} disabled={busy || dirty || comparisonBase === selected.revision || state.accessDenied} onClick={() => actions.compare(comparisonBase)}>Compare revisions</button>
          </div>}
          {validation && <div role="status" className="mt-4 p-3 rounded bg-slate-100 dark:bg-slate-800">
            <p>{validation.valid ? 'Draft is valid and ready to publish.' : 'Draft is invalid. Correct the following issues:'}</p>
            <ul className="list-disc pl-5">{validationMessages(validation.errors).map((message, index) => <li key={index}>{message}</li>)}</ul>
          </div>}
          {comparison && <div className="mt-5"><h3 className="font-semibold">Revision comparison</h3>
            {!comparison.changes.length && <p>No configuration differences.</p>}
            <ul className="space-y-3 mt-2">{comparison.changes.map((change) => <li key={change.path} className="border rounded p-3 text-sm"><p className="font-mono break-all">{change.path}</p>
              <div className="grid md:grid-cols-2 gap-2 mt-2"><pre className="whitespace-pre-wrap break-words bg-red-50 dark:bg-red-950 p-2">Before: {JSON.stringify(change.before, null, 2)}</pre><pre className="whitespace-pre-wrap break-words bg-emerald-50 dark:bg-emerald-950 p-2">After: {JSON.stringify(change.after, null, 2)}</pre></div>
            </li>)}</ul>
          </div>}
        </>}
      </main>
    </div>
  </section>;
}
