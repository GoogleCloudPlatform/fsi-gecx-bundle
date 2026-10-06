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
import ChangesView from './ChangesView.jsx';
import { buttonStyle, inputStyle, shortDigest } from './styles.js';
import { Badge } from './ui.jsx';

/** Published revision history with comparison and restore-as-change-request. */
export default function HistoryTab({ state }) {
  const { history, busy, dirty, accessDenied, comparison, actions } = state;
  const newest = history[0]?.revision;
  const [selection, setSelection] = useState({});
  const from = selection.from ?? history[1]?.revision ?? newest;
  const to = selection.to ?? newest;

  if (!history.length) return <p className="text-sm text-slate-500">Nothing has been published yet.</p>;

  const options = history.map((entry) => <option key={entry.revision} value={entry.revision}>Revision {entry.revision}{entry.current ? ' (current)' : ''}</option>);
  return <div>
    <ol className="space-y-2 mb-6">{history.map((entry) => <li key={entry.revision} className="border rounded-lg p-3 text-sm flex flex-wrap items-center justify-between gap-2">
      <div>
        <p className="flex flex-wrap items-center gap-2"><span className="font-semibold">Revision {entry.revision}</span>{entry.current && <Badge tone="PUBLISHED">Current</Badge>}<code className="text-xs">{shortDigest(entry.digest)}</code></p>
        <p className="text-xs text-slate-500 mt-1">
          Published {entry.published_at} by {entry.published_by}
          {entry.base_revision ? ` · based on revision ${entry.base_revision}` : ''}
          {entry.change_request && ` · change request #${entry.change_request.id} ${entry.change_request.title}`}
        </p>
      </div>
      {!entry.current && <button type="button" className={buttonStyle} disabled={busy || dirty || accessDenied} onClick={() => actions.restore(entry.revision)}>Restore as change request</button>}
    </li>)}</ol>
    {history.length > 1 && <div className="border rounded-xl p-4">
      <h3 className="font-semibold mb-2">Compare revisions</h3>
      <div className="flex flex-wrap items-end gap-2 mb-3">
        <label className="text-sm">From<select aria-label="Compare from revision" className={inputStyle} value={from} disabled={busy} onChange={(event) => setSelection({ ...selection, from: Number(event.target.value) })}>{options}</select></label>
        <label className="text-sm">To<select aria-label="Compare to revision" className={inputStyle} value={to} disabled={busy} onChange={(event) => setSelection({ ...selection, to: Number(event.target.value) })}>{options}</select></label>
        <button type="button" className={buttonStyle} disabled={busy || from === to || accessDenied} onClick={() => actions.compare(from, to)}>Compare</button>
        {comparison && <button type="button" className={buttonStyle} onClick={actions.clearComparison}>Clear</button>}
      </div>
      {comparison && <>
        <p className="text-sm mb-2">Changes from revision {comparison.fromRevision} to revision {comparison.toRevision}:</p>
        <ChangesView diff={comparison} />
      </>}
    </div>}
  </div>;
}
