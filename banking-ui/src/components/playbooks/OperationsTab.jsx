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
import OperationContract from './OperationContract.jsx';
import { buttonStyle, inputStyle } from './styles.js';

/** Registered banking operations, the playbooks bound to them, and new-playbook creation. */
export default function OperationsTab({ state, onOpenPlaybook, onCreated }) {
  const { capabilities, busy, accessDenied, actions } = state;
  const [operation, setOperation] = useState(capabilities[0]?.operation ?? '');
  const [form, setForm] = useState({ id: '', actionType: '', title: '' });
  const chosen = capabilities.find((capability) => capability.operation === operation) ?? capabilities[0];

  async function create(event) {
    event.preventDefault();
    if (await actions.createPlaybook(chosen, form.id, form.actionType, form.title.trim() || undefined)) {
      setForm({ id: '', actionType: '', title: '' });
      onCreated();
    }
  }

  if (!capabilities.length) return <p className="text-sm text-slate-500">No registered operations are available.</p>;
  return <div className="grid lg:grid-cols-[240px_1fr] gap-6">
    <ul className="space-y-2" aria-label="Registered operations">{capabilities.map((capability) => <li key={capability.operation}>
      <button type="button" aria-pressed={chosen?.operation === capability.operation} className={`${buttonStyle} w-full text-left ${chosen?.operation === capability.operation ? 'bg-blue-50 dark:bg-blue-950' : ''}`} onClick={() => setOperation(capability.operation)}>
        <span className="block break-words">{capability.operation}</span>
        <span className="text-xs text-slate-500">{capability.bound_playbooks.length} playbook(s)</span>
      </button>
    </li>)}</ul>
    {chosen && <div className="min-w-0 space-y-6">
      <section><h3 className="font-semibold mb-2">Contract</h3><OperationContract capability={chosen} /></section>
      <section>
        <h3 className="font-semibold mb-2">Bound playbooks</h3>
        {!chosen.bound_playbooks.length && <p className="text-sm text-slate-500">No playbooks use this operation yet.</p>}
        <ul className="space-y-1">{chosen.bound_playbooks.map((playbook) => <li key={playbook.id}>
          <button type="button" className="text-sm text-blue-700 dark:text-blue-300 underline" disabled={busy} onClick={() => onOpenPlaybook(playbook.id)}>{playbook.id}</button>
          <span className="text-xs text-slate-500"> · {playbook.action_type} · {playbook.published_revision ? `published revision ${playbook.published_revision}` : 'unpublished'}</span>
        </li>)}</ul>
      </section>
      <form onSubmit={create} className="border rounded-xl p-4 space-y-3">
        <h3 className="font-semibold">New playbook from this operation</h3>
        <p className="text-xs text-slate-500">Creates a draft from the operation's template and opens a change request. Eligibility and execution remain bank-owned.</p>
        <label className="block text-sm">Playbook ID<input required maxLength={128} aria-label="Playbook ID" className={inputStyle} disabled={busy} value={form.id} onChange={(event) => setForm({ ...form, id: event.target.value })} /></label>
        <label className="block text-sm">Action type<input required maxLength={64} aria-label="Action type" className={inputStyle} disabled={busy} value={form.actionType} onChange={(event) => setForm({ ...form, actionType: event.target.value })} /></label>
        <label className="block text-sm">Change request title (optional)<input maxLength={200} aria-label="Change request title (optional)" className={inputStyle} disabled={busy} value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} /></label>
        <button type="submit" className={buttonStyle} disabled={busy || accessDenied || !form.id.trim() || !form.actionType.trim()}>Create draft playbook</button>
      </form>
    </div>}
  </div>;
}
