// Industrial Sound Alerts Utility via Web Audio API
// Provides zero-latency, realistic industrial sirens and horns for plant safety monitoring

let audioCtx = null;
let currentOscillators = [];
let isSirenPlaying = false;

function getAudioContext() {
  if (!audioCtx) {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    audioCtx = new AudioContextClass();
  }
  if (audioCtx.state === 'suspended') {
    audioCtx.resume();
  }
  return audioCtx;
}

export const playIndustrialSiren = (durationSeconds = 3) => {
  try {
    stopAllSounds();
    const ctx = getAudioContext();
    const now = ctx.currentTime;
    
    // Main dual-tone sweep oscillator
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();

    osc.type = 'sawtooth';
    
    // High-low European/Plant emergency siren sweep
    const sweepRate = 0.4;
    const cycles = Math.ceil(durationSeconds / sweepRate);
    
    osc.frequency.setValueAtTime(650, now);
    for (let i = 0; i < cycles; i++) {
      const cycleStart = now + (i * sweepRate);
      osc.frequency.linearRampToValueAtTime(1150, cycleStart + (sweepRate / 2));
      osc.frequency.linearRampToValueAtTime(650, cycleStart + sweepRate);
    }

    gain.gain.setValueAtTime(0.25, now);
    gain.gain.setValueAtTime(0.25, now + durationSeconds - 0.2);
    gain.gain.exponentialRampToValueAtTime(0.001, now + durationSeconds);

    osc.connect(gain);
    gain.connect(ctx.destination);

    osc.start(now);
    osc.stop(now + durationSeconds);
    
    currentOscillators.push(osc);
    isSirenPlaying = true;
    
    setTimeout(() => {
      isSirenPlaying = false;
    }, durationSeconds * 1000);
    
    return true;
  } catch (err) {
    console.warn('Could not play industrial siren:', err);
    return false;
  }
};

export const playWarningHorn = (durationSeconds = 1.2) => {
  try {
    stopAllSounds();
    const ctx = getAudioContext();
    const now = ctx.currentTime;

    // Dual frequency industrial horn (440Hz + 554Hz major third creates an industrial diesel/hooter tone)
    const osc1 = ctx.createOscillator();
    const osc2 = ctx.createOscillator();
    const gain = ctx.createGain();

    osc1.type = 'sawtooth';
    osc1.frequency.setValueAtTime(440, now);

    osc2.type = 'square';
    osc2.frequency.setValueAtTime(554, now);

    gain.gain.setValueAtTime(0.2, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + durationSeconds);

    osc1.connect(gain);
    osc2.connect(gain);
    gain.connect(ctx.destination);

    osc1.start(now);
    osc2.start(now);
    osc1.stop(now + durationSeconds);
    osc2.stop(now + durationSeconds);

    currentOscillators.push(osc1, osc2);
    return true;
  } catch (err) {
    console.warn('Could not play warning horn:', err);
    return false;
  }
};

export const playViolationBeep = () => {
  try {
    const ctx = getAudioContext();
    const now = ctx.currentTime;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();

    osc.type = 'sine';
    osc.frequency.setValueAtTime(1050, now);
    osc.frequency.setValueAtTime(1300, now + 0.1);

    gain.gain.setValueAtTime(0.15, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.25);

    osc.connect(gain);
    gain.connect(ctx.destination);

    osc.start(now);
    osc.stop(now + 0.25);
    return true;
  } catch (err) {
    return false;
  }
};

export const stopAllSounds = () => {
  try {
    currentOscillators.forEach((osc) => {
      try {
        osc.stop();
        osc.disconnect();
      } catch (e) {}
    });
    currentOscillators = [];
    isSirenPlaying = false;
    return true;
  } catch (e) {
    return false;
  }
};

export const isSirenActive = () => isSirenPlaying;
