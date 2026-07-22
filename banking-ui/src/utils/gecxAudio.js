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
