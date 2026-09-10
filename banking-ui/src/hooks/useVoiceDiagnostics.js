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

import { useCallback, useEffect, useRef, useState } from 'react';
import { createResponseTimer, finiteMs, summarizeRtcStats } from '../utils/voiceDiagnostics.js';

export default function useVoiceDiagnostics({ connected, engine, roomRef, micStreamRef, cesOutputStreamRef, muted }) {
  const [metrics, setMetrics] = useState({});
  const timer = useRef(createResponseTimer());
  const mutedRef = useRef(muted);
  useEffect(() => { mutedRef.current = muted; if (muted) timer.current.cancel(); }, [muted]);
  const event = useCallback(payload => {
    if (payload.type === 'TRANSCRIPT' && payload.author === 'agent') {
      const value = timer.current.transcript(performance.now());
      if (value !== null) setMetrics(m => ({ ...m, transcriptMs: value }));
    }
    if (payload.type === 'VOICE_DIAGNOSTICS') {
      const patch = {};
      for (const [wire, local] of [['tool_ms', 'toolMs'], ['provider_first_chunk_ms', 'providerFirstChunkMs']]) {
        if (Object.hasOwn(payload, wire)) patch[local] = finiteMs(payload[wire]);
      }
      setMetrics(m => ({ ...m, ...patch }));
    }
  }, []);

  useEffect(() => {
    timer.current = createResponseTimer();
    setMetrics({});
    if (!connected) return;
    let disposed = false, context, input, output, counters = new Map(), polling = false;
    const release = node => { if (node) { node.source.disconnect(); node.analyser.disconnect(); node.sink.disconnect(); } };
    const attach = (old, track) => {
      if (old?.track === track) return old;
      release(old);
      timer.current.cancel();
      if (!track || track.readyState !== 'live') return null;
      context ||= new (window.AudioContext || window.webkitAudioContext)();
      if (context.state === 'suspended') context.resume().catch(() => {});
      const source = context.createMediaStreamSource(new MediaStream([track]));
      const analyser = context.createAnalyser(); analyser.fftSize = 1024;
      const sink = context.createGain(); sink.gain.value = 0;
      source.connect(analyser); analyser.connect(sink); sink.connect(context.destination);
      return { track, source, analyser, sink, samples: new Float32Array(1024) };
    };
    const active = node => {
      if (!node || node.track.muted || !node.track.enabled || context?.state !== 'running') return false;
      node.analyser.getFloatTimeDomainData(node.samples);
      return Math.sqrt(node.samples.reduce((sum, x) => sum + x * x, 0) / node.samples.length) > 0.012;
    };
    const tracks = () => {
      const room = roomRef.current;
      const local = Array.from(room?.localParticipant?.audioTrackPublications?.values() || []).find(p => p.source === 'microphone')?.track;
      const remote = Array.from(room?.remoteParticipants?.values() || []).flatMap(p => Array.from(p.audioTrackPublications.values())).find(p => p.track)?.track;
      return { local, remote };
    };
    const sampling = setInterval(() => {
      try {
        const { local, remote } = tracks();
        input = attach(input, engine === 'gecx' ? micStreamRef.current?.getAudioTracks()[0] : local?.mediaStreamTrack);
        output = attach(output, engine === 'gecx' ? cesOutputStreamRef.current?.getAudioTracks()[0] : remote?.mediaStreamTrack);
        if (mutedRef.current || !input || !output || document.hidden) { timer.current.cancel(); return; }
        const responseMs = timer.current.sample(performance.now(), active(input), active(output));
        if (responseMs !== null) setMetrics(m => ({ ...m, responseMs }));
      } catch { timer.current.cancel(); }
    }, 50);
    const stats = setInterval(async () => {
      if (engine === 'gecx' || polling) return;
      polling = true;
      try {
        const { local, remote } = tracks();
        const track = remote || local;
        const report = await track?.getRTCStatsReport();
        if (!disposed) {
          const result = summarizeRtcStats(report, counters); counters = result.counters;
          setMetrics(m => ({ ...m, rttMs: result.rttMs, jitterMs: result.jitterMs, lossPercent: result.lossPercent }));
        }
      } catch { if (!disposed) setMetrics(m => ({ ...m, rttMs: null, jitterMs: null, lossPercent: null })); }
      finally { polling = false; }
    }, 3000);
    return () => {
      disposed = true; clearInterval(sampling); clearInterval(stats);
      release(input); release(output); context?.close().catch(() => {});
    };
  }, [connected, engine, roomRef, micStreamRef, cesOutputStreamRef]);
  return { metrics, event };
}
