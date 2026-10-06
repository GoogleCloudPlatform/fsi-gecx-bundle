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
import { reviewableChanges } from '../../utils/playbooks.js';

/** Field-level, human-readable diff with an optional raw JSON view per change. */
export default function ChangesView({ diff, emptyText = 'No configuration differences.' }) {
  const [raw, setRaw] = useState(false);
  if (!diff) return null;
  const rows = reviewableChanges(diff.changes);
  const byPath = Object.fromEntries(diff.changes.map((change) => [change.path, change]));
  return <div>
    <label className="flex items-center gap-2 text-sm mb-3"><input type="checkbox" checked={raw} onChange={(event) => setRaw(event.target.checked)} />Show raw JSON</label>
    {!rows.length && <p className="text-sm">{emptyText}</p>}
    <ul className="space-y-2">{rows.map((row) => <li key={row.path} className="border rounded-lg p-3 text-sm">
      <p><span className="font-medium">{row.label}:</span> {row.summary}</p>
      {raw && <div className="grid md:grid-cols-2 gap-2 mt-2">
        <pre className="whitespace-pre-wrap break-words bg-red-50 dark:bg-red-950 p-2 text-xs">Before ({row.path}): {JSON.stringify(byPath[row.path].before, null, 2)}</pre>
        <pre className="whitespace-pre-wrap break-words bg-emerald-50 dark:bg-emerald-950 p-2 text-xs">After: {JSON.stringify(byPath[row.path].after, null, 2)}</pre>
      </div>}
    </li>)}</ul>
  </div>;
}
