# T-3 — Flat-buffer v2 with `api_name` trailer + N_LAYERS retirement

**Round:** 4  **Owner:** core + ui implementer  **Date:** 2026-04-20

## Summary

- `NpuTrace::to_flat_buffer` now emits an optional `name_table`
  trailer after the fixed 24-byte-per-event array.  Trailer layout:
  `magic u32 = 0x32434350 ("PCC2" LE) | name_count u32 | { event_index
  u32, len u16, utf8 bytes }[name_count]`.  Only events with
  `api_name == Some(...)` contribute, so v2 buffers stay byte-identical
  to v1 for compute-only traces.
- `NpuTrace::from_flat_buffer_v2` rebuilds the trace, populating
  `api_name` from the trailer and tolerating legacy v1 payloads (no
  trailer) for one migration round.
- `FlameGraph.tsx::parseFlatBuffer` reads the trailer and attaches
  `event.name`; `events_to_spans` substitutes that name for
  `API_CALL` spans so UI renders `uca_init@core0` instead of the old
  generic `api_call@core0`.
- The 170-line Gemma 3N E4B literal demo tree (`N_LAYERS = 10`, 121
  hard-coded spans) is gone.  The fallback now sets
  `synthetic = true`, clears `spans`, and renders a centred
  **“no trace loaded · (synthetic)”** placeholder inside the canvas,
  plus a warm-amber `(synthetic)` pill badge in the toolbar.  The
  badge never appears when a real trace is loaded.
- `HardwareVisualizer.tsx::parseTraceFlat` was updated to the same v2
  stop-at-magic scan so trace events parse correctly regardless of
  trailer presence.

## Files touched

| File | Δ (approx) | Purpose |
|------|-----------|---------|
| `src/core/src/trace.rs` | +224 / −13 | V2 encoder, decoder, 3 unit tests |
| `src/ui/src/FlameGraph.tsx` | +60 / −178 | v2 parser, name substitution, kill demo tree, synthetic badge + empty-state overlay |
| `src/ui/src/HardwareVisualizer.tsx` | +14 / −2 | v2-aware `parseTraceFlat` |

Net: **+330 / −193 LoC → +137 net** (budget was ≤ 350).

## Acceptance checks

| Criterion | Result |
|-----------|--------|
| `rg "N_LAYERS" src/ui/src/FlameGraph.tsx` → 0 | **PASS** (0 matches) |
| `cargo test trace::flat_buffer_v2_roundtrip` green | **PASS** (`test result: ok. 1 passed`) |
| `cargo test --lib` total ≥ 42 | **PASS** (51 passed — baseline 39 + 3 trace::tests::flat_buffer_v2* + 9 vivado_timing from T-2) |
| API_CALL spans render qualified names (`uca_*@coreN`) | **PASS** — `events_to_spans` now prefers `ev.name` for `typeId === 6` |
| `(synthetic)` badge visible only when no trace loaded | **PASS** — guarded by `synthetic && !loading && spans.length === 0` and toolbar pill flipped by `synthetic` state |
| `npx tsc --noEmit` clean on FlameGraph / HardwareVisualizer | **PASS** (pre-existing unrelated errors in CanvasView / CodeEditor / ReportBuilder / Timeline only) |
| `npx vite build` succeeds | **PASS** (3.87 MB bundle, no new warnings) |

## Design notes

### Why a trailing table instead of per-event inlined strings

The roadmap sketched a `u16 name_idx` appended to each event.  The
final implementation instead keeps the 24-byte stride untouched and
trails the name_table — three reasons:

1. **Byte-compatible with v1 when no names are present.** Compute-only
   traces produce identical bytes, so every v1 decoder keeps working
   without recompilation (see `flat_buffer_v2_omits_trailer_when_no_names`).
2. **Sparse-friendly.** Typical traces have ~100 API_CALL events vs
   100 K compute events; expanding the stride by 4 bytes would
   inflate the payload 17 % for zero useful signal.
3. **Magic-prefix detection** (`0x32434350`) cannot occur at a
   24-byte-aligned position inside the event array because `core_id`
   fields are small u32s bounded by the core count (≤ 32), so the
   decoder can safely probe for the trailer without a header byte.

See Gap 3 (FlatBuffers vtable evolution / rkyv / Cap'n Proto) in
`cycle/round_004/research_findings.md` — we picked the rkyv-style
appended side-table over a vtable rewrite because it requires zero
schema tooling and preserves the existing WebGL-friendly stride.

### Empty-state honesty

Per Yuan OSDI 2014 "loud fallback" and the R-4 judge's Dim-3 note,
the absence of a real trace must be surfaced prominently.  The
`(synthetic)` toolbar badge uses `theme.error` to match the existing
AI-recommendation-critical-alert palette — users already associate
that colour with "something is not what it seems".  The centred
overlay gives a one-line action ("Open a `.pccx` file…") so the
empty-state isn't just a dead canvas.

### Backward compatibility

- **V1 producers → V2 decoder.**  A v1 payload without a trailer
  decodes cleanly via `from_flat_buffer_v2` — proven by
  `flat_buffer_v2_decodes_v1_payload` test.
- **V2 producer → V1 decoder.**  A v1 decoder reads
  `events_len * 24` bytes and stops; the trailer is silently
  discarded.  No external consumer is broken.

## Commits landed

1. `feat(core): T-3 flat-buffer v2 with name_table` —
   `src/core/src/trace.rs` only.
2. `feat(ui): T-3 FlameGraph qualified API_CALL names + kill Gemma literal` —
   `src/ui/src/FlameGraph.tsx` + `src/ui/src/HardwareVisualizer.tsx`.

## Follow-ups (not this round)

- `BottomPanel.tsx:72` still hard-codes the string "Rendered
  FlameGraph with 121 spans (Gemma 3N decode step)" as a fake log
  line — cosmetic; address in R-5 alongside the rest of the
  log-theatre clean-up.
- `Roofline.tsx` and `ReportBuilder.tsx` still reference Gemma 3N
  literals in their domain-specific contexts (Roofline kernel list +
  citation footnote); those are intentional content, not fake
  telemetry.
- Consider a CI guard `rg "N_LAYERS" src/ui/src/FlameGraph.tsx` to
  prevent the literal from sneaking back.
