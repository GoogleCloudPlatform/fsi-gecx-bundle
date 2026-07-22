import assert from 'node:assert/strict';
import test from 'node:test';

import {
  connectSilentPcmSink,
  pcmFrameForMicrophoneState,
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
