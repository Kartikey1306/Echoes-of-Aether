import type { DialogueChoice } from '../game/Data';
import type { DialogueView, ResolvedLine } from '../game/Dialogue';
import { Voice } from '../audio/Voice';
import { h, type UI } from './UI';
import { portrait } from './Portraits';
import { t } from './Locale';

// Dialogue presentation: interactive conversation panel, radio/cinematic subtitles, voiced lines.

export class DialogueViewDOM implements DialogueView {
  readonly el: HTMLElement;
  private panel: HTMLElement;
  private pt: HTMLElement;
  private nm: HTMLElement;
  private tx: HTMLElement;
  private ch: HTMLElement;
  private cont: HTMLElement;
  private subs: HTMLElement;
  mode: 'interactive' | 'radio' | 'cinematic' = 'interactive';
  subtitles = true;
  speakerNames = true;
  choicesActive = false;
  private advance: (() => void) | null = null;
  private typing = { full: '', shown: 0, speed: 60 };
  private canAdvanceAt = 0;

  constructor(private ui: UI) {
    this.pt = h('div', { class: 'pt' });
    this.nm = h('div', { class: 'nm' });
    this.tx = h('div', { class: 'tx' });
    this.ch = h('div', { class: 'ch' });
    this.cont = h('div', { class: 'cont' });
    this.panel = h('div', { class: 'dialogue panel hidden' }, this.pt, h('div', {}, this.nm, this.tx, this.ch), this.cont);
    this.subs = h('div', { class: 'subs hidden' });
    this.el = h('div', {}, this.panel, this.subs);
    this.panel.addEventListener('click', () => this.tryAdvance());
  }

  private tryAdvance() {
    if (this.choicesActive) return;
    if (this.typing.shown < this.typing.full.length) {
      this.typing.shown = this.typing.full.length;
      this.tx.textContent = this.typing.full;
      return;
    }
    if (performance.now() < this.canAdvanceAt) return;
    const a = this.advance;
    this.advance = null;
    a?.();
  }

  forceAdvance() {
    const a = this.advance;
    this.advance = null;
    a?.();
  }

  async line(l: ResolvedLine, mode: 'interactive' | 'auto'): Promise<void> {
    const g = this.ui.game;
    const interactive = mode === 'interactive' && this.mode === 'interactive';
    const color = l.speaker.color;
    if (interactive) {
      this.subs.classList.add('hidden');
      this.panel.classList.remove('hidden');
      const p = portrait(l.speaker.portrait);
      this.pt.style.backgroundImage = p ? `url(${p})` : '';
      this.pt.style.display = l.speaker.portrait === 'none' ? 'none' : '';
      this.nm.textContent = l.speaker.name;
      this.nm.style.color = color;
      this.ch.innerHTML = '';
      this.typing = { full: l.text, shown: 0, speed: 70 };
      this.tx.textContent = '';
      this.cont.innerHTML = `<span>${t('dlg.continue')}</span><span class="keycap">${g.input.lastDevice === 'pad' ? 'A' : 'E'}</span>`;
      this.canAdvanceAt = performance.now() + 250;
      const voiceDone = g.voice.speak(l.text, l.speaker);
      await new Promise<void>((resolve) => {
        this.advance = () => {
          g.voice.stop();
          resolve();
        };
        // Auto-advance after the voice line when synthesis finished naturally? Keep player-paced for conversations.
        void voiceDone;
      });
      return;
    }
    // Radio / cinematic: subtitles only, paced by voice.
    this.panel.classList.add('hidden');
    if (this.subtitles) {
      this.subs.classList.remove('hidden');
      this.subs.innerHTML = '';
      const name = this.speakerNames ? h('span', { class: 'who', style: { color } }, l.speaker.name) : null;
      this.subs.appendChild(h('span', { class: 'line' }, name, l.text));
    }
    await new Promise<void>((resolve) => {
      let done = false;
      const finish = () => {
        if (done) return;
        done = true;
        this.advance = null;
        resolve();
      };
      this.advance = finish;
      void g.voice.speak(l.text, l.speaker).then(() => setTimeout(finish, 350));
      setTimeout(finish, (Voice.duration(l.text, l.speaker.voice.rate) * 2.2 + 3) * 1000);
    });
    this.subs.classList.add('hidden');
  }

  choose(l: ResolvedLine | null, choices: DialogueChoice[]): Promise<string> {
    const g = this.ui.game;
    this.subs.classList.add('hidden');
    this.panel.classList.remove('hidden');
    if (l) {
      const p = portrait(l.speaker.portrait);
      this.pt.style.backgroundImage = p ? `url(${p})` : '';
      this.pt.style.display = l.speaker.portrait === 'none' ? 'none' : '';
      this.nm.textContent = l.speaker.name;
      this.nm.style.color = l.speaker.color;
      this.typing = { full: l.text, shown: l.text.length, speed: 70 };
      this.tx.textContent = l.text;
      void g.voice.speak(l.text, l.speaker);
    }
    this.cont.innerHTML = '';
    this.ch.innerHTML = '';
    return new Promise((resolve) => {
      choices.forEach((c, i) => {
        const b = h('button', { class: 'btn', 'data-nav': 'btn', ...(i === 0 ? { 'data-autofocus': true } : {}) }, `${i + 1}. ${c.text}`);
        b.addEventListener('click', () => {
          this.choicesActive = false;
          this.ch.innerHTML = '';
          g.voice.stop();
          resolve(c.id);
        });
        this.ch.appendChild(b);
      });
      this.choicesActive = true;
      // Number keys pick choices directly.
      const onKey = (e: KeyboardEvent) => {
        const n = parseInt(e.key);
        if (n >= 1 && n <= choices.length && this.choicesActive) {
          window.removeEventListener('keydown', onKey);
          (this.ch.children[n - 1] as HTMLElement).click();
        }
      };
      window.addEventListener('keydown', onKey);
      const first = this.ch.children[0] as HTMLElement;
      first?.classList.add('focus');
      g.input.releaseLock();
    });
  }

  end() {
    this.panel.classList.add('hidden');
    this.subs.classList.add('hidden');
    this.choicesActive = false;
    this.advance = null;
  }

  update(dt: number) {
    if (this.typing.shown < this.typing.full.length) {
      this.typing.shown = Math.min(this.typing.full.length, this.typing.shown + dt * this.typing.speed);
      this.tx.textContent = this.typing.full.slice(0, Math.floor(this.typing.shown));
    }
    const g = this.ui.game;
    if (this.advance && !this.panel.classList.contains('hidden') && !this.choicesActive) {
      if (g.input.uiPressed('interact') || g.input.codePressed('Space') || g.input.codePressed('Enter') || g.input.codePressed('B0') || g.input.codePressed('Mouse0')) this.tryAdvance();
    }
  }
}
