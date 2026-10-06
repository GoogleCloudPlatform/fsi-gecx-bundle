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

import React, { useEffect, useRef } from 'react';
import { buttonStyle } from './styles.js';

export default function LeaveDialog({ blocker }) {
  const previousFocus = useRef(window.document.activeElement);
  const stayButton = useRef(null);
  useEffect(() => {
    stayButton.current?.focus();
    const original = previousFocus.current;
    return () => { if (original?.isConnected) original.focus(); };
  }, []);
  function keyboard(event) {
    if (event.key === 'Escape') { event.preventDefault(); blocker.reset(); }
    if (event.key === 'Tab') {
      const buttons = [...event.currentTarget.querySelectorAll('button')];
      const next = event.shiftKey ? buttons.at(-1) : buttons[0];
      const edge = event.shiftKey ? buttons[0] : buttons.at(-1);
      if (window.document.activeElement === edge) { event.preventDefault(); next.focus(); }
    }
  }
  return <div className="fixed inset-0 z-[100] bg-slate-900/50 flex items-center justify-center p-6">
    <div role="alertdialog" aria-modal="true" aria-labelledby="playbook-leave-title" aria-describedby="playbook-leave-description" onKeyDown={keyboard} className="bg-white dark:bg-slate-900 rounded-xl shadow-xl p-6 max-w-md">
      <h2 id="playbook-leave-title" className="text-xl font-semibold">Discard unsaved changes?</h2>
      <p id="playbook-leave-description" className="my-4">Your playbook draft has unsaved edits. Stay to save them, or discard them and leave this page.</p>
      <div className="flex gap-3"><button ref={stayButton} className={buttonStyle} onClick={() => blocker.reset()}>Stay on page</button><button className={buttonStyle} onClick={() => blocker.proceed()}>Discard and leave</button></div>
    </div>
  </div>;
}
