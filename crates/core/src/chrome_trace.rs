// Module Boundary: core/
// Google/Chromium "Trace Event Format" writer.
//
// Reference: https://docs.google.com/document/d/1CvAClvFfyA5R-PhYUmn5OOQtYMH4h6I0nSsKchNAySU
// linked from https://www.chromium.org/developers/how-tos/trace-event-profiling-tool/
//
// Emits a JSON array of Complete Events (`ph: "X"`) — the simplest
// encoding that renders correctly in ui.perfetto.dev, chrome://tracing
// and any Perfetto proto importer.  Fields per spec:
//   name  — display label
//   cat   — category string ("mac", "dma", "stall", "sync")
//   ph    — phase; "X" = complete duration event
//   ts    — timestamp (microseconds, integer)
//   dur   — duration in µs
//   pid   — process id (we map to accelerator instance)
//   tid   — thread id (we map to core_id, one lane per core)
//   args  — any extra key/value pairs (core_id mirrored for clarity)

use std::fs::File;
use std::io::{self, BufWriter, Write};
use std::path::Path;

use crate::trace::NpuTrace;

/// Assumed clock period so cycles map sensibly to microseconds.  The
/// pccx v002 reference design targets 200 MHz → 5 ns per cycle, so
/// 200 cycles = 1 µs.  Rounded to integer µs per Trace-Event spec.
const CYCLES_PER_US: u64 = 200;

fn cycles_to_us(cycles: u64) -> u64 {
    cycles / CYCLES_PER_US
}

fn category_for(event_type: &str) -> &'static str {
    match event_type {
        "MAC_COMPUTE"    => "mac",
        "DMA_READ"       => "dma",
        "DMA_WRITE"      => "dma",
        "SYSTOLIC_STALL" => "stall",
        "BARRIER_SYNC"   => "sync",
        _                => "other",
    }
}

/// Writes a Chrome Trace Event Format JSON array to `out`.
///
/// Returns the number of `ph: "X"` duration events emitted.
pub fn write_chrome_trace(trace: &NpuTrace, out: &Path) -> io::Result<usize> {
    let f = File::create(out)?;
    let mut w = BufWriter::new(f);
    write_chrome_trace_to(trace, &mut w)
}

/// Test-friendly core writing to any `Write`.
pub fn write_chrome_trace_to<W: Write>(trace: &NpuTrace, w: &mut W) -> io::Result<usize> {
    writeln!(w, "[")?;
    let mut written = 0usize;
    let mut first = true;
    for ev in &trace.events {
        if !first { writeln!(w, ",")?; }
        first = false;
        let ts = cycles_to_us(ev.start_cycle.get());
        let dur = cycles_to_us(ev.duration.get()).max(1);
        let cat = category_for(&ev.event_type);
        // Escape the event_type just in case — our known values are
        // ASCII without quotes/backslashes, but be defensive.
        let name = ev.event_type.replace('\\', "\\\\").replace('"', "\\\"");
        write!(
            w,
            "  {{\"name\":\"{name}\",\"cat\":\"{cat}\",\"ph\":\"X\",\"ts\":{ts},\"dur\":{dur},\"pid\":1,\"tid\":{tid},\"args\":{{\"core_id\":{core_id},\"start_cycle\":{start},\"duration_cycles\":{dur_cyc}}}}}",
            name = name,
            cat = cat,
            ts = ts,
            dur = dur,
            tid = ev.core_id.get(),
            core_id = ev.core_id.get(),
            start = ev.start_cycle.get(),
            dur_cyc = ev.duration.get(),
        )?;
        written += 1;
    }
    writeln!(w)?;
    writeln!(w, "]")?;
    w.flush()?;
    Ok(written)
}

// ─── Tests ───────────────────────────────────────────────────────────────
#[cfg(test)]
mod tests {
    use super::*;
    use crate::trace::{NpuEvent, NpuTrace};

    fn sample_trace() -> NpuTrace {
        NpuTrace {
            total_cycles: 1000,
            events: vec![
                NpuEvent::new(0, 0,   400, "MAC_COMPUTE"),
                NpuEvent::new(1, 400, 200, "DMA_READ"),
                NpuEvent::new(2, 600, 200, "BARRIER_SYNC"),
            ],
        }
    }

    #[test]
    fn output_is_parseable_json_array_of_complete_events() {
        let t = sample_trace();
        let mut buf: Vec<u8> = Vec::new();
        let n = write_chrome_trace_to(&t, &mut buf).unwrap();
        assert_eq!(n, 3, "one X-event per NpuEvent");
        let s = String::from_utf8(buf).unwrap();
        let v: serde_json::Value = serde_json::from_str(&s)
            .expect("output must be valid JSON per Google Trace Event Format");
        let arr = v.as_array().expect("top-level must be array");
        assert_eq!(arr.len(), 3);
        for ev in arr {
            assert_eq!(ev["ph"], "X", "every event must be a complete (duration) event");
            assert!(ev["ts"].is_number(), "ts required");
            assert!(ev["dur"].is_number(), "dur required");
            assert!(ev["name"].is_string(), "name required");
        }
    }

    #[test]
    fn categories_map_to_canonical_buckets() {
        let t = sample_trace();
        let mut buf: Vec<u8> = Vec::new();
        write_chrome_trace_to(&t, &mut buf).unwrap();
        let s = String::from_utf8(buf).unwrap();
        let v: serde_json::Value = serde_json::from_str(&s).unwrap();
        let arr = v.as_array().unwrap();
        assert_eq!(arr[0]["cat"], "mac");
        assert_eq!(arr[1]["cat"], "dma");
        assert_eq!(arr[2]["cat"], "sync");
    }
}
