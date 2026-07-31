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

import assert from 'node:assert/strict';
import test from 'node:test';

import {
  connectSilentPcmSink,
  pcmFrameForMicrophoneState,
  remainingPlayoutSeconds,
} from '../src/utils/gecxAudio.js';


test('connects PCM capture to a silent rendered audio graph', () => {
  const connections = [];
  const destination = { name: 'destination' };
  const sinkNode = {
    gain: { value: 1 },
    connect(target) {
      connections.push(['sink', target]);
    },
  };
  const workletNode = {
    connect(target) {
      connections.push(['worklet', target]);
    },
  };
  const audioContext = {
    destination,
    createGain() {
      return sinkNode;
    },
  };

  assert.equal(connectSilentPcmSink(audioContext, workletNode), sinkNode);
  assert.equal(sinkNode.gain.value, 0);
  assert.deepEqual(connections, [
    ['worklet', sinkNode],
    ['sink', destination],
  ]);
});

test('muting preserves the continuous CES PCM stream with silent frames', () => {
  const rawBuffer = Uint8Array.from([1, 2, 3, 4]).buffer;

  assert.equal(pcmFrameForMicrophoneState(rawBuffer, true), rawBuffer);
  assert.deepEqual(
    [...new Uint8Array(pcmFrameForMicrophoneState(rawBuffer, false))],
    [0, 0, 0, 0],
  );
});

test('remote close drains only audio that is still scheduled', () => {
  assert.equal(remainingPlayoutSeconds(10, 13.5, 2), 3.5);
  assert.equal(remainingPlayoutSeconds(14, 13.5, 2), 0);
  assert.equal(remainingPlayoutSeconds(10, 13.5, 0), 0);
});
