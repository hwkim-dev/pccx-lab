# Judge Report — Round 4 — 2026-04-20

## Summary

**Overall grade: B-** (up from C+). Round 3's three tickets landed as
advertised, and each closes a named Round-3 fake-fix with file-verifiable
evidence. `src/core/src/api_ring.rs:1-167` is now a real derivation from
`NpuTrace.events` — `synthetic_fallback` is deleted (grep-0) and replaced
by `list_from_trace` (`api_ring.rs:141-167`) which walks events tagged
`event_type_id::API_CALL = 6` (`trace.rs:18`), records via `ApiRing`, and
returns an empty `Vec` with an `eprintln!` per Yuan OSDI 2014 when the
trace is empty. `src/core/src/simulator.rs` prepends an 8-entry
`uca_*` prelude so `dummy_trace.pccx` now carries 8 canonical API_CALL
events (MAC_COMPUTE 3200 / DMA_R 3200 / DMA_W 3200 / STALL 3200 /
BARRIER 3200 / API_CALL 8). `cargo test --lib` reports **39 passed /
0 failed / 0 ignored** (was 36; +3 from `list_from_trace_*` suite).
`cargo test` (lib + integration) is **39 + 27 = 66 green**. `npx vite
build` succeeds in 17.67 s; bundle 1.25 kB / 3.87 MB (slightly larger
due to `elkjs` + Tauri dialog plugin).

T-1 UI-side: `App.tsx:197` uses `resolveResource("dummy_trace.pccx")`
(grep-0 on the broken `"../../dummy_trace.pccx"` literal),
`tauri.conf.json:43` maps `"../../../dummy_trace.pccx"` into the
bundle, and the stale self-reference "see judge round-1 report" is
scrubbed (grep-0). T-2: `HardwareVisualizer.tsx:4` imports ELK,
`HardwareVisualizer.tsx:359` calls `elk.layout(graph)`, and the 13
hand-placed `{x, y, w, h}` literals are gone (grep-0). T-3:
`FlameGraph.tsx` has zero `Math.random` matches, the Compare-run
button opens a real Tauri dialog → `load_pccx_alt` → `fetch_trace_payload_b`
pipeline (`lib.rs:99-127`; 8 symbol hits across decl/register/doc).

**But three Round-3 gaps survive unaddressed, and one new drift appears:**

1. **`FlameGraph.tsx:226` still has `const N_LAYERS = 10`.** The
   Round-3 judge flagged this with the exact acceptance bullet
   `rg "N_LAYERS = 10" src/ui/src/FlameGraph.tsx` → 0. Five
   matches remain (lines 226, 242, 264, 265, 322). The Round-3
   Planner scoped it out of T-1/T-2/T-3, and the literal is now
   gated behind an `if (bytes.byteLength >= 24)` guard that the
   new `resolveResource` path usually satisfies — but the branch
   is still reachable when `fetch_trace_payload` fails, and no
   toolbar "(synthetic)" badge signals the switch. Backlogged by
   omission, not by decision.
2. **T-2's own deferral: no `src/core/src/hw_layout.rs` emitter.**
   The Round-3 roadmap listed it; `implemented_T2.md:82-101`
   explicitly backlogs it. `grep hw_layout src/core/src/*.rs` → 0.
   ELK now lays out the TSX literal `DIAGRAM_NODES`
   (`HardwareVisualizer.tsx:186-202`) — the literal is shorter and
   the placement dynamic, but `MAC_ARRAY=16` vs `MAC_ARRAY=32`
   still shows an identical graph because the hardware-shape source
   of truth is still TSX, not `HardwareModel::pccx_reference()`.
3. **T-1's own deferral: `api_name` sits outside the 24-byte
   flat buffer.** `trace.rs:77` adds `api_name: Option<String>`
   to `NpuEvent`, but the UI's `parseFlatBuffer`
   (`FlameGraph.tsx`/`HardwareVisualizer.tsx:251-260`) only decodes
   the 24-byte stride (core u32, start u64, dur u64, type u32). So
   API_CALL rows render as generic "api_call" without the
   `uca_submit_cmd` label. Honest in the Rust-side aggregation,
   lossy through IPC.
4. **7-file fake-telemetry dragnet is still ≥ 20 `Math.random / Math.sin`
   hits.** `rg "Math.random|Math.sin" src/ui/src` = 20 occurrences
   across `BottomPanel (3)`, `CanvasView (2)`, `ExtensionManager (1)`,
   `HardwareVisualizer (1)`, `PerfChart (6)`, `ReportBuilder (1)`,
   `Roofline (2)`, `Timeline (2)`, `WaveformViewer (2)`. Every file
   Round 3 flagged as Top-5 #5 is untouched. `setInterval` still
   drives seven live panels (`BottomPanel:104`, `CodeEditor:284`,
   `ExtensionManager:44`, `FlameGraph:519` — AI-hotspot anim is
   legitimate —, `HardwareVisualizer:304`, `PerfChart:27`,
   `Roofline:179`).

Grade lifts to B- on the weight of 3 clean fake-fix closures, 39 green
tests, and a genuine ELK adoption — but would be B if the N_LAYERS
literal, `api_name` IPC gap, and the 7-file telemetry dragnet had
been touched.

## Table

| # | Dimension | R-4 | R-3 | R-2 | Progress vs R-3 | Anchor | Headline gap |
|---|---|---|---|---|---|---|---|
| 1 | RTL / waveform UX         | B-  | B-  | C+ | 0 | Verdi / Surfer    | `WaveformViewer.tsx:132-134` still seeds waveforms with `Math.random` |
| 2 | ISA validation & trace    | B-  | B-  | D  | 0 | Spike / Whisper   | Untouched in R4; still no reg-file, no pipe-stage trace |
| 3 | API / driver integrity    | C+  | D+  | D+ | **+2** | CUPTI             | `list_from_trace` is real; `api_name` doesn't survive flat-buffer IPC (rendered as "api_call") |
| 4 | UVM coverage & regression | B-  | B-  | B- | 0 | Questa IMC / URG  | Untouched |
| 5 | FPGA verification         | B-  | C+  | C+ | **+0.5** | Vivado ILA    | ELK layout + trace-driven `edgeAlive`; `HardwareVisualizer:472` still has `Math.sin` pulse |
| 6 | ASIC signoff readiness    | F   | F   | F  | 0 | PrimeTime         | No work; no SDF, LEC, power |
| 7 | GPU / accelerator profile | B-  | B-  | B- | 0 | Nsight Systems    | `FlameGraph.tsx:226` `N_LAYERS = 10` literal survives |
| 8 | UI / UX / docking         | B   | B   | B- | 0 | VS Code           | No Monaco (`rg monaco src/ui/package.json` → 0); `CodeEditor.tsx:213` still the regex tokenizer |
| 9 | Documentation & onboarding| B+  | B+  | B  | 0 | Nsight Guide      | `docs/_static/screenshots/` has 13 images but no R-3/R-4 refresh; no Monaco screenshot |
|10 | Openness / licensing      | C+  | B-  | B- | **-0.5** | GTKWave / Surfer | `LICENSE_SCOPE.md` still absent; no decision on open-core boundary |

## Detailed findings

**Dim-3 jumps D+ → C+.** This is the single real quality win of the
round. `api_ring.rs:141-167 list_from_trace` walks `trace.events`,
filters `ev.type_id() == 6`, feeds `ApiRing::record(name, kind, ns)`,
and returns the flushed rows — or `Vec::new()` + `eprintln!` when
the trace is API-free. The mapping table (`classify_api_kind` at
`api_ring.rs:122-132`) is one taxonomy shared with the UI. The
`simulator.rs` prelude emits 8 canonical calls, so `dummy_trace.pccx`
is self-sufficient proof (`pccx_cli` prints `API_CALL: 8`). **Four
new tests** cover empty-trace, real-events, cycle→ns scaling, and
simulator round-trip. Grade held back from B- only because `api_name`
does not survive the 24-byte flat buffer and renders as "api_call"
in the UI span.

**Dim-5 lifts C+ → B-.** `HardwareVisualizer.tsx:4` imports
`ELK, { type ElkNode, type ElkExtendedEdge } from "elkjs/lib/elk.bundled.js"`;
`buildElkGraph` (lines 223-244) uses
`algorithm: layered`, `direction: RIGHT`, `BRANDES_KOEPF`,
`LAYER_SWEEP`, and an aspect-ratio feed from viewport. `useEffect`
(line 349-) runs `elk.layout(graph)` on mount and on `ResizeObserver`
tick. `edgeAlive` (line 267-277) walks trace events when present,
falls back to the per-edge cycle window otherwise. Held at B-
because the literal `DIAGRAM_NODES` (lines 186-202) still hardcodes
12 shape IDs in TSX, `HardwareVisualizer.tsx:472` `Math.sin` pulse
is still the primary "busy" animation, and the core-side
`hw_layout.rs` emitter the Round-3 roadmap required is absent.

**Dim-7 untouched.** `FlameGraph.tsx:226` `const N_LAYERS = 10` still
lives. The comment at line 182 says "Fall back to the Gemma 3N
literal demo tree only if no trace is loaded" — the demo is no
longer the default path (T-1 made `resolveResource` load the real
trace), but the literal is still shipped and still rendered on any
IPC failure. No "(synthetic)" badge was added per the Round-3
fallback plan.

**Dim-10 downgrade.** `LICENSE_SCOPE.md` still absent. The project
ships MIT via root `LICENSE`, but the open-core boundary (which
modules are ASL-2 vs proprietary-candidate?) has never been drawn.
Round-3 judge flagged this; no action. Slipping to C+ because it's
now two rounds stale.

## Progress vs Round 3

**What got better.** (1) `synthetic_fallback` literal deleted;
`list_from_trace` real. (2) `resolveResource` replaces the broken
path. (3) Stale "judge round-1 report" self-reference scrubbed.
(4) `N_LAYERS = 10` demo fallback no longer the primary render path
(though literal still present). (5) `Math.random` jitter in
`FlameGraph.tsx` Compare-run deleted; replaced by real
`load_pccx_alt` + `fetch_trace_payload_b` IPC (+53 / -16 core, +58 / -10 UI).
(6) 13 hand-placed `{x, y, w, h}` pixel literals in
`HardwareVisualizer` removed; `elk.layout` auto-layout live.
(7) `cargo test --lib` 36 → 39 green (+3); 66 green total counting
integration suite.

**What regressed.** (1) Openness/licensing slips: `LICENSE_SCOPE.md`
now 3 rounds stale. (2) Round-3 Top-5 item #5 (fake-telemetry
dragnet) formally untouched in Round-4 implementer tickets —
the 20-match `Math.random|Math.sin` count is essentially
unchanged from Round-3's 17-ish. (3) T-1's own note (`api_name`
outside flat buffer) is a new gap introduced in Round-3 that
Round-4 does not yet address.

**What was not touched.** Dim-2 (ISA reg-file), Dim-4 (UCIS/URG),
Dim-6 (ASIC signoff), Dim-8 (Monaco), Dim-9 (screenshot refresh).

## Top-5 must-fix for Round 5 — NEW fronts

1. **Monaco editor migration — still not done.**
   `rg "@monaco-editor/react" src/ui/package.json` → 0. `CodeEditor.tsx`
   is 409 LoC with the 28-keyword regex tokenizer at line 213 and
   a `setInterval`-driven fake simulation at line 284. Add
   `@monaco-editor/react@^4.7` + `monaco-editor@^0.52` to
   `package.json`, replace `<textarea>` + `HighlightedCode` with
   `<Editor language="systemverilog">`, register a minimal
   `monaco.languages.register` + Monarch grammar for SV, and wire
   find widget (Ctrl+F). **Accept**: `rg "@monaco-editor/react"
   package.json` ≥ 1, `rg "HighlightedCode\|SV_KEYWORDS" CodeEditor.tsx`
   → 0. **(L, ~400 LoC net.)**

2. **Kill the 7-file fake-telemetry dragnet — seriously this time.**
   Round-3 Top-5 #5 asked for this and nobody picked it up.
   Target files (hit counts from ripgrep): `BottomPanel.tsx:104-117`
   (3), `PerfChart.tsx:11-41` (6), `Roofline.tsx:177-192` (2),
   `Timeline.tsx:81-90` (2), `WaveformViewer.tsx:128-139` (2),
   `ReportBuilder.tsx:103-117` (1), `ExtensionManager.tsx:40-57` (1).
   Add one new Tauri command `fetch_live_window(from_cy: u64,
   to_cy: u64) -> LiveSample` in `lib.rs` that reduces
   `state.trace.events` over the window; empty-state uses the
   placeholder pattern at `VerificationSuite.tsx:149-155`.
   **Accept**: `rg "Math.random|Math.sin" src/ui/src` ≤ 2 (residuals
   in 3D pulse animation only), all `setInterval` bodies read from
   Tauri IPC or are ornamental UI animation. **(L, ~500 LoC.)**

3. **Flat-buffer v2 + `N_LAYERS = 10` retirement.**
   `NpuEvent.api_name: Option<String>` is silently dropped by the
   24-byte flat-buffer IPC. Bump the stride to 32 bytes (add a
   `name_hash: u32` + 4-byte reserved) **or** migrate
   `fetch_trace_payload` to JSON-compressed wire format with
   serde_json. Simultaneously: delete the 5-match `N_LAYERS` literal
   (`FlameGraph.tsx:226, 242, 264, 265, 322`) or gate with a
   `(synthetic)` toolbar badge. **Accept**:
   `rg "N_LAYERS" src/ui/src/FlameGraph.tsx` → 0 or UI renders
   "(synthetic)" in toolbar; API_CALL spans show `uca_*` name not
   generic "api_call". **(M, ~250 LoC.)**

4. **Post-route ASIC timing summary parser — unblock Dim-6 from F.**
   Add `src/core/src/vivado_timing.rs` that reads Vivado 2024.1's
   `report_timing_summary -no_detailed_paths` text output (one WNS /
   WHS / TNS / THS table per clock domain), bins into a `TimingSummary`
   struct, and exposes `parse_timing_report(&Path) -> io::Result<TimingSummary>`.
   Wire a new Tauri command `load_timing_report` + a minimal UI
   table panel. **Accept**: `cargo test vivado_timing::parse_kv260_report`
   green; the sample `report_timing_summary.txt` in
   `cycle/round_004/fixtures/` is parsed into a 2-clock-domain
   summary. **(L, ~400 LoC.)**

5. **Real "Run benchmark" end-to-end.** `App.tsx:230`
   `case "trace.benchmark": await handleTestIPC()` — `handleTestIPC`
   round-trips a synthetic buffer through `test_ipc_roundtrip`.
   Replace with an actual benchmark: launch `pccx_cli` with a
   built-in workload spec (gemm 32×32×1024), write the resulting
   `.pccx` to a temp path, reload via `load_pccx`, emit a toast
   with "N events in T ms". **Accept**: running "Run benchmark" from
   menu produces a real trace with ≥ 10 k events (matching the
   simulator's default) and updates the header panel with
   workload metadata. **(M, ~250 LoC.)**

(Word count: ~1770.)
