import type { ZoneMeta } from '../game/Data';
import { h, type UI } from './UI';
import { t } from './Locale';

// Loading screen driven by real build progress from the zone loader.

const ZONE_TINT: Record<string, [string, string]> = {
  plaza: ['#1b2a3a', '#0a0f16'],
  metro: ['#2a1a14', '#0a0808'],
  facility: ['#162630', '#080c10'],
  vault: ['#1a1636', '#07060f'],
  rooftops: ['#1c2232', '#07090e'],
  core: ['#13283a', '#05080e'],
};

export class LoadingScreen {
  readonly el: HTMLElement;
  private art: HTMLElement;
  private name: HTMLElement;
  private sub: HTMLElement;
  private quote: HTMLElement;
  private hint: HTMLElement;
  private fill: HTMLElement;
  private stage: HTMLElement;
  private pct: HTMLElement;
  private err: HTMLElement;

  constructor(private ui: UI) {
    this.art = h('div', { class: 'art' });
    this.name = h('div', { class: 'zone-name' });
    this.sub = h('div', { class: 'zone-sub' });
    this.quote = h('div', { class: 'quote' });
    this.hint = h('div', { class: 'hint' });
    this.fill = h('i');
    this.stage = h('span');
    this.pct = h('span');
    this.err = h('div', { class: 'err hidden' });
    this.el = h(
      'div',
      { class: 'screen loading hidden' },
      this.art,
      h('div', { class: 'shade' }),
      h('div', { class: 'content' }, h('div', {}, h('div', { class: 'kicker' }, t('loading.loading')), h('div', { style: { height: '0.8em' } }), this.name, this.sub, this.quote), h('div', {}, this.hint, h('div', { class: 'bar' }, this.fill), h('div', { class: 'stage' }, this.stage, this.pct), this.err)),
    );
  }

  show(meta: ZoneMeta) {
    this.el.classList.remove('hidden');
    this.err.classList.add('hidden');
    this.name.textContent = meta.name;
    this.sub.textContent = meta.subtitle;
    this.quote.textContent = meta.quote;
    this.hint.innerHTML = this.ui.keyText(meta.hints[Math.floor(Math.random() * meta.hints.length)]);
    const [a, b] = ZONE_TINT[meta.id] ?? ['#1b2a3a', '#0a0f16'];
    // Authored art (DreamLayer or in-engine capture) with a procedural fallback underneath.
    this.art.className = 'art';
    this.art.style.backgroundImage = `url(${meta.art}), radial-gradient(ellipse at 70% 30%, ${a}, ${b} 70%)`;
    // Restart the slow pan animation.
    this.art.style.animation = 'none';
    void this.art.offsetWidth;
    this.art.style.animation = '';
    this.progress(0, '');
  }

  progress(f: number, label: string) {
    this.fill.style.width = (Math.max(0, Math.min(1, f)) * 100).toFixed(1) + '%';
    if (label) this.stage.textContent = label;
    this.pct.textContent = Math.round(f * 100) + '%';
  }

  error(msg: string) {
    this.err.textContent = 'Failed to load: ' + msg;
    this.err.classList.remove('hidden');
  }

  hide() {
    this.el.classList.add('hidden');
  }
}
