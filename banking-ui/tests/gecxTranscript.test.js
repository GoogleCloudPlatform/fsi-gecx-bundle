import assert from 'node:assert/strict';
import test from 'node:test';

import { mergeGecxTranscript } from '../src/utils/gecxTranscript.js';


test('CES cumulative recognition hypotheses replace the active user turn', () => {
  let transcripts = [];
  for (const text of [
    "No, I don't.",
    "No, I don't. Hello",
    "No, I don't. Hello Are you there?",
  ]) {
    transcripts = mergeGecxTranscript(transcripts, {
      type: 'TRANSCRIPT',
      author: 'user',
      text,
      replace_previous: true,
    });
  }

  assert.deepEqual(transcripts, [
    {
      author: 'user',
      text: "No, I don't. Hello Are you there?",
    },
  ]);
});


test('CES agent and completed customer turns remain separate transcript entries', () => {
  const transcripts = [
    { author: 'user', text: "No, I don't." },
    { author: 'agent', text: 'Please confirm the proposed actions.' },
  ];

  const merged = mergeGecxTranscript(transcripts, {
    type: 'TRANSCRIPT',
    author: 'user',
    text: 'I confirm.',
    replace_previous: true,
  });

  assert.deepEqual(merged, [
    { author: 'user', text: "No, I don't." },
    { author: 'agent', text: 'Please confirm the proposed actions.' },
    { author: 'user', text: 'I confirm.' },
  ]);
});
