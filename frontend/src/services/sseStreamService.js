/**
 * sseStreamService.js
 * Milestone M2.1: Robust SSE stream parsing and consumption for progressive monitoring.
 * Handles:
 * - Arbitrary network chunk boundaries
 * - Multiple SSE events in one chunk
 * - Events split across multiple chunks
 * - Malformed JSON handling
 * - Stream cancellation and abort signals
 */

/**
 * Parses an incoming text chunk against a stateful buffer.
 * Returns an array of parsed event objects: [{ event: string, data: any }]
 * 
 * @param {{ buffer: string }} state 
 * @param {string} chunk 
 * @returns {Array<{ event: string, data: any }>}
 */
export function parseSseChunk(state, chunk) {
  if (!state) {
    state = { buffer: '' };
  }
  if (!chunk) return [];

  state.buffer = (state.buffer || '') + chunk;
  state.buffer = state.buffer.replace(/\r\n/g, '\n');

  const events = [];
  let boundaryIndex;

  while ((boundaryIndex = state.buffer.indexOf('\n\n')) !== -1) {
    const rawBlock = state.buffer.slice(0, boundaryIndex).trim();
    state.buffer = state.buffer.slice(boundaryIndex + 2);

    if (!rawBlock) continue;

    let eventType = 'message';
    const dataLines = [];

    const lines = rawBlock.split('\n');
    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.startsWith('event:')) {
        eventType = trimmed.slice(6).trim();
      } else if (trimmed.startsWith('data:')) {
        dataLines.push(trimmed.slice(5).trim());
      }
    }

    if (dataLines.length > 0) {
      const rawData = dataLines.join('\n');
      try {
        const parsedData = JSON.parse(rawData);
        events.push({ event: eventType, data: parsedData });
      } catch (err) {
        // If JSON parsing fails, emit raw string or handle gracefully
        events.push({ event: eventType, data: rawData, parseError: true });
      }
    }
  }

  return events;
}

/**
 * Consumes a browser ReadableStream (e.g. from fetch response.body) using SSE semantics.
 * 
 * @param {ReadableStream} readableStream 
 * @param {(event: { event: string, data: any }) => void} onEvent 
 * @param {(error: Error) => void} onError 
 * @param {AbortSignal} [signal] 
 * @returns {Promise<void>}
 */
export async function consumeSseStream(readableStream, onEvent, onError, signal) {
  if (!readableStream) {
    if (onError) onError(new Error('ReadableStream is required'));
    return;
  }

  const reader = readableStream.getReader();
  const decoder = new TextDecoder('utf-8');
  const state = { buffer: '' };

  try {
    while (true) {
      if (signal?.aborted) {
        await reader.cancel();
        break;
      }

      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value, { stream: true });
      const parsedEvents = parseSseChunk(state, chunk);

      for (const ev of parsedEvents) {
        if (signal?.aborted) break;
        if (onEvent) onEvent(ev);
      }
    }

    // Process any remaining complete block after stream close
    if (state.buffer.trim() && !signal?.aborted) {
      const remainingEvents = parseSseChunk(state, '\n\n');
      for (const ev of remainingEvents) {
        if (onEvent) onEvent(ev);
      }
    }
  } catch (err) {
    if (err.name === 'AbortError' || signal?.aborted) {
      // Ignored on explicit cancellation
      return;
    }
    if (onError) onError(err);
    throw err;
  } finally {
    try {
      reader.releaseLock();
    } catch (_) {}
  }
}
