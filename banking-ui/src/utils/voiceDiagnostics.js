// Copyright 2026 Google LLC
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy at https://www.apache.org/licenses/LICENSE-2.0

export const finiteMs = value => Number.isFinite(value) && value >= 0 ? value : null;

// Browser energy detection estimates speech boundaries; it never controls VAD,
// microphone transmission, interruption, or banking authorization.
export function createResponseTimer() {
  let start = null, lastVoice = null, pending = null, lastAudio = null;
  let audioSeen = false, textSeen = false, speaking = false, candidateAudio = null;
  return {
    cancel() { start = lastVoice = pending = candidateAudio = null; speaking = false; },
    sample(now, inputActive, outputActive) {
      if (inputActive) {
        if (!speaking) { start = now; pending = candidateAudio = null; audioSeen = textSeen = false; }
        speaking = true;
        lastVoice = now; candidateAudio = null;
      } else if (speaking && now - lastVoice >= 250) {
        speaking = false;
        pending = lastVoice - start >= 150 ? lastVoice : null;
      }
      if (pending !== null && now - pending > 30000) pending = null;
      let responseMs = null;
      // Ignore the greeting and continuous audio from an interrupted old reply.
      if (outputActive && !inputActive && lastVoice !== null
          && (lastAudio === null || now - lastAudio >= 150) && candidateAudio === null) {
        candidateAudio = now;
      }
      if (pending !== null && !audioSeen && candidateAudio !== null && candidateAudio >= pending) {
        responseMs = candidateAudio - pending;
        audioSeen = true;
      }
      if (outputActive) lastAudio = now;
      return responseMs;
    },
    transcript(now) {
      if (pending === null || textSeen || now - pending > 30000) return null;
      textSeen = true;
      return now - pending;
    },
  };
}

export function summarizeRtcStats(report, previous = new Map()) {
  let rttMs = null, jitterMs = null, lost = 0, received = 0;
  const next = new Map();
  const reports = Array.from(report?.values?.() || []);
  const selected = new Set(reports.filter(s => s.type === 'transport').map(s => s.selectedCandidatePairId));
  for (const s of reports) {
    if (s.type === 'candidate-pair' && (selected.has(s.id) || (s.nominated && s.state === 'succeeded'))) {
      rttMs = finiteMs(s.currentRoundTripTime * 1000);
    }
    if (s.type === 'inbound-rtp' && (s.kind || s.mediaType) === 'audio' && !s.isRemote) {
      jitterMs = finiteMs(s.jitter * 1000);
      const before = previous.get(s.id);
      if (Number.isFinite(s.packetsLost) && Number.isFinite(s.packetsReceived)) {
        next.set(s.id, { lost: s.packetsLost, received: s.packetsReceived });
        if (before && s.packetsReceived >= before.received && s.packetsLost >= before.lost) {
          lost += s.packetsLost - before.lost;
          received += s.packetsReceived - before.received;
        }
      }
    }
  }
  return { rttMs, jitterMs, lossPercent: lost + received > 0 ? 100 * lost / (lost + received) : null, counters: next };
}
