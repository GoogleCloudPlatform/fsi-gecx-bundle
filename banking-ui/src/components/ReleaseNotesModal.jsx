import React, { useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { X } from 'lucide-react';
import { getFormattedBuildTime } from '../utils/releaseNotes.js';
import AnalyticsButton from './AnalyticsButton.jsx';


export function ReleaseNotesModal({ isOpen, onClose, onOpen }) {
  useEffect(() => {
    const version = window.env?.BUILD_VERSION;
    const commitId = window.env?.BUILD_COMMIT_ID;

    if (version && commitId) {
      const storageKey = 'last_seen_release_notes';
      const currentRelease = `${version} (${commitId})`;

      if (localStorage.getItem(storageKey) !== currentRelease) {
        if (onOpen) onOpen();
        localStorage.setItem(storageKey, currentRelease);
      }
    }
  }, [onOpen]);

  const [releaseNotesText, setReleaseNotesText] = useState('');

  useEffect(() => {
    if (isOpen && !releaseNotesText) {
      fetch('/release-notes.md')
        .then(res => res.text())
        .then(text => setReleaseNotesText(text))
        .catch(err => console.error("Failed to load release notes", err));
    }
  }, [isOpen, releaseNotesText]);

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

  const getProcessedReleaseNotes = () => {
    if (!releaseNotesText) return '';
    return releaseNotesText
      .replace(/\$\{version\}/g, window.env?.BUILD_VERSION || 'unknown')
      .replace(/\$\{commit_id\}/g, window.env?.BUILD_COMMIT_ID || 'unknown')
      .replace(/\$\{build_time\}/g, getFormattedBuildTime());
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[200] bg-black/50 backdrop-blur-sm flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white dark:bg-slate-900 rounded-3xl p-6 border border-slate-200 dark:border-slate-800 w-full max-w-3xl md:min-w-[800px] shadow-2xl animate-fade-in relative text-left flex flex-col max-h-[90dvh]" onClick={(e) => e.stopPropagation()}>
        <AnalyticsButton trackingName="button_click_release_notes_modal_01"
          onClick={onClose}
          className="absolute top-4 right-4 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors"
        >
          <X className="w-5 h-5" />
        </AnalyticsButton>
        <h2 className="text-xl font-bold text-slate-900 dark:text-white flex items-center gap-2.5 shrink-0 mb-4">
          <img src="/favicon.svg" alt="Nova Horizon" className="w-6 h-6" />
          <span>Release Notes: {window.env?.BUILD_VERSION || 'unknown'} ({window.env?.BUILD_COMMIT_ID || 'unknown'})</span>
        </h2>

        <div className="flex-1 overflow-y-auto pr-2 text-slate-600 dark:text-slate-400 text-sm leading-relaxed text-left">
        {releaseNotesText ? (
          /* eslint-disable no-unused-vars */
          <ReactMarkdown
            components={{
              h1: ({ _node, ...props }) => <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-200 mt-6 mb-4" {...props} />,
              h2: ({ _node, ...props }) => <h2 className="text-xl font-bold text-slate-800 dark:text-slate-200 mt-5 mb-3" {...props} />,
              h3: ({ _node, ...props }) => <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-200 mt-4 mb-2" {...props} />,
              p: ({ _node, ...props }) => <p className="mb-4 text-slate-600 dark:text-slate-400 leading-relaxed" {...props} />,
              ul: ({ _node, ...props }) => <ul className="list-disc pl-5 mb-4 space-y-1" {...props} />,
              ol: ({ _node, ...props }) => <ol className="list-decimal pl-5 mb-4 space-y-1" {...props} />,
              li: ({ _node, ...props }) => <li className="text-slate-600 dark:text-slate-400" {...props} />,
              blockquote: ({ _node, ...props }) => <blockquote className="border-l-4 border-emerald-500 pl-4 py-1 mb-4 italic text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-800/50 rounded-r" {...props} />,
              code: ({ _node, inline, ...props }) =>
                inline ? (
                  <code className="bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 rounded text-emerald-600 dark:text-emerald-400 text-xs font-mono" {...props} />
                ) : (
                  <pre className="bg-slate-900 text-slate-200 p-4 rounded-lg overflow-x-auto mb-4 text-xs font-mono">
                    <code {...props} />
                  </pre>
                ),
              strong: ({ _node, ...props }) => <strong className="font-semibold text-slate-800 dark:text-slate-200" {...props} />,
              a: ({ _node, ...props }) => <a className="text-emerald-500 hover:text-emerald-600 hover:underline" {...props} />
            }}
          >
            {getProcessedReleaseNotes()}
          </ReactMarkdown>
          /* eslint-enable no-unused-vars */
        ) : (
          <p>No release notes available for this build.</p>
        )}
        </div>

        <div className="mt-6 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 shrink-0">
          <div>
            <span className="text-[11px] text-slate-400 dark:text-slate-500">Build Time: {getFormattedBuildTime()}</span>
          </div>
          <AnalyticsButton trackingName="button_click_release_notes_modal_02"
            onClick={onClose}
            className="w-full sm:w-auto whitespace-nowrap px-5 py-2.5 rounded-full bg-emerald-500 hover:bg-emerald-600 text-white font-semibold text-sm transition-colors cursor-pointer"
          >
            Got it
          </AnalyticsButton>
        </div>
      </div>
    </div>
  );
}

export default ReleaseNotesModal;
