import { io } from 'socket.io-client';
import { subscribeLiveEvents } from './liveEvents';

const SOCKET_URL = import.meta.env.VITE_API_URL 
  ? import.meta.env.VITE_API_URL.replace('/api', '') 
  : 'http://localhost:5000';

class UnifiedEventBus {
  constructor() {
    this.callbacks = {};
    this.rawSocket = null;

    // Connect to SSE stream
    subscribeLiveEvents((payload) => {
      if (!payload) return;
      const { type, data } = payload;
      if (type === 'VIOLATION_DETECTED') {
        const eventData = data?.event || data;
        this.emit('violation:new', eventData);
        this.emit('violation', eventData);
      } else if (type === 'BUZZER_TRIGGERED') {
        this.emit('buzzer:triggered', data);
      } else if (type === 'BUZZER_SILENCED') {
        this.emit('buzzer:silenced', data);
      }
    });
  }

  on(event, fn) {
    if (!this.callbacks[event]) this.callbacks[event] = [];
    this.callbacks[event].push(fn);
  }

  off(event, fn) {
    if (!this.callbacks[event]) return;
    this.callbacks[event] = this.callbacks[event].filter(cb => cb !== fn);
  }

  emit(event, ...args) {
    if (!this.callbacks[event]) return;
    this.callbacks[event].forEach(fn => {
      try {
        fn(...args);
      } catch (err) {
        console.error('Event dispatch error:', err);
      }
    });
  }

  disconnect() {}
}

const bus = new UnifiedEventBus();

export const initSocket = () => bus;
export const getSocket = () => bus;
export const disconnectSocket = () => {};
export default bus;
