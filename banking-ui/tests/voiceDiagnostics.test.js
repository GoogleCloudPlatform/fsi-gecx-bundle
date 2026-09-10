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

import test from 'node:test';
import assert from 'node:assert/strict';
import { createResponseTimer, summarizeRtcStats, finiteMs } from '../src/utils/voiceDiagnostics.js';

function utterance(timer, start = 1000) {
  timer.sample(start, true, false);
  timer.sample(start + 200, true, false);
  timer.sample(start + 450, false, false);
}
test('opening audio is ignored, response and transcript measure once from last speech', () => {
  const timer = createResponseTimer();
  assert.equal(timer.sample(0, false, true), null);
  utterance(timer);
  assert.equal(timer.transcript(1600), 400);
  assert.equal(timer.transcript(1700), null);
  assert.equal(timer.sample(1800, false, true), 600);
  assert.equal(timer.sample(1900, false, true), null);
});
test('short noise, expired observations, and cancelled turns produce no measurement', () => {
  const timer = createResponseTimer();
  timer.sample(0, true, false); timer.sample(300, false, false);
  assert.equal(timer.sample(500, false, true), null);
  utterance(timer);
  assert.equal(timer.sample(40000, false, true), null);
  utterance(timer, 50000); timer.cancel();
  assert.equal(timer.transcript(51000), null);
});
test('continuous audio from the interrupted response is not a new response', () => {
  const timer = createResponseTimer();
  timer.sample(0, true, true); timer.sample(200, true, true);
  for (let t = 250; t <= 800; t += 50) assert.equal(timer.sample(t, false, true), null);
  timer.sample(1000, false, false);
  assert.equal(timer.sample(1100, false, true), 900);
});
test('WebRTC uses selected pair and interval loss; counter resets are unavailable', () => {
  const report = (lost, received) => new Map([
    ['transport', { type: 'transport', selectedCandidatePairId: 'pair' }],
    ['pair', { id: 'pair', type: 'candidate-pair', currentRoundTripTime: .024 }],
    ['audio', { id: 'audio', type: 'inbound-rtp', kind: 'audio', jitter: .003, packetsLost: lost, packetsReceived: received }],
  ]);
  const first = summarizeRtcStats(report(5, 100));
  assert.equal(first.rttMs, 24); assert.equal(first.jitterMs, 3); assert.equal(first.lossPercent, null);
  const second = summarizeRtcStats(report(7, 198), first.counters);
  assert.equal(second.lossPercent, 2);
  assert.equal(summarizeRtcStats(report(0, 4), second.counters).lossPercent, null);
  assert.equal(summarizeRtcStats(undefined).rttMs, null);
});
test('unknown numeric values are never displayed as zero', () => {
  for (const value of [null, undefined, NaN, Infinity, -1, '12']) assert.equal(finiteMs(value), null);
  assert.equal(finiteMs(0), 0);
});

test('audio arriving before the silence window settles retains its actual arrival time', () => {
  const timer = createResponseTimer();
  timer.sample(0, true, false); timer.sample(200, true, false);
  assert.equal(timer.sample(300, false, true), null);
  assert.equal(timer.sample(450, false, true), 100);
});
