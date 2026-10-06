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
import { policyLabel, validationMessages } from '../../utils/playbooks.js';
import { buttonStyle, primaryButtonStyle } from './styles.js';

/** Checks, policy and the Publish/Close actions for one change request. */
export default function ChecksPanel({ state }) {
  const { detail, validation, dirty, busy, policy, actions } = state;
  const changeRequest = detail.change_request;
  const open = changeRequest.status === 'OPEN';
  const blocked = policyLabel(policy).blocked;
  const publishable = open && !dirty && !busy && validation?.valid && !changeRequest.behind && !blocked;
  return <aside className="space-y-4">
    <div className="border rounded-xl p-4">
      <h3 className="font-semibold mb-2">Checks</h3>
      {!open && <p className="text-sm text-slate-500">Checks run only on open change requests.</p>}
      {open && dirty && <p className="text-sm text-slate-500">Save the draft to re-run checks.</p>}
      {open && !dirty && validation && <div role="status" className="text-sm">
        <p className={validation.valid ? 'text-emerald-700 dark:text-emerald-300' : 'text-red-700 dark:text-red-300'}>{validation.valid ? '✓ Server validation passed' : '✗ Server validation failed'}</p>
        <ul className="list-disc pl-5 mt-1">{validationMessages(validation.errors).map((message, index) => <li key={index}>{message}</li>)}</ul>
      </div>}
      {open && <button className={`${buttonStyle} mt-3`} disabled={busy || dirty} onClick={actions.validate}>Re-run checks</button>}
    </div>
    <div className="border rounded-xl p-4 space-y-2">
      <h3 className="font-semibold">Publication</h3>
      <p className="text-xs text-slate-500">Policy: {policyLabel(policy).text}. Configured by deployment, not editable here.</p>
      {changeRequest.behind && <p className="text-xs text-amber-800 dark:text-amber-200">Publishing is blocked while this change request is behind the published revision.</p>}
      {open && <div className="flex flex-wrap gap-2">
        <button className={primaryButtonStyle} disabled={!publishable} onClick={actions.publish}>Publish</button>
        <button className={buttonStyle} disabled={busy || dirty} onClick={actions.close}>Close change request</button>
      </div>}
    </div>
  </aside>;
}
