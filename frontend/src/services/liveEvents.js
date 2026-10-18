/**
 * Industrial Real-time Event Streaming Client (SSE)
 * Connects directly to Flask /api/events/stream for zero-latency live alerts.
 */
import { AI_BASE_URL } from './api';

const listeners = new Set();
let eventSource = null;
let reconnectTimer = null;

export function initLiveEvents() {
  if (eventSource) return;

  const streamUrl = `${AI_BASE_URL}/api/events/stream`;

  try {
    eventSource = new EventSource(streamUrl);

    eventSource.onopen = () => {
      console.log('⚡ [LiveEvents] SSE stream connected successfully');
    };

    eventSource.addEventListener('message', (e) => {
      try {
        const payload = JSON.parse(e.data);
        listeners.forEach((fn) => {
          try {
            fn(payload);
          } catch (err) {
            console.error('[LiveEvents] Listener callback error:', err);
          }
        });
      } catch (parseErr) {
        console.warn('[LiveEvents] Parse error:', parseErr);
      }
    });

    eventSource.onerror = (err) => {
      console.warn('[LiveEvents] Stream interrupted, reconnecting in 5s...', err);
      eventSource.close();
      eventSource = null;
      if (!reconnectTimer) {
        reconnectTimer = setTimeout(() => {
          reconnectTimer = null;
          initLiveEvents();
        }, 5000);
      }
    };
  } catch (err) {
    console.error('[LiveEvents] Failed to initialize EventSource:', err);
  }
}

export function subscribeLiveEvents(callback) {
  listeners.add(callback);
  if (!eventSource) {
    initLiveEvents();
  }
  return () => {
    listeners.delete(callback);
  };
}
