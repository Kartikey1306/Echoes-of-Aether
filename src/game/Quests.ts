import { events } from '../core/Events';
import { Log } from '../core/Log';
import { Data, type Action, type ObjectiveDef, type QuestDef } from './Data';
import type { GameState } from './GameState';

// Data-driven quest engine.

export interface ActionHost {
  runActions(actions: Action[] | undefined, ctx?: { quest?: string }): Promise<void>;
  currentZone(): string;
  partnerName(): string;
}

export class QuestSystem {
  private queue: Promise<void> = Promise.resolve();
  private unsubs: (() => void)[] = [];

  constructor(private gs: () => GameState, private host: ActionHost) {
    const on = <K extends Parameters<typeof events.on>[0]>(k: K, fn: Parameters<typeof events.on<K>>[1]) => this.unsubs.push(events.on(k, fn));
    on('interact', (p) => this.signal('interact', p.id));
    on('pickup', (p) => this.signal('interact', p.id));
    on('encounter:cleared', (p) => this.signal('kill', p.id));
    on('item:added', (p) => this.signal('collect', p.id));
    on('trigger:enter', (p) => this.signal('reach', p.id));
    on('zone:entered', (p) => this.signal('zone', p.zone));
    on('flag:set', (p) => this.signal('flag', p.flag));
    on('talk', (p) => this.signal('talk', p.npc));
  }

  dispose() {
    this.unsubs.forEach((u) => u());
  }

  private enqueue(fn: () => Promise<void> | void) {
    this.queue = this.queue.then(fn).catch((err) => Log.error('quests', err));
    return this.queue;
  }

  /** Resolves once all queued quest work (actions, stage changes) has finished. */
  idle() {
    return this.queue;
  }

  active(): QuestDef[] {
    const q = this.gs().d.quests;
    return Data.questList.filter((d) => q[d.id]?.status === 'active');
  }
  completed(): QuestDef[] {
    const q = this.gs().d.quests;
    return Data.questList.filter((d) => q[d.id]?.status === 'done');
  }

  tracked(): QuestDef | null {
    const d = this.gs().d;
    if (d.tracked && d.quests[d.tracked]?.status === 'active') return Data.quests[d.tracked];
    const main = this.active().find((q) => q.type === 'main');
    return main ?? this.active()[0] ?? null;
  }

  track(id: string) {
    if (this.gs().d.quests[id]?.status === 'active') this.gs().d.tracked = id;
  }

  currentObjectives(id: string): { def: ObjectiveDef; done: boolean; progress: number; required: number }[] {
    const st = this.gs().d.quests[id];
    const def = Data.quests[id];
    if (!st || !def || st.status !== 'active') return [];
    const stage = def.stages[st.stage];
    if (!stage) return [];
    return stage.objectives.map((o) => {
      const req = this.required(o);
      const prog = st.progress[o.id] ?? 0;
      return { def: o, done: prog >= req, progress: prog, required: req };
    });
  }

  objectiveText(o: ObjectiveDef): string {
    return o.text.replace('{partner}', this.host.partnerName());
  }

  private required(o: ObjectiveDef) {
    return o.type === 'collect' ? Math.max(1, o.count ?? 1) : 1;
  }

  start(id: string): Promise<void> {
    return this.enqueue(async () => {
      const def = Data.quests[id];
      if (!def) {
        Log.error('quests', 'unknown quest', id);
        return;
      }
      const d = this.gs().d;
      if (d.quests[id]) return;
      d.quests[id] = { status: 'active', stage: 0, progress: {} };
      if (def.type === 'main' || !d.tracked) d.tracked = id;
      events.emit('quest:started', { id });
      events.emit('ui:toast', { text: `${def.type === 'main' ? 'Mission' : 'Side quest'}: ${def.title}`, kind: 'quest' });
      await this.enterStage(id);
    });
  }

  private async enterStage(id: string) {
    const def = Data.quests[id];
    const st = this.gs().d.quests[id];
    const stage = def.stages[st.stage];
    if (!stage) return;
    st.progress = {};
    events.emit('quest:stage', { id, stage: stage.id });
    await this.host.runActions(stage.onStart, { quest: id });
    // Objectives that are already satisfied complete immediately.
    this.evaluateInstant(id);
    await this.checkStage(id);
  }

  private evaluateInstant(id: string) {
    const gs = this.gs();
    const st = gs.d.quests[id];
    for (const o of this.currentObjectives(id)) {
      if (o.done) continue;
      let v = 0;
      switch (o.def.type) {
        case 'collect': v = gs.d.inventory[o.def.target] ?? 0; break;
        case 'flag': v = gs.flag(o.def.target) ? 1 : 0; break;
        case 'zone': v = this.host.currentZone() === o.def.target ? 1 : 0; break;
        case 'kill': v = gs.isDefeated(o.def.target) ? 1 : 0; break;
        case 'interact': v = gs.isCollected(o.def.target) ? 1 : 0; break;
        default: break;
      }
      if (v > 0) st.progress[o.def.id] = Math.min(this.required(o.def), Math.max(st.progress[o.def.id] ?? 0, v));
    }
  }

  private signal(type: ObjectiveDef['type'], target: string) {
    // Collect progress is absolute (inventory count); others are one-shot.
    const gs = this.gs();
    let touched = false;
    for (const q of this.active()) {
      const st = gs.d.quests[q.id];
      for (const o of this.currentObjectives(q.id)) {
        if (o.done || o.def.type !== type || o.def.target !== target) continue;
        const req = o.required;
        const v = type === 'collect' ? Math.min(req, gs.d.inventory[target] ?? 0) : req;
        if (v > (st.progress[o.def.id] ?? 0)) {
          st.progress[o.def.id] = v;
          events.emit('quest:objective', { id: q.id, objective: o.def.id, progress: v, required: req });
          if (v >= req) events.emit('ui:toast', { text: `✓ ${this.objectiveText(o.def)}`, kind: 'quest' });
          touched = true;
        }
      }
    }
    if (touched) for (const q of this.active()) this.enqueue(() => this.checkStage(q.id));
  }

  private async checkStage(id: string) {
    const st = this.gs().d.quests[id];
    if (!st || st.status !== 'active') return;
    const objs = this.currentObjectives(id);
    if (objs.length === 0 || !objs.every((o) => o.done)) return;
    const def = Data.quests[id];
    const stage = def.stages[st.stage];
    await this.host.runActions(stage.onComplete, { quest: id });
    st.stage++;
    if (st.stage >= def.stages.length) {
      st.status = 'done';
      if (this.gs().d.tracked === id) this.gs().d.tracked = null;
      events.emit('quest:completed', { id });
      events.emit('ui:toast', { text: `${def.type === 'main' ? 'Mission complete' : 'Quest complete'}: ${def.title}`, kind: 'quest' });
      await this.host.runActions(def.onComplete, { quest: id });
      return;
    }
    await this.enterStage(id);
  }

  /** Re-check all active quests (after load or zone change). */
  refresh() {
    for (const q of this.active()) {
      this.evaluateInstant(q.id);
      this.enqueue(() => this.checkStage(q.id));
    }
  }

  /** Debug/test: complete the current stage of a quest. */
  debugCompleteStage(id: string) {
    const st = this.gs().d.quests[id];
    if (!st) return;
    for (const o of this.currentObjectives(id)) st.progress[o.def.id] = o.required;
    return this.enqueue(() => this.checkStage(id));
  }
}
