import React, { useState, useEffect, useRef } from 'react';
import { Room, RoomEvent } from 'livekit-client';
import { 
  Phone, 
  PhoneOff, 
  Mic, 
  MicOff, 
  Lock, 
  Unlock, 
  CreditCard,
  User,
  Calendar,
  AlertCircle,
  Video,
  VideoOff
} from 'lucide-react';
import { 
  getCreditCardAccount, 
  getCreditCardVoiceToken, 
  getCreditCardTransactions 
} from '../utils/api.js';
import { DataChannelEvent } from '../utils/constants.js';

export default function VoiceSupportView() {
  const [account, setAccount] = useState(null);
  const [cardStatus, setCardStatus] = useState('ACTIVE');
  const [creditLimit, setCreditLimit] = useState(0);
  const [availableCredit, setAvailableCredit] = useState(0);
  const [clearedBalance, setClearedBalance] = useState(0);
  const [transactions, setTransactions] = useState([]);
  const [transcripts, setTranscripts] = useState([]);
  
  const [isConnected, setIsConnected] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [micEnabled, setMicEnabled] = useState(true);
  const [errorMessage, setErrorMessage] = useState('');
  
  const [isHumanAgentActive, setIsHumanAgentActive] = useState(false);
  const [humanAgentName, setHumanAgentName] = useState('');
  const [highlightedTxId, setHighlightedTxId] = useState(null);
  
  const [mode, setMode] = useState('audio');
  const [warningMessage, setWarningMessage] = useState('');
  const [timeRemaining, setTimeRemaining] = useState(0);
  const [agentVideoTrack, setAgentVideoTrack] = useState(null);
  const [videoLoaded, setVideoLoaded] = useState(false);
  const [avatarName, setAvatarName] = useState('Sam');
  const [agentMode, setAgentMode] = useState(null);

  const roomRef = useRef(null);
  const chatContainerRef = useRef(null);
  const disconnectTimerRef = useRef(null);

  // Load account data and transactions on mount
  useEffect(() => {
    async function loadData() {
      try {
        const data = await getCreditCardAccount();
        setAccount(data);
        if (data.cards && data.cards.length > 0) {
          setCardStatus(data.cards[0].status);
        }
        setCreditLimit(data.credit_limit_cents / 100);
        setAvailableCredit(data.available_credit_cents / 100);
        setClearedBalance(data.cleared_balance_cents / 100);
        
        const txData = await getCreditCardTransactions();
        setTransactions(txData);
      } catch (err) {
        console.error('Failed to load card account profile:', err);
        setErrorMessage('Failed to connect to core banking service.');
      }
    }
    loadData();
  }, []);

  // Auto scroll transcript panel inside container
  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  }, [transcripts]);

  // Cleanup LiveKit room on unmount
  useEffect(() => {
    return () => {
      if (roomRef.current) {
        roomRef.current.disconnect();
      }
    };
  }, []);

  // Handle dynamically attaching/detaching the subscribed video track when the DOM element is mounted
  useEffect(() => {
    let attachedElement = null;
    
    // Exact crop alignments defined by user preference
    const AVATAR_POSITIONS = {
      'ingrid': 'center',
      'jay': 'center',
      'kira': 'center 20%',  // upper quarter (roughly 20-25% from top)
      'paul': 'center 20%',  // upper quarter
      'sam': 'center 20%',   // upper quarter
      'vera': 'center 20%'   // upper quarter
    };

    if (agentVideoTrack && isConnected) {
      const container = document.getElementById("avatar-video-container");
      if (container) {
        container.innerHTML = "";
        attachedElement = agentVideoTrack.attach();
        attachedElement.id = "agent-video-element";
        attachedElement.className = "w-full h-full object-cover rounded-3xl shadow-md";
        attachedElement.style.objectPosition = AVATAR_POSITIONS[avatarName.toLowerCase()] || "center";
        attachedElement.style.opacity = "0";
        attachedElement.style.transition = "opacity 0.5s ease-in-out";
        
        const checkFrames = (now, metadata) => {
          if (metadata.presentedFrames >= 45) {
            console.log('Stable WebRTC video stream reached (45 frames). Revealing avatar.');
            attachedElement.style.opacity = "1";
            setVideoLoaded(true);
          } else {
            attachedElement.requestVideoFrameCallback(checkFrames);
          }
        };

        if ('requestVideoFrameCallback' in attachedElement) {
          attachedElement.requestVideoFrameCallback(checkFrames);
        } else {
          // Fallback if rVFC is not supported
          attachedElement.onplaying = () => {
            setTimeout(() => {
              attachedElement.style.opacity = "1";
              setVideoLoaded(true);
            }, 1000);
          };
        }
        
        container.appendChild(attachedElement);
      }
    }
    return () => {
      if (agentVideoTrack && attachedElement) {
        agentVideoTrack.detach(attachedElement);
      }
    };
  }, [agentVideoTrack, isConnected, avatarName]);

  const startConsultation = async () => {
    if (isConnecting || isConnected) return;
    setIsConnecting(true);
    setErrorMessage('');
    setTranscripts([{ author: 'system', text: 'Connecting to voice room...' }]);

    try {
      // 1. Fetch token and room name from server
      const { token, room_name } = await getCreditCardVoiceToken(mode);
      console.log(`LiveKit token received. Room: ${room_name}`);

      // 2. Initialize LiveKit Room
      const room = new Room({
        adaptiveStream: true,
        dynacast: true,
      });
      roomRef.current = room;
      window.room = room;

      // 3. Setup event listeners
      room.on(RoomEvent.TrackSubscribed, (track, publication, participant) => {
        if (track.kind === 'audio') {
          console.log('Subscribed to audio track');
          const element = track.attach();
          document.body.appendChild(element);
        }
        if (track.kind === 'video') {
          console.log('Subscribed to video track');
          setAgentVideoTrack(track);
        }
      });

      room.on(RoomEvent.ParticipantConnected, (participant) => {
        if (participant.identity.startsWith('agent-human')) {
          console.log('Human agent joined:', participant.identity);
          setIsHumanAgentActive(true);
          const email = participant.identity.replace('agent-human-', '');
          const namePart = email.split('@')[0];
          const friendlyName = namePart.split(/[._-]/).map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
          setHumanAgentName(friendlyName);
          setTranscripts(prev => [...prev, { author: 'system', text: `🏦 Representative ${friendlyName} joined the session.` }]);
        }
      });

      room.on(RoomEvent.ParticipantDisconnected, (participant) => {
        if (participant.identity.startsWith('agent-human')) {
          console.log('Human agent disconnected');
          setIsHumanAgentActive(false);
          setTranscripts(prev => [...prev, { author: 'system', text: 'Representative left. Session closing...' }]);
          setTimeout(() => {
            endConsultation();
          }, 3000);
        }
      });

      room.on(RoomEvent.DataReceived, (payload, participant) => {
        try {
          const decoder = new TextDecoder();
          const event = JSON.parse(decoder.decode(payload));
          console.log('Received data channel event:', event);

          if (event.type === 'agent_mode') {
            console.log('Voice agent reported mode:', event.mode);
            setAgentMode(event.mode);
          } else if (event.type === DataChannelEvent.CARD_STATUS_LOCK) {
            setCardStatus(event.status);
            setTranscripts(prev => [...prev, { author: 'system', text: `SECURITY ALERT: Card status updated to ${event.status}.` }]);
          } else if (event.type === DataChannelEvent.LIMIT_UPDATED) {
            setCreditLimit(event.credit_limit_cents / 100);
            setAvailableCredit(event.available_credit_cents / 100);
            setTranscripts(prev => [...prev, { author: 'system', text: `ACCOUNT UPDATE: Credit limit increased to $${(event.credit_limit_cents / 100).toLocaleString()}.` }]);
          } else if (event.type === DataChannelEvent.FEE_REVERSED) {
            setClearedBalance(event.cleared_balance_cents / 100);
            setAvailableCredit(event.available_credit_cents / 100);
            setTranscripts(prev => [...prev, { author: 'system', text: `LEDGER UPDATE: Late fee reversed. Available credit adjusted.` }]);
            
            // Reload transaction history to show reversal credits
            getCreditCardTransactions().then(setTransactions).catch(console.error);
          } else if (event.type === DataChannelEvent.HIGHLIGHT_TRANSACTION) {
            const txId = event.id;
            if (typeof txId === 'string' && /^[a-zA-Z0-9\-_]{8,64}$/.test(txId)) {
              console.log('Highlighting transaction:', txId);
              setHighlightedTxId(txId);
              setTranscripts(prev => [...prev, { author: 'system', text: 'Representative highlighted a transaction.' }]);
              
              // Auto clear highlight after 4 seconds
              setTimeout(() => {
                setHighlightedTxId(null);
              }, 4000);
            } else {
              console.warn('Security Warning: Malformed transaction ID received via data channel.');
            }
          } else if (event.type === DataChannelEvent.SESSION_END) {
            startDisconnectCountdown();
          } else if (event.type === DataChannelEvent.TRANSCRIPT) {
            setTranscripts(prev => [...prev, { author: event.author, text: event.text }]);
            if (event.author === 'agent') {
              const text = event.text.toLowerCase();
              if (text.includes("goodbye") || text.includes("bye") || (text.includes("have a") && text.includes("day") && text.includes("good"))) {
                console.log("Agent farewell detected in transcript. Auto-initiating disconnect countdown...");
                startDisconnectCountdown();
              }
            }
          } else if (event.type === 'AVATAR_CONFIG') {
            console.log('Received active avatar configuration:', event.avatar_name);
            setAvatarName(event.avatar_name);
          } else if (event.type === 'WATCHDOG_WARNING') {
            const remaining = Math.round(event.time_remaining_seconds);
            setWarningMessage(`WARNING: Session will end in ${remaining} seconds due to compliance limits.`);
            setTimeRemaining(remaining);
          }
        } catch (e) {
          console.error('Error parsing data channel packet:', e);
        }
      });

      room.on(RoomEvent.Disconnected, () => {
        setIsConnected(false);
        setIsHumanAgentActive(false);
        setWarningMessage('');
        setTimeRemaining(0);
        setAgentVideoTrack(null);
        setVideoLoaded(false);
        setAgentMode(null);
        setTranscripts(prev => [...prev, { author: 'system', text: 'Disconnected from voice room.' }]);
      });

      // 4. Connect to LiveKit Room
      const livekitUrl = window.env?.LIVEKIT_URL || "ws://localhost:7880";
      await room.connect(livekitUrl, token);
      console.log('Connected to LiveKit Room');

      // 5. Publish microphone track
      await room.localParticipant.setMicrophoneEnabled(true);
      
      setIsConnected(true);
      setTranscripts([]);
    } catch (err) {
      console.error('Failed to establish LiveKit connection:', err);
      setErrorMessage('Failed to join voice support channel. Verify LiveKit server is running.');
      setTranscripts(prev => [...prev, { author: 'system', text: 'Error: Connection failed.' }]);
    } finally {
      setIsConnecting(false);
    }
  };

  const startDisconnectCountdown = () => {
    if (disconnectTimerRef.current) return; // already scheduled
    setTranscripts(prev => [...prev, { author: 'system', text: 'Consultation complete. Disconnecting in 5 seconds...' }]);
    disconnectTimerRef.current = setTimeout(() => {
      endConsultation();
    }, 5000);
  };

  const endConsultation = () => {
    if (disconnectTimerRef.current) {
      clearTimeout(disconnectTimerRef.current);
      disconnectTimerRef.current = null;
    }
    if (roomRef.current) {
      try {
        roomRef.current.disconnect();
      } catch (err) {
        console.error("Error disconnecting room:", err);
      }
      roomRef.current = null;
    }
    const container = document.getElementById("avatar-video-container");
    if (container) {
      container.innerHTML = "";
    }
    setIsConnected(false);
    setIsHumanAgentActive(false);
    setWarningMessage('');
    setTimeRemaining(0);
    setAgentVideoTrack(null);
    setVideoLoaded(false);
    setAgentMode(null);
  };

  const toggleMute = async () => {
    if (!roomRef.current) return;
    const enabled = !micEnabled;
    await roomRef.current.localParticipant.setMicrophoneEnabled(enabled);
    setMicEnabled(enabled);
  };

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 text-slate-100 min-h-[80vh] flex flex-col justify-between">
      
      {/* Header section */}
      <div className="text-center mb-6">
        <h1 className="text-4xl font-extrabold tracking-tight bg-gradient-to-r from-blue-400 to-indigo-400 bg-clip-text text-transparent">
          Nova Horizon Voice Support Copilot
        </h1>
        <p className="text-slate-400 mt-2 text-lg">
          Talk to our real-time AI assistant for instant credit card operations.
        </p>
      </div>

      {errorMessage && (
        <div className="bg-red-900/30 border border-red-500/50 rounded-xl p-4 flex items-center gap-3 mb-6">
          <AlertCircle className="text-red-400 flex-shrink-0" />
          <span className="text-red-200 text-sm">{errorMessage}</span>
        </div>
      )}

      {warningMessage && (
        <div className="bg-amber-900/30 border border-amber-500/50 rounded-xl p-4 flex items-center gap-3 mb-6 animate-pulse">
          <AlertCircle className="text-amber-400 flex-shrink-0 animate-pulse" />
          <span className="text-amber-200 text-sm font-semibold">{warningMessage}</span>
        </div>
      )}

      {/* Main Content Layout */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8 items-stretch flex-grow mb-8">
        
        {/* Left Side: Credit Card Mockup & Account details */}
        <div className="flex flex-col gap-6 bg-slate-900/50 backdrop-blur border border-slate-800 rounded-3xl p-8 justify-between">
          
          {/* Card Mockup */}
          <div className="relative aspect-[1.586/1] w-full rounded-2xl overflow-hidden bg-gradient-to-tr from-slate-900 via-indigo-950 to-indigo-900 p-6 shadow-2xl flex flex-col justify-between border border-slate-700/50">
            <div className="absolute inset-0 bg-gradient-to-b from-white/5 to-transparent pointer-events-none" />
            
            <div className="flex justify-between items-start">
              <div>
                <p className="text-xs uppercase tracking-widest text-slate-400 font-semibold">Credit Card</p>
                <h3 className="text-lg font-bold tracking-tight text-slate-100">Nova Horizon</h3>
              </div>
              <div className="h-8 w-12 bg-amber-500/20 rounded-md border border-amber-500/30 flex items-center justify-center">
                <span className="text-[10px] font-mono text-amber-300 font-bold uppercase">VISA</span>
              </div>
            </div>

            <div className="my-auto">
              <p className="text-2xl font-mono tracking-widest text-slate-100 flex justify-between">
                <span>••••</span> <span>••••</span> <span>••••</span> <span>{account?.cards?.[0]?.last_four || "8234"}</span>
              </p>
            </div>

            <div className="flex justify-between items-end">
              <div>
                <p className="text-[9px] uppercase tracking-wider text-slate-400">Cardholder</p>
                <p className="text-sm font-semibold tracking-wide text-slate-200 flex items-center gap-1.5">
                  <User size={13} className="text-slate-400" />
                  {account?.cards?.[0]?.cardholder_name || "Jane Doe"}
                </p>
              </div>
              <div>
                <p className="text-[9px] uppercase tracking-wider text-slate-400">Expires</p>
                <p className="text-sm font-semibold tracking-wide text-slate-200 flex items-center gap-1">
                  <Calendar size={13} className="text-slate-400" />
                  {account?.cards?.[0] ? `${account.cards[0].exp_month}/${account.cards[0].exp_year.toString().slice(-2)}` : "12/28"}
                </p>
              </div>
            </div>

            {/* Card Status Locked Overlay */}
            {cardStatus === 'BLOCKED' && (
              <div className="absolute inset-0 bg-slate-950/85 backdrop-blur-[2px] flex flex-col items-center justify-center gap-2">
                <div className="p-3 bg-red-500/20 rounded-full border border-red-500/30 text-red-400">
                  <Lock size={32} className="animate-pulse" />
                </div>
                <span className="text-red-400 font-bold tracking-widest uppercase text-sm">Card Frozen</span>
              </div>
            )}
          </div>

          {/* Account Balances Grid */}
          <div className="grid grid-cols-3 gap-4">
            <div className="bg-slate-950/40 rounded-2xl p-4 border border-slate-800/80">
              <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">Available Credit</span>
              <p className="text-xl font-bold mt-1 text-emerald-400">${availableCredit.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p>
            </div>

            <div className="bg-slate-950/40 rounded-2xl p-4 border border-slate-800/80">
              <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">Credit Limit</span>
              <p className="text-xl font-bold mt-1 text-slate-200">${creditLimit.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p>
            </div>

            <div className="bg-slate-950/40 rounded-2xl p-4 border border-slate-800/80">
              <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">Owed Balance</span>
              <p className="text-xl font-bold mt-1 text-indigo-400">${clearedBalance.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p>
            </div>
          </div>

          {/* Transaction Ledger List */}
          <div className="bg-slate-950/30 rounded-2xl p-4 border border-slate-800/80 flex-grow max-h-[200px] overflow-y-auto">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-2">Statement Ledger</h3>
            <div className="space-y-2">
              {transactions.length === 0 ? (
                <p className="text-xs text-slate-500 italic">No transactions posted.</p>
              ) : (
                transactions.map((tx) => {
                  const isHighlighted = highlightedTxId === tx.id;
                  return (
                    <div 
                      key={tx.id} 
                      className={`flex justify-between items-center p-2 rounded-lg border text-xs transition-all duration-500 ${
                        isHighlighted 
                          ? 'border-yellow-500 bg-yellow-500/10 scale-[1.02] shadow-lg shadow-yellow-500/10' 
                          : 'border-slate-800 bg-slate-900/30 text-slate-300'
                      }`}
                    >
                      <div>
                        <p className="font-semibold">{tx.description}</p>
                        <p className="text-[9px] text-slate-500">{new Date(tx.posted_at).toLocaleDateString()}</p>
                      </div>
                      <span className={`font-mono font-bold ${tx.amount_cents > 0 ? 'text-indigo-300' : 'text-emerald-400'}`}>
                        {tx.amount_cents > 0 ? '-' : '+'}
                        ${Math.abs(tx.amount_cents / 100).toFixed(2)}
                      </span>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>

        {/* Right Side: Conversation Transcripts & Video Player Panel */}
        <div className="flex flex-col bg-slate-900/50 backdrop-blur border border-slate-800 rounded-3xl p-6 min-h-[400px]">
          
          {/* Avatar Video Frame container if video mode is active */}
          {mode === 'video' && isConnected && (
            <div className="flex flex-col mb-4">
              <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-2">
                Live Avatar Stream
              </h2>
              <div className="aspect-square w-full max-w-[340px] mx-auto relative rounded-3xl overflow-hidden border-2 border-slate-800 shadow-inner bg-slate-950">
                <div 
                  id="avatar-video-container" 
                  className="w-full h-full"
                />
                {!videoLoaded && (
                  <div className="absolute inset-0 flex flex-col items-center justify-center bg-slate-900 border border-slate-800 rounded-3xl pointer-events-none">
                    <div className={`w-24 h-24 rounded-full bg-gradient-to-tr ${
                      avatarName.toLowerCase() === 'ingrid' ? 'from-rose-500 to-orange-400' :
                      avatarName.toLowerCase() === 'paul' ? 'from-emerald-500 to-teal-400' :
                      'from-indigo-600 to-violet-500'
                    } flex items-center justify-center text-white text-4xl font-extrabold shadow-lg mb-3 border border-white/10 ${
                      agentMode === 'audio' ? '' : 'animate-pulse'
                    }`}>
                      {avatarName.charAt(0).toUpperCase()}
                    </div>
                    <span className="text-xs font-semibold tracking-wider uppercase text-slate-400">
                      {agentMode === 'audio' ? `${avatarName} is connected` : `${avatarName} is connecting...`}
                    </span>
                  </div>
                )}
              </div>
            </div>
          )}

          <h2 className="text-md font-bold uppercase tracking-wider text-slate-400 mb-4 border-b border-slate-800 pb-2">
            Live Consultation Transcript
          </h2>
          
          <div 
            ref={chatContainerRef} 
            className="flex-grow overflow-y-auto space-y-4 pr-2 scrollbar-thin"
            style={{ maxHeight: mode === 'video' && isConnected ? '200px' : '350px' }}
          >
            {transcripts.map((t, idx) => {
              if (t.author === 'system') {
                return (
                  <div key={idx} className="text-center">
                    <span className="inline-block text-[10px] bg-slate-800 text-slate-400 px-2.5 py-1 rounded-full font-mono">
                      {t.text}
                    </span>
                  </div>
                );
              }

              const isUser = t.author === 'user';
              return (
                <div key={idx} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[80%] rounded-2xl px-4 py-2.5 shadow-sm text-sm ${
                    isUser 
                      ? 'bg-blue-600 text-white rounded-br-none' 
                      : isHumanAgentActive && t.author === 'agent'
                        ? 'bg-indigo-600 text-white rounded-bl-none'
                        : 'bg-slate-800 text-slate-200 rounded-bl-none'
                  }`}>
                    <p className="text-[9px] uppercase tracking-wide text-slate-400 font-bold mb-0.5">
                      {isUser ? 'You' : isHumanAgentActive ? 'Supervisor' : 'AI Assistant'}
                    </p>
                    <p className="leading-relaxed">{t.text}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

      </div>

      {/* Footer / Control Section */}
      <div className="flex flex-col items-center gap-4 bg-slate-900/50 backdrop-blur border border-slate-800 rounded-3xl p-6">
        
        {/* Connection status notification */}
        {isHumanAgentActive && (
          <div className="bg-indigo-900/30 border border-indigo-500/50 rounded-xl px-4 py-2 text-xs text-indigo-300 font-bold flex items-center gap-2 animate-pulse">
            <User size={14} />
            Representative {humanAgentName} is now live on this session.
          </div>
        )}

        {/* Pulsing Visualizer */}
        {isConnected && (
          <div className="flex items-center gap-1.5 h-6">
            <span className="w-1 bg-emerald-500 rounded animate-bounce [animation-duration:0.6s]"></span>
            <span className="w-1 bg-emerald-400 rounded animate-bounce [animation-duration:0.8s] delay-75"></span>
            <span className="w-1 bg-emerald-500 rounded animate-bounce [animation-duration:0.5s] delay-150"></span>
            <span className="w-1 bg-emerald-400 rounded animate-bounce [animation-duration:0.7s] delay-300"></span>
            <span className="w-1 bg-emerald-500 rounded animate-bounce [animation-duration:0.6s] delay-75"></span>
          </div>
        )}

        {/* Mode Selection Toggle */}
        {!isConnected && !isConnecting && (
          <div className="flex items-center gap-1.5 p-1 bg-slate-950/60 rounded-full border border-slate-800/80 mb-2">
            <button
              onClick={() => setMode('audio')}
              className={`flex items-center gap-1.5 px-4 py-1.5 rounded-full text-xs font-bold transition-all ${
                mode === 'audio' 
                  ? 'bg-blue-600/20 border border-blue-500/30 text-blue-400' 
                  : 'text-slate-500 hover:text-slate-300'
              }`}
            >
              <Mic size={14} />
              Voice Call
            </button>
            <button
              onClick={() => setMode('video')}
              className={`flex items-center gap-1.5 px-4 py-1.5 rounded-full text-xs font-bold transition-all ${
                mode === 'video' 
                  ? 'bg-indigo-600/20 border border-indigo-500/30 text-indigo-400' 
                  : 'text-slate-500 hover:text-slate-300'
              }`}
            >
              <Video size={14} />
              Live Avatar
            </button>
          </div>
        )}

        {/* Buttons */}
        <div className="flex items-center gap-4">
          {!isConnected ? (
            <button
              onClick={startConsultation}
              disabled={isConnecting}
              className={`flex items-center gap-2 px-8 py-3 rounded-full font-bold shadow-lg shadow-blue-500/20 text-white bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 transition-all transform active:scale-95 ${
                isConnecting ? 'opacity-70 cursor-not-allowed' : ''
              }`}
            >
              <Phone size={18} />
              {isConnecting ? 'Connecting...' : 'Start Voice Consultation'}
            </button>
          ) : (
            <>
              <button
                onClick={toggleMute}
                className={`p-4 rounded-full border transition-all ${
                  micEnabled 
                    ? 'border-slate-700 bg-slate-800/80 text-slate-300 hover:bg-slate-700' 
                    : 'border-red-500/50 bg-red-950/50 text-red-400 hover:bg-red-900/30'
                }`}
              >
                {micEnabled ? <Mic size={20} /> : <MicOff size={20} />}
              </button>
              
              <button
                onClick={endConsultation}
                className="flex items-center gap-2 px-8 py-3 rounded-full font-bold shadow-lg shadow-red-500/20 text-white bg-red-600 hover:bg-red-500 transition-all transform active:scale-95"
              >
                <PhoneOff size={18} />
                End Consultation
              </button>
            </>
          )}
        </div>
      </div>

    </div>
  );
}
