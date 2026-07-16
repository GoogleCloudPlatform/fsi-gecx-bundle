import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  Send, Trash2, Plus, MessageSquare, Shield, 
  AlertCircle, Loader2, Calendar, 
  ArrowLeft, CheckCircle2, User, Search, RefreshCw, Copy, Check
} from 'lucide-react';
import { useSettings } from '../context/SettingsContext.jsx';
import AnalyticsButton from './AnalyticsButton.jsx';
import { 
  getCustomersList, 
  getCustomerMessages, 
  markMessagesAgentRead, 
  createMessage, 
  adminDeleteThread, 
  adminDeleteMessage 
} from '../utils/api.js';



const CATEGORIES = ['General', 'Billing', 'Loans', 'Security'];

function AdminMessagingView({ fbUser }) {
  const navigate = useNavigate();
  const { brandColorFrom, brandColorTo } = useSettings();
  
  // Customer Directory State
  const [customers, setCustomers] = useState([]);
  const [selectedCustomerId, setSelectedCustomerId] = useState(null);
  const [customerSearchQuery, setCustomerSearchQuery] = useState('');
  const [isLoadingCustomers, setIsLoadingCustomers] = useState(false);
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);

  // Chat/Threads State for selected customer
  const [messages, setMessages] = useState([]);
  const [threads, setThreads] = useState({});
  const [activeThreadId, setActiveThreadId] = useState(null);
  const [isComposing, setIsComposing] = useState(false);
  
  // New Message State
  const [newCategory, setNewCategory] = useState('General');
  const [newText, setNewText] = useState('');
  const [replyText, setReplyText] = useState('');
  const [threadSearchQuery, setThreadSearchQuery] = useState('');
  const [copiedThreadId, setCopiedThreadId] = useState(false);
  
  // UI Feedback State
  const [isLoadingMessages, setIsLoadingMessages] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);
  const [successMsg, setSuccessMsg] = useState(null);

  const chatContainerRef = useRef(null);
  // Fetch customer directory on mount
  useEffect(() => {
    const loadCustomers = async () => {
      if (!fbUser) return;
      setIsLoadingCustomers(true);
      try {
        const data = await getCustomersList();
        setCustomers(data);
      } catch (err) {
        console.error("Failed to load customer directory:", err);
      } finally {
        setIsLoadingCustomers(false);
      }
    };
    loadCustomers();
  }, [fbUser]);

  // Fetch messages for selected customer
  const fetchCustomerMessages = useCallback(async (customerId, silent = false) => {
    if (!silent) setIsLoadingMessages(true);
    setErrorMsg(null);
    try {
      const data = await getCustomerMessages(customerId);
      setMessages(data);
      groupIntoThreads(data);
    } catch (err) {
      console.error('Error fetching customer messages:', err);
      setErrorMsg('Could not load messages. Please verify connection.');
    } finally {
      if (!silent) setIsLoadingMessages(false);
    }
  }, []);

  useEffect(() => {
    if (selectedCustomerId) {
      setActiveThreadId(null);
      setIsComposing(false);
      fetchCustomerMessages(selectedCustomerId);
    } else {
      setMessages([]);
      setThreads({});
      setActiveThreadId(null);
    }
  }, [selectedCustomerId, fetchCustomerMessages]);

  useEffect(() => {
    const handlePushNotification = (e) => {
      console.log("Admin received custom push notification event:", e.detail);
      const payload = e.detail;
      if (
        (payload?.data?.type === 'user_message' || payload?.data?.type === 'support_message') && 
        payload?.data?.user_id === selectedCustomerId
      ) {
        console.log("Notification matches selected customer ID! Silently refreshing conversation messages...");
        fetchCustomerMessages(selectedCustomerId, true);
      }
    };
    window.addEventListener('firebase-push-notification', handlePushNotification);
    return () => window.removeEventListener('firebase-push-notification', handlePushNotification);
  }, [selectedCustomerId, fetchCustomerMessages]);

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
      
      if (new Date(msg.created_at) > new Date(grouped[tid].lastMessageAt)) {
        grouped[tid].lastMessageAt = msg.created_at;
        grouped[tid].lastMessageText = msg.message;
      }
    });

    Object.keys(grouped).forEach((tid) => {
      grouped[tid].messages.sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
    });

    setThreads(grouped);
  };

  // Scroll to bottom of history
  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  }, [activeThreadId, threads]);

  useEffect(() => {
    if (activeThreadId && threads[activeThreadId] && selectedCustomerId) {
      const activeThread = threads[activeThreadId];
      const unreadMsgIds = activeThread.messages
        .filter((msg) => msg.sender === 'user' && !msg.is_agent_read)
        .map((msg) => msg.message_id);

      if (unreadMsgIds.length > 0) {
        const markAgentRead = async () => {
          try {
            await markMessagesAgentRead({
              message_ids: unreadMsgIds,
              user_id: selectedCustomerId
            });
            const updatedMessages = messages.map((msg) =>
              unreadMsgIds.includes(msg.message_id)
                ? { ...msg, is_agent_read: true }
                : msg
            );
            setMessages(updatedMessages);
            groupIntoThreads(updatedMessages);
          } catch (err) {
            console.error('Failed to mark messages as agent read:', err);
          }
        };
        markAgentRead();
      }
    }
  }, [activeThreadId, threads, selectedCustomerId, messages]);

  const getCategoryStyle = (cat) => {
    switch (cat?.toLowerCase()) {
      case 'security':
        return 'bg-red-500/10 dark:bg-red-500/20 text-red-600 dark:text-red-400 border-red-500/20';
      case 'loans':
        return 'bg-emerald-500/10 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 border-emerald-500/20';
      case 'billing':
        return 'bg-amber-500/10 dark:bg-amber-500/20 text-amber-600 dark:text-amber-400 border-amber-500/20';
      default:
        return 'bg-sky-500/10 dark:bg-sky-500/20 text-sky-600 dark:text-sky-400 border-sky-500/20';
    }
  };

  // Create a new secure message/thread for this customer
  const handleStartThread = async (e) => {
    e.preventDefault();
    if (!newText.trim() || !selectedCustomerId) return;

    setIsSending(true);
    setErrorMsg(null);
    try {
      const createdMsg = await createMessage({
        category: newCategory,
        message: newText.trim(),
        sender: "bank",
        user_id: selectedCustomerId
      });
      
      setNewText('');
      setIsComposing(false);
      
      const updatedMessages = [...messages, createdMsg];
      setMessages(updatedMessages);
      groupIntoThreads(updatedMessages);
      
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
    if (!replyText.trim() || !activeThreadId || !selectedCustomerId) return;

    setIsSending(true);
    setErrorMsg(null);
    const activeThread = threads[activeThreadId];

    try {
      const createdMsg = await createMessage({
        category: activeThread.category,
        message: replyText.trim(),
        thread_id: activeThreadId,
        sender: "bank",
        user_id: selectedCustomerId
      });
      
      setReplyText('');
      
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

  // Admin delete entire thread
  const handleDeleteThread = async (tid) => {
    if (!window.confirm('Are you sure you want to delete this thread? This action cannot be undone.')) return;
    if (!selectedCustomerId) return;

    setErrorMsg(null);
    try {
      await adminDeleteThread(tid, selectedCustomerId);

      if (activeThreadId === tid) {
        setActiveThreadId(null);
      }

      const updatedMessages = messages.filter((msg) => msg.thread_id !== tid);
      setMessages(updatedMessages);
      groupIntoThreads(updatedMessages);

      setSuccessMsg('Thread deleted successfully by admin.');
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch (err) {
      console.error('Error deleting thread:', err);
      setErrorMsg('Could not delete thread. Please try again.');
    }
  };

  // Admin delete single message
  const handleDeleteMessage = async (msgId) => {
    if (!window.confirm('Are you sure you want to delete this message?')) return;
    if (!selectedCustomerId) return;

    setErrorMsg(null);
    try {
      await adminDeleteMessage(msgId, selectedCustomerId);

      const updatedMessages = messages.filter((msg) => msg.message_id !== msgId);
      setMessages(updatedMessages);
      groupIntoThreads(updatedMessages);
    } catch (err) {
      console.error('Error deleting message:', err);
      setErrorMsg('Could not delete message. Please try again.');
    }
  };

  const handleCopyThreadId = () => {
    if (!activeThreadId) return;
    navigator.clipboard.writeText(activeThreadId);
    setCopiedThreadId(true);
    setTimeout(() => setCopiedThreadId(false), 2000);
  };

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

  // Filter customer directory list
  const filteredCustomers = customers.filter(c => {
    const fullName = `${c.first_name || ''} ${c.last_name || ''}`.toLowerCase();
    const id = (c.user_id || '').toLowerCase();
    const query = customerSearchQuery.toLowerCase();
    return fullName.includes(query) || id.includes(query);
  });

  const selectedCustomer = customers.find(c => c.user_id === selectedCustomerId);

  const filteredThreads = Object.values(threads)
    .filter(t => t.thread_id.toLowerCase().includes(threadSearchQuery.toLowerCase()))
    .sort((a, b) => new Date(b.lastMessageAt) - new Date(a.lastMessageAt));

  return (
    <section className="relative pt-24 pb-16 md:pt-28 md:pb-24 px-6 max-w-7xl mx-auto min-h-[calc(100vh-80px)] flex flex-col">
      {/* Background Glow */}
      <div className="absolute top-1/4 left-1/4 w-[400px] h-[400px] rounded-full bg-emerald-500/5 dark:bg-emerald-500/5 blur-[120px] pointer-events-none -z-10" />

      {/* Header Info */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8">
        <div className="text-left">
          <AnalyticsButton trackingName="button_click_admin_messaging_view_01" 
            onClick={() => navigate('/admin')}
            className="inline-flex items-center gap-2 text-sm font-medium text-slate-500 hover:text-slate-900 dark:hover:text-white transition-colors mb-3 group"
          >
            <ArrowLeft className="w-4 h-4 group-hover:-translate-x-1 transition-transform" />
            Back to Admin Portal
          </AnalyticsButton>
          <h1 className="text-3xl font-extrabold bg-gradient-to-r from-slate-900 via-slate-700 to-slate-500 dark:from-white dark:via-slate-200 dark:to-slate-400 bg-clip-text text-transparent">
            Support Agent Portal
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Send support replies and manage secure messages directly with bank customers.
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
      </div>

      {/* Customer Directory Dropdown Selector Row */}
      <div className="mb-6 relative text-left max-w-md">
        <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
          Target Customer Account
        </label>
        <div 
          onClick={() => setIsDropdownOpen(!isDropdownOpen)}
          className="w-full p-3.5 text-sm rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500 transition-all cursor-pointer flex justify-between items-center shadow-md font-semibold"
        >
          <span>
            {selectedCustomer 
              ? `${selectedCustomer.first_name || ''} ${selectedCustomer.last_name || ''} (ID: ${selectedCustomer.user_id.slice(0, 10)}...)`
              : "Select a customer to message..."}
          </span>
          <Plus className={`w-4 h-4 text-slate-400 transition-transform ${isDropdownOpen ? 'rotate-45' : ''}`} />
        </div>

        {/* Dropdown Options List */}
        {isDropdownOpen && (
          <div className="absolute top-full left-0 right-0 mt-2 z-50 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl p-4 shadow-2xl space-y-3 flex flex-col">
            <div className="relative">
              <Search className="absolute left-3 top-2.5 w-3.5 h-3.5 text-slate-400" />
              <input
                type="text"
                placeholder="Search by name or customer ID..."
                value={customerSearchQuery}
                onChange={(e) => setCustomerSearchQuery(e.target.value)}
                onClick={(e) => e.stopPropagation()} // Keep dropdown open
                className="w-full pl-9 pr-4 py-2 text-xs rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-805 text-slate-900 dark:text-white focus:outline-none"
              />
            </div>
            
            <div className="max-h-48 overflow-y-auto divide-y divide-slate-100 dark:divide-slate-800/40 pr-1">
              {isLoadingCustomers ? (
                <div className="flex items-center justify-center py-6 text-slate-400 gap-2">
                  <Loader2 className="w-4 h-4 animate-spin text-emerald-500" />
                  <span className="text-xs">Loading directory...</span>
                </div>
              ) : filteredCustomers.length === 0 ? (
                <div className="text-center py-6 text-xs text-slate-400">No customers match search.</div>
              ) : (
                filteredCustomers.map(c => (
                  <div
                    key={c.user_id}
                    onClick={() => {
                      setSelectedCustomerId(c.user_id);
                      setIsDropdownOpen(false);
                      setCustomerSearchQuery('');
                    }}
                    className="p-2.5 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-800/60 cursor-pointer text-xs flex justify-between items-center text-slate-700 dark:text-slate-300 font-medium"
                  >
                    <span>{c.first_name || ''} {c.last_name || ''}</span>
                    <span className="text-[10px] text-slate-400 font-mono">ID: {c.user_id}</span>
                  </div>
                ))
              )}
            </div>
          </div>
        )}
      </div>

      {/* Primary Workspace Panel */}
      <div className="flex-grow grid grid-cols-1 md:grid-cols-12 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800/80 rounded-3xl overflow-hidden shadow-2xl min-h-[550px]">
        
        {/* Left Side Pane: Threads List */}
        <div className="md:col-span-4 border-r border-slate-200 dark:border-slate-800/80 flex flex-col h-full bg-slate-50/50 dark:bg-slate-900/50">
          <div className="p-4 border-b border-slate-200 dark:border-slate-800/80 flex items-center justify-between gap-3 bg-white dark:bg-slate-900">
            <span className="font-bold text-slate-800 dark:text-slate-200 text-sm">Customer Conversations</span>
            <AnalyticsButton trackingName="button_click_admin_messaging_view_02"
              disabled={!selectedCustomerId}
              onClick={() => {
                setIsComposing(true);
                setActiveThreadId(null);
              }}
              className="p-2 py-1.5 text-xs font-semibold rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-200 hover:bg-emerald-50 dark:hover:bg-emerald-950/30 hover:text-emerald-600 dark:hover:text-emerald-400 transition-all flex items-center gap-1 cursor-pointer border border-slate-200 dark:border-slate-700/50 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>New Thread</span>
            </AnalyticsButton>
          </div>

          {selectedCustomerId && Object.keys(threads).length > 0 && (
            <div className="p-3 bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800/80 relative">
              <Search className="absolute left-6 top-5 w-3.5 h-3.5 text-slate-400" />
              <input
                type="text"
                placeholder="Filter by Thread ID..."
                value={threadSearchQuery}
                onChange={(e) => setThreadSearchQuery(e.target.value)}
                className="w-full pl-9 pr-4 py-1.5 text-xs rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none"
              />
            </div>
          )}

          {/* List Wrapper */}
          <div className="flex-grow overflow-y-auto divide-y divide-slate-100 dark:divide-slate-800/50 max-h-[550px]">
            {!selectedCustomerId ? (
              <div className="flex flex-col items-center justify-center text-center py-20 px-4 text-slate-400 gap-3">
                <User className="w-8 h-8 text-slate-300 dark:text-slate-700" />
                <div className="text-xs font-semibold text-slate-500">No Customer Selected</div>
                <p className="text-[11px] text-slate-400 max-w-[220px]">
                  Choose a customer account from the dropdown menu above to browse their message threads.
                </p>
              </div>
            ) : isLoadingMessages ? (
              <div className="flex flex-col items-center justify-center py-20 text-slate-400 gap-2">
                <Loader2 className="w-6 h-6 animate-spin text-emerald-500" />
                <span className="text-xs">Loading conversations...</span>
              </div>
            ) : Object.keys(threads).length === 0 ? (
              <div className="flex flex-col items-center justify-center text-center py-20 px-4 text-slate-400 gap-3">
                <MessageSquare className="w-8 h-8 text-slate-300 dark:text-slate-700" />
                <div className="text-xs font-semibold text-slate-500">No active conversations</div>
                <p className="text-[11px] text-slate-400 max-w-[200px]">
                  Click "New Thread" above to draft the first support message.
                </p>
              </div>
            ) : filteredThreads.length === 0 ? (
              <div className="flex flex-col items-center justify-center text-center py-20 px-4 text-slate-400 gap-2 select-none">
                <Search className="w-6 h-6 text-slate-300 dark:text-slate-700 animate-pulse" />
                <div className="text-xs font-semibold text-slate-500">No matching threads</div>
                <p className="text-[11px] text-slate-400 max-w-[180px]">
                  Adjust your search keyword to find the Thread ID.
                </p>
              </div>
            ) : (
              filteredThreads.map((thread) => {
                  const isActive = activeThreadId === thread.thread_id;
                  const hasUnread = thread.messages.some((msg) => msg.sender === 'user' && !msg.is_agent_read);
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
                        fetchCustomerMessages(selectedCustomerId, true);
                      }}
                    >
                      <div className="flex-grow overflow-hidden text-left">
                        <div className="flex items-center justify-between gap-2">
                          <span className={`px-2 py-0.5 text-[9px] font-bold tracking-wider uppercase rounded-full border ${getCategoryStyle(thread.category)}`}>
                            {thread.category}
                          </span>
                          <div className="flex items-center gap-1.5 shrink-0">
                            {hasUnread && (
                              <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                            )}
                            <span className="text-[10px] text-slate-400">
                              {formatTime(thread.lastMessageAt)}
                            </span>
                          </div>
                        </div>

                        <p className={`text-xs truncate mt-2 pr-2 ${hasUnread ? 'text-slate-900 dark:text-white font-bold' : 'text-slate-600 dark:text-slate-450 font-medium'}`}>
                          {thread.lastMessageText}
                        </p>
                      </div>

                      <AnalyticsButton trackingName="button_click_admin_messaging_view_03"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDeleteThread(thread.thread_id);
                        }}
                        className="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg bg-red-50 dark:bg-red-950/20 hover:bg-red-100 dark:hover:bg-red-950/50 text-red-500 transition-all cursor-pointer"
                        title="Delete Thread"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </AnalyticsButton>
                    </div>
                  );
                })
            )}
          </div>
        </div>

        {/* Right Side Pane: Chat View / Compose Form */}
        <div className="md:col-span-8 flex flex-col h-full bg-white dark:bg-slate-900 relative">
          
          {/* Form: Compose New Thread */}
          {isComposing && (
            <div className="flex flex-col h-full p-6 text-left">
              <div className="flex items-center gap-3 mb-6 pb-4 border-b border-slate-100 dark:border-slate-800/50">
                <AnalyticsButton trackingName="button_click_admin_messaging_view_04" 
                  onClick={() => setIsComposing(false)}
                  className="p-1.5 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 transition-colors"
                >
                  <ArrowLeft className="w-4 h-4" />
                </AnalyticsButton>
                <span className="font-bold text-slate-800 dark:text-slate-100">Send New Secure Thread to Customer</span>
              </div>

              <form onSubmit={handleStartThread} className="space-y-6 flex-grow flex flex-col">
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

                <div className="p-4 bg-slate-50 dark:bg-slate-950 rounded-2xl border border-slate-100 dark:border-slate-800/50 flex-grow flex flex-col">
                  <label htmlFor="message" className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                    Your Support Message
                  </label>
                  <textarea
                    id="message"
                    rows={8}
                    value={newText}
                    onChange={(e) => setNewText(e.target.value)}
                    placeholder="Write your secure message to the customer here..."
                    className="w-full p-3 text-sm rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500 transition-all resize-none flex-grow"
                    required
                  />
                </div>

                <div className="flex justify-end gap-3 pt-4 border-t border-slate-100 dark:border-slate-800/50">
                  <AnalyticsButton trackingName="button_click_admin_messaging_view_05"
                    type="button"
                    onClick={() => setIsComposing(false)}
                    className="px-6 py-2.5 text-sm font-semibold rounded-full bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 transition-all cursor-pointer"
                  >
                    Cancel
                  </AnalyticsButton>
                  <AnalyticsButton trackingName="button_click_admin_messaging_view_06"
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
                  </AnalyticsButton>
                </div>
              </form>
            </div>
          )}

          {/* Chat History View */}
          {!isComposing && activeThreadId && threads[activeThreadId] && (
            <div className="flex flex-col h-full max-h-[550px] text-left">
              {/* Header */}
              <div className="p-4 border-b border-slate-200 dark:border-slate-800/80 flex items-center justify-between gap-4 bg-slate-50/20 dark:bg-slate-950/20">
                <div className="flex items-center gap-3">
                  <span className={`px-2.5 py-0.5 text-[10px] font-bold tracking-wider uppercase rounded-full border ${getCategoryStyle(threads[activeThreadId].category)}`}>
                    {threads[activeThreadId].category}
                  </span>
                  <div className="flex items-center gap-1.5 text-xs text-slate-400 dark:text-slate-500">
                    <span>Thread ID: {activeThreadId}</span>
                    <AnalyticsButton trackingName="button_click_admin_messaging_view_07"
                      onClick={handleCopyThreadId}
                      className="p-1 rounded-md hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 transition-colors cursor-pointer"
                      title="Copy Thread ID"
                    >
                      {copiedThreadId ? (
                        <Check className="w-3.5 h-3.5 text-emerald-500" />
                      ) : (
                        <Copy className="w-3.5 h-3.5" />
                      )}
                    </AnalyticsButton>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <AnalyticsButton trackingName="button_click_admin_messaging_view_08"
                    onClick={() => fetchCustomerMessages(selectedCustomerId, true)}
                    className="p-1.5 rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-500 dark:text-slate-400 transition-colors cursor-pointer flex items-center justify-center"
                    title="Refresh Messages"
                  >
                    <RefreshCw className="w-4 h-4" />
                  </AnalyticsButton>
                  <AnalyticsButton trackingName="button_click_admin_messaging_view_09"
                    onClick={() => handleDeleteThread(activeThreadId)}
                    className="p-1.5 rounded-lg bg-red-50 dark:bg-red-950/20 hover:bg-red-100 dark:hover:bg-red-950/50 text-red-500 transition-colors cursor-pointer flex items-center justify-center"
                    title="Delete Thread"
                  >
                    <Trash2 className="w-4 h-4" />
                  </AnalyticsButton>
                </div>
              </div>

              {/* Message bubbles (User left, bank right) */}
              <div ref={chatContainerRef} className="flex-grow overflow-y-auto p-4 space-y-4 max-h-[350px]">
                {threads[activeThreadId].messages.map((msg, index) => {
                  const isUser = msg.sender === 'user'; // User/customer sent
                  const showDateLine = index === 0 || 
                    new Date(threads[activeThreadId].messages[index - 1].created_at).toDateString() !== new Date(msg.created_at).toDateString();

                  return (
                    <div key={msg.message_id} className="space-y-2">
                      {showDateLine && (
                        <div className="flex items-center justify-center py-2">
                          <div className="px-3 py-1 rounded-full bg-slate-100 dark:bg-slate-800 text-[10px] font-bold text-slate-400 dark:text-slate-500 flex items-center gap-1 border border-slate-200/40 dark:border-slate-700/40">
                            <Calendar className="w-3 h-3" />
                            <span>{formatDate(msg.created_at)}</span>
                          </div>
                        </div>
                      )}

                      <div className={`flex ${!isUser ? 'justify-end' : 'justify-start'} items-end gap-2 group`}>
                        {isUser && (
                          <div className="w-7 h-7 rounded-full bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 flex items-center justify-center text-slate-550 shrink-0 shadow-sm font-bold text-[10px]">
                            U
                          </div>
                        )}

                        <div className="max-w-[80%] flex flex-col relative">
                          <div
                            className={`p-3.5 rounded-2xl text-xs leading-relaxed font-medium shadow-sm ${
                              !isUser
                                ? 'text-slate-950 rounded-br-sm'
                                : 'bg-slate-100 dark:bg-slate-800/80 text-slate-800 dark:text-slate-200 rounded-bl-sm border border-slate-200/50 dark:border-slate-700/50'
                            }`}
                            style={!isUser ? {
                              backgroundImage: `linear-gradient(to top right, ${brandColorFrom}, ${brandColorTo})`,
                            } : {}}
                          >
                            <p className="whitespace-pre-line break-words">{msg.message}</p>
                          </div>
                          <span className={`text-[9px] text-slate-400 mt-1 ${!isUser ? 'text-right pr-1' : 'text-left pl-1'}`}>
                            {formatTime(msg.created_at)}
                          </span>
                        </div>

                        <AnalyticsButton trackingName="button_click_admin_messaging_view_10"
                          onClick={() => handleDeleteMessage(msg.message_id)}
                          className="opacity-0 group-hover:opacity-100 p-1 rounded-md bg-slate-50 dark:bg-slate-800 text-slate-400 hover:text-red-500 transition-all cursor-pointer"
                          title="Delete message"
                        >
                          <Trash2 className="w-3 h-3" />
                        </AnalyticsButton>
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Chat Input form */}
              <form onSubmit={handleSendReply} className="p-4 border-t border-slate-200 dark:border-slate-800/80 flex gap-3 bg-white dark:bg-slate-900">
                <textarea
                  rows={1}
                  value={replyText}
                  onChange={(e) => setReplyText(e.target.value)}
                  placeholder="Write your support response to the customer..."
                  className="flex-grow p-3 text-xs rounded-2xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500 transition-all resize-none max-h-[80px]"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      handleSendReply(e);
                    }
                  }}
                  required
                />
                <AnalyticsButton trackingName="button_click_admin_messaging_view_11"
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
                </AnalyticsButton>
              </form>
            </div>
          )}

          {/* Empty State */}
          {!isComposing && !activeThreadId && (
            <div className="flex flex-col items-center justify-center text-center p-8 py-20 text-slate-400 gap-4 flex-grow h-full select-none">
              <div className="w-16 h-16 rounded-3xl bg-slate-50 dark:bg-slate-950 border border-slate-100 dark:border-slate-800/50 flex items-center justify-center shadow-lg text-slate-300 dark:text-slate-800 animate-pulse">
                <Shield className="w-8 h-8 text-emerald-500/40 dark:text-emerald-500/20" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-slate-700 dark:text-slate-300">Support Communications Panel</h3>
                <p className="text-xs text-slate-400 dark:text-slate-500 max-w-sm mt-1.5 leading-relaxed">
                  Select a customer thread on the left panel or click "New Thread" to draft a new support request to the customer.
                </p>
              </div>
              <AnalyticsButton trackingName="button_click_admin_messaging_view_12"
                disabled={!selectedCustomerId}
                onClick={() => setIsComposing(true)}
                className="mt-2 px-5 py-2 text-xs font-semibold rounded-full text-slate-950 shadow-lg hover:scale-105 active:scale-95 transition-all cursor-pointer flex items-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed"
                style={{
                  backgroundImage: `linear-gradient(to right, ${brandColorFrom}, ${brandColorTo})`,
                  boxShadow: `0 8px 12px -3px ${brandColorFrom}25`
                }}
              >
                <Plus className="w-4 h-4" />
                <span>Compose message</span>
              </AnalyticsButton>
            </div>
          )}

        </div>
      </div>
    </section>
  );
}

export default AdminMessagingView;
