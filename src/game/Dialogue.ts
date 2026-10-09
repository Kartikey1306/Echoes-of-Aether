import { events } from '../core/Events';
import { Log } from '../core/Log';
import { Data, type Action, type DialogueChoice, type DialogueDef, type DialogueNode, type SpeakerDef } from './Data';
import type { GameState } from './GameState';

// Data-driven dialogue runner. Presentation is delegated to a DialogueView.

export interface ResolvedLine {
  dialogue: string;
  node: string;
  speaker: SpeakerDef;
  text: string;
}

export interface DialogueView {
  /** Show a line; resolves when it should advance (player input or auto timing). */
  line(l: ResolvedLine, mode: 'interactive' | 'auto'): Promise<void>;
  choose(l: ResolvedLine | null, choices: DialogueChoice[]): Promise<string>;
  end(): void;
}

export class DialogueSystem {
  active: string | null = null;
  private cancelled = false;

  constructor(
    private gs: () => GameState,
    private view: () => DialogueView,
    private runActions: (a: Action[] | undefined) => Promise<void>,
  ) {}

  resolveSpeaker(id: string): SpeakerDef {
    const d = this.gs().d;
    const partner = d.character === 'kael' ? 'lyra' : 'kael';
    const real = id === 'active' ? d.character : id === 'partner' ? partner : id;
    return Data.speakers[real] ?? Data.speakers.system;
  }

  private text(t: string): string {
    const d = this.gs().d;
    const partner = d.character === 'kael' ? 'Lyra' : 'Kael';
    return t.replace(/\{partner\}/g, partner).replace(/\{active\}/g, d.character === 'kael' ? 'Kael' : 'Lyra');
  }

  /** Iterate the lines of a dialogue (resolving branches/conditions) without presenting them. */
  linearLines(id: string): ResolvedLine[] {
    const def = Data.dialogues[id];
    if (!def) return [];
    const out: ResolvedLine[] = [];
    let node = this.enter(def, def.start);
    let guard = 0;
    while (node && guard++ < 200) {
      if (node.text && node.speaker) out.push({ dialogue: id, node: node.id, speaker: this.resolveSpeaker(node.speaker), text: this.text(node.text) });
      node = node.next ? this.enter(def, node.next) : null;
    }
    return out;
  }

  private enter(def: DialogueDef, nodeId: string | undefined): DialogueNode | null {
    let guard = 0;
    while (nodeId && guard++ < 50) {
      const node = def.nodes.find((n) => n.id === nodeId);
      if (!node) {
        Log.error('dialogue', `missing node ${def.id}/${nodeId}`);
        return null;
      }
      if (node.branch) {
        const b = node.branch.find((br) => this.gs().checkAll(br.if));
        nodeId = b?.goto;
        continue;
      }
      if (node.conditions && !this.gs().checkAll(node.conditions)) {
        nodeId = node.else;
        continue;
      }
      return node;
    }
    return null;
  }

  cancel() {
    this.cancelled = true;
  }

  async play(id: string, mode: 'interactive' | 'auto' = 'interactive'): Promise<void> {
    const def = Data.dialogues[id];
    if (!def) {
      Log.error('dialogue', 'unknown dialogue', id);
      return;
    }
    if (this.active) {
      Log.warn('dialogue', `dialogue ${id} requested while ${this.active} active; queued after`);
    }
    this.active = id;
    this.cancelled = false;
    events.emit('dialogue:started', { id });
    try {
      let node = this.enter(def, def.start);
      let guard = 0;
      while (node && !this.cancelled && guard++ < 200) {
        await this.runActions(node.actions);
        const line: ResolvedLine | null = node.text && node.speaker ? { dialogue: id, node: node.id, speaker: this.resolveSpeaker(node.speaker), text: this.text(node.text) } : null;
        const choices = (node.choices ?? []).filter((c) => this.gs().checkAll(c.conditions));
        if (choices.length) {
          const picked = await this.view().choose(line, choices.map((c) => ({ ...c, text: this.text(c.text) })));
          const c = choices.find((x) => x.id === picked) ?? choices[0];
          events.emit('dialogue:choice', { id, node: node.id, choice: c.id });
          await this.runActions(c.actions);
          node = this.enter(def, c.next);
        } else {
          if (line) await this.view().line(line, mode);
          node = node.next ? this.enter(def, node.next) : null;
        }
      }
    } finally {
      this.view().end();
      this.active = null;
      events.emit('dialogue:ended', { id });
      if (def.npc) events.emit('talk', { npc: def.npc });
    }
  }
}
