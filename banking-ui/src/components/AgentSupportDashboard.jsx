import React, { useState, useEffect, useRef, useMemo } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Room, RoomEvent } from 'livekit-client';
import { 
  Phone, 
  PhoneOff, 
  User, 
  AlertCircle, 
  ArrowRight, 
  CheckCircle2, 
  Volume2, 
  Sparkles, 
  MousePointerClick,
  ExternalLink,
  ArrowLeft
} from 'lucide-react';
import GoogleCloudIcon from './icons/GoogleCloudIcon.jsx';
import GoogleCompassIcon from './icons/GoogleCompassIcon.jsx';
import GcpInfoModal from './GcpInfoModal.jsx';
import { showInfoModals } from '../utils/constants.js';
import { useSettings } from '../context/SettingsContext.jsx';
import { Joyride, STATUS, EVENTS, ACTIONS } from 'react-joyride';
import { getJoyrideStyles } from '../utils/joyrideStyles.js';
import { 
  getPendingEscalations, 
  getAgentVoiceToken,
  getCreditCardAccount,
  getCreditCardTransactions,
  reverseCreditCardFee,
  updateCreditCardLimit,
  blockCreditCard,
  completeEscalation
} from '../utils/api.js';
import { DataChannelEvent } from '../utils/constants.js';

export default function AgentSupportDashboard() {
  const { brandColorFrom, resolvedTheme } = useSettings();
  const navigate = useNavigate();
  const location = useLocation();

  // Joyride Tour States
  const [tourRun, setTourRun] = useState(false);
  const [tourKey, setTourKey] = useState(0);
  const [domReady, setDomReady] = useState(false);

  useEffect(() => {
    const isCompleted = localStorage.getItem('supervisor-tour-completed') === 'true';
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
      if (document.querySelector('#supervisor-tour-btn')) {
        setDomReady(true);
        clearInterval(checkElement);
      }
    }, 50);
    return () => clearInterval(checkElement);
  }, []);

  const steps = useMemo(() => {
    return [
      {
        target: '#supervisor-tour-btn',
        content: "Welcome to the Supervisor Takeover Console! Here, you can monitor ongoing customer-to-AI support sessions and step in via WebRTC voice handoffs.",
        placement: 'bottom-end',
        skipBeacon: true
      },
      {
        target: '#inbound-request-queue',
        content: "Inbound Request Queue: Real-time list of customers requesting escalation. Click on a customer card to inspect their context.",
        placement: 'right',
        skipBeacon: true
      },
      {
        target: '#takeover-session-header',
        content: "Takeover Controller: Connect live voice rooms by clicking 'Accept Takeover' once a customer thread is selected.",
        placement: 'bottom',
        skipBeacon: true
      },
      {
        target: '#live-chat-history',
        content: "Live Chat Transcript: Review all messages exchanged between the customer and the Gemini AI agent before escalation.",
        placement: 'top',
        skipBeacon: true
      },
      {
        target: '#cobrowse-control-panel',
        content: "Co-Browsing Panel: Highlight transactions or reverse fees to guide the customer. Changes sync instantly on their viewport.",
        placement: 'top',
        skipBeacon: true
      },
      {
        target: '#supervisor-quick-actions',
        content: "Supervisor Quick Actions: Direct admin commands to freeze cards or adjust credit limits immediately.",
        placement: 'top',
        skipBeacon: true
      }
    ];
  }, []);
  const [escalations, setEscalations] = useState([]);
  const [selectedEscalation, setSelectedEscalation] = useState(null);
  const [isInfoModalOpen, setIsInfoModalOpen] = useState(false);
  
  const [isConnected, setIsConnected] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [activeRoomName, setActiveRoomName] = useState('');
  const [errorMessage, setErrorMessage] = useState('');
  
  const [isProcessing, setIsProcessing] = useState(false);
  const [limitInput, setLimitInput] = useState('');
  const [successMessage, setSuccessMessage] = useState('');
  const [customerAccount, setCustomerAccount] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [highlightedTxId, setHighlightedTxId] = useState(null);
  
  const roomRef = useRef(null);

  // Poll for pending escalations every 3 seconds
  useEffect(() => {
    async function fetchEscalations() {
      try {
        const data = await getPendingEscalations();
        setEscalations(data);
      } catch (err) {
        console.error('Failed to poll escalations:', err);
      }
    }

    fetchEscalations();
    const interval = setInterval(fetchEscalations, 3000);
    return () => clearInterval(interval);
  }, []);

  // Fetch transactions and account details for the customer when selected
  useEffect(() => {
    if (selectedEscalation) {
      const targetId = selectedEscalation.customer_id;
      
      // Clear messages
      setErrorMessage('');
      setSuccessMessage('');

      getCreditCardAccount(targetId)
        .then(setCustomerAccount)
        .catch(err => console.error('Failed to load user account:', err));

      getCreditCardTransactions(targetId)
        .then(setTransactions)
        .catch(err => console.error('Failed to load user transactions:', err));
    } else {
      setTransactions([]);
      setCustomerAccount(null);
      setLimitInput('');
      setErrorMessage('');
      setSuccessMessage('');
    }
  }, [selectedEscalation]);

  const handleReverseFee = async (txId) => {
    if (isProcessing || !selectedEscalation) return;
    setIsProcessing(true);
    setErrorMessage('');
    setSuccessMessage('');
    try {
      const targetId = selectedEscalation.customer_id;
      await reverseCreditCardFee(txId, targetId);
      setSuccessMessage('Fee reversal posted successfully.');
      // Refresh transactions and account profile
      const txs = await getCreditCardTransactions(targetId);
      setTransactions(txs);
      const acc = await getCreditCardAccount(targetId);
      setCustomerAccount(acc);
      
      // Broadcast real-time update to customer via LiveKit data channel
      if (roomRef.current) {
        const encoder = new TextEncoder();
        const payload = encoder.encode(JSON.stringify({
          type: DataChannelEvent.FEE_REVERSED,
          cleared_balance_cents: acc.cleared_balance_cents,
          available_credit_cents: acc.available_credit_cents
        }));
        await roomRef.current.localParticipant.publishData(payload);
      }
    } catch (err) {
      setErrorMessage(err.response?.data?.detail || 'Failed to reverse fee.');
    } finally {
      setIsProcessing(false);
    }
  };

  const handleFreezeCard = async () => {
    if (isProcessing || !selectedEscalation || !customerAccount?.cards?.[0]) return;
    setIsProcessing(true);
    setErrorMessage('');
    setSuccessMessage('');
    try {
      const targetId = selectedEscalation.customer_id;
      const cardToken = customerAccount.cards[0].card_token;
      await blockCreditCard(cardToken, targetId);
      setSuccessMessage('Card blocked successfully.');
      const acc = await getCreditCardAccount(targetId);
      setCustomerAccount(acc);
      
      // Broadcast real-time update to customer via LiveKit data channel
      if (roomRef.current) {
        const encoder = new TextEncoder();
        const payload = encoder.encode(JSON.stringify({
          type: DataChannelEvent.CARD_STATUS_LOCK,
          status: 'BLOCKED'
        }));
        await roomRef.current.localParticipant.publishData(payload);
      }
    } catch (err) {
      setErrorMessage(err.response?.data?.detail || 'Failed to block card.');
    } finally {
      setIsProcessing(false);
    }
  };

  const handleUpdateLimit = async () => {
    if (isProcessing || !selectedEscalation || !limitInput) return;
    setIsProcessing(true);
    setErrorMessage('');
    setSuccessMessage('');
    try {
      const targetId = selectedEscalation.customer_id;
      const limitCents = Math.round(parseFloat(limitInput) * 100);
      await updateCreditCardLimit(limitCents, targetId);
      setSuccessMessage(`Credit limit updated to $${limitInput} successfully.`);
      setLimitInput('');
      const acc = await getCreditCardAccount(targetId);
      setCustomerAccount(acc);
      
      // Broadcast real-time update to customer via LiveKit data channel
      if (roomRef.current) {
        const encoder = new TextEncoder();
        const payload = encoder.encode(JSON.stringify({
          type: DataChannelEvent.LIMIT_UPDATED,
          credit_limit_cents: acc.credit_limit_cents,
          available_credit_cents: acc.available_credit_cents
        }));
        await roomRef.current.localParticipant.publishData(payload);
      }
    } catch (err) {
      setErrorMessage(err.response?.data?.detail || 'Failed to update credit limit.');
    } finally {
      setIsProcessing(false);
    }
  };

  // Clean up Room on unmount
  useEffect(() => {
    return () => {
      if (roomRef.current) {
        roomRef.current.disconnect();
      }
    };
  }, []);

  const acceptCall = async (esc) => {
    if (isConnecting || isConnected) return;
    setIsConnecting(true);
    setErrorMessage('');
    
    try {
      // 1. Fetch agent room token from backend
      const { token, room_name } = await getAgentVoiceToken(esc.room_name);
      setActiveRoomName(room_name);
      
      // 2. Initialize LiveKit Room
      const room = new Room({
        adaptiveStream: true,
        dynacast: true,
      });
      roomRef.current = room;

      // 3. Setup track subscription listeners to route customer audio
      room.on(RoomEvent.TrackSubscribed, (track) => {
        if (track.kind === 'audio') {
          console.log('Subscribed to customer audio track');
          const element = track.attach();
          document.body.appendChild(element);
        }
      });

      room.on(RoomEvent.Disconnected, () => {
        setIsConnected(false);
        setSelectedEscalation(null);
        setActiveRoomName('');
        // Mark the escalation request as successfully completed in database
        completeEscalation(esc.id).catch(err => {
          console.error(`Failed to mark escalation ${esc.id} as completed on disconnect:`, err);
        });
      });

      // 4. Connect to the room
      const livekitUrl = window.env?.LIVEKIT_URL || "ws://localhost:7880";
      await room.connect(livekitUrl, token);
      console.log(`Agent connected to room: ${room_name}`);

      // 5. Publish microphone audio to speak to customer
      await room.localParticipant.setMicrophoneEnabled(true);

      setIsConnected(true);
    } catch (err) {
      console.error('Failed to connect agent to room:', err);
      setErrorMessage('Failed to connect to the active WebRTC room.');
    } finally {
      setIsConnecting(false);
    }
  };

  const endCall = () => {
    if (roomRef.current) {
      // Broadcast session end signal to client
      const encoder = new TextEncoder();
      const payload = encoder.encode(JSON.stringify({ type: DataChannelEvent.SESSION_END }));
      roomRef.current.localParticipant.publishData(payload);
      
      roomRef.current.disconnect();
      roomRef.current = null;
    }
    setIsConnected(false);
    setSelectedEscalation(null);
    setActiveRoomName('');
  };

  const highlightTransaction = async (txId) => {
    if (!roomRef.current) return;
    try {
      console.log('Publishing highlight transaction payload for ID:', txId);
      const encoder = new TextEncoder();
      const payload = encoder.encode(JSON.stringify({
        type: DataChannelEvent.HIGHLIGHT_TRANSACTION,
        id: txId
      }));
      await roomRef.current.localParticipant.publishData(payload);
      setHighlightedTxId(txId);
      
      setTimeout(() => {
        setHighlightedTxId(null);
      }, 4000);
    } catch (err) {
      console.error('Failed to send data channel co-browse payload:', err);
    }
  };

  return (
    <div className="relative pt-24 pb-16 md:pt-28 md:pb-24 px-6 max-w-7xl mx-auto min-h-[calc(100vh-80px)] flex flex-col justify-between text-slate-800 dark:text-slate-100">
      
      {/* Header section */}
      <div className="mb-6 flex justify-between items-center border-b border-slate-200 dark:border-slate-805 pb-4 w-full">
        <div>
          <button 
            onClick={() => navigate('/admin')}
            className="inline-flex items-center gap-2 text-sm font-medium text-slate-500 hover:text-slate-900 dark:hover:text-white transition-colors mb-3 group"
          >
            <ArrowLeft className="w-4 h-4 group-hover:-translate-x-1 transition-transform" />
            Back to Admin Portal
          </button>
          <h1 className="text-3xl font-extrabold tracking-tight bg-gradient-to-r from-slate-900 via-slate-705 to-slate-500 dark:from-white dark:via-slate-200 dark:to-slate-400 bg-clip-text text-transparent">
            Supervisor Takeover Dashboard
          </h1>
          <p className="text-slate-500 dark:text-slate-450 mt-1 text-sm">
            Monitor active credit support AI sessions and execute sub-second live human takeover.
          </p>
        </div>
        
        <div className="flex items-center gap-3">
          <button
            id="supervisor-tour-btn"
            onClick={() => {
              localStorage.removeItem('supervisor-tour-completed');
              setTourKey(prev => prev + 1);
              setTourRun(true);
            }}
            className="p-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-500 hover:text-slate-900 dark:hover:text-white transition-all active:scale-95 cursor-pointer flex items-center justify-center"
            title="Take Supervisor Console Tour"
          >
            <GoogleCompassIcon className="w-4 h-4 text-emerald-500" />
          </button>
          {isConnected && (
            <div className="bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-500/50 rounded-full px-4 py-1.5 text-xs text-emerald-600 dark:text-emerald-300 font-bold flex items-center gap-2 animate-pulse">
              <Volume2 size={14} className="text-emerald-505 dark:text-emerald-400" />
              Live Voice Room: {activeRoomName}
            </div>
          )}
          {showInfoModals() && (
            <button
              onClick={() => setIsInfoModalOpen(true)}
              className="p-2.5 rounded-2xl hover:bg-slate-800/80 border border-slate-200 dark:border-slate-850 bg-white dark:bg-slate-900 shadow-sm text-slate-400 hover:text-slate-200 transition-all active:scale-95 cursor-pointer flex items-center justify-center"
              title="GCP Co-Browse Integration Info"
            >
              <GoogleCloudIcon className="w-5 h-5 text-indigo-400" />
            </button>
          )}
        </div>
      </div>

      {errorMessage && (
        <div className="bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-505/50 rounded-xl p-4 flex items-center gap-3 mb-6">
          <AlertCircle className="text-red-500 dark:text-red-400 flex-shrink-0" />
          <span className="text-red-700 dark:text-red-200 text-sm">{errorMessage}</span>
        </div>
      )}

      {successMessage && (
        <div className="bg-emerald-50 dark:bg-emerald-900/30 border border-emerald-200 dark:border-emerald-500/50 rounded-xl p-4 flex items-center gap-3 mb-6">
          <CheckCircle2 className="text-emerald-500 dark:text-emerald-400 flex-shrink-0" size={20} />
          <span className="text-emerald-700 dark:text-emerald-200 text-sm">{successMessage}</span>
        </div>
      )}

      {/* Main Grid View */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 items-stretch flex-grow mb-8">
        
        {/* Left Panel: Pending Escalations Queue */}
        <div className="bg-white dark:bg-slate-900/50 backdrop-blur border border-slate-200 dark:border-slate-800 rounded-3xl p-6 flex flex-col justify-between min-h-[500px] shadow-sm" id="inbound-request-queue">
          <div>
            <h2 className="text-md font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-4 border-b border-slate-200 dark:border-slate-805 pb-2">
              Inbound Request Queue ({escalations.length})
            </h2>
            
            <div className="space-y-3 max-h-[400px] overflow-y-auto pr-1">
              {escalations.length === 0 ? (
                <div className="text-center py-12 text-slate-500 italic">
                  <CheckCircle2 size={36} className="mx-auto text-emerald-500/50 mb-3" />
                  No pending escalations. All clear!
                </div>
              ) : (
                escalations.map((esc) => (
                  <div 
                    key={esc.id}
                    onClick={() => !isConnected && setSelectedEscalation(esc)}
                    className={`p-4 rounded-2xl border text-sm cursor-pointer transition-all duration-300 ${
                      selectedEscalation?.id === esc.id 
                        ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-950/20 text-slate-900 dark:text-slate-100' 
                        : 'border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/30 hover:border-slate-300 dark:hover:border-slate-700'
                    } ${isConnected ? 'opacity-50 cursor-not-allowed' : ''}`}
                  >
                    <div className="flex justify-between items-start mb-2">
                      <span className="font-bold text-slate-800 dark:text-slate-200 font-mono text-xs">{esc.customer_id}</span>
                      <span className="text-[10px] bg-red-50 dark:bg-red-950/50 text-red-600 dark:text-red-400 px-2 py-0.5 rounded border border-red-200 dark:border-red-800/30 font-bold uppercase tracking-wider">
                        Needs Help
                      </span>
                    </div>
                    <p className="text-xs text-slate-600 dark:text-slate-400 line-clamp-2 italic mb-2">"{esc.reason}"</p>
                    <div className="flex justify-between items-center text-[10px] text-slate-400 dark:text-slate-500">
                      <span>Room: {esc.room_name}</span>
                      <span>{new Date(esc.created_at).toLocaleTimeString()}</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {/* Center Panel: Transcript & Accept Handoff */}
        <div className="bg-white dark:bg-slate-900/50 backdrop-blur border border-slate-200 dark:border-slate-800 rounded-3xl p-6 flex flex-col justify-between min-h-[500px] lg:col-span-2 shadow-sm">
          {selectedEscalation ? (
            <div className="flex flex-col justify-between h-full gap-6">
              
              {/* Top metadata info */}
              <div className="flex justify-between items-start border-b border-slate-200 dark:border-slate-800 pb-4" id="takeover-session-header">
                <div>
                  <h3 className="text-lg font-bold text-slate-900 dark:text-slate-200">Session Context: {selectedEscalation.customer_id}</h3>
                  <p className="text-xs text-indigo-600 dark:text-indigo-400 mt-0.5 font-semibold">Escalation Reason: {selectedEscalation.reason}</p>
                </div>
                
                {!isConnected ? (
                  <button
                    onClick={() => acceptCall(selectedEscalation)}
                    disabled={isConnecting}
                    className="flex items-center gap-2 px-6 py-2.5 rounded-full font-bold shadow-lg shadow-indigo-500/20 text-white bg-gradient-to-r from-indigo-600 to-blue-600 hover:from-indigo-500 hover:to-blue-500 transition-all transform active:scale-95 text-sm"
                  >
                    <Phone size={15} />
                    {isConnecting ? 'Connecting Representative...' : 'Accept Takeover'}
                  </button>
                ) : (
                  <button
                    onClick={endCall}
                    className="flex items-center gap-2 px-6 py-2.5 rounded-full font-bold shadow-lg shadow-red-500/20 text-white bg-red-600 hover:bg-red-500 transition-all transform active:scale-95 text-sm"
                  >
                    <PhoneOff size={15} />
                    Disconnect Session
                  </button>
                )}
              </div>

              {/* Grid content split: Live transcript and Ledger Co-browse */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 flex-grow items-stretch max-h-[350px] overflow-hidden">
                
                {/* Transcript feed */}
                <div className="flex flex-col border border-slate-200 dark:border-slate-800/80 rounded-2xl p-4 bg-slate-50/50 dark:bg-slate-950/20 overflow-y-auto max-h-[330px] scrollbar-thin" id="live-chat-history">
                  <span className="text-[10px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-3 block">Conversation History</span>
                  <div className="space-y-3">
                    {!selectedEscalation.transcript || selectedEscalation.transcript.length === 0 ? (
                      <p className="text-xs text-slate-500 italic">No chat history recorded.</p>
                    ) : (
                      selectedEscalation.transcript.map((msg, index) => {
                        const isUser = msg.author === 'user';
                        return (
                          <div key={index} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
                            <div className={`max-w-[85%] rounded-xl px-3 py-2 text-xs ${
                              isUser 
                                ? 'bg-indigo-605 text-white rounded-br-none' 
                                : 'bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-300 rounded-bl-none border border-slate-200 dark:border-slate-700/50'
                            }`}>
                              <p className="text-[8px] uppercase tracking-wide text-slate-400 dark:text-slate-500 font-bold mb-0.5">
                                {isUser ? 'Customer' : 'AI'}
                              </p>
                              <p className="leading-relaxed">{msg.text}</p>
                            </div>
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>

                {/* Ledger Interactive Co-browsing */}
                <div className="flex flex-col border border-slate-200 dark:border-slate-800/80 rounded-2xl p-4 bg-slate-50/50 dark:bg-slate-950/20 max-h-[330px]" id="cobrowse-control-panel">
                  <div className="flex items-center gap-1.5 mb-3">
                    <Sparkles size={13} className="text-yellow-500 dark:text-yellow-400 animate-pulse" />
                    <span className="text-[10px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Co-Browsing Control Panel</span>
                  </div>
                  
                  <div className="space-y-2 overflow-y-auto flex-grow pr-1 scrollbar-thin">
                    {!isConnected ? (
                      <div className="text-center py-12 text-slate-400 dark:text-slate-500 italic text-xs">
                        Accept the call to unlock co-browsing and highlight items.
                      </div>
                    ) : transactions.length === 0 ? (
                      <p className="text-xs text-slate-500 italic">No transactions available to highlight.</p>
                    ) : (
                      transactions.map((tx) => {
                        const isHighlighted = highlightedTxId === tx.id;
                        return (
                          <div 
                            key={tx.id}
                            className={`flex justify-between items-center p-2 rounded-xl border transition-all duration-300 ${
                              isHighlighted 
                                ? 'border-yellow-500 bg-yellow-500/10' 
                                : 'border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/30 text-slate-800 dark:text-slate-300'
                            }`}
                          >
                            <div className="max-w-[70%]">
                              <p className="font-semibold text-[11px] truncate">{tx.description}</p>
                              <span className="text-[9px] text-slate-400 dark:text-slate-500">${Math.abs(tx.amount_cents / 100).toFixed(2)}</span>
                            </div>
                            
                            <div className="flex gap-1.5">
                              <button
                                onClick={() => highlightTransaction(tx.id)}
                                className="p-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 active:scale-90 transition-all flex items-center gap-1 text-[10px] font-bold shadow-sm"
                              >
                                <MousePointerClick size={12} className="text-yellow-505 dark:text-yellow-400" />
                                Highlight
                              </button>
                              
                              {tx.amount_cents < 0 && (
                                <button
                                  onClick={() => handleReverseFee(tx.id)}
                                  disabled={isProcessing}
                                  className="p-1.5 rounded-lg border border-emerald-250 dark:border-emerald-800/80 bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-300 hover:bg-emerald-100 dark:hover:bg-emerald-900/40 disabled:opacity-50 disabled:cursor-not-allowed active:scale-90 transition-all text-[10px] font-bold shadow-sm"
                                >
                                  Reverse Charge
                                </button>
                              )}
                            </div>
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>

              </div>

              {/* Quick Actions Panel */}
              <div className="border-t border-slate-205 dark:border-slate-800 pt-4 mt-2" id="supervisor-quick-actions">
                <span className="text-[10px] font-bold text-slate-550 dark:text-slate-400 uppercase tracking-wider mb-3 block">Supervisor Quick Actions</span>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  
                  {/* Card Controls */}
                  <div className="flex items-center justify-between p-4 rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/30">
                    <div>
                      <h4 className="text-xs font-bold text-slate-800 dark:text-slate-200">Card Status Control</h4>
                      <p className="text-[10px] text-slate-500 dark:text-slate-400 mt-1">
                        Current Status: <span className={`font-mono font-bold ${customerAccount?.cards?.[0]?.status === 'ACTIVE' ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'}`}>
                          {customerAccount?.cards?.[0]?.status || 'ACTIVE'}
                        </span>
                      </p>
                    </div>
                    <button
                      onClick={handleFreezeCard}
                      disabled={isProcessing || customerAccount?.cards?.[0]?.status !== 'ACTIVE'}
                      className="px-4 py-2 rounded-xl text-xs font-bold border border-red-500/20 bg-red-50 dark:bg-red-950/20 text-red-600 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-900/20 disabled:opacity-50 disabled:cursor-not-allowed transition-all active:scale-95 shadow-sm"
                    >
                      Freeze Credit Card
                    </button>
                  </div>

                  {/* Limit Controls */}
                  <div className="flex items-center justify-between p-4 rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/30">
                    <div>
                      <h4 className="text-xs font-bold text-slate-800 dark:text-slate-200">Credit Limit Adjustment</h4>
                      <p className="text-[10px] text-slate-500 dark:text-slate-400 mt-1">
                        Current Limit: <span className="font-mono font-bold text-indigo-600 dark:text-indigo-400">
                          ${customerAccount ? (customerAccount.credit_limit_cents / 100).toFixed(2) : '0.00'}
                        </span>
                      </p>
                    </div>
                    
                    <div className="flex items-center gap-2">
                      <div className="relative">
                        <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[11px] text-slate-400 dark:text-slate-500 font-bold">$</span>
                        <input
                          type="number"
                          value={limitInput}
                          onChange={(e) => setLimitInput(e.target.value)}
                          placeholder="Amount"
                          disabled={isProcessing}
                          className="w-24 pl-5 pr-2 py-1.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 text-slate-800 dark:text-slate-200 text-xs font-mono focus:outline-none focus:border-slate-400 dark:focus:border-slate-700"
                        />
                      </div>
                      <button
                        onClick={handleUpdateLimit}
                        disabled={isProcessing || !limitInput}
                        className="px-4 py-2 rounded-xl text-xs font-bold text-white bg-indigo-650 hover:bg-indigo-500 disabled:bg-indigo-950/50 disabled:text-indigo-600 disabled:cursor-not-allowed transition-all active:scale-95 shadow-md"
                      >
                        Update
                      </button>
                    </div>

                  </div>

                </div>
              </div>

            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-slate-400 dark:text-slate-500 italic">
              <ArrowRight size={48} className="text-slate-300 dark:text-slate-600 mb-3 animate-pulse" />
              Select an active customer escalation from the queue to view context.
            </div>
          )}
        </div>

      </div>

      <GcpInfoModal
        isOpen={isInfoModalOpen}
        onClose={() => setIsInfoModalOpen(false)}
        title="WebRTC Handoff & Co-Browsing"
      >
        <div className="space-y-4 text-slate-600 dark:text-slate-400 text-sm leading-relaxed">
          <p>
            The <strong>Supervisor Takeover Console</strong> facilitates live WebRTC presenter handoff and co-browsing synchronization.
          </p>
          <p>
            When a customer requests escalation, the AI voice agent submits an escalation request to the database. The supervisor's browser polls the backend, claims the session, and requests a secure WebRTC token to join the customer's LiveKit room.
          </p>
          <p>
            Co-browsing features (such as highlighting transactions) are transmitted as sub-second JSON payloads directly over the WebRTC data channel, updating the customer's viewport immediately.
          </p>
          <div className="bg-slate-50 dark:bg-slate-950 p-4 rounded-2xl border border-slate-100 dark:border-slate-800 space-y-3">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h4 className="font-semibold text-slate-800 dark:text-slate-200 text-xs uppercase tracking-wider">LiveKit Console</h4>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">View real-time room sessions, active participants, and track distribution logs.</p>
              </div>
              <a
                href={`https://console.livekit.io`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-emerald-500 hover:text-emerald-600 font-semibold text-xs shrink-0 hover:underline"
              >
                <span>View Dashboard</span>
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
              localStorage.setItem('supervisor-tour-completed', 'true');
            }
          }}
          styles={getJoyrideStyles(resolvedTheme, brandColorFrom)}
        />
      )}

    </div>
  );
}
