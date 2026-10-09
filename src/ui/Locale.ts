import en from '../data/locale/en.json';
import { Log } from '../core/Log';

// Localization: UI strings are looked up by key. English is the source locale; adding a language means
// adding src/data/locale/<lang>.json with the same keys and registering it here.

const tables: Record<string, Record<string, string>> = { en };
let current = 'en';
const missing = new Set<string>();

export function setLocale(lang: string) {
  current = tables[lang] ? lang : 'en';
}

export function locales() {
  return Object.keys(tables);
}

export function t(key: string, vars?: Record<string, string | number>): string {
  let s = tables[current]?.[key] ?? tables.en[key];
  if (s === undefined) {
    if (!missing.has(key)) {
      missing.add(key);
      Log.warn('locale', 'missing key', key);
    }
    s = key;
  }
  if (vars) for (const [k, v] of Object.entries(vars)) s = s.replace(new RegExp(`\\{${k}\\}`, 'g'), String(v));
  return s;
}
