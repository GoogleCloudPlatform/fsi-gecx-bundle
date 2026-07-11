import React, { useState, useEffect, useRef, useCallback } from 'react';
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
  CheckCircle2,
  Video,
  VideoOff,
  ExternalLink
} from 'lucide-react';
import { 
  getCreditCardAccount, 
  getCreditCardVoiceToken, 
  getCreditCardTransactions 
} from '../utils/api.js';
import { DataChannelEvent } from '../utils/constants.js';
import GcpInfoModal from './GcpInfoModal.jsx';
import GoogleCloudIcon from './GoogleCloudIcon.jsx';

function FraudStep({ label, complete }) {
  return (
    <div className="flex items-center gap-2">
      <div className={`h-2.5 w-2.5 rounded-full ${complete ? 'bg-emerald-500' : 'bg-slate-300 dark:bg-slate-700'}`} />
      <span className={`text-[11px] font-medium ${complete ? 'text-emerald-800 dark:text-emerald-300' : 'text-slate-600 dark:text-slate-400'}`}>
        {label}
      </span>
    </div>
  );
}

function normalizeCardId(cardId) {
  return cardId == null ? null : String(cardId);
}

function formatCents(amountCents) {
  return `$${Math.abs((amountCents || 0) / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function applyReplacementCardEvent(cards, replacement) {
  if (!replacement) return cards || [];
  const newCardId = normalizeCardId(replacement.new_card_id);
  const compromisedCardId = normalizeCardId(replacement.compromised_card_id || replacement.old_card_id);
  let replacementSeen = false;
  const updatedCards = (cards || []).map((card) => {
    const cardId = normalizeCardId(card.card_id || card.id);
    if (cardId === newCardId) {
      replacementSeen = true;
      return {
        ...card,
        card_id: card.card_id || newCardId,
        id: card.id || newCardId,
        last_four: replacement.new_last_four || card.last_four,
        card_token: replacement.new_card_token || replacement.card_token || card.card_token,
        status: replacement.status || card.status || 'ACTIVE',
        is_virtual: replacement.is_virtual ?? card.is_virtual ?? true,
      };
    }
    if (compromisedCardId && cardId === compromisedCardId) {
      return {
        ...card,
        status: card.status === 'REPORTED_STOLEN' ? card.status : 'BLOCKED',
        is_active: false,
      };
    }
    return card;
  });
  if (!replacementSeen && newCardId) {
    updatedCards.push({
      card_id: newCardId,
      id: newCardId,
      cardholder_name: replacement.cardholder_name || updatedCards[0]?.cardholder_name || 'Cardholder',
      last_four: replacement.new_last_four,
      card_token: replacement.new_card_token || replacement.card_token,
      status: replacement.status || 'ACTIVE',
      is_active: true,
      is_virtual: replacement.is_virtual ?? true,
      exp_month: replacement.exp_month || updatedCards[0]?.exp_month,
      exp_year: replacement.exp_year || updatedCards[0]?.exp_year,
    });
  }
  return updatedCards;
}

function applyWalletProvisioningEvent(cards, event) {
  const cardToken = event?.card_token;
  if (!cardToken) return cards || [];
  return (cards || []).map((card) => {
    if (card.card_token !== cardToken) return card;
    return {
      ...card,
      wallet_provider: event.wallet_provider || card.wallet_provider || 'GOOGLE_WALLET',
      wallet_provisioning_status: event.wallet_provisioning_status || card.wallet_provisioning_status || 'QUEUED',
    };
  });
}

export default function VoiceSupportView() {
  const projectId = window.firebaseConfig?.projectId;
  const voiceParts = (window.env?.CX_AGENT_STUDIO_VOICE_AGENT_DEPLOYMENT_NAME || '').split('/');
  const cxProjectId = voiceParts.includes('projects') ? voiceParts[voiceParts.indexOf('projects') + 1] : '';
  const appId = voiceParts.includes('apps') ? voiceParts[voiceParts.indexOf('apps') + 1] : '';
  const [isInfoModalOpen, setIsInfoModalOpen] = useState(false);
  const [account, setAccount] = useState(null);
  const [cardStatus, setCardStatus] = useState('ACTIVE');
  const [creditLimit, setCreditLimit] = useState(0);
  const [availableCredit, setAvailableCredit] = useState(0);
  const [clearedBalance, setClearedBalance] = useState(0);
  const [transactions, setTransactions] = useState([]);
  const [transcripts, setTranscripts] = useState([]);
  const [fraudContext, setFraudContext] = useState(null);
  const [fraudTriage, setFraudTriage] = useState({
    outcome: null,
    voided_authorizations: [],
    provisional_credits: [],
    replacement_card: null,
    secure_message: null,
    escalated: false,
    walletQueued: false,
  });
  
  const [isConnected, setIsConnected] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [micEnabled, setMicEnabled] = useState(true);
  const [errorMessage, setErrorMessage] = useState('');
  
  const [isHumanAgentActive, setIsHumanAgentActive] = useState(false);
  const [humanAgentName, setHumanAgentName] = useState('');
  const [highlightedTxId, setHighlightedTxId] = useState(null);
  
  const [mode, setMode] = useState('audio');
  const [warningMessage, setWarningMessage] = useState('');

  const [agentVideoTrack, setAgentVideoTrack] = useState(null);
  const [videoLoaded, setVideoLoaded] = useState(false);
  const [avatarName, setAvatarName] = useState('Sam');
  const [agentMode, setAgentMode] = useState(null);

  // New engine-specific configuration states
  const [engine, setEngine] = useState('livekit'); // 'livekit' | 'gecx'
  const [volume, setVolume] = useState(0.8);
  const [latency, setLatency] = useState(0);

  const affectedCardId = normalizeCardId(fraudContext?.fraud_alert?.card_id);
  const cards = account?.cards || [];
  const compromisedCard = cards.find((card) => normalizeCardId(card.card_id || card.id) === affectedCardId) || cards[0];
  const replacementCardId = normalizeCardId(fraudTriage.replacement_card?.new_card_id);
  const replacementCard = cards.find((card) => normalizeCardId(card.card_id || card.id) === replacementCardId);
  const displayCard = replacementCard || compromisedCard || cards[0];

  const fraudProgress = {
    inspected: Boolean(fraudContext?.fraud_alert?.inspected),
    blocked: compromisedCard?.status === 'BLOCKED' || cardStatus === 'BLOCKED',
    triaged: Boolean(fraudTriage.outcome),
    replaced: Boolean(fraudTriage.replacement_card || replacementCard),
    walletQueued: Boolean(fraudTriage.walletQueued) || transcripts.some(t => t.author === 'system' && t.text.includes('Virtual card provisioning')),
    specialistReview: Boolean(fraudTriage.outcome && fraudTriage.outcome !== 'CUSTOMER_RECOGNIZED'),
  };
  const showFraudRemediationProgress = fraudProgress.triaged || fraudProgress.blocked || fraudProgress.replaced || fraudProgress.walletQueued;

  const roomRef = useRef(null);
  const chatContainerRef = useRef(null);
  const disconnectTimerRef = useRef(null);
  
  // GECX connection hooks & streaming timing refs
  const wsRef = useRef(null);
  const audioContextRef = useRef(null);
  const micStreamRef = useRef(null);
  const workletNodeRef = useRef(null);
  const activeSourcesRef = useRef([]);
  const nextPlayoutTimeRef = useRef(0);
  const volumeRef = useRef(0.8);
  const micEnabledRef = useRef(true);
  const pingIntervalRef = useRef(null);

  const stopPlayoutQueue = useCallback(() => {
    activeSourcesRef.current.forEach(source => {
      try {
        source.stop();
      } catch {
        // Ignore error
      }
    });
    activeSourcesRef.current = [];
    
    const audioCtx = audioContextRef.current;
    if (audioCtx) {
      nextPlayoutTimeRef.current = audioCtx.currentTime + 0.05;
    }
  }, []);

  const cleanupGecxSession = useCallback(() => {
    stopPlayoutQueue();
    if (pingIntervalRef.current) {
      clearInterval(pingIntervalRef.current);
      pingIntervalRef.current = null;
    }
    if (wsRef.current) {
      try {
        wsRef.current.close();
      } catch {
        // Ignore error
      }
      wsRef.current = null;
    }
    if (workletNodeRef.current) {
      try {
        workletNodeRef.current.disconnect();
      } catch {
        // Ignore error
      }
      workletNodeRef.current = null;
    }
    if (micStreamRef.current) {
      try {
        micStreamRef.current.getTracks().forEach(track => track.stop());
      } catch {
        // Ignore error
      }
      micStreamRef.current = null;
    }
    if (audioContextRef.current) {
      try {
        audioContextRef.current.close();
      } catch {
        // Ignore error
      }
      audioContextRef.current = null;
    }
    setIsConnected(false);
    setLatency(0);
  }, [stopPlayoutQueue]);

  const endConsultation = useCallback(() => {
    if (engine === 'gecx') {
      return cleanupGecxSession();
    }
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
    setAgentVideoTrack(null);
    setVideoLoaded(false);
    setAgentMode(null);
  }, [engine, cleanupGecxSession]);

  const startDisconnectCountdown = useCallback(() => {
    if (disconnectTimerRef.current) return; // already scheduled
    setTranscripts(prev => [...prev, { author: 'system', text: 'Consultation complete. Disconnecting in 5 seconds...' }]);
    disconnectTimerRef.current = setTimeout(() => {
      endConsultation();
    }, 5000);
  }, [endConsultation]);

  const refreshCreditCardData = useCallback(async () => {
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
  }, []);

  // Sync state values to references to avoid stale closures inside event listeners
  useEffect(() => {
    volumeRef.current = volume;
  }, [volume]);

  useEffect(() => {
    micEnabledRef.current = micEnabled;
  }, [micEnabled]);

  // Force voice/audio mode when using GECX engine (video avatars not supported)
  useEffect(() => {
    if (engine === 'gecx') {
      setMode('audio');
    }
  }, [engine]);

  // Load account data and transactions on mount
  useEffect(() => {
    async function loadData() {
      try {
        await refreshCreditCardData();
      } catch (err) {
        console.error('Failed to load card account profile:', err);
        setErrorMessage('Failed to connect to core banking service.');
      }
    }
    loadData();
  }, [refreshCreditCardData]);

  // Auto scroll transcript panel inside container
  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  }, [transcripts]);

  // Cleanup LiveKit room and GECX WebSocket on unmount
  useEffect(() => {
    return () => {
      if (roomRef.current) {
        roomRef.current.disconnect();
      }
      cleanupGecxSession();
    };
  }, [cleanupGecxSession]);

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

  const getWebSocketUrl = () => {
    const url = window.env?.BANKING_API_URL || import.meta.env.VITE_BANKING_API_URL || "http://localhost:8080";
    return url.replace(/^http/, 'ws') + '/voice/gecx-stream';
  };



  const handleGecxAudioChunk = (arrayBuffer) => {
    const audioCtx = audioContextRef.current;
    if (!audioCtx || audioCtx.state === 'closed') return;

    const int16Array = new Int16Array(arrayBuffer);
    const float32Array = new Float32Array(int16Array.length);
    for (let i = 0; i < int16Array.length; i++) {
      float32Array[i] = int16Array[i] / (int16Array[i] < 0 ? 0x8000 : 0x7FFF);
    }

    const audioBuffer = audioCtx.createBuffer(1, float32Array.length, 16000);
    audioBuffer.copyToChannel(float32Array, 0);

    const now = audioCtx.currentTime;
    let playTime = nextPlayoutTimeRef.current;
    if (playTime < now) {
      playTime = now + 0.05; // 50ms playout lookahead to prevent jitter
    }

    const sourceNode = audioCtx.createBufferSource();
    sourceNode.buffer = audioBuffer;

    const gainNode = audioCtx.createGain();
    gainNode.gain.setValueAtTime(volumeRef.current, audioCtx.currentTime);

    sourceNode.connect(gainNode);
    gainNode.connect(audioCtx.destination);

    activeSourcesRef.current.push(sourceNode);
    sourceNode.onended = () => {
      activeSourcesRef.current = activeSourcesRef.current.filter(src => src !== sourceNode);
    };

    sourceNode.start(playTime);
    nextPlayoutTimeRef.current = playTime + audioBuffer.duration;
  };

  const handleGecxControlMessage = useCallback((payload) => {
    if (payload.type === 'TRANSCRIPT') {
      setTranscripts(prev => [...prev, { author: payload.author, text: payload.text }]);
      if (payload.author === 'agent') {
        const text = payload.text.toLowerCase();
        if (text.includes("goodbye") || text.includes("bye") || (text.includes("have a") && text.includes("good") && text.includes("day"))) {
          startDisconnectCountdown();
        }
      }
    } else if (payload.type === 'PONG') {
      const rtt = Date.now() - payload.timestamp;
      setLatency(rtt);
    } else if (payload.type === 'CARD_STATUS') {
      setCardStatus(payload.status);
      setTranscripts(prev => [...prev, { author: 'system', text: `SECURITY ALERT: Card status updated to ${payload.status}.` }]);
    } else if (payload.type === 'LIMIT_UPDATED') {
      setCreditLimit(payload.credit_limit_cents / 100);
      setAvailableCredit(payload.available_credit_cents / 100);
      setTranscripts(prev => [...prev, { author: 'system', text: `ACCOUNT UPDATE: Credit limit increased to $${(payload.credit_limit_cents / 100).toLocaleString()}.` }]);
    } else if (payload.type === 'FEE_REVERSED') {
      setClearedBalance(payload.cleared_balance_cents / 100);
      setAvailableCredit(payload.available_credit_cents / 100);
      setTranscripts(prev => [...prev, { author: 'system', text: `LEDGER UPDATE: Late fee reversed. Available credit adjusted.` }]);
      getCreditCardTransactions().then(setTransactions).catch(console.error);
    } else if (payload.type === 'HIGHLIGHT_TRANSACTION') {
      const txId = payload.id;
      if (typeof txId === 'string' && /^[a-zA-Z0-9\-_]{8,64}$/.test(txId)) {
        setHighlightedTxId(txId);
        setTranscripts(prev => [...prev, { author: 'system', text: 'Representative highlighted a transaction.' }]);
        setTimeout(() => {
          setHighlightedTxId(null);
        }, 4000);
      }
    } else if (payload.type === 'INTERRUPT') {
      console.log("Barge-in: Interrupting agent speech playback.");
      stopPlayoutQueue();
    } else if (payload.type === 'ERROR') {
      setErrorMessage(payload.message);
    }
  }, [startDisconnectCountdown, stopPlayoutQueue]);

  const startGecxConsultation = async () => {
    if (isConnecting || isConnected) return;
    setIsConnecting(true);
    setErrorMessage('');
    setTranscripts([{ author: 'system', text: 'Connecting to GECX voice stream...' }]);

    try {
      const micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      micStreamRef.current = micStream;

      const audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
      audioContextRef.current = audioCtx;
      nextPlayoutTimeRef.current = 0;

      if (audioCtx.state === 'suspended') {
        await audioCtx.resume();
      }

      let fbToken = "";
      if (window.firebaseAuth && typeof window.firebaseAuth.getCurrentUser === 'function') {
        const user = window.firebaseAuth.getCurrentUser();
        if (user) {
          fbToken = await user.getIdToken();
        }
      }

      const wsUrl = getWebSocketUrl();
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      ws.binaryType = 'arraybuffer';

      ws.onopen = () => {
        console.log("GECX WebSocket opened. Transmitting Auth frame...");
        setTranscripts(prev => [...prev, { author: 'system', text: 'Securing streaming session...' }]);
        ws.send(JSON.stringify({
          type: "AUTH",
          token: fbToken
        }));
        
        // Start latency diagnostics ping loop
        pingIntervalRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
              type: "PING",
              timestamp: Date.now()
            }));
          }
        }, 3000);
      };

      ws.onmessage = async (event) => {
        if (typeof event.data === 'string') {
          handleGecxControlMessage(JSON.parse(event.data));
        } else {
          handleGecxAudioChunk(event.data);
        }
      };

      ws.onclose = (e) => {
        console.log(`GECX WebSocket closed: ${e.code} | ${e.reason}`);
        cleanupGecxSession();
        if (e.code === 4001) {
          setErrorMessage("Access Denied: Session authentication failed.");
        } else {
          setTranscripts(prev => [...prev, { author: 'system', text: 'Session ended.' }]);
        }
      };

      ws.onerror = (err) => {
        console.error("GECX WebSocket error:", err);
        setErrorMessage("Failed to establish voice session connection.");
      };

      // Inline AudioWorklet Processor Blob to prevent asset loaders compiling issues in Vite
      const workletCode = `
        class PCMProcessor extends AudioWorkletProcessor {
          constructor() {
            super();
            this.buffer = new Float32Array(0);
          }
          process(inputs, outputs, parameters) {
            const input = inputs[0];
            if (!input || !input[0]) return true;
            
            const samples = input[0];
            const combined = new Float32Array(this.buffer.length + samples.length);
            combined.set(this.buffer);
            combined.set(samples, this.buffer.length);
            this.buffer = combined;
            
            const sendChunkSize = 2048; // packet size of ~128ms
            while (this.buffer.length >= sendChunkSize) {
              const chunk = this.buffer.slice(0, sendChunkSize);
              this.buffer = this.buffer.slice(sendChunkSize);
              
              const int16Buffer = new Int16Array(chunk.length);
              for (let i = 0; i < chunk.length; i++) {
                const s = Math.max(-1, Math.min(1, chunk[i]));
                int16Buffer[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
              }
              
              this.port.postMessage(int16Buffer.buffer, [int16Buffer.buffer]);
            }
            return true;
          }
        }
        registerProcessor('pcm-processor', PCMProcessor);
      `;
      
      const blob = new Blob([workletCode], { type: 'application/javascript' });
      const workletUrl = URL.createObjectURL(blob);
      await audioCtx.audioWorklet.addModule(workletUrl);
      URL.revokeObjectURL(workletUrl);

      const sourceNode = audioCtx.createMediaStreamSource(micStream);
      const workletNode = new AudioWorkletNode(audioCtx, 'pcm-processor');
      workletNodeRef.current = workletNode;

      workletNode.port.onmessage = (e) => {
        const rawBuffer = e.data;
        if (micEnabledRef.current && wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
          wsRef.current.send(rawBuffer);
        }
      };

      sourceNode.connect(workletNode);
      setIsConnected(true);
      setTranscripts([]);
    } catch (err) {
      console.error("Failed to initialize GECX call:", err);
      setErrorMessage(
        err.name === 'NotAllowedError' 
          ? 'Microphone permission denied. Enable microphone access in browser settings.' 
          : 'Failed to access microphone or establish call connection.'
      );
      cleanupGecxSession();
    } finally {
      setIsConnecting(false);
    }
  };

  const startConsultation = async () => {
    if (engine === 'gecx') {
      return startGecxConsultation();
    }
    if (isConnecting || isConnected) return;
    setIsConnecting(true);
    setErrorMessage('');
    setTranscripts([{ author: 'system', text: 'Connecting to voice room...' }]);

    try {
      // 1. Fetch token and room name from server
      const { token, room_name, fraud_context } = await getCreditCardVoiceToken(mode);
      console.log(`LiveKit token received. Room: ${room_name}`);
      setFraudContext(fraud_context || null);

      // 2. Initialize LiveKit Room
      const room = new Room({
        adaptiveStream: true,
        dynacast: true,
      });
      roomRef.current = room;

      // 3. Setup event listeners
      room.on(RoomEvent.TrackSubscribed, (track) => {
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

      room.on(RoomEvent.DataReceived, (payload) => {
        try {
          const decoder = new TextDecoder();
          const event = JSON.parse(decoder.decode(payload));
          console.log('Received data channel event:', event);

          if (event.type === 'agent_mode') {
            console.log('Voice agent reported mode:', event.mode);
            setAgentMode(event.mode);
          } else if (event.type === DataChannelEvent.FRAUD_ALERT_INSPECTED) {
            setFraudContext(prev => prev ? {
              ...prev,
              has_active_fraud_alert: true,
              fraud_alert: prev.fraud_alert ? {
                ...prev.fraud_alert,
                inspected: true,
                status: event.status || prev.fraud_alert.status,
              } : prev.fraud_alert,
            } : prev);
            setTranscripts(prev => [
              ...prev,
              {
                author: 'system',
                text: `CASE UPDATE: Fraud alert reviewed. ${event.suspicious_transactions_count || 0} suspicious charge${event.suspicious_transactions_count === 1 ? '' : 's'} ready for confirmation.`,
              },
            ]);
          } else if (event.type === DataChannelEvent.CARD_STATUS_LOCK) {
            setCardStatus(event.status);
            setTranscripts(prev => [...prev, { author: 'system', text: `SECURITY ALERT: Card status updated to ${event.status}.` }]);
          } else if (event.type === DataChannelEvent.CARD_REPLACED) {
            setCardStatus(event.status || 'ACTIVE');
            setAccount(prev => {
              if (!prev) return prev;
              return {
                ...prev,
                cards: applyReplacementCardEvent(prev.cards, event),
              };
            });
            setTranscripts(prev => [
              ...prev,
              {
                author: 'system',
                text: `ACCOUNT UPDATE: Replacement ${event.is_virtual ? 'virtual ' : ''}card ending in ${event.new_last_four} is ready.`,
              },
            ]);
          } else if (event.type === DataChannelEvent.WALLET_PROVISIONING_QUEUED) {
            setFraudTriage(prev => ({ ...prev, walletQueued: true }));
            setAccount(prev => prev ? {
              ...prev,
              cards: applyWalletProvisioningEvent(prev.cards, event),
            } : prev);
            setTranscripts(prev => [
              ...prev,
              {
                author: 'system',
                text: `ACCOUNT UPDATE: Virtual card provisioning to ${event.wallet_provider || 'Google Wallet'} is queued.`,
              },
            ]);
          } else if (event.type === DataChannelEvent.FRAUD_ALERT_RESOLVED || event.type === DataChannelEvent.FRAUD_CASE_TRIAGED) {
            const isRecognized = event.resolution === 'CUSTOMER_RECOGNIZED' || event.outcome === 'CUSTOMER_RECOGNIZED';
            const replacement = event.replacement_card || null;
            setFraudTriage(prev => ({
              ...prev,
              outcome: event.outcome || event.resolution || prev.outcome,
              voided_authorizations: event.voided_authorizations || prev.voided_authorizations,
              provisional_credits: event.provisional_credits || prev.provisional_credits,
              replacement_card: replacement || prev.replacement_card,
              secure_message: event.secure_message || prev.secure_message,
              escalated: event.escalated ?? prev.escalated,
            }));
            if (replacement) {
              setAccount(prev => prev ? {
                ...prev,
                cards: applyReplacementCardEvent(prev.cards, replacement),
              } : prev);
            }
            if (event.secure_message) {
              window.dispatchEvent(new CustomEvent('secure-message-created', {
                detail: {
                  thread_id: event.secure_message.thread_id,
                  message_id: event.secure_message.message_id,
                },
              }));
              window.dispatchEvent(new CustomEvent('refresh-unread-count'));
            }
            refreshCreditCardData().catch(err => {
              console.error('Failed to refresh credit card data after fraud triage:', err);
            });
            setFraudContext(prev => prev ? {
              ...prev,
              has_active_fraud_alert: false,
              fraud_alert: prev.fraud_alert ? {
                ...prev.fraud_alert,
                status: event.status || prev.fraud_alert.status,
                resolution: event.resolution || prev.fraud_alert.resolution,
              } : prev.fraud_alert,
            } : prev);
            setTranscripts(prev => [
              ...prev,
              {
                author: 'system',
                text: isRecognized
                  ? 'CASE UPDATE: Fraud alert reviewed as recognized activity.'
                  : `CASE UPDATE: Fraud case triaged. ${(event.voided_authorizations || []).length} pending hold${(event.voided_authorizations || []).length === 1 ? '' : 's'} released, ${(event.provisional_credits || []).length} provisional credit${(event.provisional_credits || []).length === 1 ? '' : 's'} applied.`,
              },
            ]);
          } else if (event.type === DataChannelEvent.LIMIT_UPDATED) {
            setCreditLimit(event.credit_limit_cents / 100);
            setAvailableCredit(event.available_credit_cents / 100);
            setTranscripts(prev => [...prev, { author: 'system', text: `ACCOUNT UPDATE: Credit limit increased to $${(event.credit_limit_cents / 100).toLocaleString()}.` }]);
          } else if (event.type === DataChannelEvent.FEE_REVERSED) {
            setClearedBalance(event.cleared_balance_cents / 100);
            setAvailableCredit(event.available_credit_cents / 100);
            setTranscripts(prev => [...prev, { author: 'system', text: `LEDGER UPDATE: Late fee reversed. Available credit adjusted.` }]);
            
            getCreditCardTransactions().then(setTransactions).catch(console.error);
          } else if (event.type === DataChannelEvent.HIGHLIGHT_TRANSACTION) {
            const txId = event.id;
            if (typeof txId === 'string' && /^[a-zA-Z0-9\-_]{8,64}$/.test(txId)) {
              console.log('Highlighting transaction:', txId);
              setHighlightedTxId(txId);
              setTranscripts(prev => [...prev, { author: 'system', text: 'Representative highlighted a transaction.' }]);
              
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
          }
        } catch (e) {
          console.error('Error parsing data channel packet:', e);
        }
      });

      room.on(RoomEvent.Disconnected, () => {
        setIsConnected(false);
        setIsHumanAgentActive(false);
        setWarningMessage('');
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



  const toggleMute = async () => {
    const enabled = !micEnabled;
    if (engine === 'gecx') {
      setMicEnabled(enabled);
    } else {
      if (roomRef.current) {
        await roomRef.current.localParticipant.setMicrophoneEnabled(enabled);
      }
      setMicEnabled(enabled);
    }
  };

  return (
    <div className="max-w-6xl mx-auto px-4 pt-28 pb-12 text-slate-100 min-h-[80vh] flex flex-col justify-between">
      
      {/* Header section */}
      <div className="text-center mb-6 flex flex-col items-center relative w-full">
        <h1 className="text-4xl font-extrabold tracking-tight bg-gradient-to-r from-blue-400 to-indigo-400 bg-clip-text text-transparent">
          Nova Horizon Voice Support
        </h1>
        <p className="text-slate-400 mt-2 text-lg">
          Talk to our real-time AI assistant for instant credit card operations.
        </p>
        <button
          onClick={() => setIsInfoModalOpen(true)}
          className="absolute right-0 top-1/2 -translate-y-1/2 p-2.5 rounded-2xl bg-white dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800/80 border border-slate-200 dark:border-slate-800 shadow-sm text-slate-500 hover:text-slate-750 dark:text-slate-400 dark:hover:text-slate-200 transition-all active:scale-95 cursor-pointer flex items-center justify-center"
          title="GCP App Integration Info"
        >
          <GoogleCloudIcon className="w-5 h-5" />
        </button>

        {/* Engine Selection Toggle */}
        {!isConnected && !isConnecting && (
          <div className="flex items-center gap-1.5 p-1 bg-slate-100 dark:bg-slate-950/60 rounded-full border border-slate-200 dark:border-slate-800/80 mt-4">
            <button
              onClick={() => setEngine('livekit')}
              className={`flex items-center gap-1.5 px-4 py-1.5 rounded-full text-xs font-bold transition-all ${
                engine === 'livekit' 
                  ? 'bg-blue-600/20 border border-blue-500/30 text-blue-600 dark:text-blue-400' 
                  : 'text-slate-500 dark:text-slate-450 hover:text-slate-750 dark:hover:text-slate-200'
              }`}
            >
              LiveKit WebRTC
            </button>
            <button
              onClick={() => setEngine('gecx')}
              className={`flex items-center gap-1.5 px-4 py-1.5 rounded-full text-xs font-bold transition-all ${
                engine === 'gecx' 
                  ? 'bg-indigo-600/20 border border-indigo-500/30 text-indigo-650 dark:text-indigo-400' 
                  : 'text-slate-500 dark:text-slate-450 hover:text-slate-750 dark:hover:text-slate-200'
              }`}
            >
              GECX Direct WS
            </button>
          </div>
        )}
      </div>

      {errorMessage && (
        <div className="fixed inset-0 z-[250] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 animate-fade-in">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl max-w-sm w-full overflow-hidden shadow-2xl p-6 text-center space-y-4">
            <div className="w-12 h-12 rounded-full bg-red-500/10 text-red-500 flex items-center justify-center mx-auto">
              <AlertCircle className="w-6 h-6" />
            </div>
            <h3 className="text-lg font-bold text-slate-900 dark:text-white">Connection Error</h3>
            <p className="text-sm text-slate-600 dark:text-slate-400 leading-relaxed">
              {errorMessage}
            </p>
            <button
              onClick={() => setErrorMessage('')}
              className="w-full py-2.5 rounded-xl bg-red-500 hover:bg-red-650 text-white font-bold text-sm shadow-md transition-colors cursor-pointer"
            >
              Acknowledge
            </button>
          </div>
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
        <div className="flex flex-col gap-6 bg-white dark:bg-slate-900/50 backdrop-blur border border-slate-200 dark:border-slate-800 rounded-3xl p-8 justify-between shadow-sm dark:shadow-none">
          {fraudContext?.fraud_alert && (fraudContext.has_active_fraud_alert || fraudTriage.outcome) && (
            <div className="rounded-2xl border border-amber-300/70 dark:border-amber-700/60 bg-amber-50 dark:bg-amber-950/30 p-4">
              <div className="flex items-start gap-3">
                <AlertCircle className="mt-0.5 h-5 w-5 text-amber-600 dark:text-amber-400 flex-shrink-0" />
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-amber-900 dark:text-amber-200">Active fraud case</p>
                  <p className="mt-1 text-sm text-amber-800 dark:text-amber-300">
                    {fraudContext.fraud_alert.summary}
                  </p>
                  {showFraudRemediationProgress ? (
                    <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2">
                      <FraudStep label="Case triaged" complete={fraudProgress.triaged} />
                      <FraudStep label="Card blocked" complete={fraudProgress.blocked} />
                      <FraudStep label="Replacement issued" complete={fraudProgress.replaced} />
                      <FraudStep label="Wallet queued" complete={fraudProgress.walletQueued} />
                      <FraudStep label="Specialist review" complete={fraudProgress.specialistReview} />
                    </div>
                  ) : (
                    <div className="mt-3 rounded-xl border border-amber-200 dark:border-amber-800/70 bg-white/80 dark:bg-slate-950/30 p-3">
                      <div className="flex items-center gap-2">
                        <div className="flex h-7 w-7 items-center justify-center rounded-full bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">
                          {fraudProgress.inspected ? <CheckCircle2 className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
                        </div>
                        <div>
                          <p className="text-xs font-bold uppercase tracking-wide text-amber-900 dark:text-amber-200">
                            {fraudProgress.inspected ? 'Ready for confirmation' : 'Alert review'}
                          </p>
                          <p className="text-xs text-amber-800 dark:text-amber-300">
                            {fraudProgress.inspected
                              ? 'Suspicious transactions have been reviewed with the customer.'
                              : 'Suspicious activity is being reviewed before account action.'}
                          </p>
                        </div>
                      </div>
                    </div>
                  )}
                  {fraudTriage.outcome && (
                    <div className="mt-3 rounded-xl border border-amber-200 dark:border-amber-800/70 bg-white/70 dark:bg-slate-950/30 p-3 text-xs text-amber-900 dark:text-amber-200">
                      <p className="font-bold uppercase tracking-wide">Fraud triage summary</p>
                      <div className="mt-2 grid gap-1.5">
                        <p>Outcome: <span className="font-semibold">{fraudTriage.outcome.replaceAll('_', ' ')}</span></p>
                        <p>Pending holds released: <span className="font-semibold">{fraudTriage.voided_authorizations.length}</span></p>
                        <p>Provisional credits: <span className="font-semibold">{fraudTriage.provisional_credits.length}</span></p>
                        {fraudTriage.provisional_credits.length > 0 && (
                          <p>
                            Credit total:{' '}
                            <span className="font-semibold">
                              {formatCents(fraudTriage.provisional_credits.reduce((total, item) => total + (item.credited_amount_cents || 0), 0))}
                            </span>
                          </p>
                        )}
                        {fraudTriage.replacement_card && (
                          <p>Replacement virtual card: <span className="font-semibold">ending in {fraudTriage.replacement_card.new_last_four}</span></p>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
          
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
                <span>••••</span> <span>••••</span> <span>••••</span> <span>{displayCard?.last_four || "8234"}</span>
              </p>
            </div>

            <div className="flex justify-between items-end">
              <div>
                <p className="text-[9px] uppercase tracking-wider text-slate-400">Cardholder</p>
                <p className="text-sm font-semibold tracking-wide text-slate-200 flex items-center gap-1.5">
                  <User size={13} className="text-slate-400" />
                  {displayCard?.cardholder_name || "Jane Doe"}
                </p>
              </div>
              <div>
                <p className="text-[9px] uppercase tracking-wider text-slate-400">Expires</p>
                <p className="text-sm font-semibold tracking-wide text-slate-200 flex items-center gap-1">
                  <Calendar size={13} className="text-slate-400" />
                  {displayCard ? `${displayCard.exp_month}/${displayCard.exp_year?.toString().slice(-2)}` : "12/28"}
                </p>
              </div>
            </div>

            {/* Card Status Locked Overlay */}
            {displayCard?.status === 'BLOCKED' && (
              <div className="absolute inset-0 bg-slate-950/85 backdrop-blur-[2px] flex flex-col items-center justify-center gap-2">
                <div className="p-3 bg-red-500/20 rounded-full border border-red-500/30 text-red-400">
                  <Lock size={32} className="animate-pulse" />
                </div>
                <span className="text-red-400 font-bold tracking-widest uppercase text-sm">Card Frozen</span>
              </div>
            )}
          </div>

          {cards.length > 0 && (
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950/30 p-4">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-3">Card instruments</h3>
              <div className="space-y-2">
                {cards.map((card) => {
                  const cardId = normalizeCardId(card.card_id || card.id);
                  const isAffected = affectedCardId && cardId === affectedCardId;
                  const isReplacement = replacementCardId && cardId === replacementCardId;
                  return (
                    <div
                      key={cardId || card.card_token || card.last_four}
                      className={`flex items-center justify-between rounded-xl border px-3 py-2 text-xs ${
                        isAffected
                          ? 'border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950/30'
                          : isReplacement
                            ? 'border-emerald-300 dark:border-emerald-700 bg-emerald-50 dark:bg-emerald-950/30'
                            : 'border-slate-200 dark:border-slate-800 bg-white/70 dark:bg-slate-900/40'
                      }`}
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <CreditCard className="h-4 w-4 text-slate-500 dark:text-slate-400 flex-shrink-0" />
                        <div className="min-w-0">
                          <p className="font-semibold text-slate-800 dark:text-slate-200">
                            {card.is_virtual ? 'Virtual card' : 'Physical card'} ending in {card.last_four}
                          </p>
                          <p className="text-[10px] text-slate-500 dark:text-slate-400">
                            {isAffected ? 'Compromised card' : isReplacement ? 'Replacement card' : card.wallet_provisioning_status ? `${card.wallet_provider || 'Google Wallet'} ${card.wallet_provisioning_status.toLowerCase()}` : 'Unaffected active card'}
                          </p>
                        </div>
                      </div>
                      <span className={`ml-3 rounded-full px-2 py-1 font-bold ${
                        card.status === 'ACTIVE'
                          ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'
                          : 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300'
                      }`}>
                        {card.status}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Account Balances Grid */}
          <div className="grid grid-cols-3 gap-4">
            <div className="bg-slate-50 dark:bg-slate-950/40 rounded-2xl p-4 border border-slate-200 dark:border-slate-800/80">
              <span className="text-[10px] text-slate-500 dark:text-slate-400 font-bold uppercase tracking-wider">Available Credit</span>
              <p className="text-xl font-bold mt-1 text-emerald-600 dark:text-emerald-400">${availableCredit.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p>
            </div>

            <div className="bg-slate-50 dark:bg-slate-950/40 rounded-2xl p-4 border border-slate-200 dark:border-slate-800/80">
              <span className="text-[10px] text-slate-500 dark:text-slate-400 font-bold uppercase tracking-wider">Credit Limit</span>
              <p className="text-xl font-bold mt-1 text-slate-800 dark:text-slate-200">${creditLimit.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p>
            </div>

            <div className="bg-slate-50 dark:bg-slate-950/40 rounded-2xl p-4 border border-slate-200 dark:border-slate-800/80">
              <span className="text-[10px] text-slate-500 dark:text-slate-400 font-bold uppercase tracking-wider">Current Balance</span>
              <p className="text-xl font-bold mt-1 text-indigo-600 dark:text-indigo-400">${clearedBalance.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p>
            </div>
          </div>

          {/* Transaction Ledger List */}
          <div className="bg-slate-50/50 dark:bg-slate-950/30 rounded-2xl p-4 border border-slate-200 dark:border-slate-800/80 flex-grow max-h-[200px] overflow-y-auto">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-2">Statement Ledger</h3>
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
                          ? 'border-yellow-500 bg-yellow-500/10 scale-[1.02] shadow-lg shadow-yellow-500/10 text-slate-900 dark:text-white' 
                          : 'border-slate-200 dark:border-slate-800 bg-white/60 dark:bg-slate-900/30 text-slate-700 dark:text-slate-300'
                      }`}
                    >
                      <div>
                        <p className="font-semibold text-slate-900 dark:text-slate-200">{tx.description}</p>
                        <p className="text-[9px] text-slate-450 dark:text-slate-500">{new Date(tx.posted_at).toLocaleDateString()}</p>
                      </div>
                      <span className={`font-mono font-bold ${tx.amount_cents > 0 ? 'text-indigo-600 dark:text-indigo-300' : 'text-emerald-600 dark:text-emerald-400'}`}>
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
        <div className="flex flex-col bg-white dark:bg-slate-900/50 backdrop-blur border border-slate-200 dark:border-slate-800 rounded-3xl p-6 min-h-[400px] shadow-sm dark:shadow-none">
          
          {/* Avatar Video Frame container if video mode is active */}
          {mode === 'video' && isConnected && (
            <div className="flex flex-col mb-4">
              <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-2">
                Live Avatar Stream
              </h2>
              <div className="aspect-square w-full max-w-[340px] mx-auto relative rounded-3xl overflow-hidden border-2 border-slate-200 dark:border-slate-800 shadow-inner bg-slate-950">
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

          <h2 className="text-md font-bold uppercase tracking-wider text-slate-900 dark:text-white mb-4 border-b border-slate-200 dark:border-slate-800 pb-2">
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
                    <span className="inline-block text-[10px] bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 px-2.5 py-1 rounded-full font-mono">
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
                        : 'bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-200 rounded-bl-none border border-slate-200/50 dark:border-transparent'
                  }`}>
                    <p className="text-[9px] uppercase tracking-wide text-slate-500 dark:text-slate-400 font-bold mb-0.5">
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
      <div className="flex flex-col items-center gap-4 bg-white dark:bg-slate-900/50 backdrop-blur border border-slate-200 dark:border-slate-800 rounded-3xl p-6 shadow-sm dark:shadow-none">
        
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

        {/* Diagnostics & Volume Control Panel (Only when connected) */}
        {isConnected && (
          <div className="w-full max-w-md bg-slate-50 dark:bg-slate-950/40 border border-slate-200 dark:border-slate-800/80 rounded-2xl p-4 flex flex-col gap-3 text-xs mb-2">
            <div className="flex justify-between items-center text-slate-500 dark:text-slate-400">
              <span className="font-semibold uppercase tracking-wider text-[10px]">Diagnostics</span>
              <span className="font-mono text-emerald-600 dark:text-emerald-400">Active</span>
            </div>
            <div className="grid grid-cols-2 gap-2 text-[11px] text-slate-700 dark:text-slate-300 font-mono">
              <div>Engine: <span className="text-blue-600 dark:text-blue-400 font-bold">{engine === 'gecx' ? 'GECX Direct WS' : 'LiveKit WebRTC'}</span></div>
              <div>Codec: <span className="text-indigo-650 dark:text-indigo-400">{engine === 'gecx' ? 'PCM (16kHz 16-bit)' : 'Opus (48kHz)'}</span></div>
              {engine === 'gecx' && (
                <>
                  <div>RTT Latency: <span className="text-yellow-650 dark:text-yellow-400">{latency} ms</span></div>
                  <div>Transport: <span className="text-slate-500 dark:text-slate-400">Stateless Proxy</span></div>
                </>
              )}
            </div>
            
            {/* Volume Playout slider control */}
            <div className="flex items-center gap-3 border-t border-slate-200 dark:border-slate-800/80 pt-3 mt-1">
              <span className="text-[10px] text-slate-500 dark:text-slate-400 font-bold uppercase tracking-wider">Volume:</span>
              <input 
                type="range" 
                min="0" 
                max="1.0" 
                step="0.05"
                value={volume}
                onChange={(e) => setVolume(parseFloat(e.target.value))}
                className="flex-grow h-1 bg-slate-200 dark:bg-slate-800 rounded-lg appearance-none cursor-pointer accent-blue-500"
              />
              <span className="text-[10px] text-slate-700 dark:text-slate-300 font-mono w-8 text-right">{Math.round(volume * 100)}%</span>
            </div>
          </div>
        )}

        {/* Mode Selection Toggle */}
        {!isConnected && !isConnecting && engine === 'livekit' && (
          <div className="flex items-center gap-1.5 p-1 bg-slate-100 dark:bg-slate-950/60 rounded-full border border-slate-200 dark:border-slate-800/80 mb-2">
            <button
              onClick={() => setMode('audio')}
              className={`flex items-center gap-1.5 px-4 py-1.5 rounded-full text-xs font-bold transition-all ${
                mode === 'audio' 
                  ? 'bg-blue-600/20 border border-blue-500/30 text-blue-600 dark:text-blue-400' 
                  : 'text-slate-500 dark:text-slate-450 hover:text-slate-700 dark:hover:text-slate-200'
              }`}
            >
              <Mic size={14} />
              Voice Call
            </button>
            <button
              onClick={() => setMode('video')}
              className={`flex items-center gap-1.5 px-4 py-1.5 rounded-full text-xs font-bold transition-all ${
                mode === 'video' 
                  ? 'bg-indigo-600/20 border border-indigo-500/30 text-indigo-650 dark:text-indigo-400' 
                  : 'text-slate-500 dark:text-slate-450 hover:text-slate-700 dark:hover:text-slate-200'
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

      <GcpInfoModal
        isOpen={isInfoModalOpen}
        onClose={() => setIsInfoModalOpen(false)}
        title={engine === 'gecx' ? 'GECX Voice Telephony Integration' : 'Gemini Live WebRTC Integration'}
      >
        <div className="space-y-4 text-slate-600 dark:text-slate-400 text-sm leading-relaxed">
          {engine === 'gecx' ? (
            <>
              <p>
                The voice support consultation in GECX mode is powered by <strong>Gemini Enterprise for Customer Experience (GECX)</strong> using bidirectional audio streaming.
              </p>
              <p>
                The frontend opens a direct WebSocket pipeline to the <code>banking-service</code> backend. The backend acts as a gateway proxy, establishing a bidirectional gRPC session (via the <code>BidiRunSession</code> RPC) to the conversational agent deployment in CX Agent Studio.
              </p>
              <div className="bg-slate-50 dark:bg-slate-950 p-4 rounded-2xl border border-slate-100 dark:border-slate-800 space-y-3">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h4 className="font-semibold text-slate-800 dark:text-slate-200 text-xs uppercase tracking-wider">CX Agent Studio Console</h4>
                    <p className="text-[11px] text-slate-500 dark:text-slate-400">View agent deployments, versions, and flow configurations.</p>
                  </div>
                  <div className="flex flex-col items-end gap-1.5 shrink-0">
                    <a
                      href={`https://ces.cloud.google.com/projects/${projectId}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-emerald-500 hover:text-emerald-600 font-semibold text-xs hover:underline"
                    >
                      <span>View Console</span>
                      <ExternalLink className="w-3.5 h-3.5" />
                    </a>
                    {appId && (
                      <a
                        href={`https://ces.cloud.google.com/projects/${cxProjectId || projectId}/locations/us/apps/${appId}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-emerald-500 hover:text-emerald-600 font-semibold text-xs hover:underline"
                      >
                        <span>View Agent</span>
                        <ExternalLink className="w-3.5 h-3.5" />
                      </a>
                    )}
                  </div>
                </div>
                <hr className="border-slate-100 dark:border-slate-800" />
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h4 className="font-semibold text-slate-800 dark:text-slate-200 text-xs uppercase tracking-wider">Architecture Guide</h4>
                    <p className="text-[11px] text-slate-500 dark:text-slate-400">Learn about GECX Bidi gRPC streaming and the telephony gateway topology.</p>
                  </div>
                  <a
                    href="https://github.com/GoogleCloudPlatform/fsi-gecx-bundle/blob/main/docs/architecture/ai-and-voice/gecx_telephony_voice_agent.md"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-emerald-500 hover:text-emerald-600 font-semibold text-xs shrink-0 hover:underline"
                  >
                    <span>View Design</span>
                    <ExternalLink className="w-3.5 h-3.5" />
                  </a>
                </div>
              </div>
            </>
          ) : (
            <>
              <p>
                The Gemini Live experience is powered by the <strong>Multimodal Gemini Live API</strong>, using a low-latency WebRTC connection.
              </p>
              <p>
                The client initiates a connection to a self-contained LiveKit server deployment running on Cloud Run. The LiveKit server establishes a persistent media stream back and forth with Vertex AI Multimodal Live APIs, delivering sub-second voice interactions and rich real-time visual tool feedback.
              </p>
              <div className="bg-slate-50 dark:bg-slate-950 p-4 rounded-2xl border border-slate-100 dark:border-slate-800 space-y-3">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h4 className="font-semibold text-slate-800 dark:text-slate-200 text-xs uppercase tracking-wider">Vertex AI Live Console</h4>
                    <p className="text-[11px] text-slate-500 dark:text-slate-400">Inspect Multimodal model configuration and settings.</p>
                  </div>
                  <a
                    href={`https://console.cloud.google.com/vertex-ai?project=${projectId}`}
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
                    <h4 className="font-semibold text-slate-800 dark:text-slate-200 text-xs uppercase tracking-wider">Architecture Guide</h4>
                    <p className="text-[11px] text-slate-500 dark:text-slate-400">Learn about LiveKit, WebRTC signaling, and low-latency audio/video routing.</p>
                  </div>
                  <a
                      href="https://github.com/GoogleCloudPlatform/fsi-gecx-bundle/blob/main/docs/architecture/ai-and-voice/gemini_live_voice_agent.md"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-emerald-500 hover:text-emerald-600 font-semibold text-xs shrink-0 hover:underline"
                  >
                    <span>View Design</span>
                    <ExternalLink className="w-3.5 h-3.5" />
                  </a>
                </div>
              </div>
            </>
          )}
        </div>
      </GcpInfoModal>

    </div>
  );
}
