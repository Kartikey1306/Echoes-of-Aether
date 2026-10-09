// Small ring-buffer logger. The debug overlay reads `Log.recent`.

type Level = 'info' | 'warn' | 'error';
interface Entry { t: number; level: Level; tag: string; msg: string }

const MAX = 200;
const recent: Entry[] = [];

function push(level: Level, tag: string, args: unknown[]) {
  const msg = args.map((a) => (typeof a === 'string' ? a : safeStringify(a))).join(' ');
  recent.push({ t: performance.now(), level, tag, msg });
  if (recent.length > MAX) recent.shift();
  const line = `[${tag}] ${msg}`;
  if (level === 'error') console.error(line);
  else if (level === 'warn') console.warn(line);
  else if (__DEV_TOOLS__) console.log(line);
}

function safeStringify(v: unknown) {
  if (v instanceof Error) return `${v.name}: ${v.message}`;
  try {
    return JSON.stringify(v);
  } catch {
    return String(v);
  }
}

export const Log = {
  recent,
  info: (tag: string, ...a: unknown[]) => push('info', tag, a),
  warn: (tag: string, ...a: unknown[]) => push('warn', tag, a),
  error: (tag: string, ...a: unknown[]) => push('error', tag, a),
  errorCount: () => recent.filter((e) => e.level === 'error').length,
};
