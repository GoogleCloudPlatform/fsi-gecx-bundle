import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Send, AlertCircle, CheckCircle2, Loader2, Bell, Shield, Radio, ArrowLeft } from 'lucide-react';
import { useSettings } from '../context/SettingsContext.jsx';
import { getCustomersList, sendNotification } from '../utils/api.js';




function MessagingDebug({ fbUser, customerProfile }) {
  const navigate = useNavigate();
  const { brandColorFrom, brandColorTo } = useSettings();

  // Form Fields
  const [title, setTitle] = useState('New Support Message (Loans)');
  const [body, setBody] = useState('This is a message sent via the real FCM backend.');
  const [targetType, setTargetType] = useState('customer'); // customer | topic
  const [topic, setTopic] = useState('all');
  const [notificationType, setNotificationType] = useState('support_message');
  const [threadId, setThreadId] = useState('6551917e-0337-43ba-aa47-219dbe6a8057');

  // Customer selection list state
  const [customers, setCustomers] = useState([]);
  const [selectedCustomerIds, setSelectedCustomerIds] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoadingCustomers, setIsLoadingCustomers] = useState(false);

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);
  const [successMsg, setSuccessMsg] = useState(null);

  const fetchCustomers = useCallback(async () => {
    if (!fbUser) return;
    setIsLoadingCustomers(true);
    try {
      const data = await getCustomersList();
      setCustomers(data);
      
      // Select current user's customer ID by default
      if (customerProfile?.user_id) {
        const matched = data.find(c => c.user_id === customerProfile.user_id);
        if (matched) {
          setSelectedCustomerIds([customerProfile.user_id]);
        }
      }
    } catch (err) {
      console.error("Failed to fetch customers list:", err);
    } finally {
      setIsLoadingCustomers(false);
    }
  }, [fbUser, customerProfile]);

  useEffect(() => {
    fetchCustomers();
  }, [fetchCustomers]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMsg(null);
    setSuccessMsg(null);

    if (!title.trim()) {
      setErrorMsg('Title is required.');
      return;
    }
    if (!body.trim()) {
      setErrorMsg('Body/message content is required.');
      return;
    }
    if (targetType === 'customer' && selectedCustomerIds.length === 0) {
      setErrorMsg('Please select at least one target customer.');
      return;
    }
    if (targetType === 'topic' && !topic.trim()) {
      setErrorMsg('Topic name is required for topic targeted notifications.');
      return;
    }

    setIsSubmitting(true);

    const data = {
      title: title.trim(),
      body: body.trim()
    };
    if (notificationType) {
      data.type = notificationType.trim();
    }
    if (threadId) {
      data.thread_id = threadId.trim();
    }

    const payloads = [];

    if (targetType === 'customer') {
      selectedCustomerIds.forEach(cid => {
        const payload = { user_id: cid };
        const payloadData = { ...data, user_id: cid };
        payload.data = payloadData;
        payloads.push(payload);
      });
    } else {
      const payload = { 
        topic: topic.trim(),
        data: data 
      };
      payloads.push(payload);
    }

    try {
      const requests = payloads.map(payload =>
        sendNotification(payload)
          .then(() => ({ ok: true, payload }))
          .catch(err => ({ ok: false, payload, err }))
      );

      const responses = await Promise.all(requests);

      const failed = [];
      for (let i = 0; i < responses.length; i++) {
        if (!responses[i].ok) {
          const payloadTarget = payloads[i].user_id ? `Customer: ${payloads[i].user_id}` : `Topic: ${payloads[i].topic}`;
          failed.push(payloadTarget);
        }
      }

      if (failed.length > 0) {
        throw new Error(`Failed to send notifications to: ${failed.join(', ')}`);
      }

      setSuccessMsg(`FCM push notification request sent successfully to ${payloads.length} target(s)!`);
    } catch (err) {
      console.error('Error sending push notification:', err);
      setErrorMsg(err.message || 'An unexpected error occurred.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const filteredCustomers = customers.filter(c => {
    const fullName = `${c.first_name || ''} ${c.last_name || ''}`.toLowerCase();
    const id = (c.user_id || '').toLowerCase();
    const query = searchQuery.toLowerCase();
    return fullName.includes(query) || id.includes(query);
  });

  return (
    <section className="relative pt-24 pb-16 md:pt-28 md:pb-24 px-6 max-w-4xl mx-auto min-h-[calc(100vh-80px)] flex flex-col text-left">
      {/* Background ambient lighting */}
      <div className="absolute top-1/3 left-1/4 w-[450px] h-[450px] rounded-full bg-purple-500/10 blur-[120px] pointer-events-none -z-10 animate-pulse" />
      <div className="absolute top-1/2 right-1/4 w-[400px] h-[400px] rounded-full bg-pink-600/10 blur-[100px] pointer-events-none -z-10" />

      {/* Header Navigation */}
      <div className="mb-10 flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-200 dark:border-slate-800 pb-6">
        <div>
          <button 
            type="button"
            onClick={() => navigate('/admin')}
            className="inline-flex items-center gap-2 text-sm font-medium text-slate-500 hover:text-slate-900 dark:hover:text-white transition-colors mb-3 group"
          >
            <ArrowLeft className="w-4 h-4 group-hover:-translate-x-1 transition-transform" />
            Back to Admin Portal
          </button>
          <div className="flex items-center gap-3">
            <div className="p-3 rounded-2xl bg-gradient-to-br from-purple-500 to-pink-600 text-slate-950 flex items-center justify-center shadow-lg shadow-purple-500/20 animate-pulse">
              <Bell className="w-7 h-7" />
            </div>
            <div>
              <h1 className="text-3xl font-extrabold bg-gradient-to-r from-slate-900 via-slate-700 to-slate-500 dark:from-white dark:via-slate-200 dark:to-slate-400 bg-clip-text text-transparent">
                FCM Messaging Debug
              </h1>
              <p className="text-sm text-slate-505 dark:text-slate-400 mt-1">
                Test real Firebase Cloud Messages from the backend API.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Main card panel */}
      <div className="p-6 md:p-8 rounded-3xl bg-white/80 dark:bg-slate-900/80 border border-slate-200/80 dark:border-slate-800/80 backdrop-blur-xl shadow-xl shadow-slate-950/5 relative overflow-hidden">
        {/* Alerts */}
        {errorMsg && (
          <div className="mb-6 p-4 rounded-2xl bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800/30 text-red-600 dark:text-red-400 text-sm flex items-center gap-2.5 animate-shake">
            <AlertCircle className="w-5 h-5 shrink-0" />
            <span className="text-left">{errorMsg}</span>
          </div>
        )}

        {successMsg && (
          <div className="mb-6 p-4 rounded-2xl bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800/30 text-emerald-600 dark:text-emerald-400 text-sm flex items-center gap-2.5">
            <CheckCircle2 className="w-5 h-5 shrink-0 animate-bounce" />
            <span className="text-left">{successMsg}</span>
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-6 text-left">
          {/* Notification Title & Body */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="p-4 bg-slate-50 dark:bg-slate-950 rounded-2xl border border-slate-100 dark:border-slate-800/50">
              <label htmlFor="title" className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1.5">
                Notification Title
              </label>
              <div className="relative">
                <span className="absolute left-3 top-2.5 text-slate-400">
                  <Bell className="w-4 h-4" />
                </span>
                <input
                  id="title"
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="w-full pl-10 pr-4 py-2 text-sm rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500 transition-all"
                  required
                />
              </div>
            </div>

            <div className="p-4 bg-slate-50 dark:bg-slate-950 rounded-2xl border border-slate-100 dark:border-slate-800/50">
              <label htmlFor="targetType" className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1.5">
                Recipient Target
              </label>
              <div className="relative">
                <span className="absolute left-3 top-2.5 text-slate-400">
                  <Radio className="w-4 h-4" />
                </span>
                <select
                  id="targetType"
                  value={targetType}
                  onChange={(e) => setTargetType(e.target.value)}
                  className="w-full pl-10 pr-4 py-2 text-sm rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500 transition-all cursor-pointer"
                >
                  <option value="customer">Specific Customer(s)</option>
                  <option value="topic">Topic Broadcast</option>
                </select>
              </div>
            </div>
          </div>

          <div className="p-4 bg-slate-50 dark:bg-slate-950 rounded-2xl border border-slate-100 dark:border-slate-800/50">
            <label htmlFor="body" className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1.5">
              Notification Body / Message
            </label>
            <textarea
              id="body"
              rows={3}
              value={body}
              onChange={(e) => setBody(e.target.value)}
              className="w-full p-3 text-sm rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500 transition-all resize-none"
              required
            />
          </div>

          {/* Conditional Target Options */}
          {targetType === 'customer' ? (
            <div className="p-4 bg-slate-50 dark:bg-slate-950 rounded-2xl border border-slate-100 dark:border-slate-800/50 space-y-3">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-2 border-b border-slate-200/50 dark:border-slate-800/50">
                <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider">
                  Select Target Customers ({selectedCustomerIds.length} selected)
                </label>
                <input
                  type="text"
                  placeholder="Filter by name or ID..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="px-3 py-1 text-xs rounded-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-emerald-500/30 transition-all"
                />
              </div>

              <div className="h-44 overflow-y-auto border border-slate-200 dark:border-slate-800/50 rounded-xl p-3 bg-white dark:bg-slate-900 divide-y divide-slate-100 dark:divide-slate-800/40 space-y-1">
                {isLoadingCustomers ? (
                  <div className="flex items-center justify-center py-8 text-slate-400 gap-2">
                    <Loader2 className="w-4 h-4 animate-spin text-emerald-500" />
                    <span className="text-xs">Loading customer directory...</span>
                  </div>
                ) : filteredCustomers.length === 0 ? (
                  <div className="text-center py-8 text-xs text-slate-400">
                    No customers found matching your search.
                  </div>
                ) : (
                  filteredCustomers.map((c) => {
                    const isSelected = selectedCustomerIds.includes(c.user_id);
                    return (
                      <label 
                        key={c.user_id}
                        className="flex items-center justify-between py-2 cursor-pointer text-xs font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800/40 px-2 rounded-lg transition-colors"
                      >
                        <div className="flex items-center gap-2.5">
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => {
                              if (isSelected) {
                                setSelectedCustomerIds(selectedCustomerIds.filter(id => id !== c.user_id));
                              } else {
                                setSelectedCustomerIds([...selectedCustomerIds, c.user_id]);
                              }
                            }}
                            className="rounded border-slate-300 dark:border-slate-700 text-emerald-600 focus:ring-emerald-500 w-3.5 h-3.5"
                          />
                          <span>{c.first_name || ''} {c.last_name || ''}</span>
                        </div>
                        <span className="text-[10px] text-slate-400 dark:text-slate-500 font-mono">ID: {c.user_id}</span>
                      </label>
                    );
                  })
                )}
              </div>

              <div className="flex gap-3 justify-end pt-1">
                <button
                  type="button"
                  onClick={() => {
                    const idsToAdd = filteredCustomers.map(c => c.user_id);
                    const union = Array.from(new Set([...selectedCustomerIds, ...idsToAdd]));
                    setSelectedCustomerIds(union);
                  }}
                  className="text-[10px] font-bold text-slate-500 dark:text-slate-400 hover:text-emerald-500 transition-colors cursor-pointer"
                >
                  Select All Matches
                </button>
                <span className="text-[10px] text-slate-300 dark:text-slate-700">|</span>
                <button
                  type="button"
                  onClick={() => setSelectedCustomerIds([])}
                  className="text-[10px] font-bold text-slate-500 dark:text-slate-400 hover:text-red-500 transition-colors cursor-pointer"
                >
                  Clear Selection
                </button>
              </div>
            </div>
          ) : (
            <div className="p-4 bg-slate-50 dark:bg-slate-950 rounded-2xl border border-slate-100 dark:border-slate-800/50">
              <label htmlFor="topic" className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1.5">
                Target Topic Name
              </label>
              <div className="relative">
                <span className="absolute left-3 top-2.5 text-slate-400">
                  <Radio className="w-4 h-4" />
                </span>
                <input
                  id="topic"
                  type="text"
                  value={topic}
                  onChange={(e) => setTopic(e.target.value)}
                  className="w-full pl-10 pr-4 py-2 text-sm rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500 transition-all"
                  required
                />
              </div>
            </div>
          )}

          {/* Custom Metadata (Type & Thread ID) */}
          <div className="p-4 bg-slate-50 dark:bg-slate-950 rounded-2xl border border-slate-100 dark:border-slate-800/50">
            <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4 border-b border-slate-200/40 dark:border-slate-800/50 pb-2">Custom Notification Data Metadata (Optional)</h3>
            
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label htmlFor="notificationType" className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">
                  Notification Type (e.g. support_message, alert)
                </label>
                <input
                  id="notificationType"
                  type="text"
                  value={notificationType}
                  onChange={(e) => setNotificationType(e.target.value)}
                  className="w-full p-2.5 text-xs rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500 transition-all"
                />
              </div>

              <div>
                <label htmlFor="threadId" className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">
                  Thread ID
                </label>
                <input
                  id="threadId"
                  type="text"
                  value={threadId}
                  onChange={(e) => setThreadId(e.target.value)}
                  className="w-full p-2.5 text-xs rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500 transition-all"
                />
              </div>
            </div>
          </div>

          {/* Submit CTA */}
          <div className="flex justify-end pt-4 border-t border-slate-100 dark:border-slate-800/50">
            <button
              type="submit"
              disabled={isSubmitting}
              className="px-6 py-2.5 text-sm font-semibold rounded-full text-slate-950 hover:scale-102 active:scale-98 transition-all flex items-center justify-center gap-2 shadow-lg cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
              style={{
                backgroundImage: `linear-gradient(to right, ${brandColorFrom}, ${brandColorTo})`,
                boxShadow: `0 10px 15px -3px ${brandColorFrom}30`
              }}
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Sending FCM Request...</span>
                </>
              ) : (
                <>
                  <Send className="w-4 h-4" />
                  <span>Send Notification</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </section>
  );
}

export default MessagingDebug;
