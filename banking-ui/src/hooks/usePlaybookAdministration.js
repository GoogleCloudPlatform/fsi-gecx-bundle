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

import { useEffect, useRef, useState } from 'react';
import { useBlocker } from 'react-router-dom';
import { playbooksAdmin } from '../utils/api.js';
import { STALE_PLAYBOOK, applyConfiguration, isStaleConflict, newPlaybookDocument, playbookError } from '../utils/playbooks.js';

const DISCARD = 'Discard unsaved playbook changes?';

export default function usePlaybookAdministration() {
  const [catalog, setCatalog] = useState([]);
  const [capabilities, setCapabilities] = useState([]);
  const [policy, setPolicy] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [published, setPublished] = useState(null);
  const [changeRequests, setChangeRequests] = useState([]);
  const [history, setHistory] = useState([]);
  const [detail, setDetail] = useState(null);
  const [document, setDocument] = useState(null);
  const [validation, setValidation] = useState(null);
  const [comparison, setComparison] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [advancedText, setAdvancedText] = useState(null);
  const [accessDenied, setAccessDenied] = useState(false);
  const requestSequence = useRef(0);
  const draft = detail?.draft;
  const editable = detail?.change_request.status === 'OPEN' && !accessDenied;
  const dirty = !!editable && (JSON.stringify(document) !== JSON.stringify(draft.document) || advancedText !== null);
  const head = catalog.find((item) => item.id === selectedId);
  const blocker = useBlocker(dirty);

  useEffect(() => {
    let cancelled = false;
    setBusy(true);
    Promise.all([playbooksAdmin.list(), playbooksAdmin.capabilities(), playbooksAdmin.policy()]).then(([list, supported, effective]) => {
      if (!cancelled) { setCatalog(list.playbooks); setCapabilities(supported.operations); setPolicy(effective); }
    }).catch((failure) => { if (!cancelled) { setError(playbookError(failure)); setAccessDenied([401, 403].includes(failure.response?.status)); } })
      .finally(() => { if (!cancelled) setBusy(false); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!dirty) return;
    const warn = (event) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);

  function installDetail(next) {
    setDetail(next); setDocument(next ? structuredClone(next.draft.document) : null);
    setAdvancedText(null); setValidation(next?.validation ?? null); setComparison(null);
  }

  async function run(action) {
    setBusy(true); setError(''); setNotice('');
    try { await action(); setAccessDenied(false); return true; } catch (failure) { setError(playbookError(failure)); setAccessDenied([401, 403].includes(failure.response?.status)); return false; }
    finally { setBusy(false); }
  }

  async function refreshCatalog() {
    const [list, effective, supported] = await Promise.all([playbooksAdmin.list(), playbooksAdmin.policy(), playbooksAdmin.capabilities()]);
    setCatalog(list.playbooks); setPolicy(effective); setCapabilities(supported.operations);
    return list.playbooks;
  }

  async function loadPlaybook(id, playbooks = catalog) {
    const entry = playbooks.find((item) => item.id === id);
    const [current, requests, log] = await Promise.all([
      entry?.published_revision ? playbooksAdmin.revision(id, entry.published_revision) : null,
      playbooksAdmin.changeRequests(id),
      playbooksAdmin.history(id),
    ]);
    setPublished(current); setChangeRequests(requests.change_requests); setHistory(log.revisions);
  }

  async function openDetail(id, changeRequestId) {
    const sequence = ++requestSequence.current;
    const next = await playbooksAdmin.changeRequest(id, changeRequestId);
    if (sequence === requestSequence.current) installDetail(next);
    return next;
  }

  async function afterAllocation(id, created, message) {
    const playbooks = await refreshCatalog();
    setSelectedId(id);
    await loadPlaybook(id, playbooks);
    await openDetail(id, created.change_request.id);
    setNotice(message);
  }

  const confirmDiscard = () => !dirty || window.confirm(DISCARD);

  const actions = {
    selectPlaybook: (id) => {
      if (!confirmDiscard()) return false;
      requestSequence.current += 1;
      setSelectedId(id); installDetail(null); setPublished(null);
      run(() => loadPlaybook(id));
      return true;
    },
    reload: () => run(async () => {
      if (dirty && !window.confirm('Reload and discard unsaved playbook changes?')) return;
      const playbooks = await refreshCatalog();
      if (selectedId) await loadPlaybook(selectedId, playbooks);
      if (detail) await openDetail(selectedId, detail.change_request.id);
    }),
    openChangeRequest: (changeRequestId) => {
      if (!confirmDiscard()) return;
      run(() => openDetail(selectedId, changeRequestId));
    },
    leaveChangeRequest: () => {
      if (!confirmDiscard()) return false;
      requestSequence.current += 1;
      installDetail(null);
      return true;
    },
    newChangeRequest: (title) => (!confirmDiscard() ? Promise.resolve(false) : run(async () => {
      const [entry] = (await refreshCatalog()).filter((item) => item.id === selectedId);
      const source = entry.published_revision ?? entry.revisions.at(-1).revision;
      const created = await playbooksAdmin.clone(selectedId, source, entry.generation, title);
      await afterAllocation(selectedId, created, 'Change request opened. Published definitions remain unchanged.');
    })),
    createPlaybook: (capability, id, actionType, title) => (!confirmDiscard() ? Promise.resolve(false) : run(async () => {
      const created = await playbooksAdmin.create(newPlaybookDocument(capability.template, id, actionType), title);
      await afterAllocation(created.id, created, 'Playbook draft and change request created.');
    })),
    restore: (revision) => {
      if (!confirmDiscard()) return Promise.resolve(false);
      if (!window.confirm(`Open a change request that restores revision ${revision} on top of the current published revision?`)) return Promise.resolve(false);
      return run(async () => {
        const [entry] = (await refreshCatalog()).filter((item) => item.id === selectedId);
        const created = await playbooksAdmin.restore(selectedId, revision, entry.generation);
        await afterAllocation(selectedId, created, `Restore of revision ${revision} opened as a change request. Review the changes before publishing.`);
      });
    },
    recreateFromHead: () => (!confirmDiscard() ? Promise.resolve(false) : run(async () => {
      const fresh = await openDetail(selectedId, detail.change_request.id);
      const created = await playbooksAdmin.recreateFromHead(selectedId, fresh.change_request.id, fresh.draft.draft_version, fresh.head.generation);
      await afterAllocation(selectedId, created, 'New change request started from the current revision with your draft content. Review the changes; the previous change request was closed.');
    })),
    updateDetails: (fields) => run(async () => {
      await playbooksAdmin.updateChangeRequest(selectedId, detail.change_request.id, detail.change_request.version, fields);
      const requests = await playbooksAdmin.changeRequests(selectedId);
      setChangeRequests(requests.change_requests);
      const next = await playbooksAdmin.changeRequest(selectedId, detail.change_request.id);
      setDetail(next);
    }),
    save: () => run(async () => {
      await playbooksAdmin.save(selectedId, draft.revision, document, draft.draft_version);
      await openDetail(selectedId, detail.change_request.id);
      setNotice('Draft saved. Checks were re-run.');
    }),
    validate: () => run(async () => { setValidation(await playbooksAdmin.validate(selectedId, draft.revision, draft.draft_version)); }),
    publish: () => run(async () => {
      // Generation is shared by every draft allocation; always publish against the latest head.
      const fresh = await openDetail(selectedId, detail.change_request.id);
      if (fresh.change_request.behind) { setError('This change request is behind the published revision. Start a new change request from the current revision.'); return; }
      if (!fresh.validation?.valid) { setError('Checks are failing. Fix the draft before publishing.'); return; }
      if (!window.confirm('Publish this change request for new agent proposals? Existing proposals retain their original revision.')) return;
      try {
        await playbooksAdmin.publish(selectedId, fresh.draft.revision, fresh.draft.draft_version, fresh.head.generation);
      } catch (failure) {
        if (!isStaleConflict(failure)) throw failure;
        const playbooks = await refreshCatalog();
        await loadPlaybook(selectedId, playbooks);
        await openDetail(selectedId, fresh.change_request.id);
        setError(STALE_PLAYBOOK);
        return;
      }
      const playbooks = await refreshCatalog();
      await loadPlaybook(selectedId, playbooks);
      await openDetail(selectedId, fresh.change_request.id);
      setNotice('Change request published. New proposals use this revision.');
    }),
    close: () => run(async () => {
      if (!window.confirm('Close this change request? The draft is kept for the record but can no longer be edited or published.')) return;
      await playbooksAdmin.closeChangeRequest(selectedId, detail.change_request.id);
      const playbooks = await refreshCatalog();
      await loadPlaybook(selectedId, playbooks);
      await openDetail(selectedId, detail.change_request.id);
      setNotice('Change request closed.');
    }),
    compare: (fromRevision, toRevision) => run(async () => {
      setComparison({ fromRevision, toRevision, ...(await playbooksAdmin.compare(selectedId, fromRevision, toRevision)) });
    }),
    clearComparison: () => setComparison(null),
  };

  function edit(next) { setDocument(next); setValidation(null); setAdvancedText(null); }

  return {
    catalog, capabilities, policy, head, published, changeRequests, history, detail, document,
    editable, dirty, busy, error, notice, validation, comparison, actions, edit, advancedText, accessDenied, blocker,
    editAdvanced: (text) => { setAdvancedText(text); setValidation(null); },
    applyAdvanced: () => { try { edit(applyConfiguration(advancedText, draft.document)); setError(''); } catch { setError('Configuration must be a valid JSON definition with discovery guidance.'); } },
  };
}
