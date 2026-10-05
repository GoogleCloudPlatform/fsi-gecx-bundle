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
import { playbooksAdmin } from '../utils/api.js';
import { applyConfiguration, playbookError } from '../utils/playbooks.js';

export default function usePlaybookAdministration() {
  const [catalog, setCatalog] = useState([]);
  const [capabilities, setCapabilities] = useState([]);
  const [selected, setSelected] = useState(null);
  const [document, setDocument] = useState(null);
  const [validation, setValidation] = useState(null);
  const [comparison, setComparison] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [advancedText, setAdvancedText] = useState(null);
  const [accessDenied, setAccessDenied] = useState(false);
  const requestSequence = useRef(0);
  const dirty = !!selected && (JSON.stringify(document) !== JSON.stringify(selected.document) || advancedText !== null);
  const head = catalog.find((item) => item.id === selected?.id);
  const editable = selected?.status === 'DRAFT' && !accessDenied;

  async function refresh() {
    const result = await playbooksAdmin.list();
    setCatalog(result.playbooks);
  }

  useEffect(() => {
    let cancelled = false;
    setBusy(true);
    Promise.all([playbooksAdmin.list(), playbooksAdmin.capabilities()]).then(([list, supported]) => {
      if (!cancelled) { setCatalog(list.playbooks); setCapabilities(supported.operations); }
    }).catch((failure) => { if (!cancelled) { setError(playbookError(failure)); setAccessDenied([401, 403].includes(failure.response?.status)); } })
      .finally(() => { if (!cancelled) setBusy(false); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!dirty) return;
    const warn = (event) => { event.preventDefault(); event.returnValue = ''; };
    const warnNavigation = (event) => {
      const link = event.target.closest?.('a[href]');
      if (link && link.href !== window.location.href && !window.confirm('Discard unsaved playbook changes?')) { event.preventDefault(); event.stopPropagation(); }
    };
    window.addEventListener('beforeunload', warn);
    window.document.addEventListener('click', warnNavigation, true);
    return () => { window.removeEventListener('beforeunload', warn); window.document.removeEventListener('click', warnNavigation, true); };
  }, [dirty]);

  function install(result) {
    setSelected(result); setDocument(structuredClone(result.document));
    setAdvancedText(null); setValidation(null); setComparison(null);
  }

  async function run(action) {
    setBusy(true); setError(''); setNotice('');
    try { await action(); setAccessDenied(false); } catch (failure) { setError(playbookError(failure)); setValidation(null); setAccessDenied([401, 403].includes(failure.response?.status)); }
    finally { setBusy(false); }
  }

  async function select(id, revision) {
    if (dirty && !window.confirm('Discard unsaved playbook changes?')) return;
    const sequence = ++requestSequence.current;
    await run(async () => {
      const result = await playbooksAdmin.revision(id, revision);
      if (sequence === requestSequence.current) install(result);
    });
  }

  function edit(next) { setDocument(next); setValidation(null); setComparison(null); setAdvancedText(null); }

  const actions = {
    select,
    reload: () => run(async () => {
      if (dirty && !window.confirm('Reload and discard unsaved playbook changes?')) return;
      await refresh();
      if (selected) install(await playbooksAdmin.revision(selected.id, selected.revision));
    }),
    clone: () => run(async () => {
      if (dirty && !window.confirm('Discard unsaved playbook changes?')) return;
      const result = await playbooksAdmin.clone(selected.id, selected.revision, head.generation);
      await refresh(); install(result); setNotice('Draft created. Published definitions remain unchanged.');
    }),
    create: (next) => run(async () => { const result = await playbooksAdmin.create(next); await refresh(); install(result); setNotice('Draft created.'); }),
    save: () => run(async () => {
      const result = await playbooksAdmin.save(selected.id, selected.revision, document, selected.draft_version);
      await refresh(); install(result); setNotice('Draft saved. Validate before publishing.');
    }),
    validate: () => run(async () => { setValidation(await playbooksAdmin.validate(selected.id, selected.revision, selected.draft_version)); }),
    compare: (fromRevision) => run(async () => { setComparison(await playbooksAdmin.compare(selected.id, fromRevision ?? head.published_revision, selected.revision)); }),
    publish: () => run(async () => {
      if (!window.confirm('Publish this validated revision for new agent proposals? Existing proposals retain their original revision.')) return;
      const result = await playbooksAdmin.publish(selected.id, selected.revision, selected.draft_version, head.generation);
      await refresh(); install(result); setNotice('Revision published. New proposals use this revision.');
    }),
  };
  return { catalog, capabilities, selected, document, editable, dirty, busy, error, notice, validation, comparison, head, actions, edit, advancedText, accessDenied,
    editAdvanced: (text) => { setAdvancedText(text); setValidation(null); setComparison(null); },
    applyAdvanced: () => { try { edit(applyConfiguration(advancedText, selected.document)); setError(''); } catch { setError('Configuration must be a valid JSON definition with discovery guidance.'); } },
  };
}
