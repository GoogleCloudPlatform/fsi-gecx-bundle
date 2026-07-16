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

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useLocation } from 'react-router-dom';
import { Search, MessageSquare, RotateCcw, ExternalLink } from 'lucide-react';

import { findAnswer, performSearch } from '../utils/api.js';
import GoogleCloudIcon from './icons/GoogleCloudIcon.jsx';
import AnalyticsButton from './AnalyticsButton.jsx';
import GcpInfoModal from './GcpInfoModal.jsx';

function SearchView() {
  const location = useLocation();
  const initialQuery = location.state?.initialQuery || "";
  const projectId = window.firebaseConfig?.projectId;

  const [searchQuery, setSearchQuery] = useState(initialQuery);
  const [followupQuery, setFollowupQuery] = useState("");
  const [chatHistory, setChatHistory] = useState([]);
  const [sessionId, setSessionId] = useState(null);
  const [queryId, setQueryId] = useState(null);
  const [isSearchLoading, setIsSearchLoading] = useState(false);
  const [relatedQuestions, setRelatedQuestions] = useState([]);
  const [searchResults, setSearchResults] = useState([]);
  const [isInfoModalOpen, setIsInfoModalOpen] = useState(false);
  const hasTriggeredRef = useRef(false);

  const getLocalDocLink = (link) => {
    if (!link) return "";
    try {
      if (link.startsWith("http://") || link.startsWith("https://")) {
        const urlObj = new URL(link);
        return `${window.location.origin}${urlObj.pathname}${urlObj.search}`;
      }
      return link;
    } catch {
      return link;
    }
  };

  const handleConversationSubmit = useCallback(async (queryText) => {
    if (!queryText.trim()) return;

    setChatHistory(prev => [...prev, { role: 'user', text: queryText }]);
    setIsSearchLoading(true);

    if (chatHistory.length === 0) {
      setSearchQuery("");
    } else {
      setFollowupQuery("");
    }

    const answersPromise = findAnswer({
      query: queryText,
      query_id: queryId,
      session: sessionId
    });

    const searchPromise = performSearch({
      query: queryText
    });

    try {
      const [answersData, searchData] = await Promise.all([answersPromise, searchPromise]);

      setChatHistory(prev => [...prev, { role: 'bot', text: answersData.answer }]);
      setSessionId(answersData.session);
      setQueryId(answersData.queryId);
      setRelatedQuestions(answersData.relatedQuestions || []);
      setSearchResults(searchData.results || []);
    } catch (err) {
      console.error("Error fetching search or answers:", err);
      setChatHistory(prev => [...prev, { role: 'bot', text: "Sorry, I'm having trouble retrieving answers. Please try again later." }]);
    } finally {
      setIsSearchLoading(false);
    }
  }, [chatHistory, queryId, sessionId]);

  useEffect(() => {
    if (initialQuery && !hasTriggeredRef.current) {
      hasTriggeredRef.current = true;
      handleConversationSubmit(initialQuery);
    }
  }, [initialQuery, handleConversationSubmit]);

  const handleNewChat = () => {
    setChatHistory([]);
    setSessionId(null);
    setQueryId(null);
    setRelatedQuestions([]);
    setSearchResults([]);
    setSearchQuery("");
    setFollowupQuery("");
    hasTriggeredRef.current = false;
  };



  return (
    <div className="max-w-7xl mx-auto pt-28 pb-6 px-6 h-[calc(100vh-112px)] flex flex-col animate-fade-in w-full">
      <div className="w-full text-center space-y-2 mb-4 shrink-0 relative">
        <h1 className="text-3xl font-bold tracking-tight text-slate-900 dark:text-white">Site Search Assistant</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">Conversational site search backed by generative answers and matching documents.</p>
        <AnalyticsButton trackingName="button_click_search_view_01"
          onClick={() => setIsInfoModalOpen(true)}
          className="absolute right-0 top-1/2 -translate-y-1/2 p-2.5 rounded-2xl hover:bg-slate-100 dark:hover:bg-slate-800 transition-all active:scale-95 cursor-pointer flex items-center justify-center border border-slate-200/60 dark:border-slate-800/60 bg-white dark:bg-slate-900 shadow-sm"
          title="GCP App Integration Info"
        >
          <GoogleCloudIcon className="w-5 h-5" />
        </AnalyticsButton>
      </div>

      <div className="w-full grid grid-cols-1 md:grid-cols-5 gap-8 bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-3xl p-6 shadow-2xl flex-1 min-h-0">
        {/* Left column: Conversational Q&A */}
        <div className="md:col-span-3 flex flex-col gap-4 md:border-r md:border-slate-100 dark:md:border-slate-850 md:pr-8 h-full min-h-0">
          <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-2 shrink-0">
            <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">Search Assistant</span>
            {chatHistory.length > 0 && (
              <AnalyticsButton trackingName="button_click_search_view_02" 
                onClick={handleNewChat}
                className="text-[10px] text-emerald-500 hover:text-emerald-600 dark:hover:text-emerald-400 font-bold flex items-center gap-1 cursor-pointer transition-all hover:scale-105"
              >
                <RotateCcw className="w-3 h-3" />
                <span>New Chat</span>
              </AnalyticsButton>
            )}
          </div>
          {/* Main/Initial Search Input */}
          {chatHistory.length === 0 && (
            <div className="relative">
              <Search className="absolute left-4 top-3.5 w-5 h-5 text-slate-400" />
              <input
                type="text"
                placeholder="What are you looking for?"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && searchQuery.trim()) {
                    handleConversationSubmit(searchQuery);
                  }
                }}
                className="w-full pl-12 pr-4 py-3 rounded-2xl bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-emerald-500/30 text-sm"
                disabled={isSearchLoading}
              />
            </div>
          )}

          {/* Conversation Logs */}
          {chatHistory.length > 0 && (
            <div className="space-y-4 overflow-y-auto pr-2 scrollbar-thin flex-1 min-h-0 flex flex-col">
              {chatHistory.map((msg, idx) => (
                <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[80%] px-4 py-3 rounded-2xl leading-relaxed text-sm shadow-sm ${msg.role === 'user'
                      ? 'bg-emerald-500 text-white rounded-tr-none'
                      : 'bg-slate-100 dark:bg-slate-900 text-slate-800 dark:text-slate-200 rounded-tl-none border border-slate-200/50 dark:border-slate-800/50'
                    }`}>
                    {msg.text}
                  </div>
                </div>
              ))}
              {isSearchLoading && (
                <div className="flex justify-start">
                  <div className="bg-slate-100 dark:bg-slate-900 px-4 py-2.5 rounded-2xl rounded-tl-none border border-slate-200/50 dark:border-slate-800/50 flex items-center gap-1.5 shadow-sm">
                    <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce"></span>
                    <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce [animation-delay:0.2s]"></span>
                    <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce [animation-delay:0.4s]"></span>
                  </div>
                </div>
              )}

              {/* Related Questions Suggestions */}
              {!isSearchLoading && relatedQuestions.length > 0 && (
                <div className="flex flex-wrap gap-2 pt-2 justify-start w-full">
                  {relatedQuestions.map((q, qIdx) => (
                    <AnalyticsButton trackingName="button_click_search_view_03"
                      key={qIdx}
                      onClick={() => handleConversationSubmit(q)}
                      className="px-3 py-1.5 rounded-full border border-slate-200 dark:border-slate-800 text-xs text-slate-600 dark:text-slate-400 bg-slate-50 dark:bg-slate-900/50 hover:bg-slate-100 dark:hover:bg-slate-900 hover:text-slate-900 dark:hover:text-white transition-all cursor-pointer font-medium shadow-sm"
                    >
                      {q}
                    </AnalyticsButton>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Follow-up input triggers */}
          {chatHistory.length > 0 && (
            <div className="relative border-t border-slate-100 dark:border-slate-900 pt-4 shrink-0">
              <MessageSquare className="absolute left-4 top-7 w-4 h-4 text-slate-400" />
              <input
                type="text"
                placeholder="Ask a follow-up question..."
                value={followupQuery}
                onChange={(e) => setFollowupQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && followupQuery.trim()) {
                    handleConversationSubmit(followupQuery);
                  }
                }}
                className="w-full pl-12 pr-4 py-2.5 rounded-xl bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-emerald-500/30 text-xs"
                disabled={isSearchLoading}
              />
            </div>
          )}
        </div>

        {/* Right column: Raw Search Results Cards */}
        <div className="md:col-span-2 flex flex-col gap-4 h-full min-h-0">
          <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-2 shrink-0">
            <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">Search Results</span>
            <span className="text-[10px] text-slate-500 font-semibold">{searchResults.length} results</span>
          </div>

          {searchResults.length > 0 ? (
            <div className="space-y-4 overflow-y-auto pr-1 scrollbar-thin flex-1 min-h-0">
              {searchResults.map((item) => (
                <div
                  key={item.id}
                  className="bg-slate-50 dark:bg-slate-900/40 border border-slate-200/60 dark:border-slate-800/60 rounded-2xl p-4 hover:border-slate-300 dark:hover:border-slate-700 transition-all shadow-sm flex flex-col gap-2 group text-left"
                >
                  <h3 className="text-xs font-bold text-slate-800 dark:text-slate-200 group-hover:text-emerald-500 transition-colors">
                    {item.title}
                  </h3>
                  <p 
                    className="text-[11px] text-slate-500 dark:text-slate-400 leading-relaxed line-clamp-3"
                    dangerouslySetInnerHTML={{ __html: item.snippets && item.snippets.length > 0 ? item.snippets[0] : "No snippet description available." }}
                  />
                  {item.link && (
                    <a
                      href={getLocalDocLink(item.link)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-[10px] text-emerald-500 hover:text-emerald-600 hover:underline font-semibold flex items-center gap-1 mt-1 cursor-pointer w-fit"
                    >
                      <span>View document</span>
                      <span>&rarr;</span>
                    </a>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center border border-dashed border-slate-200 dark:border-slate-800 rounded-2xl text-slate-400 dark:text-slate-600 gap-2 flex-1">
              <Search className="w-6 h-6 opacity-30 animate-pulse" />
              <span className="text-[10px] font-medium">No document matches yet</span>
            </div>
          )}
        </div>
      </div>

      <GcpInfoModal
        isOpen={isInfoModalOpen}
        onClose={() => setIsInfoModalOpen(false)}
      >
        <div className="space-y-4 text-slate-600 dark:text-slate-400 text-sm leading-relaxed">
          <p>
            This search assistant is powered by <strong>Google Cloud Platform's Generative AI App Builder</strong> (Vertex AI Search).
          </p>
          <p>
            You can inspect the underlying configuration, engines, and ingested datastores directly in the Google Cloud Console using the links below:
          </p>
          <div className="bg-slate-50 dark:bg-slate-950 p-4 rounded-2xl border border-slate-100 dark:border-slate-800 space-y-3">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h4 className="font-semibold text-slate-800 dark:text-slate-200 text-xs uppercase tracking-wider">AI Application Engine</h4>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">Manage search and conversational agent flow settings.</p>
              </div>
              <a
                href={`https://console.cloud.google.com/gen-app-builder/engines?project=${projectId}`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-emerald-500 hover:text-emerald-600 font-semibold text-xs shrink-0 hover:underline"
              >
                <span>View Engine</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            </div>
            <hr className="border-slate-100 dark:border-slate-800" />
            <div className="flex items-start justify-between gap-4">
              <div>
                <h4 className="font-semibold text-slate-800 dark:text-slate-200 text-xs uppercase tracking-wider">Vertex AI Datastore</h4>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">Explore structured and unstructured document sources.</p>
              </div>
              <a
                href={`https://console.cloud.google.com/gen-app-builder/data-stores?project=${projectId}`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-emerald-500 hover:text-emerald-600 font-semibold text-xs shrink-0 hover:underline"
              >
                <span>View Datastores</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            </div>
            <hr className="border-slate-100 dark:border-slate-800" />
            <div className="flex items-start justify-between gap-4">
              <div>
                <h4 className="font-semibold text-slate-800 dark:text-slate-200 text-xs uppercase tracking-wider">Documentation</h4>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">Learn about Agent Search, conversational apps, and data integration.</p>
              </div>
              <a
                href="https://docs.cloud.google.com/generative-ai-app-builder/docs"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-emerald-500 hover:text-emerald-600 font-semibold text-xs shrink-0 hover:underline"
              >
                <span>View Docs</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            </div>
          </div>
        </div>
      </GcpInfoModal>
    </div>
  );
}

export default SearchView;
