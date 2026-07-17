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
import { ExternalLink } from 'lucide-react';
import AnalyticsButton from './AnalyticsButton.jsx';
import { getConsoleViewerGroupUrl } from '../utils/consoleAccess.js';

function ConsoleAccessStep({ analyticsId, compact = false }) {
  const consoleViewerUrl = getConsoleViewerGroupUrl();

  if (!consoleViewerUrl) return null;

  return (
    <div className={`rounded-2xl border border-blue-200/80 bg-blue-50/70 text-left dark:border-blue-900/40 dark:bg-blue-950/20 ${compact ? 'p-4' : 'p-5'}`}>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-wider text-blue-600 dark:text-blue-400">
            Optional step 2
          </p>
          <h3 className="mt-1 text-sm font-bold text-slate-900 dark:text-white">
            Enable Google Cloud console access
          </h3>
          <p className="mt-1 max-w-2xl text-xs leading-relaxed text-slate-600 dark:text-slate-400">
            Self-join the demo console viewer group to explore the provisioned services. Already a member? Skip this step—there is no need to join again.
          </p>
          <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-500">
            Resetting or removing your banking demo accounts does not remove your console access.
          </p>
        </div>
        <AnalyticsButton
          analyticsId={analyticsId}
          type="button"
          onClick={() => window.open(consoleViewerUrl, '_blank', 'noopener,noreferrer')}
          className="flex w-full shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-xl border border-blue-200 bg-white px-4 py-2.5 text-xs font-bold text-blue-700 shadow-sm transition-colors hover:bg-blue-100/70 dark:border-blue-800 dark:bg-blue-950/30 dark:text-blue-300 dark:hover:bg-blue-900/40 sm:w-auto"
        >
          <span>Join or manage access</span>
          <ExternalLink className="h-3.5 w-3.5" />
        </AnalyticsButton>
      </div>
    </div>
  );
}

export default ConsoleAccessStep;
