import '@fontsource/rajdhani/latin-500.css';
import '@fontsource/rajdhani/latin-600.css';
import '@fontsource/rajdhani/latin-700.css';
import '@fontsource/inter/latin-400.css';
import '@fontsource/inter/latin-500.css';
import '@fontsource/inter/latin-600.css';
import { Physics } from './physics/Physics';
import { Log } from './core/Log';

async function boot() {
  const params = new URLSearchParams(location.search);
  const bootEl = document.getElementById('boot');
  const status = (s: string) => {
    if (bootEl) bootEl.textContent = s;
  };
  status('Initializing physics');
  await Physics.init();
  if (__DEV_TOOLS__ && params.get('view') === 'chars') {
    const { runCharacterViewer } = await import('./dev/CharacterViewer');
    await runCharacterViewer(params);
    bootEl?.remove();
    return;
  }
  status('Building world');
  const { Game } = await import('./game/Game');
  const { buildPortraits } = await import('./ui/Portraits');
  const app = document.getElementById('app')!;
  const game = new Game(app);
  status('Rendering portraits');
  await buildPortraits(game.rs.renderer, ['kael', 'lyra', 'oren', 'mira', 'tomas', 'nia'], (id) => (id === 'kael' || id === 'lyra' ? game.lookFor(id) : null));
  await document.fonts.ready;
  status('Preparing menu');
  await game.boot();
  bootEl?.remove();
  // Automation hooks: always on in development; in a release build only with ?test (no UI exposes them).
  const automation = __DEV_TOOLS__ || params.has('test');
  if (automation) {
    const { installTestApi } = await import('./dev/TestApi');
    installTestApi(game);
  }
  const auto = automation ? params.get('autostart') : null;
  if (auto === 'kael' || auto === 'lyra') {
    game.ui.hideAllScreens();
    if (params.get('skipintro') === '1') game.cinematics.register('cin_intro', async () => undefined);
    await game.newGame(auto, parseInt(params.get('slot') ?? '3'));
  }
  (window as unknown as { __ready: boolean }).__ready = true;
}

boot().catch((err) => {
  Log.error('boot', err);
  const el = document.getElementById('boot');
  if (el) el.textContent = 'Failed to start: ' + (err?.message ?? err);
  (window as unknown as { __bootError: string }).__bootError = String(err?.stack ?? err);
});
