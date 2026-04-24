let initialized = false;

export async function ensureMonacoReady() {
  if (initialized) return;
  initialized = true;

  const [{ loader }, monaco, { default: EditorWorker }] = await Promise.all([
    import("@monaco-editor/react"),
    import("monaco-editor"),
    import("monaco-editor/esm/vs/editor/editor.worker?worker"),
  ]);

  // Point @monaco-editor/react's loader at the bundled npm package instead of
  // the default jsdelivr CDN. This keeps pccx-lab fully offline / CSP-safe
  // inside the Tauri asset:// origin — no cross-origin worker downloads.
  //
  // SystemVerilog has no dedicated language worker (it's a Monarch DFA), so
  // the generic editor worker is the only one we need to wire up.
  (globalThis as any).MonacoEnvironment = {
    getWorker(_workerId: string, _label: string) {
      return new EditorWorker();
    },
  };

  loader.config({ monaco });
}
