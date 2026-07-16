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

import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { 
  Send, Trash2, Plus, MessageSquare, Shield, 
  AlertCircle, Loader2, Calendar, 
  ArrowLeft, CheckCircle2, Copy, Check, Bug, RefreshCw, ExternalLink
} from 'lucide-react';
import { useSettings } from '../context/SettingsContext.jsx';
import GoogleCloudIcon from './icons/GoogleCloudIcon.jsx';
import GoogleCompassIcon from './icons/GoogleCompassIcon.jsx';
import AnalyticsButton from './AnalyticsButton.jsx';
import GcpInfoModal from './GcpInfoModal.jsx';
import { 
  getMessages, 
  markMessagesRead, 
  createMessage, 
  deleteThread, 
  deleteMessage,
  acknowledgeFraudAlert,
} from '../utils/api.js';



import { Joyride, STATUS, EVENTS, ACTIONS } from 'react-joyride';
import { getJoyrideStyles } from '../utils/joyrideStyles.js';

const CATEGORIES = ['General', 'Billing', 'Loans', 'Security'];

function SecureMessagingView({ fbUser, customerProfile }) {
  const { brandColorFrom, brandColorTo, resolvedTheme } = useSettings();
  const location = useLocation();
  const navigate = useNavigate();

  // Joyride Tour States
  const [tourRun, setTourRun] = useState(false);
  const [tourKey, setTourKey] = useState(0);
  const [domReady, setDomReady] = useState(false);

  useEffect(() => {
    const isCompleted = localStorage.getItem('secure-messaging-tour-completed') === 'true';
    const params = new URLSearchParams(location.search);
    const forceTour = params.get('tour') === 'true';

    if (forceTour || !isCompleted) {
      setTourRun(true);
    } else {
      setTourRun(false);
    }
  }, [location.search]);

  useEffect(() => {
    const checkElement = setInterval(() => {
      if (document.querySelector('#secure-messaging-tour-btn')) {
        setDomReady(true);
        clearInterval(checkElement);
      }
    }, 50);
    return () => clearInterval(checkElement);
  }, []);

  const steps = useMemo(() => {
    return [
      {
        target: '#secure-messaging-tour-btn',
        content: "Welcome to your Secure Messages portal! Here you can communicate directly and securely with bank representatives.",
        placement: 'bottom-end',
        skipBeacon: true
      },
      {
        target: '#compose-message-btn',
        content: "Click New Thread to start a new secure conversation. Select categories like Loans, Security, or Billing to reach the appropriate support team.",
        placement: 'bottom',
        skipBeacon: true
      },
      {
        target: '#threads-list-container',
        content: "Conversations List: View your active and past conversations. Unread messages from support will be highlighted.",
        placement: 'right',
        skipBeacon: true
      },
      {
        target: '#chat-history-pane',
        content: "Message Viewer: View the full history of the active thread, reply to support, and directly resolve alert issues.",
        placement: 'left',
        skipBeacon: true
      }
    ];
  }, []);

  const [messages, setMessages] = useState([]);
  const [threads, setThreads] = useState({});
  const [activeThreadId, setActiveThreadId] = useState(null);
  const [isComposing, setIsComposing] = useState(false);
  const [copiedThreadId, setCopiedThreadId] = useState(false);
  const [copiedQuery, setCopiedQuery] = useState(false);

  // Debug Simulator Modal State
  const [isDebugOpen, setIsDebugOpen] = useState(false);
  const [debugThreadId, setDebugThreadId] = useState('');
  const [debugCategory, setDebugCategory] = useState('General');
  const [debugTitle, setDebugTitle] = useState('');
  const [debugBody, setDebugBody] = useState('');
  const [debugType, setDebugType] = useState('support_message');
  const [isInfoModalOpen, setIsInfoModalOpen] = useState(false);
  const projectId = window.firebaseConfig?.projectId;
  
  // New Message / Thread Form State
  const [newCategory, setNewCategory] = useState('General');
  const [newText, setNewText] = useState('');
  const [replyText, setReplyText] = useState('');
  
  // UI Loading / Feedback State
  const [isLoading, setIsLoading] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [isAcknowledgingFraud, setIsAcknowledgingFraud] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);
  const [successMsg, setSuccessMsg] = useState(null);

  const chatContainerRef = useRef(null);

  const fetchMessages = useCallback(async (silent = false) => {
    if (!silent) setIsLoading(true);
    setErrorMsg(null);
    try {
      const data = await getMessages();
      setMessages(data);
      groupIntoThreads(data);
      window.dispatchEvent(new CustomEvent('refresh-unread-count'));
    } catch (err) {
      console.error('Error fetching messages:', err);
      setErrorMsg('Could not load messages. Please verify your connection.');
    } finally {
      if (!silent) setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (fbUser) {
      fetchMessages();
    }
  }, [fbUser, fetchMessages]);

  useEffect(() => {
    const handlePushNotification = (e) => {
      console.log("Customer received custom push notification event:", e.detail);
      const payload = e.detail;
      const notificationUserId = payload?.data?.user_id;
      const currentUserId = customerProfile?.user_id || fbUser?.uid;
      if (payload?.data?.type === 'support_message' &&
          (!notificationUserId || notificationUserId === currentUserId)) {
        console.log("Support reply received! Silently refreshing secure messages...");
        fetchMessages(true);
      }
    };
    const handleSecureMessageCreated = () => fetchMessages(true);
    window.addEventListener('firebase-push-notification', handlePushNotification);
    window.addEventListener('secure-message-created', handleSecureMessageCreated);
    return () => {
      window.removeEventListener('firebase-push-notification', handlePushNotification);
      window.removeEventListener('secure-message-created', handleSecureMessageCreated);
    };
  }, [fetchMessages, customerProfile, fbUser]);

  useEffect(() => {
    const selectThreadId = location.state?.selectThreadId;
    if (selectThreadId && Object.keys(threads).length > 0) {
      if (threads[selectThreadId]) {
        setActiveThreadId(selectThreadId);
        setIsComposing(false);
        // Clear selectThreadId state so that clicking "View" on future notifications for this thread triggers state updates correctly
        navigate(location.pathname, { replace: true, state: {} });
      }
    }
  }, [threads, location.state, location.pathname, navigate]);

  useEffect(() => {
    if (activeThreadId && threads[activeThreadId]) {
      const activeThread = threads[activeThreadId];
      const unreadMsgIds = activeThread.messages
        .filter((msg) => msg.sender !== 'user' && !msg.is_user_read)
        .map((msg) => msg.message_id);

      if (unreadMsgIds.length > 0) {
        const markRead = async () => {
          try {
            await markMessagesRead(unreadMsgIds);
            const updatedMessages = messages.map((msg) =>
              unreadMsgIds.includes(msg.message_id)
                ? { ...msg, is_user_read: true }
                : msg
            );
            setMessages(updatedMessages);
            groupIntoThreads(updatedMessages);
            window.dispatchEvent(new CustomEvent('refresh-unread-count'));
          } catch (err) {
            console.error('Failed to mark messages as read:', err);
          }
        };
        markRead();
      }
    }
  }, [activeThreadId, threads, messages]);

  function groupIntoThreads(rawMessages) {
    const grouped = {};
    rawMessages.forEach((msg) => {
      const tid = msg.thread_id;
      if (!grouped[tid]) {
        grouped[tid] = {
          thread_id: tid,
          category: msg.category,
          messages: [],
          lastMessageAt: msg.created_at,
          lastMessageText: msg.message
        };
      }
      grouped[tid].messages.push(msg);
      
      // Update last message metadata
      if (new Date(msg.created_at) > new Date(grouped[tid].lastMessageAt)) {
        grouped[tid].lastMessageAt = msg.created_at;
        grouped[tid].lastMessageText = msg.message;
      }
    });

    // Sort messages inside each thread
    Object.keys(grouped).forEach((tid) => {
      grouped[tid].messages.sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
    });

    setThreads(grouped);
  };

  // Scroll to bottom of thread chat history
  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  }, [activeThreadId, threads]);

  // Category styling helpers
  const getCategoryStyle = (cat) => {
    switch (cat?.toLowerCase()) {
      case 'security':
      case 'fraud alert':
        return 'bg-red-500/10 dark:bg-red-500/20 text-red-600 dark:text-red-400 border-red-500/20';
      case 'loans':
        return 'bg-emerald-500/10 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 border-emerald-500/20';
      case 'billing':
        return 'bg-amber-500/10 dark:bg-amber-500/20 text-amber-600 dark:text-amber-400 border-amber-500/20';
      default:
        return 'bg-sky-500/10 dark:bg-sky-500/20 text-sky-600 dark:text-sky-400 border-sky-500/20';
    }
  };

  const isFraudAlertMessage = (msg) => (
    msg.sender !== 'user'
    && msg.category?.toLowerCase() === 'fraud alert'
    && msg.message?.toLowerCase().includes('suspicious transactions')
  );

  const renderMessageText = (messageText) => {
    const parts = messageText.split(/(\/support\/voice\?entry=fraud-alert|\/support\/voice)/g);
    return parts.map((part, index) => {
      if (part === '/support/voice' || part === '/support/voice?entry=fraud-alert') {
        return (
          <button
            key={`${part}-${index}`}
            type="button"
            onClick={() => navigate('/support/voice', { state: { entry: 'fraud-alert' } })}
            className="inline-flex items-center gap-1 font-bold text-emerald-600 dark:text-emerald-400 hover:underline"
          >
            {part}
            <ExternalLink className="w-3 h-3" />
          </button>
        );
      }
      return <React.Fragment key={`${part}-${index}`}>{part}</React.Fragment>;
    });
  };

  const handleAcknowledgeFraudAlert = async () => {
    setIsAcknowledgingFraud(true);
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      const result = await acknowledgeFraudAlert();
      if (result.success === false) {
        throw new Error(result.message || 'No open fraud alert was found.');
      }
      setSuccessMsg('Thanks. We marked these purchases as recognized activity and closed the fraud alert.');
      await fetchMessages(true);
    } catch (err) {
      console.error('Failed to acknowledge fraud alert:', err);
      setErrorMsg(err.response?.data?.detail || err.message || 'Unable to acknowledge the fraud alert.');
    } finally {
      setIsAcknowledgingFraud(false);
    }
  };

  // Create a new secure message/thread
  const handleStartThread = async (e) => {
    e.preventDefault();
    if (!newText.trim()) return;

    setIsSending(true);
    setErrorMsg(null);
    try {
      const createdMsg = await createMessage({
        category: newCategory,
        message: newText.trim()
      });
      
      // Reset form
      setNewText('');
      setIsComposing(false);
      
      // Update local state
      const updatedMessages = [...messages, createdMsg];
      setMessages(updatedMessages);
      groupIntoThreads(updatedMessages);
      
      // Set active thread
      setActiveThreadId(createdMsg.thread_id);
      setSuccessMsg('Message sent successfully.');
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch (err) {
      console.error('Error starting thread:', err);
      setErrorMsg('Could not send message. Please try again.');
    } finally {
      setIsSending(false);
    }
  };

  // Reply to an existing thread
  const handleSendReply = async (e) => {
    e.preventDefault();
    if (!replyText.trim() || !activeThreadId) return;

    setIsSending(true);
    setErrorMsg(null);
    const activeThread = threads[activeThreadId];

    try {
      const createdMsg = await createMessage({
        category: activeThread.category,
        message: replyText.trim(),
        thread_id: activeThreadId
      });
      
      // Reset reply state
      setReplyText('');
      
      // Update local state
      const updatedMessages = [...messages, createdMsg];
      setMessages(updatedMessages);
      groupIntoThreads(updatedMessages);
    } catch (err) {
      console.error('Error sending reply:', err);
      setErrorMsg('Could not send reply. Please try again.');
    } finally {
      setIsSending(false);
    }
  };

  // Delete an entire thread
  const handleDeleteThread = async (tid) => {
    if (!window.confirm('Are you sure you want to delete this thread? This action cannot be undone.')) return;

    setErrorMsg(null);
    try {
      await deleteThread(tid);

      // If deleted thread is active, deselect
      if (activeThreadId === tid) {
        setActiveThreadId(null);
      }

      // Filter out messages from local state
      const updatedMessages = messages.filter((msg) => msg.thread_id !== tid);
      setMessages(updatedMessages);
      groupIntoThreads(updatedMessages);

      setSuccessMsg('Thread deleted successfully.');
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch (err) {
      console.error('Error deleting thread:', err);
      setErrorMsg('Could not delete thread. Please try again.');
    }
  };

  // Delete an individual message
  const handleDeleteMessage = async (msgId) => {
    if (!window.confirm('Are you sure you want to delete this message?')) return;

    setErrorMsg(null);
    try {
      await deleteMessage(msgId);

      // Filter out deleted message from local state
      const updatedMessages = messages.filter((msg) => msg.message_id !== msgId);
      setMessages(updatedMessages);
      groupIntoThreads(updatedMessages);
    } catch (err) {
      console.error('Error deleting message:', err);
      setErrorMsg('Could not delete message. Please try again.');
    }
  };

  // Copy current thread ID to clipboard
  const handleCopyThreadId = async () => {
    if (!activeThreadId) return;
    try {
      await navigator.clipboard.writeText(activeThreadId);
      setCopiedThreadId(true);
      setTimeout(() => setCopiedThreadId(false), 2000);
    } catch (err) {
      console.error('Failed to copy thread ID:', err);
    }
  };

  const handleCopyQuery = async () => {
    try {
      await navigator.clipboard.writeText('select * from identity.user_secure_messages;');
      setCopiedQuery(true);
      setTimeout(() => setCopiedQuery(false), 2000);
    } catch (err) {
      console.error('Failed to copy query:', err);
    }
  };

  // Populate and open simulation modal
  const handleOpenDebugModal = () => {
    if (activeThreadId && threads[activeThreadId]) {
      const activeThread = threads[activeThreadId];
      setDebugThreadId(activeThreadId);
      setDebugCategory(activeThread.category);
      setDebugTitle(`New Support Message (${activeThread.category})`);
      setDebugBody("Hello! This is a simulated response from the support team.");
      setDebugType("support_message");
      setIsDebugOpen(true);
    }
  };

  // Dispatch custom window event to simulate push notification toast
  const handleSendSimulatedNotification = (e) => {
    e.preventDefault();
    if (!debugThreadId.trim()) return;

    const event = new CustomEvent('firebase-push-notification', {
      detail: {
        data: {
          title: debugTitle.trim() || 'New Support Message',
          body: debugBody.trim() || 'Simulated Message content',
          thread_id: debugThreadId.trim(),
          type: debugType.trim() || 'support_message',
          category: debugCategory,
          user_id: customerProfile?.user_id
        }
      }
    });

    window.dispatchEvent(event);
    setIsDebugOpen(false);
  };

  // Formatter for timestamp
  const formatTime = (isoString) => {
    try {
      const d = new Date(isoString);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch {
      return '';
    }
  };

  const formatDate = (isoString) => {
    try {
      const d = new Date(isoString);
      return d.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' });
    } catch {
      return '';
    }
  };
  return (
    <section className="relative pt-28 pb-12 px-6 max-w-7xl mx-auto min-h-[calc(100vh-80px)] flex flex-col">
      {/* Background Glow */}
      <div className="absolute top-1/4 left-1/4 w-[400px] h-[400px] rounded-full bg-emerald-500/5 dark:bg-emerald-500/5 blur-[120px] pointer-events-none -z-10" />
      <div className="absolute bottom-1/4 right-1/4 w-[400px] h-[400px] rounded-full bg-cyan-500/5 dark:bg-cyan-500/5 blur-[120px] pointer-events-none -z-10" />

      {/* Header Info */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8 relative pr-28">
        <div>
          <h1 className="text-3xl font-extrabold bg-gradient-to-r from-slate-900 via-slate-700 to-slate-500 dark:from-white dark:via-slate-200 dark:to-slate-400 bg-clip-text text-transparent">
            Secure Messages
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Secure, encrypted messaging to interact directly with our banking support agents.
          </p>
        </div>

        {/* Action Alerts */}
        <div className="flex flex-col gap-2 shrink-0">
          {errorMsg && (
            <div className="p-3 rounded-xl bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-800/30 text-red-600 dark:text-red-400 text-xs flex items-center gap-2 animate-shake">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{errorMsg}</span>
            </div>
          )}
          {successMsg && (
            <div className="p-3 rounded-xl bg-emerald-50 dark:bg-emerald-950/20 border border-emerald-200 dark:border-emerald-800/30 text-emerald-600 dark:text-emerald-400 text-xs flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              <span>{successMsg}</span>
            </div>
          )}
        </div>

        <div className="absolute right-0 top-1/2 -translate-y-1/2 flex items-center gap-2">
          <AnalyticsButton
            id="secure-messaging-tour-btn"
            onClick={() => {
              localStorage.removeItem('secure-messaging-tour-completed');
              setTourKey(prev => prev + 1);
              setTourRun(true);
            }}
            className="p-2.5 rounded-2xl hover:bg-slate-100 dark:hover:bg-slate-800 transition-all active:scale-95 cursor-pointer flex items-center justify-center border border-slate-200/60 dark:border-slate-800/60 bg-white dark:bg-slate-900 shadow-sm text-slate-500 hover:text-slate-900 dark:hover:text-white"
            title="Take Secure Messaging Tour"
            trackingName="start_secure_messaging_tour"
          >
            <GoogleCompassIcon className="w-5 h-5 text-emerald-500" />
          </AnalyticsButton>
          <AnalyticsButton
            onClick={() => setIsInfoModalOpen(true)}
            className="p-2.5 rounded-2xl hover:bg-slate-100 dark:hover:bg-slate-800 transition-all active:scale-95 cursor-pointer flex items-center justify-center border border-slate-200/60 dark:border-slate-800/60 bg-white dark:bg-slate-900 shadow-sm"
            title="GCP & Firebase Integration Info"
            trackingName="open_secure_messaging_backend_info_modal"
          >
            <GoogleCloudIcon className="w-5 h-5" />
          </AnalyticsButton>
        </div>
      </div>

      {/* Primary Workspace Panel */}
      <div className="flex-grow grid grid-cols-1 md:grid-cols-12 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800/80 rounded-3xl overflow-hidden shadow-2xl min-h-[600px]">
        
        {/* Left Side Pane: Threads List */}
        <div className="md:col-span-4 border-r border-slate-200 dark:border-slate-800/80 flex flex-col h-full bg-slate-50/50 dark:bg-slate-900/50" id="threads-list-container">
          <div className="p-4 border-b border-slate-200 dark:border-slate-800/80 flex items-center justify-between gap-3 bg-white dark:bg-slate-900">
            <span className="font-bold text-slate-800 dark:text-slate-200 text-sm">Conversations</span>
            <button
              id="compose-message-btn"
              onClick={() => {
                setIsComposing(true);
                setActiveThreadId(null);
              }}
              className="p-2 py-1.5 text-xs font-semibold rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-200 hover:bg-emerald-50 dark:hover:bg-emerald-950/30 hover:text-emerald-600 dark:hover:text-emerald-400 transition-all flex items-center gap-1 cursor-pointer border border-slate-200 dark:border-slate-700/50"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>New Thread</span>
            </button>
          </div>

          {/* List Wrapper */}
          <div className="flex-grow overflow-y-auto divide-y divide-slate-100 dark:divide-slate-800/50 max-h-[600px]">
            {isLoading ? (
              <div className="flex flex-col items-center justify-center py-16 text-slate-400 gap-2">
                <Loader2 className="w-6 h-6 animate-spin text-emerald-500" />
                <span className="text-xs">Loading conversations...</span>
              </div>
            ) : Object.keys(threads).length === 0 ? (
              <div className="flex flex-col items-center justify-center text-center py-16 px-4 text-slate-400 gap-3">
                <MessageSquare className="w-8 h-8 text-slate-300 dark:text-slate-700" />
                <div className="text-xs font-semibold text-slate-500">No active message threads</div>
                <p className="text-[11px] text-slate-400 max-w-[200px]">
                  Click "New Thread" above to start a secure conversation.
                </p>
              </div>
            ) : (
              Object.values(threads)
                .sort((a, b) => new Date(b.lastMessageAt) - new Date(a.lastMessageAt))
                .map((thread) => {
                  const isActive = activeThreadId === thread.thread_id;
                  const hasUnread = thread.messages.some((msg) => msg.sender !== 'user' && !msg.is_user_read);
                  return (
                    <div
                      key={thread.thread_id}
                      className={`group p-4 flex gap-3 cursor-pointer items-start transition-all ${
                        isActive
                          ? 'bg-slate-100/80 dark:bg-slate-800/60 border-l-4 border-emerald-500'
                          : 'hover:bg-slate-100/40 dark:hover:bg-slate-800/20 border-l-4 border-transparent'
                      }`}
                      onClick={() => {
                        setActiveThreadId(thread.thread_id);
                        setIsComposing(false);
                        fetchMessages(true); // silent refresh from backend
                      }}
                    >
                      <div className="flex-grow overflow-hidden text-left">
                        {/* Thread Header details */}
                        <div className="flex items-center justify-between gap-2">
                          <span className={`px-2 py-0.5 text-[9px] font-bold tracking-wider uppercase rounded-full border ${getCategoryStyle(thread.category)}`}>
                            {thread.category}
                          </span>
                          <div className="flex items-center gap-1.5 shrink-0">
                            {hasUnread && (
                              <span className="w-2 h-2 rounded-full bg-emerald-500 shrink-0" title="Unread message(s)"></span>
                            )}
                            <span className="text-[10px] text-slate-400">
                              {formatTime(thread.lastMessageAt)}
                            </span>
                          </div>
                        </div>

                        {/* Text preview */}
                        <p className={`text-xs truncate mt-2 pr-2 ${hasUnread ? 'text-slate-900 dark:text-white font-bold' : 'text-slate-700 dark:text-slate-300 font-medium'}`}>
                          {thread.lastMessageText}
                        </p>
                      </div>

                      {/* Deletion action */}
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDeleteThread(thread.thread_id);
                        }}
                        className="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg bg-red-50 dark:bg-red-950/20 hover:bg-red-100 dark:hover:bg-red-950/50 text-red-500 transition-all cursor-pointer"
                        title="Delete Thread"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  );
                })
            )}
          </div>
        </div>

        {/* Right Side Pane: Chat View / Compose Form */}
        <div className="md:col-span-8 flex flex-col h-full bg-white dark:bg-slate-900 relative" id="chat-history-pane">
          
          {/* Form State: Compose New Thread */}
          {isComposing && (
            <div className="flex flex-col h-full p-6 text-left">
              <div className="flex items-center gap-3 mb-6 pb-4 border-b border-slate-100 dark:border-slate-800/50">
                <button 
                  onClick={() => setIsComposing(false)}
                  className="p-1.5 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 transition-colors"
                >
                  <ArrowLeft className="w-4 h-4" />
                </button>
                <span className="font-bold text-slate-800 dark:text-slate-100">Start New Secure Thread</span>
              </div>

              <form onSubmit={handleStartThread} className="space-y-6 flex-grow flex flex-col">
                {/* Category Selection */}
                <div className="p-4 bg-slate-50 dark:bg-slate-950 rounded-2xl border border-slate-100 dark:border-slate-800/50">
                  <label htmlFor="category" className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                    Category Topic
                  </label>
                  <select
                    id="category"
                    value={newCategory}
                    onChange={(e) => setNewCategory(e.target.value)}
                    className="w-full p-2.5 text-sm rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500 transition-all cursor-pointer"
                  >
                    {CATEGORIES.map((cat) => (
                      <option key={cat} value={cat}>{cat}</option>
                    ))}
                  </select>
                </div>

                {/* Message input */}
                <div className="p-4 bg-slate-50 dark:bg-slate-950 rounded-2xl border border-slate-100 dark:border-slate-800/50 flex-grow flex flex-col">
                  <label htmlFor="message" className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                    Your Message
                  </label>
                  <textarea
                    id="message"
                    rows={8}
                    value={newText}
                    onChange={(e) => setNewText(e.target.value)}
                    placeholder="Write your secure message here. Be as detailed as possible..."
                    className="w-full p-3 text-sm rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500 transition-all resize-none flex-grow"
                    required
                  />
                </div>

                {/* Action CTA */}
                <div className="flex justify-end gap-3 pt-4 border-t border-slate-100 dark:border-slate-800/50">
                  <button
                    type="button"
                    onClick={() => setIsComposing(false)}
                    className="px-6 py-2.5 text-sm font-semibold rounded-full bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 transition-all cursor-pointer"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isSending || !newText.trim()}
                    className="px-6 py-2.5 text-sm font-semibold rounded-full text-slate-950 hover:scale-102 active:scale-98 transition-all flex items-center justify-center gap-2 shadow-lg cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                    style={{
                      backgroundImage: `linear-gradient(to right, ${brandColorFrom}, ${brandColorTo})`,
                      boxShadow: `0 10px 15px -3px ${brandColorFrom}30`
                    }}
                  >
                    {isSending ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span>Sending...</span>
                      </>
                    ) : (
                      <>
                        <Send className="w-4 h-4" />
                        <span>Send Message</span>
                      </>
                    )}
                  </button>
                </div>
              </form>
            </div>
          )}

          {/* State: Viewing Active Chat Thread */}
          {!isComposing && activeThreadId && threads[activeThreadId] && (
            <div className="flex flex-col h-full max-h-[600px] text-left">
              {/* Header metadata */}
              <div className="p-4 border-b border-slate-200 dark:border-slate-800/80 flex items-center justify-between gap-4 bg-slate-50/20 dark:bg-slate-950/20">
                <div className="flex items-center gap-3">
                  <span className={`px-2.5 py-0.5 text-[10px] font-bold tracking-wider uppercase rounded-full border ${getCategoryStyle(threads[activeThreadId].category)}`}>
                    {threads[activeThreadId].category}
                  </span>
                  <div className="flex items-center gap-1.5 text-xs text-slate-400 dark:text-slate-500">
                    <span>Thread ID: {activeThreadId}</span>
                    <button
                      onClick={handleCopyThreadId}
                      className="p-1 rounded-md hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 transition-colors cursor-pointer"
                      title="Copy Thread ID"
                    >
                      {copiedThreadId ? (
                        <Check className="w-3.5 h-3.5 text-emerald-500" />
                      ) : (
                        <Copy className="w-3.5 h-3.5" />
                      )}
                    </button>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={handleOpenDebugModal}
                    className="p-1.5 rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-500 dark:text-slate-400 transition-colors cursor-pointer flex items-center justify-center"
                    title="Simulate push notification for this thread"
                  >
                    <Bug className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => fetchMessages(true)}
                    className="p-1.5 rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-500 dark:text-slate-400 transition-colors cursor-pointer flex items-center justify-center"
                    title="Refresh Messages"
                  >
                    <RefreshCw className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => handleDeleteThread(activeThreadId)}
                    className="p-1.5 rounded-lg bg-red-50 dark:bg-red-950/20 hover:bg-red-100 dark:hover:bg-red-950/50 text-red-500 transition-colors cursor-pointer flex items-center justify-center"
                    title="Delete Thread"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>

              {/* Chat Message History */}
              <div ref={chatContainerRef} className="flex-grow overflow-y-auto p-4 space-y-4 max-h-[400px]">
                {threads[activeThreadId].messages.map((msg, index) => {
                  const isUser = msg.sender === 'user';
                  const showDateLine = index === 0 || 
                    new Date(threads[activeThreadId].messages[index - 1].created_at).toDateString() !== new Date(msg.created_at).toDateString();

                  return (
                    <div key={msg.message_id} className="space-y-2">
                      {/* Optional Date line wrapper */}
                      {showDateLine && (
                        <div className="flex items-center justify-center py-2">
                          <div className="px-3 py-1 rounded-full bg-slate-100 dark:bg-slate-800 text-[10px] font-bold text-slate-400 dark:text-slate-500 flex items-center gap-1 border border-slate-200/40 dark:border-slate-700/40">
                            <Calendar className="w-3 h-3" />
                            <span>{formatDate(msg.created_at)}</span>
                          </div>
                        </div>
                      )}

                      {/* Chat Bubble Align block */}
                      <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} items-end gap-2 group`}>
                        
                        {/* Support Agent Icon */}
                        {!isUser && (
                          <div className="w-7 h-7 rounded-full bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 flex items-center justify-center text-slate-500 shrink-0 shadow-sm">
                            <Shield className="w-3.5 h-3.5 text-emerald-500" />
                          </div>
                        )}

                        {/* Content text container */}
                        <div className="max-w-[80%] flex flex-col relative">
                          <div
                            className={`p-3.5 rounded-2xl text-xs leading-relaxed font-medium shadow-sm ${
                              isUser
                                ? 'text-slate-950 rounded-br-sm'
                                : 'bg-slate-100 dark:bg-slate-800/80 text-slate-800 dark:text-slate-200 rounded-bl-sm border border-slate-200/50 dark:border-slate-700/50'
                            }`}
                            style={isUser ? {
                              backgroundImage: `linear-gradient(to top right, ${brandColorFrom}, ${brandColorTo})`,
                            } : {}}
                          >
                            <p className="whitespace-pre-line break-words">{renderMessageText(msg.message)}</p>
                            {isFraudAlertMessage(msg) && (
                              <div className="mt-3 pt-3 border-t border-slate-200/70 dark:border-slate-700/70 flex flex-col sm:flex-row gap-2">
                                <button
                                  type="button"
                                  onClick={() => navigate('/support/voice', { state: { entry: 'fraud-alert' } })}
                                  className="inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-[11px] font-bold transition-colors"
                                >
                                  <ExternalLink className="w-3.5 h-3.5" />
                                  Chat with support
                                </button>
                                <button
                                  type="button"
                                  onClick={handleAcknowledgeFraudAlert}
                                  disabled={isAcknowledgingFraud}
                                  className="inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl bg-slate-200 hover:bg-slate-300 dark:bg-slate-700 dark:hover:bg-slate-600 text-slate-800 dark:text-slate-100 text-[11px] font-bold transition-colors disabled:opacity-60"
                                >
                                  {isAcknowledgingFraud ? (
                                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                  ) : (
                                    <CheckCircle2 className="w-3.5 h-3.5" />
                                  )}
                                  I recognize these
                                </button>
                              </div>
                            )}
                          </div>
                          <span className={`text-[9px] text-slate-400 mt-1 ${isUser ? 'text-right pr-1' : 'text-left pl-1'}`}>
                            {formatTime(msg.created_at)}
                          </span>
                        </div>

                        {/* Delete Single message on hover */}
                        <button
                          onClick={() => handleDeleteMessage(msg.message_id)}
                          className="opacity-0 group-hover:opacity-100 p-1 rounded-md bg-slate-50 dark:bg-slate-800 text-slate-400 hover:text-red-500 transition-all cursor-pointer"
                          title="Delete message"
                        >
                          <Trash2 className="w-3 h-3" />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Chat Input form area */}
              <form onSubmit={handleSendReply} className="p-4 border-t border-slate-200 dark:border-slate-800/80 flex gap-3 bg-white dark:bg-slate-900">
                <textarea
                  rows={1}
                  value={replyText}
                  onChange={(e) => setReplyText(e.target.value)}
                  placeholder="Write your secure response here..."
                  className="flex-grow p-3 text-xs rounded-2xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500 transition-all resize-none max-h-[100px]"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      handleSendReply(e);
                    }
                  }}
                  required
                />
                <button
                  type="submit"
                  disabled={isSending || !replyText.trim()}
                  className="p-3.5 rounded-2xl text-slate-950 font-semibold shadow-md hover:scale-105 active:scale-95 transition-all flex items-center justify-center shrink-0 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
                  style={{
                    backgroundImage: `linear-gradient(to top right, ${brandColorFrom}, ${brandColorTo})`,
                  }}
                  title="Send message"
                >
                  {isSending ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Send className="w-4 h-4" />
                  )}
                </button>
              </form>
            </div>
          )}

          {/* Empty State Overlay */}
          {!isComposing && !activeThreadId && (
            <div className="flex flex-col items-center justify-center text-center p-8 py-24 text-slate-400 gap-4 flex-grow h-full select-none">
              <div className="w-16 h-16 rounded-3xl bg-slate-50 dark:bg-slate-950 border border-slate-100 dark:border-slate-800/50 flex items-center justify-center shadow-lg text-slate-300 dark:text-slate-800 animate-pulse">
                <Shield className="w-8 h-8 text-emerald-500/40 dark:text-emerald-500/20" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-slate-700 dark:text-slate-300">Secure Messaging Workspace</h3>
                <p className="text-xs text-slate-400 dark:text-slate-500 max-w-sm mt-1.5 leading-relaxed">
                  Select an existing conversation from the side panel or click "New Thread" to draft a secure message to our support experts.
                </p>
              </div>
              <button
                onClick={() => setIsComposing(true)}
                className="mt-2 px-5 py-2 text-xs font-semibold rounded-full text-slate-950 shadow-lg hover:scale-105 active:scale-95 transition-all cursor-pointer flex items-center gap-1.5"
                style={{
                  backgroundImage: `linear-gradient(to right, ${brandColorFrom}, ${brandColorTo})`,
                  boxShadow: `0 8px 12px -3px ${brandColorFrom}25`
                }}
              >
                <Plus className="w-4 h-4" />
                <span>Compose message</span>
              </button>
            </div>
          )}

        </div>
      </div>

      {/* Debug Push Notification Simulator Modal */}
      {isDebugOpen && (
        <div className="fixed inset-0 z-[250] bg-black/65 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl p-6 max-w-md w-full shadow-2xl space-y-6 text-left">
            <div className="flex items-center gap-2.5 pb-2 border-b border-slate-100 dark:border-slate-800">
              <div className="w-8 h-8 rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 flex items-center justify-center">
                <Bug className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-base font-bold text-slate-900 dark:text-white">Push Notification Simulator</h3>
                <p className="text-[11px] text-slate-400">Trigger a simulated push event in the foreground</p>
              </div>
            </div>

            <form onSubmit={handleSendSimulatedNotification} className="space-y-4">
              <div>
                <label htmlFor="debugThreadId" className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">
                  Thread ID
                </label>
                <input
                  id="debugThreadId"
                  type="text"
                  value={debugThreadId}
                  onChange={(e) => setDebugThreadId(e.target.value)}
                  className="w-full p-2.5 text-xs rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-850 text-slate-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-emerald-500"
                  required
                />
              </div>

              <div>
                <label htmlFor="debugType" className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">
                  Notification Type (e.g. support_message, alert, etc.)
                </label>
                <input
                  id="debugType"
                  type="text"
                  value={debugType}
                  onChange={(e) => setDebugType(e.target.value)}
                  className="w-full p-2.5 text-xs rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-850 text-slate-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-emerald-500"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label htmlFor="debugCategory" className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">
                    Category
                  </label>
                  <select
                    id="debugCategory"
                    value={debugCategory}
                    onChange={(e) => setDebugCategory(e.target.value)}
                    className="w-full p-2.5 text-xs rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-850 text-slate-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-emerald-500"
                  >
                    {CATEGORIES.map(cat => (
                      <option key={cat} value={cat}>{cat}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label htmlFor="debugTitle" className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">
                    Notification Title
                  </label>
                  <input
                    id="debugTitle"
                    type="text"
                    value={debugTitle}
                    onChange={(e) => setDebugTitle(e.target.value)}
                    className="w-full p-2.5 text-xs rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-850 text-slate-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-emerald-500"
                    required
                  />
                </div>
              </div>

              <div>
                <label htmlFor="debugBody" className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">
                  Notification Body/Message
                </label>
                <textarea
                  id="debugBody"
                  rows={3}
                  value={debugBody}
                  onChange={(e) => setDebugBody(e.target.value)}
                  className="w-full p-2.5 text-xs rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-850 text-slate-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-emerald-500 resize-none"
                  required
                />
              </div>

              <div className="flex justify-end gap-3 pt-3 border-t border-slate-100 dark:border-slate-800">
                <button
                  type="button"
                  onClick={() => setIsDebugOpen(false)}
                  className="px-4 py-2 text-xs font-semibold rounded-full bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 text-xs font-semibold rounded-full text-slate-950 hover:scale-105 active:scale-95 transition-all cursor-pointer"
                  style={{
                    backgroundImage: `linear-gradient(to right, ${brandColorFrom}, ${brandColorTo})`,
                    boxShadow: `0 8px 12px -3px ${brandColorFrom}20`
                  }}
                >
                  Simulate Event
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      <GcpInfoModal
        isOpen={isInfoModalOpen}
        onClose={() => setIsInfoModalOpen(false)}
        title="Secure Messaging Backend Integration"
      >
        <div className="space-y-4 text-slate-600 dark:text-slate-400 text-sm leading-relaxed">
          <p>
            This secure messaging feature integrates both <strong>Google Cloud Platform (BigQuery)</strong> and <strong>Firebase (Cloud Messaging)</strong>.
          </p>
          <p>
            When customer or support agents transmit messaging payload data, the logs and metadata records are saved to the BigQuery database in real-time. In parallel, <strong>Firebase Cloud Messaging (FCM)</strong> dispatches instantaneous device push notifications to keep the conversation responsive.
          </p>
          <p>
            You can inspect the underlying data table and message delivery status directly in the consoles using the links below:
          </p>
          <div className="bg-slate-50 dark:bg-slate-950 p-4 rounded-2xl border border-slate-100 dark:border-slate-800 space-y-3">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h4 className="font-semibold text-slate-800 dark:text-slate-200 text-xs uppercase tracking-wider">Secure Message Table</h4>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">View message text archives, timestamps, and thread keys. Login to the banking database using IAM upon clicking 'Open Cloud SQL Studio'.</p>
              </div>
              <div className="flex flex-col items-end gap-1.5 shrink-0">
                <a
                  href={`https://console.cloud.google.com/sql/instances/banking-data/studio?project=${projectId}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-emerald-500 hover:text-emerald-600 font-semibold text-xs hover:underline"
                >
                  <span>Open Cloud SQL Studio</span>
                  <ExternalLink className="w-3.5 h-3.5" />
                </a>
                <button
                  type="button"
                  onClick={handleCopyQuery}
                  className="inline-flex items-center gap-1 text-emerald-500 hover:text-emerald-600 font-semibold text-xs hover:underline cursor-pointer"
                >
                  {copiedQuery ? (
                    <>
                      <span>Copied!</span>
                      <Check className="w-3.5 h-3.5" />
                    </>
                  ) : (
                    <>
                      <span>Copy Query</span>
                      <Copy className="w-3.5 h-3.5" />
                    </>
                  )}
                </button>
              </div>
            </div>
            <hr className="border-slate-100 dark:border-slate-800" />
            <div className="flex items-start justify-between gap-4">
              <div>
                <h4 className="font-semibold text-slate-800 dark:text-slate-200 text-xs uppercase tracking-wider">Firebase Cloud Messaging Reports</h4>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">Monitor push notification delivery rates, errors, and campaigns.</p>
              </div>
              <a
                href={`https://console.firebase.google.com/project/${projectId}/messaging/reports`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-emerald-500 hover:text-emerald-600 font-semibold text-xs shrink-0 hover:underline"
              >
                <span>View Console</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            </div>
            <hr className="border-slate-100 dark:border-slate-800" />
            <div className="flex items-start justify-between gap-4">
              <div>
                <h4 className="font-semibold text-slate-800 dark:text-slate-200 text-xs uppercase tracking-wider">Documentation</h4>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">Learn about Firebase Cloud Messaging, message types, and setup options.</p>
              </div>
              <a
                href="https://firebase.google.com/docs/cloud-messaging"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-emerald-500 hover:text-emerald-600 font-semibold text-xs shrink-0 hover:underline"
              >
                <span>View Docs</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            </div>
            <hr className="border-slate-100 dark:border-slate-800" />
            <div className="flex items-start justify-between gap-4">
              <div>
                <h4 className="font-semibold text-slate-800 dark:text-slate-200 text-xs uppercase tracking-wider">Architecture Guide</h4>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">Read about the FCM real-time push multicast topology, background service workers, and DB schema.</p>
              </div>
              <a
                href="https://github.com/GoogleCloudPlatform/fsi-gecx-bundle/blob/main/docs/architecture/domain-workflows/support/secure_messaging_backend_integration.md"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-emerald-500 hover:text-emerald-600 font-semibold text-xs shrink-0 hover:underline"
              >
                <span>View Design</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            </div>
          </div>
        </div>
      </GcpInfoModal>

      {/* Joyride Onboarding Tour */}
      {tourRun && domReady && steps.length > 0 && (
        <Joyride
          key={tourKey}
          run={tourRun}
          options={{
            scrollOffset: 120
          }}
          steps={steps}
          continuous={true}
          locale={{ last: 'Done' }}
          showSkipButton={true}
          showCloseButton={true}
          onEvent={(data) => {
            const { status, type, action } = data;
            if (
              [STATUS.FINISHED, STATUS.SKIPPED].includes(status) ||
              type === EVENTS.TOUR_END ||
              action === ACTIONS.CLOSE ||
              action === ACTIONS.SKIP
            ) {
              setTourRun(false);
              localStorage.setItem('secure-messaging-tour-completed', 'true');
            }
          }}
          styles={getJoyrideStyles(resolvedTheme, brandColorFrom)}
        />
      )}
    </section>
  );
}

export default SecureMessagingView;
