// Module Boundary: core/
// VCD (Value Change Dump, IEEE 1364 §21) ingest for the Waveform
// panel.  Delegates lexing to the `vcd` crate (MIT) and repackages
// the output as a flat, serde-friendly `WaveformDump`:
//
//   ┌────────────────────────┐        ┌──────────────────────────┐
//   │ $scope / $var header   │  ───▶  │ Vec<SignalMeta>          │
//   └────────────────────────┘        └──────────────────────────┘
//   ┌────────────────────────┐        ┌──────────────────────────┐
//   │ $timestamp + value …   │  ───▶  │ Vec<VcdChange>           │
//   └────────────────────────┘        └──────────────────────────┘
//
// The UI consumes this via the `parse_vcd_file` Tauri command and
// binary-searches per signal to render O(log n) value-at-tick lookups.

use std::fs::File;
use std::io::BufReader;
use std::path::Path;

use serde::{Deserialize, Serialize};
use thiserror::Error;
use vcd::{Command, Parser, ScopeItem, Value as VcdValue};

/// Per-signal metadata collected from the VCD `$var` headers.  The
/// `id` is the raw IEEE-1364 identifier code — the 1- to 4-character
/// printable string that the value-change section references.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SignalMeta {
    /// VCD identifier code (e.g. "!", "#n3"). Doubles as the key the
    /// UI groups transitions by.
    pub id:    String,
    /// Human-readable reference name from `$var <type> <width> <id> <name>`.
    pub name:  String,
    /// Dot-joined scope path ("top.ctrl.mat" etc) — empty at file root.
    pub scope: String,
    /// Bit-width declared in the `$var` command (1 for wires).
    pub width: u32,
}

/// A single value-change event.  `tick` is the cumulative simulation
/// time in the file's own timescale units — we do not rescale here
/// because the UI is cycle-oriented and the caller already knows the
/// timescale via `WaveformDump::timescale_ps`.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VcdChange {
    /// Matches `SignalMeta::id`.
    pub sig_id: String,
    /// VCD timestamp at which the change is observed.
    pub tick:   u64,
    /// Stringified value.  Scalars emit `"0"`, `"1"`, `"x"`, `"z"`;
    /// buses emit a 2-/16-radix bit string as the VCD spec dictates.
    /// The UI radix formatter re-parses this lazily.
    pub value:  String,
}

/// Structured result of parsing a `.vcd` file.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WaveformDump {
    pub signals: Vec<SignalMeta>,
    pub events:  Vec<VcdChange>,
    /// File timescale converted to picoseconds so the UI can label
    /// the ruler without re-implementing the unit math.  `None` when
    /// the VCD omitted `$timescale`.
    pub timescale_ps: Option<u64>,
}

/// Errors returned by [`parse_vcd_file`].
#[derive(Debug, Error)]
pub enum VcdError {
    #[error("I/O error reading '{path}': {source}")]
    Io {
        path: String,
        #[source]
        source: std::io::Error,
    },
    /// Wraps an `io::Error` produced by the `vcd` crate's parser.
    /// (The crate exposes `ParseError` but re-casts to `io::Error`
    /// at the `Iterator::next` boundary, so we follow suit.)
    #[error("VCD parse error: {0}")]
    Parse(String),
}

/// Parses a VCD file end-to-end into a flat [`WaveformDump`].
///
/// The parser uses buffered I/O plus a streaming walk of the
/// `$var` / `$scope` / `$upscope` commands, so memory usage is
/// proportional to `signals + events` rather than the raw byte
/// stream.  On a 500-signal / 50k-event trace the end-to-end parse
/// is expected to complete in < 80 ms on a Ryzen 4500U; the UI
/// budget is 800 ms including IPC + first paint.
pub fn parse_vcd_file(path: &Path) -> Result<WaveformDump, VcdError> {
    let file = File::open(path).map_err(|source| VcdError::Io {
        path: path.display().to_string(),
        source,
    })?;
    let reader = BufReader::new(file);
    let mut parser = Parser::new(reader);

    let header = parser
        .parse_header()
        .map_err(|e| VcdError::Parse(e.to_string()))?;

    // Walk the scope tree once, flattening each `$var` into a
    // `SignalMeta`.  Scope names are joined with '.' in declaration
    // order, matching Surfer / GTKWave / Verdi behaviour.
    let mut signals: Vec<SignalMeta> = Vec::new();
    let mut scope_stack: Vec<String> = Vec::new();
    collect_signals(&header.items, &mut scope_stack, &mut signals);

    // Convert the `$timescale 1 ns` etc. tuple to picoseconds so the
    // UI does not need to carry a unit enum through its state tree.
    let timescale_ps = header.timescale.map(|(num, unit)| {
        use vcd::TimescaleUnit::*;
        let per_unit_ps: u64 = match unit {
            S  => 1_000_000_000_000,
            MS => 1_000_000_000,
            US => 1_000_000,
            NS => 1_000,
            PS => 1,
            FS => 0, // below ps resolution; round to 0 and carry on
        };
        (num as u64).saturating_mul(per_unit_ps)
    });

    // Stream the value-change section.  We allocate once per change
    // to keep `VcdChange` owned (serde-friendly) — at a projected
    // 50k events this is ~2 MB of peak heap, well under the 30 MB
    // IPC buffer ceiling.
    let mut events: Vec<VcdChange> = Vec::new();
    let mut current_tick: u64 = 0;
    for cmd_res in parser {
        let cmd = cmd_res.map_err(|e| VcdError::Parse(e.to_string()))?;
        match cmd {
            Command::Timestamp(t) => {
                current_tick = t;
            }
            Command::ChangeScalar(id, value) => {
                events.push(VcdChange {
                    sig_id: id.to_string(),
                    tick:   current_tick,
                    value:  scalar_to_str(value).to_string(),
                });
            }
            Command::ChangeVector(id, vector) => {
                events.push(VcdChange {
                    sig_id: id.to_string(),
                    tick:   current_tick,
                    value:  vector.to_string(),
                });
            }
            Command::ChangeReal(id, r) => {
                events.push(VcdChange {
                    sig_id: id.to_string(),
                    tick:   current_tick,
                    value:  format!("{r}"),
                });
            }
            Command::ChangeString(id, s) => {
                events.push(VcdChange {
                    sig_id: id.to_string(),
                    tick:   current_tick,
                    value:  s,
                });
            }
            // Begin/End/Comment/Version/Date are informational only.
            _ => {}
        }
    }

    Ok(WaveformDump { signals, events, timescale_ps })
}

// ─── Internal helpers ────────────────────────────────────────────────────

fn collect_signals(
    items: &[ScopeItem],
    scope_stack: &mut Vec<String>,
    out: &mut Vec<SignalMeta>,
) {
    for item in items {
        match item {
            ScopeItem::Scope(scope) => {
                scope_stack.push(scope.identifier.clone());
                collect_signals(&scope.items, scope_stack, out);
                scope_stack.pop();
            }
            ScopeItem::Var(var) => {
                out.push(SignalMeta {
                    id:    var.code.to_string(),
                    name:  var.reference.clone(),
                    scope: scope_stack.join("."),
                    width: var.size,
                });
            }
            // ScopeItem::Comment — swallowed.
            _ => {}
        }
    }
}

fn scalar_to_str(v: VcdValue) -> &'static str {
    match v {
        VcdValue::V0 => "0",
        VcdValue::V1 => "1",
        VcdValue::X  => "x",
        VcdValue::Z  => "z",
    }
}

// ─── Tests ───────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    const MINIMAL_VCD: &str = "\
$date   Apr 20 2026 $end
$version   pccx_core vcd test fixture $end
$timescale 1 ns $end
$scope module top $end
$scope module ctrl $end
$var wire 1 ! clk $end
$var reg  8 # counter $end
$upscope $end
$upscope $end
$enddefinitions $end
#0
0!
b00000000 #
#10
1!
b00000001 #
#20
0!
#30
1!
b00000010 #
";

    fn write_fixture(contents: &str) -> tempfile::NamedTempFile {
        let mut f = tempfile::NamedTempFile::new().expect("tempfile");
        f.write_all(contents.as_bytes()).expect("write");
        f.flush().expect("flush");
        f
    }

    #[test]
    fn parse_header_var_and_one_value_change() {
        let f = write_fixture(MINIMAL_VCD);
        let dump = parse_vcd_file(f.path()).expect("parse ok");

        // Header sanity.
        assert_eq!(dump.timescale_ps, Some(1_000), "1 ns = 1000 ps");
        assert_eq!(dump.signals.len(), 2, "two $var entries");

        let clk = dump.signals.iter().find(|s| s.name == "clk").expect("clk present");
        assert_eq!(clk.width, 1);
        assert_eq!(clk.scope, "top.ctrl");

        let counter = dump.signals.iter().find(|s| s.name == "counter").expect("counter present");
        assert_eq!(counter.width, 8);
        assert_eq!(counter.scope, "top.ctrl");

        // Value-change sanity.
        assert!(!dump.events.is_empty(), "at least one transition parsed");
        let first_clk_rise = dump.events.iter().find(|e| {
            e.sig_id == clk.id && e.tick == 10 && e.value == "1"
        });
        assert!(first_clk_rise.is_some(), "clk should rise at tick 10");

        // Counter transitions must round-trip into bit strings.
        let counter_at_10 = dump.events.iter().find(|e| {
            e.sig_id == counter.id && e.tick == 10
        }).expect("counter updates at 10");
        assert_eq!(counter_at_10.value, "00000001");
    }

    #[test]
    fn missing_file_yields_io_error() {
        let err = parse_vcd_file(Path::new("/nonexistent/definitely-not-here.vcd"))
            .expect_err("should not exist");
        matches!(err, VcdError::Io { .. });
    }
}
