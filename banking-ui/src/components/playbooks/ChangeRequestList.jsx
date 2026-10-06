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
import { behindLabel } from '../../utils/playbooks.js';
import { buttonStyle, inputStyle } from './styles.js';
import { Badge } from './ui.jsx';

const FILTERS = [['OPEN', 'Open'], ['PUBLISHED', 'Published'], ['CLOSED', 'Closed'], ['ALL', 'All']];

/** Change requests for one playbook with a status filter and a "new change request" form. */
export default function ChangeRequestList({ state }) {
  const { changeRequests, busy, accessDenied, dirty, actions, head } = state;
  const [filter, setFilter] = useState('OPEN');
  const [title, setTitle] = useState('');
  const visible = changeRequests.filter((item) => filter === 'ALL' || item.status === filter);
  const count = (status) => changeRequests.filter((item) => status === 'ALL' || item.status === status).length;

  function start(event) {
    event.preventDefault();
    actions.newChangeRequest(title.trim() || undefined);
    setTitle('');
  }

  return <div>
    <form onSubmit={start} className="flex flex-wrap items-end gap-2 mb-4">
      <label className="text-sm grow">New change request title (optional)
        <input aria-label="New change request title" maxLength={200} className={inputStyle} disabled={busy || accessDenied} value={title} onChange={(event) => setTitle(event.target.value)} placeholder={`Update ${head?.id ?? ''}`} />
      </label>
      <button type="submit" className={buttonStyle} disabled={busy || accessDenied || dirty}>New change request</button>
    </form>
    <p className="text-xs text-slate-500 mb-3">A change request copies the current published revision into a draft. Published definitions stay unchanged until it is published.</p>
    <div role="group" aria-label="Filter change requests" className="flex flex-wrap gap-2 mb-3">
      {FILTERS.map(([key, label]) => <button key={key} type="button" aria-pressed={filter === key} className={`${buttonStyle} ${filter === key ? 'bg-blue-50 dark:bg-blue-950' : ''}`} onClick={() => setFilter(key)}>{label} ({count(key)})</button>)}
    </div>
    {!visible.length && <p className="text-sm text-slate-500">No change requests in this view.</p>}
    <ul className="space-y-2">{visible.map((item) => <li key={item.id}>
      <button type="button" className={`${buttonStyle} w-full text-left`} disabled={busy} onClick={() => actions.openChangeRequest(item.id)}>
        <span className="flex flex-wrap items-center gap-2">
          <span className="font-semibold break-words">#{item.id} {item.title}</span>
          <Badge tone={item.status}>{item.status}</Badge>
          {behindLabel(item) && <Badge tone="warning">{behindLabel(item)}</Badge>}
        </span>
        <span className="block text-xs text-slate-500 mt-1">
          Draft revision {item.revision} · based on {item.base_revision ? `revision ${item.base_revision}` : 'nothing (new playbook)'} · opened by {item.opened_by}
          {item.status === 'PUBLISHED' && ` · published as revision ${item.published_revision}`}
          {item.status === 'CLOSED' && item.closed_by && ` · closed by ${item.closed_by}`}
        </span>
      </button>
    </li>)}</ul>
  </div>;
}
