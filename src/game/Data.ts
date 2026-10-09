import itemsJson from '../data/items.json';
import powerupsJson from '../data/powerups.json';
import abilitiesJson from '../data/abilities.json';
import enemiesJson from '../data/enemies.json';
import questsJson from '../data/quests.json';
import dialogueJson from '../data/dialogue.json';
import speakersJson from '../data/speakers.json';
import zonesJson from '../data/zones.json';
import collectiblesJson from '../data/collectibles.json';
import hintsJson from '../data/hints.json';

// Typed access to the JSON game data.

export type ItemCategory = 'aether' | 'powerups' | 'quest' | 'upgrades' | 'lore';
export interface ItemDef {
  id: string; name: string; category: ItemCategory; description: string; icon: string;
  rarity: 'common' | 'uncommon' | 'rare' | 'epic'; stack: number;
  effect: { type: string; [k: string]: unknown };
  quest: string | false;
}
export interface PowerupDef { id: string; item: string; name: string; duration: number; color: string; icon: string; stat: string; value: number; sfx: string; description: string }
export interface AbilityDef { id: string; character: 'kael' | 'lyra'; name: string; slot: 'ability' | 'dash' | 'ultimate'; description: string; energy: number; cooldown: number; unlock: string; icon: string }
export interface SkillNode { id: string; ability: string; name: string; description: string; cost: number; requires: string[] }
export interface EnemyDef { id: string; name: string; health: number; poise: number; damage: number; speed: number; sight: number; attackRange: number; leash: number; tags: string[]; drops: { item: string; chance: number }[] }

export type Action = { do: string; [k: string]: unknown };
export interface ObjectiveDef { id: string; type: 'flag' | 'interact' | 'kill' | 'collect' | 'reach' | 'zone' | 'talk'; target: string; count?: number; text: string; marker?: string }
export interface StageDef { id: string; objectives: ObjectiveDef[]; onStart?: Action[]; onComplete?: Action[] }
export interface QuestDef { id: string; type: 'main' | 'side'; order: number; title: string; zone: string; summary: string; giver?: string; requires?: string; stages: StageDef[]; onComplete?: Action[] }

export interface DialogueChoice { id: string; text: string; next?: string; conditions?: string[]; actions?: Action[] }
export interface DialogueNode {
  id: string; speaker?: string; text?: string; next?: string; else?: string; conditions?: string[];
  actions?: Action[]; choices?: DialogueChoice[]; branch?: { if?: string[]; goto: string }[];
}
export interface DialogueDef { id: string; start: string; npc?: string; cinematic?: boolean; lore?: boolean; nodes: DialogueNode[] }
export interface SpeakerDef { id: string; name: string; portrait: string; color: string; voice: { pitch: number; rate: number; prefer: string[] } }
export interface ZoneMeta { id: string; name: string; subtitle: string; art: string; music: string; ambience: string; hints: string[]; quote: string }
export interface CollectibleDef { id: string; kind: 'fragment' | 'recording' | 'cache'; zone: string; hidden: boolean; give: Record<string, number> }
export interface HintDef { id: string; text: string }

const byId = <T extends { id: string }>(arr: T[]) => Object.fromEntries(arr.map((x) => [x.id, x])) as Record<string, T>;

export const Data = {
  items: byId(itemsJson.items as unknown as ItemDef[]),
  itemList: itemsJson.items as unknown as ItemDef[],
  powerups: byId(powerupsJson.powerups as unknown as PowerupDef[]),
  powerupList: powerupsJson.powerups as unknown as PowerupDef[],
  abilities: byId(abilitiesJson.abilities as unknown as AbilityDef[]),
  abilityList: abilitiesJson.abilities as unknown as AbilityDef[],
  skills: byId(abilitiesJson.tree as unknown as SkillNode[]),
  skillList: abilitiesJson.tree as unknown as SkillNode[],
  enemies: byId(enemiesJson.enemies as unknown as EnemyDef[]),
  quests: byId(questsJson.quests as unknown as QuestDef[]),
  questList: (questsJson.quests as unknown as QuestDef[]).slice().sort((a, b) => a.order - b.order),
  dialogues: byId(dialogueJson.dialogues as unknown as DialogueDef[]),
  speakers: byId(speakersJson.speakers as unknown as SpeakerDef[]),
  zones: byId(zonesJson.zones as unknown as ZoneMeta[]),
  zoneList: zonesJson.zones as unknown as ZoneMeta[],
  collectibles: byId(collectiblesJson.collectibles as unknown as CollectibleDef[]),
  collectibleList: collectiblesJson.collectibles as unknown as CollectibleDef[],
  hints: byId(hintsJson.hints as unknown as HintDef[]),
};

export const COLLECTIBLE_TOTALS = {
  fragment: Data.collectibleList.filter((c) => c.kind === 'fragment').length,
  recording: Data.collectibleList.filter((c) => c.kind === 'recording').length,
  cache: Data.collectibleList.filter((c) => c.kind === 'cache').length,
};
