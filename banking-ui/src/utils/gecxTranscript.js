export function mergeGecxTranscript(transcripts, payload) {
  const next = {
    author: payload.author,
    text: payload.text,
    ...(payload.transcript_id ? { transcript_id: payload.transcript_id } : {}),
  };
  const previous = transcripts[transcripts.length - 1];

  if (payload.transcript_id) {
    const existingIndex = transcripts.findIndex(
      transcript => transcript.transcript_id === payload.transcript_id
    );
    if (existingIndex >= 0) {
      if (transcripts[existingIndex].text === payload.text) return transcripts;
      return transcripts.map((transcript, index) => (
        index === existingIndex ? next : transcript
      ));
    }
  }

  if (
    payload.replace_previous === true
    && previous?.author === payload.author
  ) {
    if (previous.text === payload.text) return transcripts;
    return [...transcripts.slice(0, -1), next];
  }

  return [...transcripts, next];
}
