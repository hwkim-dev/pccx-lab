// Module Boundary: core/
// VCD (Value Change Dump, IEEE 1364-2005 §18) minimal writer.
//
// Emits a spec-legal VCD from an `NpuTrace` so users can drop the
// resulting file into GTKWave / Surfer / Verdi / the built-in
// Waveform panel.  The encoding models the trace as three groups of
// signals so every NpuEvent kind is observable on the timeline:
//
//   clk        1-bit wire — toggles every `clk_half_period` ticks
//   rst_n      1-bit wire — deasserts once at tick 0
//   mac_busy   1-bit wire — active during MAC_COMPUTE events
//   dma_rd     1-bit wire — active during DMA_READ events
//   dma_wr     1-bit wire — active during DMA_WRITE events
//   stall      1-bit wire — active during SYSTOLIC_STALL events
//   barrier    1-bit wire — active during BARRIER_SYNC events
//   core_id    8-bit bus  — current event's core_id (0 when idle)
//
// We emit value changes ordered by time with `#<tick>` prefixes per
// IEEE 1364-2005 §18.2.3.  Identifier codes use printable ASCII in
// the 33..=126 range (`!` onward) — spec §18.2.1.

use std::fs::File;
use std::io::{self, BufWriter, Write};
use std::path::Path;

use crate::trace::NpuTrace;

/// Writes an IEEE 1364-2005 §18 VCD rendering of `trace` to `out`.
///
/// The timescale is 1 ns (matches the `vcd` crate's default unit in the
/// parser-round-trip tests) and the clock half-period is chosen to be
/// 1 tick so consumers with a time cursor can still step instruction by
/// instruction.  Returns the number of value-change records emitted.
pub fn write_vcd(trace: &NpuTrace, out: &Path) -> io::Result<usize> {
    let f = File::create(out)?;
    let mut w = BufWriter::new(f);
    write_vcd_to(trace, &mut w)
}

/// Test-friendly core: writes into any `Write` sink.  Enables unit
/// tests to assert on the exact byte stream without touching the FS.
pub fn write_vcd_to<W: Write>(trace: &NpuTrace, w: &mut W) -> io::Result<usize> {
    // ─── Header ──────────────────────────────────────────────────────
    writeln!(w, "$version pccx_core vcd_writer 0.1 $end")?;
    writeln!(w, "$date 2026-04-20 $end")?;
    writeln!(w, "$timescale 1 ns $end")?;
    writeln!(w, "$scope module top $end")?;
    // Id codes: !=clk, "=rst_n, #=mac_busy, $=dma_rd, %=dma_wr, &=stall, '=barrier, (=core_id
    writeln!(w, "$var wire 1 ! clk $end")?;
    writeln!(w, "$var wire 1 \" rst_n $end")?;
    writeln!(w, "$var wire 1 # mac_busy $end")?;
    writeln!(w, "$var wire 1 $ dma_rd $end")?;
    writeln!(w, "$var wire 1 % dma_wr $end")?;
    writeln!(w, "$var wire 1 & stall $end")?;
    writeln!(w, "$var wire 1 ' barrier $end")?;
    writeln!(w, "$var wire 8 ( core_id $end")?;
    writeln!(w, "$upscope $end")?;
    writeln!(w, "$enddefinitions $end")?;

    // ─── Initial values (§18.2.4 $dumpvars) ──────────────────────────
    writeln!(w, "$dumpvars")?;
    writeln!(w, "0!")?;       // clk low
    writeln!(w, "0\"")?;      // rst_n low (held during reset)
    writeln!(w, "0#")?;       // mac_busy idle
    writeln!(w, "0$")?;
    writeln!(w, "0%")?;
    writeln!(w, "0&")?;
    writeln!(w, "0'")?;
    writeln!(w, "b00000000 (")?;
    writeln!(w, "$end")?;

    // ─── Event stream ────────────────────────────────────────────────
    // Build a (tick, signal_id, value) record set.  For each NpuEvent
    // we emit a rising edge at `start_cycle` and a falling edge at
    // `start_cycle + duration`.  The core_id bus mirrors the most
    // recently started event.
    #[derive(Clone)]
    struct Change { tick: u64, id: char, val: String }
    let mut changes: Vec<Change> = Vec::with_capacity(trace.events.len() * 2 + 4);

    // rst_n goes high at tick 1 so designs can exit reset.
    changes.push(Change { tick: 1, id: '"', val: "1".into() });

    let clk_half = 1u64.max(1);
    // Clock transitions across the window.  Bounded to avoid a runaway
    // write if total_cycles is huge; the UI already clips the window.
    let max_tick = trace.total_cycles.max(
        trace.events.iter().map(|e| e.start_cycle.get() + e.duration.get()).max().unwrap_or(0),
    );
    let mut t = 0u64;
    let mut level = 0u8;
    while t <= max_tick && changes.len() < 20_000 {
        level ^= 1;
        changes.push(Change { tick: t, id: '!', val: (level as u32).to_string() });
        t = t.saturating_add(clk_half);
        if t == 0 { break; }
    }

    for ev in &trace.events {
        let id = match ev.event_type.as_str() {
            "MAC_COMPUTE"    => '#',
            "DMA_READ"       => '$',
            "DMA_WRITE"      => '%',
            "SYSTOLIC_STALL" => '&',
            "BARRIER_SYNC"   => '\'',
            _                => continue,
        };
        let end = ev.start_cycle.get() + ev.duration.get();
        changes.push(Change { tick: ev.start_cycle.get(), id, val: "1".into() });
        changes.push(Change { tick: end, id, val: "0".into() });
        // core_id bus: 8-bit binary string, MSB first.
        let bits = format!("{:08b}", (ev.core_id.get() & 0xFF) as u8);
        changes.push(Change { tick: ev.start_cycle.get(), id: '(', val: format!("b{} ", bits) });
    }

    changes.sort_by(|a, b| a.tick.cmp(&b.tick));

    // Emit grouped by timestamp.
    let mut written = 0usize;
    let mut last_tick: Option<u64> = None;
    for c in &changes {
        if last_tick != Some(c.tick) {
            writeln!(w, "#{}", c.tick)?;
            last_tick = Some(c.tick);
        }
        if c.id == '(' {
            // Bus literal already carries its own prefix and trailing space.
            writeln!(w, "{}{}", c.val, c.id)?;
        } else {
            writeln!(w, "{}{}", c.val, c.id)?;
        }
        written += 1;
    }
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
            total_cycles: 20,
            events: vec![
                NpuEvent::new(1, 2,  5, "MAC_COMPUTE"),
                NpuEvent::new(0, 8,  4, "DMA_READ"),
                NpuEvent::new(3, 13, 2, "SYSTOLIC_STALL"),
            ],
        }
    }

    #[test]
    fn header_is_spec_legal() {
        let t = sample_trace();
        let mut buf: Vec<u8> = Vec::new();
        write_vcd_to(&t, &mut buf).expect("write ok");
        let s = String::from_utf8(buf).unwrap();
        assert!(s.starts_with("$version "), "§18.2.1 header must begin with a declaration command");
        assert!(s.contains("$timescale 1 ns $end"), "§18.2.2 timescale required");
        assert!(s.contains("$scope module top $end"), "§18.2.2 scope required");
        assert!(s.contains("$enddefinitions $end"), "§18.2.3 enddefinitions terminates header");
    }

    #[test]
    fn every_event_kind_declares_a_var() {
        let t = sample_trace();
        let mut buf: Vec<u8> = Vec::new();
        write_vcd_to(&t, &mut buf).unwrap();
        let s = String::from_utf8(buf).unwrap();
        for sig in ["clk", "rst_n", "mac_busy", "dma_rd", "dma_wr", "stall", "barrier", "core_id"] {
            assert!(s.contains(&format!(" {} $end", sig)),
                "expected $var declaration for '{}': got:\n{}", sig, s);
        }
    }

    #[test]
    fn value_changes_emit_rising_edge_at_event_start() {
        let t = sample_trace();
        let mut buf: Vec<u8> = Vec::new();
        let n = write_vcd_to(&t, &mut buf).unwrap();
        let s = String::from_utf8(buf).unwrap();
        assert!(n > 0, "expected at least one value change");
        // MAC_COMPUTE starts at tick 2 → `#2` then `1#` somewhere after.
        assert!(s.contains("#2\n"), "timestamp #2 must appear");
        assert!(s.contains("1#"), "mac_busy must rise at an event start");
        // DMA_READ ends at tick 12 → `0$` on drop.
        assert!(s.contains("0$"), "dma_rd must fall at an event end");
    }
}
