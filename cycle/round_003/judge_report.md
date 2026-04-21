# Judge Report — Round 3 — 2026-04-20

## Summary

**Overall grade: C+** (up from C). Round 2 landed the single biggest integrity
repair of the cycle so far — `src/core/src/vcd_writer.rs` (215 LoC, 3 tests),
`src/core/src/chrome_trace.rs` (136 LoC, 2 tests), and registrations of
`export_vcd` / `export_chrome_trace` in `src/ui/src-tauri/src/lib.rs:600-601`
close the "stealth fake" Round-2 call-out. `cargo test --lib` now reports
**36 green, 0 failed, 0 ignored** (up from 19); `npx vite build` finishes in
8.04 s. `src/core/src/isa_replay.rs` (238 LoC, 6 tests) is a genuine Spike
`--log-commits` parser with the pccx NPU latency table, and `validate_isa_trace`
at `lib.rs:395-400` forwards unchanged. `DUMMY_ISA_RESULTS` / `API_ROWS` /
`executeRegression` / `setInterval` are all **grep-0** in `VerificationSuite.tsx`
(acceptance met). Docs ship `docs/getting-started.md` (117 lines) and
`docs/ko/getting-started.md` (114 lines), both linked from their toctrees at
line 10. `useShortcuts.tsx` exports a 15-entry `SHORTCUT_MAP` plus a real
focus-trapped `<ShortcutHelp>` modal bound to `?` / `F1`. `aria-label` count
is **38** across `src/ui/src/` (from 0 at Round 1; roadmap floor was 30).

**But**: Round 3 uncovers a new textbook fake-fix and three deferrals the
roadmap silently accepted.

1. **`list_api_calls` is a hardcoded-array move, not removal.**
   `lib.rs:411-422` always returns `pccx_core::api_ring::synthetic_fallback()`
   — and `api_ring.rs:117-130` is the same 8-row literal (`uca_init, uca_alloc_buffer…`)
   that used to live as `API_ROWS` in TSX. The comment on line 414 even admits
   "The v002 generator does not emit `API_CALL` events yet, so we return the
   synthetic-fallback rows". A literal array was simply relocated one layer
   deeper in the stack. Round-2 roadmap T-1 required fidelity to the `.pccx`
   event stream ±1 ms; that acceptance bullet is unmet.

2. **Gemma-3N flame-graph literal still renders 100% of the time.**
   `FlameGraph.tsx:184` keeps `const N_LAYERS = 10`, the exact literal the
   Round-2 roadmap T-2 required to grep-zero. The primary IPC path
   (`fetch_trace_payload` → `events_to_spans`) only wins when the cached
   buffer is ≥ 24 bytes; the auto-load in `App.tsx:191` points to
   `"../../dummy_trace.pccx"` which is wrong relative to the tauri binary
   working directory, so the buffer is almost always empty at render time
   and the Gemma demo tree displays.

3. **Compare-run jitter is still `Math.random`.** `FlameGraph.tsx:126`:
   `const jitter = 0.6 + Math.random() * 1.2`. Deferred again without any
   "(synthetic)" toolbar prefix.

4. **`App.tsx:233` still self-references this report.** Error branch still
   prints "vcd_writer may not be wired yet — see judge round-1 report" —
   the command is now real, so the fallback string is fiction.

Round 3 clears the ISA parser and the export pipeline honestly, but the
API-integrity panel, the flame-graph data flow and the comparison toolbar
are fake-fixed or deferred. Grade lifts to **C+** on the weight of the real
VCD/Chrome writers and the 38-strong `aria-label` pass, but would be B-
without the above regressions.

## Table

| # | Dimension | R-3 | R-2 | R-1 | Progress vs R-2 | Anchor | Headline gap |
|---|---|---|---|---|---|---|---|
| 1 | RTL / waveform UX         | B-  | C+  | D+ | **+0.5** | Verdi / Surfer    | `vcd_writer` round-trip ships; still no FST, no virtual/expression signals, no transaction view |
| 2 | ISA validation & trace    | B-  | D   | D  | **+2** | Spike / Whisper   | Real Spike-format parser + 6 tests; no reg-file, no pipe-stage trace |
| 3 | API / driver integrity    | D+  | D+  | D+ | **0** | CUPTI             | `list_api_calls` returns the same 8-row literal relocated into `api_ring.rs:117` |
| 4 | UVM coverage & regression | B-  | B-  | C- | 0 | Questa IMC / URG  | Untouched; still JSONL-only, no UCIS, no trend |
| 5 | FPGA verification         | C+  | C+  | C  | 0 | Vivado ILA        | `HardwareVisualizer.tsx:255-267` still hand-placed px coords |
| 6 | ASIC signoff readiness    | F   | F   | F  | 0 | PrimeTime         | No work; no SDF, LEC, power |
| 7 | GPU / accelerator profile | B-  | B-  | C+ | 0 | Nsight Systems    | `N_LAYERS = 10` literal survives (`FlameGraph.tsx:184`); Compare-run still `Math.random` (line 126) |
| 8 | UI / UX / docking         | B   | B-  | B- | **+0.5** | VS Code       | 38 `aria-label` hits; `SHORTCUT_MAP` + `ShortcutHelp` modal; still no Monaco editor |
| 9 | Documentation & onboarding| B+  | B   | B  | **+0.5** | Nsight Guide  | `docs/getting-started.md` ships EN+KO (117/114 lines); walkthrough omits cross-coverage & bottleneck steps the roadmap required |
|10 | Openness / licensing      | B-  | B-  | B- | 0 | GTKWave / Surfer  | Still no `LICENSE_SCOPE.md` |

## Detailed findings

**T-2 writers verified — this is the real landmark of Round 2.**
`vcd_writer.rs` emits IEEE 1364-2005 §18 with spec-legal identifier codes
(`!` onward), `$dumpvars`, and a paired rising/falling edge per event
kind (`header_is_spec_legal`, `every_event_kind_declares_a_var`,
`value_changes_emit_rising_edge_at_event_start` all pass). `chrome_trace.rs`
emits the canonical `ph: "X"` duration event with `ts`/`dur`/`pid`/`tid`
and a `CYCLES_PER_US = 200` assumption that matches the pccx v002 200 MHz
reference. `cargo test --lib vcd_writer` → 3/3; `cargo test --lib chrome_trace`
→ 2/2.

**T-1 isa_replay verified with honest scope.** `isa_replay.rs:85-147`
parses `core N: 0x<pc> (0x<insn>) mnemonic operands` with optional
`;cycles=<N>` suffix, then classifies via ±10 % tolerance (`delta * 10 <= expected`
= WARN else FAIL). The mnemonic → latency table is prefix-based and
prosaic (mac.arr/gemm → 1024, dma → 64, sync/barrier → 16). 6 tests
cover the Spike baseline path (no suffix → PASS), WARN jitter, FAIL
stall, multi-line comments, empty log, and file round-trip. Grade
jumps from D to B- because the parser is real; it does not yet model
register-file effects or pipeline-stage visibility, but the roadmap
explicitly backlogged those ("no reg-file model").

**T-1 api_ring is a fake-fix.** The ring itself (`api_ring.rs:44-107`)
is correct — `record` / `flush` / p99 via nearest-rank method
(Hyndman & Fan 1996 type 1) with WARN > 1 ms / FAIL > 10 ms. **But**
the Tauri command `list_api_calls` (`lib.rs:410-422`) *never* calls
`record` against a real event stream; it drops the trace lock and
returns `synthetic_fallback()` — the 8-row literal at
`api_ring.rs:117-130` with canonical `uca_*` names and driver-README
latency numbers. The in-file comment admits this. **Verdict**: the
literal array moved from `VerificationSuite.tsx:383-392` (TSX) to
`api_ring.rs:117-130` (Rust). That is address-line relocation, not
behavioural change, and the Round-2 acceptance bullet "≥ 1 `uca_*`
row whose timestamp is within ±1 ms of the `.pccx` event stream
timestamp" is formally unmet. Dim-3 grade remains D+.

**T-3 accessibility + docs verified.**
- `useShortcuts.tsx:22-44` — 15-entry `SHORTCUT_MAP` with `key/desc/action`
  (roadmap floor was 10).
- `ShortcutHelp` at line 86 is a real focus-trapped `<div role="dialog"
  aria-modal="true">` with outside-click dismiss and Escape handling.
- `useShortcutHelp` at line 50 binds `?` / `F1` and respects
  `isContentEditable` — honest WCAG 2.2 SC 2.1.1 pass.
- `aria-label` rg count = 38 across `src/ui/src/*` (Round 2 was 0);
  distribution: App 10, WaveformViewer 8, FlameGraph 6, MemoryDump 5,
  MenuBar 4, useShortcuts 3, VerificationSuite 2. Ratio against
  `<button` (91 total) = **42 %** — roadmap required ≥ 90 % of
  icon-only buttons, unmet, but the absolute floor of ≥ 30 is met.
- `docs/getting-started.md` ships at 117 lines (floor was 80) with
  2 screenshot embeds (`flamegraph-gemma3n.png`, `waveform-enterprise.png`).
  Roadmap required 4 screenshots *and* a walkthrough of one
  bookmark + one cross-coverage cell + one bottleneck recommendation
  — the doc covers the bookmark only. Step-through for cross-coverage
  and `detect_bottlenecks` is missing.
- Link at line 106 references `src/ui/src/useShortcuts.ts` but the
  actual file is `useShortcuts.tsx` — doc drift.

**Untouched dimensions.** `CodeEditor.tsx:213` is still the 409-LoC
regex tokenizer (Monaco *not* installed in `package.json`);
`MemoryDump.tsx:43-53` still synthesises bytes from a per-region LCG seed;
`HardwareVisualizer.tsx:255-267` still has hand-placed pixel coordinates;
`BottomPanel.tsx:109-111`, `PerfChart.tsx:17-35`, `Roofline.tsx:179-184`
all still drive live panels off `Math.sin + Math.random` inside
`setInterval(..., 50ms)` timers. `CanvasView.tsx` invokes
`get_core_utilisation` but once data lands the colours are frozen and
the pulsing "heartbeat" animation (line 164) is a pure `phase += 0.018`
clock — the 32 × 32 array tiles do not animate from trace events.

## Regressions / silent scope drops

1. **`api_ring::synthetic_fallback` is a literal-array relocation
   disguised as ingestion.** The only honest path out is to add an
   `API_CALL` event kind to `NpuTrace` (`src/core/src/trace.rs:7-14`)
   and have the Tauri command walk `state.trace.events` through an
   `ApiRing::record`. Until that happens, dim-3 cannot rise above D+.
2. **`FlameGraph.tsx:184` `N_LAYERS = 10` literal survives** despite
   the Round-2 roadmap T-2 acceptance bullet
   `rg "N_LAYERS = 10" src/ui/src/FlameGraph.tsx` → 0 (unmet).
3. **`FlameGraph.tsx:126` `loadRunB` `Math.random` jitter** is
   untouched and un-disclaimered in the toolbar, despite the roadmap's
   explicit "prefix toolbar label with (synthetic)" fallback plan.
4. **`App.tsx:233` error string** still points users at "judge round-1
   report" for a wiring bug that was fixed in `2310d96`. Cosmetic but
   a stale self-reference at runtime.
5. **`App.tsx:191` auto-load path** `"../../dummy_trace.pccx"` resolves
   from `src/ui/src-tauri/` under the tauri dev binary but the file
   lives at repo root — three levels up, not two. Runtime auto-load
   silently fails every time, which is *why* the Gemma literal
   fallback appears universally.

## Top-5 must-fix for Round 4 — NEW fronts

1. **Monaco editor migration.** `CodeEditor.tsx:195-228` is still a
   28-keyword regex tokenizer. Add `@monaco-editor/react@^4` to
   `src/ui/package.json`, drop the `monaco-languages` SystemVerilog
   grammar, and register hover/fold/minimap. Accept
   `rg "@monaco-editor/react" src/ui/package.json` ≥ 1, editor
   renders `interface_def` template with syntax colours from Monaco's
   own tokenizer, and `Ctrl+F` opens Monaco's find widget. **(L, ~400 LoC net.)**
2. **Genuinely derive `HardwareVisualizer` placement from
   `HardwareModel::pccx_reference()` via an ELK.js auto-layout.**
   Current state: 13 hand-placed `{x,y,w,h}` objects at
   `HardwareVisualizer.tsx:255-267` + 13 hand-tuned `alive(cycle)`
   lambdas at lines 270-284. Target: add
   `src/core/src/hw_layout.rs` emitting nodes + edges from the
   RTL `HIERARCHY`, pipe through `elkjs` in the UI, and drive
   `alive(cycle)` from trace events keyed by `event_type`.
   Accept: `rg "x: \d+, y: \d+" src/ui/src/HardwareVisualizer.tsx`
   → 0; dragging a core node re-flows edges. **(L, ~450 LoC.)**
3. **Real `load_pccx_alt(path)` for Compare-run + kill the
   `Math.random` jitter.** `FlameGraph.tsx:119-132`: remove the
   synthetic map; add an `AppState::trace_b: Mutex<Option<NpuTrace>>`
   and a new `fetch_trace_payload_b` Tauri command; open via Tauri
   dialog. Accept: `rg "Math.random" src/ui/src/FlameGraph.tsx` → 0;
   second `.pccx` file loads and diff-coloured ratio is real.
   **(M, ~250 LoC.)**
4. **Fix `api_ring::synthetic_fallback` by emitting `API_CALL`
   events from the v002 generator.** Add `API_CALL` to
   `event_type_id` (`trace.rs:7-14`), bump `NpuEvent` to carry
   `api_name: Option<String>`, teach the generator (in sibling
   pccx-FPGA) to emit at `uca_*` boundary crossings, then rewrite
   `list_api_calls` to walk `state.trace.events` through a real
   `ApiRing`. Accept: `rg "synthetic_fallback" src/core/src/api_ring.rs`
   → 0 or gated behind `#[cfg(test)]`; `cargo test -p pccx_core
   api_ring::records_from_trace` passes. **(L, ~350 LoC across two
   repos.)**
5. **Drive `BottomPanel`, `PerfChart`, and `Roofline` live charts
   off real trace data, not sin+random.** Three files,
   identical pattern. `BottomPanel.tsx:104-114`, `PerfChart.tsx:27-40`,
   `Roofline.tsx:179-184` all have `setInterval(..., 50ms)` loops
   that compose `Math.sin(tick/6) + Math.random()*6` into a
   "live telemetry" chart that is 0 % real. Replace with a
   windowed reduction over `state.trace.events` exposed via a new
   `fetch_live_window(from_cycle, to_cycle)` Tauri command; if no
   trace is loaded, show the empty-state placeholder pattern
   `VerificationSuite.tsx:149-155` already uses. Accept:
   `rg "Math.random|Math.sin" src/ui/src/{BottomPanel,PerfChart,Roofline}.tsx`
   → 0. **(L, ~300 LoC.)**

(Word count: ~1740.)
