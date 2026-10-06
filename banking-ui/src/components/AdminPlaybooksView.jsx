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
import { policyLabel } from '../utils/playbooks.js';
import ChangeRequestDetail from './playbooks/ChangeRequestDetail.jsx';
import ChangeRequestList from './playbooks/ChangeRequestList.jsx';
import DefinitionView from './playbooks/DefinitionView.jsx';
import HistoryTab from './playbooks/HistoryTab.jsx';
import LeaveDialog from './playbooks/LeaveDialog.jsx';
import OperationContract from './playbooks/OperationContract.jsx';
import OperationsTab from './playbooks/OperationsTab.jsx';
import { buttonStyle, shortDigest } from './playbooks/styles.js';
import { Badge, Tabs } from './playbooks/ui.jsx';

function Overview({ state }) {
  const { head, published, changeRequests } = state;
  const open = changeRequests.filter((item) => item.status === 'OPEN').length;
  return <div>
    <p className="text-sm mb-4">{open ? `${open} open change request(s).` : 'No open change requests.'} Agents use only the published revision for new proposals.</p>
    {head.published_revision && published
      ? <><p className="text-xs text-slate-500 mb-3">Published revision {head.published_revision} · digest {shortDigest(published.digest)} · published {published.published_at} by {published.updated_by}</p><DefinitionView document={published.document} /></>
      : <p className="text-sm text-slate-500">This playbook has not been published yet. Publish its change request to make it available to agents.</p>}
  </div>;
}

export default function AdminPlaybooksView() {
  const state = usePlaybookAdministration();
  const navigate = useNavigate();
  const [area, setArea] = useState('playbooks');
  const [playbookTab, setPlaybookTab] = useState('overview');
  const { catalog, capabilities, head, changeRequests, detail, editable, dirty, busy, error, notice, policy, actions } = state;
  const canSave = editable && dirty && state.advancedText === null && !busy;
  const policyState = policyLabel(policy);
  const openCount = changeRequests.filter((item) => item.status === 'OPEN').length;
  // An open change request always lives on the Change requests tab.
  const activeTab = detail ? 'changes' : playbookTab;
  const capability = capabilities.find((item) => item.operation === head?.operation);

  function selectPlaybook(id) {
    if (actions.selectPlaybook(id)) { setPlaybookTab('overview'); setArea('playbooks'); }
  }

  function changeTab(tab) {
    if (detail && tab !== 'changes' && !actions.leaveChangeRequest()) return;
    setPlaybookTab(tab);
  }

  return <section className="pt-24 pb-16 px-6 max-w-7xl mx-auto text-left text-slate-900 dark:text-slate-100">
    {state.blocker.state === 'blocked' && <LeaveDialog blocker={state.blocker} />}
    <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
      <div>
        <h1 className="text-3xl font-semibold">Playbook administration</h1>
        <p className="mt-2 text-slate-500">Propose, review and publish versioned definitions for banking action proposals.</p>
        <p className="mt-2"><Badge tone={policyState.blocked ? 'warning' : 'info'}>{policyState.text}</Badge> <span className="text-xs text-slate-500">Publish policy is set by deployment configuration.</span></p>
      </div>
      <div className="flex gap-2">
        <button className={buttonStyle} disabled={busy} onClick={() => navigate('/admin')}>Back to administration</button>
        <button className={buttonStyle} disabled={busy} onClick={actions.reload}>Reload</button>
      </div>
    </div>
    {error && <div role="alert" className="mb-4 p-4 rounded-lg bg-red-50 text-red-800">{error}</div>}
    {notice && <div role="status" className="mb-4 p-4 rounded-lg bg-emerald-50 text-emerald-800">{notice}</div>}
    {busy && <p role="status" className="mb-3">Working…</p>}
    <Tabs label="Playbook administration areas" tabs={[['playbooks', 'Playbooks'], ['operations', 'Operations']]} active={area} onChange={setArea} />
    {area === 'operations' && <OperationsTab state={state} onOpenPlaybook={selectPlaybook} onCreated={() => setArea('playbooks')} />}
    {area === 'playbooks' && <div className="grid lg:grid-cols-[260px_1fr] gap-6">
      <aside className="border rounded-xl p-4 h-fit">
        <h2 className="font-semibold mb-3">Playbooks</h2>
        {!busy && !catalog.length && <p className="text-sm text-slate-500">No playbooks yet. Create one from the Operations tab.</p>}
        <ul className="space-y-2">{catalog.map((playbook) => <li key={playbook.id}>
          <button className={`${buttonStyle} w-full text-left ${head?.id === playbook.id ? 'bg-blue-50 dark:bg-blue-950' : ''}`} disabled={busy} onClick={() => selectPlaybook(playbook.id)}>
            <span className="block break-words">{playbook.id}</span>
            <span className="text-xs text-slate-500">{playbook.published_revision ? `Revision ${playbook.published_revision}` : 'Unpublished'}{playbook.open_change_requests ? ` · ${playbook.open_change_requests} open` : ''}</span>
          </button>
        </li>)}</ul>
      </aside>
      <main className="border rounded-xl p-5 min-w-0">
        {!head ? <p>Select a playbook to view its definition, change requests and history.</p> : <>
          <div className="mb-4">
            <h2 className="text-xl font-semibold break-words">{head.id}</h2>
            <p className="text-sm text-slate-500">{head.operation} · {head.action_type} · {head.contract_version} · {head.published_revision ? `published revision ${head.published_revision}` : 'unpublished'}</p>
          </div>
          <Tabs label="Playbook views" active={activeTab} onChange={changeTab} tabs={[
            ['overview', 'Overview'], ['changes', `Change requests (${openCount})`], ['history', 'History'], ['contract', 'Operation contract'],
          ]} />
          {activeTab === 'overview' && <Overview state={state} />}
          {activeTab === 'changes' && (detail
            ? <ChangeRequestDetail key={detail.change_request.id} state={state} canSave={canSave} />
            : <ChangeRequestList state={state} />)}
          {activeTab === 'history' && <HistoryTab key={head.id} state={state} />}
          {activeTab === 'contract' && <OperationContract capability={capability} />}
        </>}
      </main>
    </div>}
  </section>;
}
