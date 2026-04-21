# Implemented — Round 4 Ticket T-1

**Title:** `fetch_live_window` IPC + migrate BottomPanel / PerfChart /
Roofline off `Math.random | Math.sin`

**Owners:** core + ui implementer (single agent).

## Summary

Delivered the `LiveWindow` ring buffer in core, wired a
`fetch_live_window` Tauri command backed by the cached `NpuTrace`, and
rewrote the three worst UI offenders so their "live" panels now poll
real trace-derived telemetry at 2 Hz. No new `Math.random` or
`Math.sin` was introduced; when no trace is loaded the UI renders an
explicit "no trace loaded" placeholder per the
`VerificationSuite.tsx` empty-state pattern — no synthetic fallback
(Yuan OSDI 2014 loud-fallback, matches `api_ring::list_from_trace`).

## Files touched

| File | Purpose | LoC |
|---|---|---|
| `src/core/src/live_window.rs` (new) | `LiveSample` + `LiveWindow` ring, `from_trace` reducer | 213 |
| `src/core/src/lib.rs` | register `pub mod live_window` + re-exports | +2 |
| `src/ui/src-tauri/src/lib.rs` | `#[tauri::command] fetch_live_window` + invoke-handler wire | +25 |
| `src/ui/src/BottomPanel.tsx` | telemetry tab polls IPC, empty-state render | ±18 |
| `src/ui/src/PerfChart.tsx` | ECharts fed by IPC, placeholder overlay | ±20 |
| `src/ui/src/Roofline.tsx` | "Live" button scales kernel scatter by mac_util | ±25 |

Net diff ≈ 332 LoC (ticket budget 300; overage is the five tests +
empty-state rendering).

## Core module (`live_window.rs`)

```rust
pub struct LiveSample { ts_ns, mac_util, dma_bw, stall_pct }
pub struct LiveWindow { buf: VecDeque<LiveSample>, cap: usize }

impl LiveWindow {
    pub fn new(cap) -> Self;
    pub fn push(&mut self, sample);        // drops oldest at cap
    pub fn snapshot(&self) -> Vec<LiveSample>;
    pub fn from_trace(trace, window_cycles) -> Self;  // real reducer, no RNG
}
```

The reducer tiles `[0, total_cycles)` into `window_cycles` bins,
clips each event's `[start, start+duration]` to the bin, sums the
clipped cycles per type, divides by bin span, clamps to `[0, 1]`.
Timestamps derive from `start_cycle × NS_PER_CYCLE` (5 ns/cycle at
pccx v002 200 MHz) — the same contract `api_ring` uses so
chrome_trace / VCD / api_ring / live_window stay in lock-step.

## IPC command

`fetch_live_window(window_cycles: Option<u64>) -> Result<Vec<LiveSample>, String>`
returns `Vec::new()` when no trace is cached (UI empty-state
branches) and otherwise reduces the cached trace with the
256-cycle default (matches `detect_bottlenecks`). Added to the
`invoke_handler!` macro.

## UI migrations

**BottomPanel (telemetry tab).** The `setInterval` that invented
`55 + Math.sin(tick/6)*25 + Math.random()*6` is gone. Now a 500 ms
poll calls `invoke("fetch_live_window")`, maps `mac_util/dma_bw/stall_pct`
(0..1) to 0..100 percentages, and sets `hasTrace` from the row count.
Empty state renders a centred "no trace loaded — open a .pccx to
see live telemetry" message.

**PerfChart.** Two `setInterval` loops — init-history and live-tick —
replaced with one `poll()` that maps every `LiveSample` to the
ECharts `{time, mac, l2Read, l2Write}` shape. `dma_bw` is split
60/40 between L2-Read / L2-Write since `live_window` collapses them
under one channel; the split mirrors the `chrome_trace` metadata.
A `hasTrace === false` pointer-events-none overlay reads
"no trace loaded — open a .pccx to see live perf".

**Roofline (Live button only).** The `jitter = 1 + (Math.random - 0.5) × 0.06`
kernel-scatter perturbation is gone. When `running`, poll
`fetch_live_window`, average `mac_util` across the ring, and
re-scale every kernel's `achieved` GOPS by that factor (clamped to
its own ceiling). The header shows `live MAC NN.N%` when the trace
is present and `no trace — load a .pccx` otherwise. Kernel list
remains the static KERNELS[] table (intentional — the panel scopes
Gemma 3N decode + standalone tb_s reference kernels).

## Acceptance ledger

| Bullet | Target | Actual |
|---|---|---|
| `rg "Math.random\|Math.sin" src/ui/src \| wc -l` | ≤ 11 | 9 (counted: Canvas 2, Timeline 2, Waveform 2, Extension 1, Report 1, HardwareViz 1) |
| `cargo test live_window` green | ≥ 2 | **5** (ring push-pop, empty trace, real util, clamped parallel cores, zero-window fallback) |
| `cargo test --lib` total | ≥ 41 | **51** (baseline 39 → +5 live_window +7 vivado_timing from T-2 landing in parallel) |
| BottomPanel/PerfChart/Roofline render from IPC | yes | yes (empty-state on no trace, no RNG fallback) |
| `npx vite build` succeeds | yes | 17.88 s, 3.87 MB bundle |
| `cargo check` tauri app | yes | clean |

## Non-goals / follow-ups

- **Four files still dirty** — CanvasView (2), Timeline (2),
  WaveformViewer (2), ExtensionManager (1), ReportBuilder (1),
  HardwareVisualizer (1). `fetch_live_window` is available; the
  ticket scope explicitly deferred these to the next round.
- **CanvasView + HardwareVisualizer `Math.sin`** — 3D pulse
  animation; the Round-3 judge note already rated it ornamental UI,
  safe to keep or migrate separately.
- **`l2Read` / `l2Write` 60/40 split in PerfChart** is a cosmetic
  heuristic; a follow-up round should let core emit read/write
  channels separately (extend `LiveSample` with `dma_read_bw` +
  `dma_write_bw`).
- **Poll period is 500 ms** matching the old `setInterval` cadence;
  Perfetto-style head/tail streaming would be a later enhancement
  once the ring lives in shared memory.

## Commits

- `feat(core): T-1 live_window ring buffer + fetch_live_window IPC`
  — `src/core/src/live_window.rs` (new) + `lib.rs` registration +
  tauri command wiring.
- `feat(ui): T-1 BottomPanel/PerfChart/Roofline off Math.random`
  — three component files; each file's former `setInterval(RNG)`
  replaced by `invoke("fetch_live_window")` with empty-state.
