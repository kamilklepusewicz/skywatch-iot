const field = id => document.getElementById(id);
const names = {idle: 'Bezczynna', live: 'LIVE', replay: 'REPLAY'};
let reconnect = false;
field('image').addEventListener('error', () => { reconnect = true; });
async function refresh() {
  try {
    const response = await fetch('/status.json', {cache: 'no-store', signal: AbortSignal.timeout(3000)});
    if (!response.ok) throw new Error('status');
    const state = await response.json();
    field('camera').textContent = state.camera_id;
    field('mode').textContent = names[state.mode] ?? state.mode;
    field('device').textContent = state.device;
    field('resolution').textContent = state.width ? `${state.width} × ${state.height}` : '—';
    field('captured').textContent = state.captured_at ?? '—';
    field('detector').textContent = state.detector === 'motion'
      ? 'Ruch — ramki „unknown” nie oznaczają rozpoznania samolotu'
      : 'YOLO — samoloty i ptaki';
    field('error').hidden = !state.error;
    field('error').textContent = state.error ?? '';
    const stale = state.frame_age_seconds !== null && state.frame_age_seconds > 5;
    field('image').hidden = stale;
    field('message').textContent = state.mode === 'idle'
      ? 'Agent czeka. Uruchom LIVE lub REPLAY w panelu SkyWatch.'
      : stale ? 'Brak nowych klatek. Sprawdź połączenie kamery.'
      : state.captured_at ? (state.mode === 'live' ? 'Obraz na żywo' : `Nagranie · ${state.scenario_id}`)
      : 'Oczekiwanie na pierwszą klatkę…';
    if (reconnect) { field('image').src = `/stream.mjpg?t=${Date.now()}`; reconnect = false; }
  } catch {
    field('mode').textContent = 'Rozłączono';
    field('message').textContent = 'Brak połączenia z agentem. Próbuję ponownie…';
    field('image').hidden = true;
    reconnect = true;
  } finally { setTimeout(refresh, 1000); }
}
refresh();
