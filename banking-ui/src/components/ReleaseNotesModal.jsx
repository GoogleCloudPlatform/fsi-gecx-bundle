import React, { useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import GcpInfoModal from './GcpInfoModal.jsx';
import { getFormattedBuildTime } from '../utils/formatters.js';

export const hasReleaseNotes = () => !!window.env?.RELEASE_NOTES?.trim();

export function ReleaseNotesModal({ isOpen, onClose, onOpen }) {
  useEffect(() => {
    const version = window.env?.BUILD_VERSION;
    const commitId = window.env?.BUILD_COMMIT_ID;
    const releaseNotes = window.env?.RELEASE_NOTES;

    if (version && commitId && releaseNotes) {
      const storageKey = 'last_seen_release_notes';
      const currentRelease = `${version} (${commitId})`;

      if (localStorage.getItem(storageKey) !== currentRelease) {
        if (onOpen) onOpen();
        localStorage.setItem(storageKey, currentRelease);
      }
    }
  }, [onOpen]);

  const getProcessedReleaseNotes = () => {
    if (!window.env?.RELEASE_NOTES) return '';
    return window.env.RELEASE_NOTES
      .replace(/\$\{version\}/g, window.env?.BUILD_VERSION || 'unknown')
      .replace(/\$\{commit_id\}/g, window.env?.BUILD_COMMIT_ID || 'unknown')
      .replace(/\$\{build_time\}/g, getFormattedBuildTime());
  };

  return (
    <GcpInfoModal
      isOpen={isOpen}
      onClose={onClose}
      title={`${window.env?.BUILD_VERSION || 'unknown'} (${window.env?.BUILD_COMMIT_ID || 'unknown'})`}
      maxWidthClass="max-w-2xl"
      titleClassName="mb-1"
    >
      <div className="text-slate-600 dark:text-slate-400 text-sm leading-relaxed text-left max-h-[60vh] overflow-y-auto pr-2">
        <div className="text-[11px] text-slate-400 dark:text-slate-500 mb-4 flex items-center gap-1.5 border-b border-slate-100 dark:border-slate-800 pb-3">
          <span>Build Time: {getFormattedBuildTime()}</span>
        </div>
        {window.env?.RELEASE_NOTES ? (
          <ReactMarkdown
            components={{
              h1: ({ node, ...props }) => <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-200 mt-6 mb-4" {...props} />,
              h2: ({ node, ...props }) => <h2 className="text-xl font-bold text-slate-800 dark:text-slate-200 mt-5 mb-3" {...props} />,
              h3: ({ node, ...props }) => <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-200 mt-4 mb-2" {...props} />,
              p: ({ node, ...props }) => <p className="mb-4 text-slate-600 dark:text-slate-400 leading-relaxed" {...props} />,
              ul: ({ node, ...props }) => <ul className="list-disc pl-5 mb-4 space-y-1" {...props} />,
              ol: ({ node, ...props }) => <ol className="list-decimal pl-5 mb-4 space-y-1" {...props} />,
              li: ({ node, ...props }) => <li className="text-slate-600 dark:text-slate-400" {...props} />,
              blockquote: ({ node, ...props }) => <blockquote className="border-l-4 border-emerald-500 pl-4 py-1 mb-4 italic text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-800/50 rounded-r" {...props} />,
              code: ({ node, inline, ...props }) =>
                inline ? (
                  <code className="bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 rounded text-emerald-600 dark:text-emerald-400 text-xs font-mono" {...props} />
                ) : (
                  <pre className="bg-slate-900 text-slate-200 p-4 rounded-lg overflow-x-auto mb-4 text-xs font-mono">
                    <code {...props} />
                  </pre>
                ),
              strong: ({ node, ...props }) => <strong className="font-semibold text-slate-800 dark:text-slate-200" {...props} />,
              a: ({ node, ...props }) => <a className="text-emerald-500 hover:text-emerald-600 hover:underline" {...props} />
            }}
          >
            {getProcessedReleaseNotes()}
          </ReactMarkdown>
        ) : (
          <p>No release notes available for this build.</p>
        )}
      </div>
    </GcpInfoModal>
  );
}

export default ReleaseNotesModal;
