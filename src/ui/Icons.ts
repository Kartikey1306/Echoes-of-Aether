// Original SVG icon set for abilities, powerups, items and UI. Stroke-based, readable at small sizes.

const wrap = (body: string, color = '#5fd4f0') =>
  `<svg class="icon" viewBox="0 0 48 48" fill="none" stroke="${color}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">${body}</svg>`;

const ICONS: Record<string, (c?: string) => string> = {
  ab_pulse: (c = '#5fd4f0') => wrap('<circle cx="24" cy="24" r="4" fill="' + c + '"/><circle cx="24" cy="24" r="11"/><path d="M24 4a20 20 0 0 1 0 40M24 44A20 20 0 0 1 24 4" stroke-dasharray="4 5"/>', c),
  ab_dash: (c = '#5fd4f0') => wrap('<path d="M8 24h20M14 16h16M14 32h16"/><path d="M30 12l10 12-10 12"/>', c),
  ab_corebreak: (c = '#5fd4f0') => wrap('<path d="M24 4l6 14 14 2-10 10 3 14-13-7-13 7 3-14L4 20l14-2z"/><circle cx="24" cy="25" r="4" fill="' + c + '"/>', c),
  ab_echo: (c = '#a68bff') => wrap('<path d="M4 24s8-12 20-12 20 12 20 12-8 12-20 12S4 24 4 24z"/><circle cx="24" cy="24" r="5"/><path d="M24 6v-2M24 44v-2M8 10l-2-2M40 10l2-2" />', c),
  ab_step: (c = '#a68bff') => wrap('<path d="M18 36l-8-12 8-12"/><path d="M30 36l-8-12 8-12" opacity="0.6"/><path d="M42 36l-8-12 8-12" opacity="0.3"/>', c),
  ab_resonance: (c = '#a68bff') => wrap('<circle cx="24" cy="24" r="5" fill="' + c + '"/><path d="M24 8a16 16 0 0 1 16 16M24 40A16 16 0 0 1 8 24M40 24a16 16 0 0 1-16 16M8 24A16 16 0 0 1 24 8" stroke-dasharray="6 4"/>', c),
  ab_bolt: (c = '#5fd4f0') => wrap('<path d="M6 24h26"/><path d="M28 16l12 8-12 8"/><circle cx="10" cy="24" r="3" fill="' + c + '"/>', c),
  pu_shard: (c = '#62d4ff') => wrap('<path d="M24 4l7 16-7 24-7-24z" fill="' + c + '" fill-opacity="0.25"/><path d="M12 16l3 8-3 10M36 16l-3 8 3 10"/>', c),
  pu_phase: (c = '#9a7bff') => wrap('<circle cx="24" cy="24" r="7" fill="' + c + '" fill-opacity="0.3"/><ellipse cx="24" cy="24" rx="18" ry="8"/><ellipse cx="24" cy="24" rx="8" ry="18"/>', c),
  pu_overcharge: (c = '#ffb45e') => wrap('<path d="M26 4L12 28h10l-2 16 16-24H26z" fill="' + c + '" fill-opacity="0.25"/>', c),
  pu_shield: (c = '#7fe8c8') => wrap('<path d="M24 4l16 6v12c0 10-7 17-16 22C15 39 8 32 8 22V10z" fill="' + c + '" fill-opacity="0.2"/><path d="M17 24l5 5 9-10"/>', c),
  pu_echo: (c = '#c39bff') => wrap('<path d="M24 6l10 18-10 18-10-18z" fill="' + c + '" fill-opacity="0.2"/><circle cx="24" cy="24" r="18" stroke-dasharray="3 5"/>', c),
  fragment: (c = '#5fd4f0') => wrap('<path d="M24 4l8 14-8 26-8-26z" fill="' + c + '" fill-opacity="0.3"/><path d="M16 18h16"/>', c),
  core: (c = '#ffb45e') => wrap('<circle cx="24" cy="24" r="10" fill="' + c + '" fill-opacity="0.3"/><circle cx="24" cy="24" r="17"/><path d="M24 4v6M24 38v6M4 24h6M38 24h6"/>', c),
  q_part: (c = '#ffc46a') => wrap('<circle cx="24" cy="24" r="7"/><path d="M24 6v6M24 36v6M6 24h6M36 24h6M11 11l4 4M33 33l4 4M37 11l-4 4M15 33l-4 4"/>', c),
  q_cell: (c = '#ffc46a') => wrap('<rect x="14" y="10" width="20" height="32" rx="2"/><path d="M20 6h8v4M24 18l-4 8h8l-4 8"/>', c),
  q_chip: (c = '#ffc46a') => wrap('<rect x="12" y="12" width="24" height="24" rx="2"/><rect x="19" y="19" width="10" height="10"/><path d="M18 6v6M24 6v6M30 6v6M18 36v6M24 36v6M30 36v6M6 18h6M6 24h6M6 30h6M36 18h6M36 24h6M36 30h6"/>', c),
  q_tape: (c = '#ffc46a') => wrap('<rect x="6" y="12" width="36" height="24" rx="2"/><circle cx="17" cy="24" r="5"/><circle cx="31" cy="24" r="5"/><path d="M17 29h14"/>', c),
  q_key: (c = '#ffc46a') => wrap('<circle cx="16" cy="24" r="8"/><path d="M24 24h18M36 24v6M41 24v5"/>', c),
  up_shield: (c = '#7fe8c8') => wrap('<path d="M24 4l16 6v12c0 10-7 17-16 22C15 39 8 32 8 22V10z"/><path d="M24 14v20M14 24h20"/>', c),
  up_echo: (c = '#c39bff') => wrap('<path d="M4 24s8-12 20-12 20 12 20 12-8 12-20 12S4 24 4 24z"/><circle cx="24" cy="24" r="5"/><path d="M38 6v8M34 10h8"/>', c),
  up_core: (c = '#ffb45e') => wrap('<circle cx="24" cy="24" r="6" fill="' + c + '"/><circle cx="24" cy="24" r="13"/><circle cx="24" cy="24" r="20" stroke-dasharray="2 4"/>', c),
  up_resonant: (c = '#ffb45e') => wrap('<path d="M24 4l17 10v20L24 44 7 34V14z"/><circle cx="24" cy="24" r="6" fill="' + c + '" fill-opacity="0.5"/>', c),
  lore_rec: (c = '#6fa8ff') => wrap('<rect x="16" y="8" width="16" height="32" rx="3"/><path d="M20 16h8M20 22h8M20 28h5"/><circle cx="24" cy="44" r="1"/>', c),
  lore_log: (c = '#a68bff') => wrap('<path d="M12 6h18l8 8v28H12z"/><path d="M30 6v8h8M18 22h14M18 28h14M18 34h9"/>', c),
  swap: (c = '#dfe7ee') => wrap('<path d="M10 18h26l-6-6M38 30H12l6 6"/>', c),
  lock: (c = '#8a9aab') => wrap('<rect x="12" y="22" width="24" height="18" rx="2"/><path d="M17 22v-6a7 7 0 0 1 14 0v6"/>', c),
};

export function icon(name: string, color?: string): string {
  const f = ICONS[name];
  return f ? f(color) : wrap('<circle cx="24" cy="24" r="12"/>', color ?? '#8a9aab');
}

export function hasIcon(name: string) {
  return !!ICONS[name];
}

export const ICON_NAMES = Object.keys(ICONS);
