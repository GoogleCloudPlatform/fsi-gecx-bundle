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

function List({ items }) {
  if (!items?.length) return <span className="text-slate-500">None</span>;
  return <span className="flex flex-wrap gap-1">{items.map((item) => <code key={item} className="text-xs rounded bg-slate-100 dark:bg-slate-800 px-1">{item}</code>)}</span>;
}

function Json({ value }) {
  if (!value || (typeof value === 'object' && !Object.keys(value).length)) return <span className="text-slate-500">None</span>;
  return <pre className="text-xs whitespace-pre-wrap break-words bg-slate-50 dark:bg-slate-900 rounded p-2">{JSON.stringify(value, null, 2)}</pre>;
}

/** Read-only, code-owned contract of a registered banking operation. */
export default function OperationContract({ capability }) {
  if (!capability) return <p className="text-sm text-slate-500">This playbook's operation is not a registered capability.</p>;
  const contract = capability.contract || {};
  return <div className="text-sm">
    <p className="text-xs text-slate-500 mb-3">Operation contracts are defined in code and cannot be changed from this page. Playbooks can only describe and bind to them.</p>
    <dl className="grid md:grid-cols-[180px_1fr] gap-x-4 gap-y-3">
      <dt className="font-medium">Operation</dt><dd><code>{capability.operation}</code></dd>
      <dt className="font-medium">Parameters</dt><dd><Json value={contract.parameters} /></dd>
      <dt className="font-medium">Literal bindings</dt><dd><Json value={contract.literal_bindings} /></dd>
      <dt className="font-medium">Required facts</dt><dd><List items={contract.required_facts} /></dd>
      <dt className="font-medium">Public fields</dt><dd><List items={contract.public_fields} /></dd>
      <dt className="font-medium">Template fields</dt><dd><List items={contract.template_fields} /></dd>
      <dt className="font-medium">Payload fields</dt><dd><List items={contract.payload_fields} /></dd>
    </dl>
  </div>;
}
