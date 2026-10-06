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
import { DISCOVERY_FIELDS } from '../../utils/playbooks.js';

function Value({ value }) {
  if (Array.isArray(value)) {
    return value.length ? <ul className="list-disc pl-5 space-y-1">{value.map((item, index) => <li key={index}>{typeof item === 'string' ? item : JSON.stringify(item)}</li>)}</ul> : <span className="text-slate-500">None</span>;
  }
  if (value && typeof value === 'object') return <code className="text-xs break-all">{JSON.stringify(value)}</code>;
  if (value === null || value === undefined || value === '') return <span className="text-slate-500">None</span>;
  return <span className="whitespace-pre-wrap">{String(value)}</span>;
}

function Section({ title, children }) {
  return <section className="mb-6"><h3 className="font-semibold mb-2">{title}</h3>{children}</section>;
}

/** Read-only rendering of a playbook definition (no disabled form controls). */
export default function DefinitionView({ document }) {
  const presentation = document.presentation || {};
  return <div className="text-sm">
    <Section title="Discovery guidance">
      <dl className="grid md:grid-cols-[180px_1fr] gap-x-4 gap-y-3">
        {DISCOVERY_FIELDS.map(([field, label]) => <React.Fragment key={field}><dt className="font-medium text-slate-600 dark:text-slate-300">{label}</dt><dd><Value value={document.discovery?.[field]} /></dd></React.Fragment>)}
      </dl>
    </Section>
    <Section title="Configuration">
      <dl className="grid md:grid-cols-[180px_1fr] gap-x-4 gap-y-3">
        <dt className="font-medium text-slate-600 dark:text-slate-300">Parameters</dt><dd><Value value={document.parameters} /></dd>
        <dt className="font-medium text-slate-600 dark:text-slate-300">Authorization policy</dt><dd><Value value={document.authorization_policy} /></dd>
        <dt className="font-medium text-slate-600 dark:text-slate-300">Required facts</dt><dd><Value value={presentation.required_facts} /></dd>
        <dt className="font-medium text-slate-600 dark:text-slate-300">Displayed fields</dt><dd><Value value={presentation.display_selection} /></dd>
        <dt className="font-medium text-slate-600 dark:text-slate-300">Template</dt><dd><Value value={presentation.template} /></dd>
      </dl>
    </Section>
  </div>;
}
