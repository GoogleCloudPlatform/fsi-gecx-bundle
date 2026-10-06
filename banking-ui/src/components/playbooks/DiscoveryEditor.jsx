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

import React from 'react';
import { DISCOVERY_FIELDS, editDiscovery } from '../../utils/playbooks.js';
import { buttonStyle, inputStyle } from './styles.js';

/** Structured discovery-guidance form plus advanced JSON for an editable draft. */
export default function DiscoveryEditor({ state, canSave }) {
  const { document, editable, busy } = state;
  const locked = !editable || busy;
  return <div>
    <div className="grid md:grid-cols-2 gap-4">
      {DISCOVERY_FIELDS.map(([field, label]) => { const value = document.discovery?.[field] ?? ''; const isList = Array.isArray(value); return <label key={field} className={`block text-sm ${field === 'purpose' || field === 'input_guidance' ? 'md:col-span-2' : ''}`}>
        <span className="font-medium">{label}</span>{isList && <span className="text-xs text-slate-500"> · One item per line</span>}
        <textarea aria-label={label} rows={field === 'title' ? 2 : 4} className={inputStyle} disabled={locked || state.advancedText !== null} value={isList ? value.join('\n') : value} onChange={(event) => state.edit(editDiscovery(document, field, event.target.value))} />
      </label>; })}
    </div>
    <details className="mt-5 border rounded-lg p-3"><summary className="cursor-pointer font-medium">Advanced configuration</summary>
      <p className="text-sm my-2 text-slate-500">The server validates operation bindings, required facts, and authorization policy. Identity and revision stay fixed when editing a draft.</p>
      <textarea aria-label="Advanced configuration JSON" rows={16} className={`${inputStyle} font-mono text-xs`} disabled={locked} value={state.advancedText ?? JSON.stringify(document, null, 2)} onChange={(event) => state.editAdvanced(event.target.value)} />
      {editable && <button className={`${buttonStyle} mt-2`} disabled={busy || state.advancedText === null} onClick={state.applyAdvanced}>Apply configuration</button>}
    </details>
    {editable && <button className={`${buttonStyle} mt-4`} disabled={!canSave} onClick={state.actions.save}>Save draft</button>}
  </div>;
}
