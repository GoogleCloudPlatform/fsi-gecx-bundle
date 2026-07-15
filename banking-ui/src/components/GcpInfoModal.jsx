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

import React, { useRef, useState, useEffect } from 'react';
import { X } from 'lucide-react';
import GoogleCloudIcon from './icons/GoogleCloudIcon.jsx';

export function GcpInfoModal({ isOpen, onClose, title = "GCP AI Application Integration", maxWidthClass = "max-w-lg", children }) {
  const contentRef = useRef(null);
  const [hasConsoleLink, setHasConsoleLink] = useState(false);

  useEffect(() => {
    if (isOpen && contentRef.current) {
      const links = contentRef.current.querySelectorAll('a');
      let found = false;
      for (const link of Array.from(links)) {
        if (link.hostname === 'console.cloud.google.com' || link.hostname === 'ces.cloud.google.com') {
          found = true;
          break;
        }
      }
      setHasConsoleLink(found);
    }
  }, [isOpen, children]);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown);
    }
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, onClose]);

  const consoleViewerUrl = window.env?.CONSOLE_VIEWER_GROUP_JOIN_URL || import.meta.env.VITE_CONSOLE_VIEWER_GROUP_JOIN_URL;

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[200] bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
      <div className={`bg-white dark:bg-slate-900 rounded-3xl p-6 border border-slate-200 dark:border-slate-800 ${maxWidthClass} w-full shadow-2xl animate-fade-in relative text-left flex flex-col max-h-[90vh]`}>
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors"
        >
          <X className="w-5 h-5" />
        </button>
        <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-4 flex items-center gap-2.5 shrink-0">
          <GoogleCloudIcon className="w-6 h-6" />
          <span>{title}</span>
        </h2>
        
        <div className="flex-1 overflow-y-auto pr-1" ref={contentRef}>
          {children}
        </div>

        <div className="mt-6 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 shrink-0">
          <div>
            {hasConsoleLink && consoleViewerUrl && (
              <p className="text-sm text-slate-500 dark:text-slate-400">
                GCP console access viewer <a href={consoleViewerUrl} target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:text-blue-600 underline">self join</a>.
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="w-full sm:w-auto whitespace-nowrap px-5 py-2.5 rounded-full bg-emerald-500 hover:bg-emerald-600 text-white font-semibold text-sm transition-colors cursor-pointer"
          >
            Got it
          </button>
        </div>
      </div>
    </div>
  );
}

export default GcpInfoModal;
