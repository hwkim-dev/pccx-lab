// Module Boundary: core/
// Parses Vivado `report_utilization` and `report_timing_summary` text
// output into structured summaries the pccx-lab UI can display.
//
// The parsers are forgiving: they scan for the first plausible data row
// and tolerate header reformatting between Vivado versions. Fields that
// are not found fall back to zero / `is_timing_met: true` so a partial
// report never poisons the whole load.

use serde::{Deserialize, Serialize};
use std::fs;

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct UtilSummary {
    pub top_module: String,
    pub total_luts: u64,
    pub logic_luts: u64,
    pub ffs: u64,
    pub rams_36: u64,
    pub rams_18: u64,
    pub urams: u64,
    pub dsps: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct TimingSummary {
    pub wns_ns: f64,
    pub tns_ns: f64,
    pub failing_endpoints: u64,
    pub total_endpoints: u64,
    pub is_timing_met: bool,
    pub worst_clock: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct SynthReport {
    pub utilisation: UtilSummary,
    pub timing: TimingSummary,
    pub device: String,
}

/// Parse `report_utilization -hierarchical` output.
/// Finds the first top-level row of the hierarchy table.
pub fn parse_utilization(text: &str) -> UtilSummary {
    let mut summary = UtilSummary::default();
    let mut in_table = false;
    for line in text.lines() {
        let trimmed = line.trim();
        if trimmed.starts_with('|') && summary.top_module.is_empty() {
            if let Some((key, val)) = trimmed[1..].split_once(':') {
                if key.trim() == "Design" {
                    summary.top_module = val.trim().to_string();
                }
            }
        }
        if trimmed.starts_with("1. Utilization by Hierarchy") {
            in_table = true;
            continue;
        }
        if !in_table {
            continue;
        }
        // The first data row under that section starts with `| <top_module> ` — we pick it
        // by looking for a row whose first cell contains the top module name.
        if !summary.top_module.is_empty()
            && trimmed.starts_with('|')
            && trimmed.contains(&format!(" {} ", summary.top_module))
        {
            let cells: Vec<&str> = trimmed
                .split('|')
                .map(|c| c.trim())
                .filter(|c| !c.is_empty())
                .collect();
            // Expected columns after instance/module:
            // Total LUTs, Logic LUTs, LUTRAMs, SRLs, FFs, RAMB36, RAMB18, URAM, DSP Blocks
            if cells.len() >= 11 {
                let g = |i: usize| cells.get(i).and_then(|s| s.parse::<u64>().ok()).unwrap_or(0);
                summary.total_luts = g(2);
                summary.logic_luts = g(3);
                summary.ffs        = g(6);
                summary.rams_36    = g(7);
                summary.rams_18    = g(8);
                summary.urams      = g(9);
                summary.dsps       = g(10);
                break;
            }
        }
    }
    summary
}

/// Parse `report_timing_summary` output — extracts the Design Timing Summary
/// row (WNS / TNS / failing endpoints) and the "met / not met" verdict.
pub fn parse_timing(text: &str) -> TimingSummary {
    let mut t = TimingSummary::default();
    t.is_timing_met = true;

    // "Timing constraints are not met." signals failure.
    if text.contains("Timing constraints are not met") {
        t.is_timing_met = false;
    }

    let lines: Vec<&str> = text.lines().collect();

    // Find the Design Timing Summary block.
    let mut i = 0;
    while i < lines.len() {
        if lines[i].trim().starts_with("| Design Timing Summary") {
            // Skip the header / divider lines until we hit a row starting with
            // a signed number.
            let mut j = i + 1;
            while j < lines.len() {
                let row = lines[j].trim();
                // Skip divider (pure dashes/spaces), header, empty, pipe-prefixed lines.
                let is_divider = !row.is_empty() && row.chars().all(|c| c == '-' || c.is_whitespace());
                if is_divider || row.is_empty() || row.starts_with("WNS") || row.starts_with('|') {
                    j += 1;
                    continue;
                }
                // Row like:
                //   -9.792    -3615.208                   4194                28602  ...
                let cols: Vec<&str> = row.split_whitespace().collect();
                if cols.len() >= 4 {
                    t.wns_ns              = cols[0].parse().unwrap_or(0.0);
                    t.tns_ns              = cols[1].parse().unwrap_or(0.0);
                    t.failing_endpoints   = cols[2].parse().unwrap_or(0);
                    t.total_endpoints     = cols[3].parse().unwrap_or(0);
                }
                break;
            }
            break;
        }
        i += 1;
    }

    // Walk the Per-Clock summary for the worst clock name. The per-clock
    // block is distinguishable from the design-level summary by a header
    // line that starts with the literal "Clock" keyword (plus whitespace,
    // plus "WNS" somewhere on the line).
    let mut per_clock_idx: Option<usize> = None;
    for (idx, line) in lines.iter().enumerate() {
        let trimmed = line.trim_start();
        if trimmed.starts_with("Clock ") && trimmed.contains("WNS(ns)") {
            per_clock_idx = Some(idx);
            break;
        }
    }
    if let Some(start) = per_clock_idx {
        let mut worst = ("".to_string(), f64::INFINITY);
        for line in lines.iter().skip(start + 2).take(20) {
            let row = line.trim();
            let is_divider = !row.is_empty()
                && row.chars().all(|c| c == '-' || c.is_whitespace());
            if row.is_empty() || is_divider {
                break;
            }
            let cols: Vec<&str> = row.split_whitespace().collect();
            if cols.len() < 2 {
                continue;
            }
            if let Ok(wns) = cols[1].parse::<f64>() {
                if wns < worst.1 {
                    worst = (cols[0].to_string(), wns);
                }
            }
        }
        t.worst_clock = worst.0;
    }

    t
}

fn parse_device(text: &str) -> String {
    for line in text.lines() {
        let trimmed = line.trim();
        if trimmed.starts_with('|') {
            if let Some((key, val)) = trimmed[1..].split_once(':') {
                if key.trim() == "Device" {
                    return val.trim().to_string();
                }
            }
        }
    }
    String::new()
}

pub fn load_from_files(
    utilisation_path: &str,
    timing_path: &str,
) -> Result<SynthReport, String> {
    let util_text = fs::read_to_string(utilisation_path)
        .map_err(|e| format!("Cannot read utilisation report '{}': {}", utilisation_path, e))?;
    let timing_text = fs::read_to_string(timing_path)
        .map_err(|e| format!("Cannot read timing report '{}': {}", timing_path, e))?;

    Ok(SynthReport {
        utilisation: parse_utilization(&util_text),
        timing:      parse_timing(&timing_text),
        device:      parse_device(&util_text),
    })
}
