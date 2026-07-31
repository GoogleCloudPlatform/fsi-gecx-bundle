/**
 * Copyright 2026 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

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
