import test from 'node:test';
import assert from 'node:assert/strict';
import { parseSseChunk, consumeSseStream } from './sseStreamService.js';

test('1. parseSseChunk - Single complete event', () => {
  const state = { buffer: '' };
  const chunk = 'event: init\ndata: {"fps": 25.0, "duration": 10.5}\n\n';
  const events = parseSseChunk(state, chunk);

  assert.equal(events.length, 1);
  assert.equal(events[0].event, 'init');
  assert.equal(events[0].data.fps, 25.0);
  assert.equal(events[0].data.duration, 10.5);
  assert.equal(state.buffer, '');
});

test('2. parseSseChunk - Multiple events in a single chunk', () => {
  const state = { buffer: '' };
  const chunk = 
    'event: frame\ndata: {"frame_idx": 1, "timestamp_sec": 0.8}\n\n' +
    'event: progress\ndata: {"processed_frames": 1, "progress_pct": 10.0}\n\n';
  
  const events = parseSseChunk(state, chunk);

  assert.equal(events.length, 2);
  assert.equal(events[0].event, 'frame');
  assert.equal(events[0].data.frame_idx, 1);
  assert.equal(events[1].event, 'progress');
  assert.equal(events[1].data.progress_pct, 10.0);
  assert.equal(state.buffer, '');
});

test('3. parseSseChunk - Event split across two arbitrary network chunks', () => {
  const state = { buffer: '' };
  
  // Chunk 1: Incomplete event
  const chunk1 = 'event: incident\ndata: {"episode_id": "ep_123", "worker';
  const events1 = parseSseChunk(state, chunk1);
  assert.equal(events1.length, 0, 'No event should be emitted from partial chunk');
  assert.ok(state.buffer.length > 0, 'Partial chunk should be preserved in buffer');

  // Chunk 2: Completing the event
  const chunk2 = '_id": "W-001", "missingPPE": ["helmet"]}\n\n';
  const events2 = parseSseChunk(state, chunk2);
  assert.equal(events2.length, 1, 'Event must be emitted once completed');
  assert.equal(events2[0].event, 'incident');
  assert.equal(events2[0].data.episode_id, 'ep_123');
  assert.equal(events2[0].data.worker_id, 'W-001');
  assert.deepEqual(events2[0].data.missingPPE, ['helmet']);
  assert.equal(state.buffer, '');
});

test('4. parseSseChunk - Normalizes Windows CRLF line endings', () => {
  const state = { buffer: '' };
  const chunk = 'event: frame\r\ndata: {"frame_idx": 2}\r\n\r\n';
  const events = parseSseChunk(state, chunk);

  assert.equal(events.length, 1);
  assert.equal(events[0].event, 'frame');
  assert.equal(events[0].data.frame_idx, 2);
  assert.equal(state.buffer, '');
});

test('5. parseSseChunk - Gracefully handles malformed JSON without crashing', () => {
  const state = { buffer: '' };
  const chunk = 'event: frame\ndata: {unquoted_broken_json\n\n';
  const events = parseSseChunk(state, chunk);

  assert.equal(events.length, 1);
  assert.equal(events[0].event, 'frame');
  assert.equal(events[0].parseError, true);
  assert.equal(events[0].data, '{unquoted_broken_json');
});

test('6. parseSseChunk - Custom event types verification', () => {
  const state = { buffer: '' };
  const eventTypes = ['init', 'frame', 'incident', 'resolution', 'progress', 'done', 'error'];
  const chunk = eventTypes.map(et => `event: ${et}\ndata: {"type": "${et}"}\n\n`).join('');
  
  const events = parseSseChunk(state, chunk);
  assert.equal(events.length, 7);
  for (let i = 0; i < eventTypes.length; i++) {
    assert.equal(events[i].event, eventTypes[i]);
    assert.equal(events[i].data.type, eventTypes[i]);
  }
});

test('7. consumeSseStream - Consumes readable stream chunks and delivers to callback', async () => {
  const chunks = [
    new TextEncoder().encode('event: init\ndata: {"session_id": "test_1"}\n\n'),
    new TextEncoder().encode('event: frame\ndata: {"frame_idx": 1}\n\n'),
    new TextEncoder().encode('event: done\ndata: {"status": "COMPLIANT"}\n\n')
  ];

  let readIdx = 0;
  const mockStream = {
    getReader() {
      return {
        async read() {
          if (readIdx < chunks.length) {
            return { done: false, value: chunks[readIdx++] };
          }
          return { done: true, value: undefined };
        },
        releaseLock() {}
      };
    }
  };

  const received = [];
  await consumeSseStream(mockStream, (ev) => received.push(ev));

  assert.equal(received.length, 3);
  assert.equal(received[0].event, 'init');
  assert.equal(received[1].event, 'frame');
  assert.equal(received[2].event, 'done');
});

test('8. consumeSseStream - AbortSignal halts consumption immediately', async () => {
  const controller = new AbortController();
  const chunks = [
    new TextEncoder().encode('event: frame\ndata: {"frame_idx": 1}\n\n'),
    new TextEncoder().encode('event: frame\ndata: {"frame_idx": 2}\n\n')
  ];

  let readIdx = 0;
  const mockStream = {
    getReader() {
      return {
        async read() {
          if (readIdx === 1) {
            controller.abort();
          }
          if (readIdx < chunks.length) {
            return { done: false, value: chunks[readIdx++] };
          }
          return { done: true, value: undefined };
        },
        async cancel() {},
        releaseLock() {}
      };
    }
  };

  const received = [];
  await consumeSseStream(mockStream, (ev) => received.push(ev), null, controller.signal);

  // Should have aborted after chunk 1
  assert.equal(received.length, 1);
  assert.equal(received[0].data.frame_idx, 1);
});
