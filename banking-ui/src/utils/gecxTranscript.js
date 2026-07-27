export function mergeGecxTranscript(transcripts, payload) {
  const next = {
    author: payload.author,
    text: payload.text,
  };
  const previous = transcripts[transcripts.length - 1];

  if (
    payload.replace_previous === true
    && previous?.author === payload.author
  ) {
    if (previous.text === payload.text) return transcripts;
    return [...transcripts.slice(0, -1), next];
  }

  return [...transcripts, next];
}
