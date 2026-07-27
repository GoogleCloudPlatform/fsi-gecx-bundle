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

test('Gemini Live agent deltas update one transcript entry per provider turn', () => {
  let transcripts = [];
  for (const text of [
    "Hi, I'm Nova",
    "Hi, I'm Nova with Nova Horizon Bank.",
    "Hi, I'm Nova with Nova Horizon Bank. How can I help?",
  ]) {
    transcripts = mergeGecxTranscript(transcripts, {
      type: 'TRANSCRIPT',
      author: 'agent',
      text,
      transcript_id: 'ces-1:agent:1',
      replace_previous: true,
    });
  }

  assert.deepEqual(transcripts, [
    {
      author: 'agent',
      text: "Hi, I'm Nova with Nova Horizon Bank. How can I help?",
      transcript_id: 'ces-1:agent:1',
    },
  ]);
});


test('agent transcript identity survives interleaved operational events', () => {
  const transcripts = [
    {
      author: 'agent',
      text: 'Your fraud report was submitted',
      transcript_id: 'ces-1:agent:2',
    },
    { author: 'system', text: 'CASE UPDATE: Fraud case triaged.' },
  ];

  const merged = mergeGecxTranscript(transcripts, {
    type: 'TRANSCRIPT',
    author: 'agent',
    text: 'Your fraud report was submitted for specialist review.',
    transcript_id: 'ces-1:agent:2',
    replace_previous: true,
  });

  assert.deepEqual(merged, [
    {
      author: 'agent',
      text: 'Your fraud report was submitted for specialist review.',
      transcript_id: 'ces-1:agent:2',
    },
    { author: 'system', text: 'CASE UPDATE: Fraud case triaged.' },
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
