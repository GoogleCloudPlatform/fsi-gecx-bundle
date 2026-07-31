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

export function mergeGecxTranscript(transcripts, payload) {
  const text = typeof payload.text === 'string' ? payload.text.trim() : '';
  if (!text) return transcripts;
  const next = {
    author: payload.author,
    text,
    ...(payload.transcript_id ? { transcript_id: payload.transcript_id } : {}),
  };
  const previous = transcripts[transcripts.length - 1];

  if (payload.transcript_id) {
    const existingIndex = transcripts.findIndex(
      transcript => transcript.transcript_id === payload.transcript_id
    );
    if (existingIndex >= 0) {
      if (transcripts[existingIndex].text === text) return transcripts;
      return transcripts.map((transcript, index) => (
        index === existingIndex ? next : transcript
      ));
    }
  }

  if (
    payload.replace_previous === true
    && previous?.author === payload.author
  ) {
    if (previous.text === text) return transcripts;
    return [...transcripts.slice(0, -1), next];
  }

  return [...transcripts, next];
}
