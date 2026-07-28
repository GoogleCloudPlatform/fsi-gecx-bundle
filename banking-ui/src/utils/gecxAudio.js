export function connectSilentPcmSink(audioContext, workletNode) {
  const sinkNode = audioContext.createGain();
  sinkNode.gain.value = 0;
  workletNode.connect(sinkNode);
  sinkNode.connect(audioContext.destination);
  return sinkNode;
}

export function pcmFrameForMicrophoneState(rawBuffer, microphoneEnabled) {
  if (microphoneEnabled) return rawBuffer;
  return new ArrayBuffer(rawBuffer.byteLength);
}

export function remainingPlayoutSeconds(currentTime, nextPlayoutTime, activeSourceCount) {
  if (!Number.isFinite(currentTime) || !Number.isFinite(nextPlayoutTime)) return 0;
  if (activeSourceCount <= 0) return 0;
  return Math.max(0, nextPlayoutTime - currentTime);
}
