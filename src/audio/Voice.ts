import type { SpeakerDef } from '../game/Data';

// Voice-over using the platform speech synthesizer. Disabled in this build: Game.applySettings keeps
// `enabled` false, so every line is subtitle-only and timed from its text length.

export class Voice {
  enabled = false;
  volume = 0.9;
  private voices: SpeechSynthesisVoice[] = [];
  private current: SpeechSynthesisUtterance | null = null;
  readonly supported: boolean;

  constructor() {
    this.supported = typeof window !== 'undefined' && 'speechSynthesis' in window;
    if (this.supported) {
      const load = () => (this.voices = window.speechSynthesis.getVoices().filter((v) => v.lang.startsWith('en')));
      load();
      window.speechSynthesis.onvoiceschanged = load;
    }
  }

  /** Estimated reading time for subtitles. */
  static duration(text: string, rate = 1) {
    const words = text.split(/\s+/).length;
    return Math.max(1.6, (words / 2.6) / rate + 0.5);
  }

  private pick(s: SpeakerDef): SpeechSynthesisVoice | null {
    if (!this.voices.length) return null;
    for (const name of s.voice.prefer) {
      const v = this.voices.find((x) => x.name.includes(name));
      if (v) return v;
    }
    return this.voices[0];
  }

  /** Speak a line. Resolves when finished (or after the estimated duration as a fallback). */
  speak(text: string, s: SpeakerDef): Promise<void> {
    const est = Voice.duration(text, s.voice.rate);
    if (!this.supported || !this.enabled || this.volume <= 0.001 || s.id === 'system') {
      return new Promise((r) => setTimeout(r, est * 1000));
    }
    this.stop();
    return new Promise((resolve) => {
      const u = new SpeechSynthesisUtterance(text);
      const v = this.pick(s);
      if (v) u.voice = v;
      u.pitch = s.voice.pitch;
      u.rate = s.voice.rate;
      u.volume = this.volume;
      let done = false;
      const finish = () => {
        if (done) return;
        done = true;
        resolve();
      };
      u.onend = finish;
      u.onerror = finish;
      // Safety net: some engines never fire onend.
      setTimeout(finish, (est * 1.8 + 2) * 1000);
      this.current = u;
      try {
        window.speechSynthesis.speak(u);
      } catch {
        setTimeout(finish, est * 1000);
      }
    });
  }

  stop() {
    if (this.supported) window.speechSynthesis.cancel();
    this.current = null;
  }

  get speaking() {
    return this.supported && window.speechSynthesis.speaking;
  }
}
