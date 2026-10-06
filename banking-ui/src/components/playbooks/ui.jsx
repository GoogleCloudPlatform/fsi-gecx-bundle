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

const tones = {
  OPEN: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200',
  PUBLISHED: 'bg-violet-100 text-violet-800 dark:bg-violet-950 dark:text-violet-200',
  CLOSED: 'bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
  warning: 'bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200',
  info: 'bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-200',
};

export function Badge({ tone, children }) {
  return <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${tones[tone] || tones.info}`}>{children}</span>;
}

export function Tabs({ label, tabs, active, onChange }) {
  return <div role="tablist" aria-label={label} className="flex flex-wrap gap-1 border-b border-slate-200 dark:border-slate-700 mb-4">
    {tabs.map(([key, text]) => <button key={key} role="tab" type="button" aria-selected={active === key}
      className={`px-3 py-2 text-sm -mb-px border-b-2 ${active === key ? 'border-blue-600 font-semibold' : 'border-transparent text-slate-500 hover:text-slate-900 dark:hover:text-slate-100'}`}
      onClick={() => onChange(key)}>{text}</button>)}
  </div>;
}
