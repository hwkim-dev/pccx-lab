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

// KV260 ZU5EV device capacity (Vivado 2023.2 device summary).
const DEVICE_LUTS: u64 = 117_120;
const DEVICE_FFS: u64 = 234_240;
const DEVICE_BRAM: u64 = 144; // RAMB36 equivalent
const DEVICE_DSP: u64 = 1_248;

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
                let g = |i: usize| {
                    cells
                        .get(i)
                        .and_then(|s| s.parse::<u64>().ok())
                        .unwrap_or(0)
                };
                summary.total_luts = g(2);
                summary.logic_luts = g(3);
                summary.ffs = g(6);
                summary.rams_36 = g(7);
                summary.rams_18 = g(8);
                summary.urams = g(9);
                summary.dsps = g(10);
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
                let is_divider =
                    !row.is_empty() && row.chars().all(|c| c == '-' || c.is_whitespace());
                if is_divider || row.is_empty() || row.starts_with("WNS") || row.starts_with('|') {
                    j += 1;
                    continue;
                }
                // Row like:
                //   -9.792    -3615.208                   4194                28602  ...
                let cols: Vec<&str> = row.split_whitespace().collect();
                if cols.len() >= 4 {
                    t.wns_ns = cols[0].parse().unwrap_or(0.0);
                    t.tns_ns = cols[1].parse().unwrap_or(0.0);
                    t.failing_endpoints = cols[2].parse().unwrap_or(0);
                    t.total_endpoints = cols[3].parse().unwrap_or(0);
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
            let is_divider = !row.is_empty() && row.chars().all(|c| c == '-' || c.is_whitespace());
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

pub fn load_from_files(utilisation_path: &str, timing_path: &str) -> Result<SynthReport, String> {
    let util_text = fs::read_to_string(utilisation_path).map_err(|e| {
        format!(
            "Cannot read utilisation report '{}': {}",
            utilisation_path, e
        )
    })?;
    let timing_text = fs::read_to_string(timing_path)
        .map_err(|e| format!("Cannot read timing report '{}': {}", timing_path, e))?;

    Ok(SynthReport {
        utilisation: parse_utilization(&util_text),
        timing: parse_timing(&timing_text),
        device: parse_device(&util_text),
    })
}

// ─── Resource heatmap ────────────────────────────────────────────────────────

/// Per-cell resource data for the heatmap grid.
/// Resource utilization fields are fractional (0.0–1.0) relative to device
/// capacity. `power_mw` is an estimated absolute value in milliwatts.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HeatmapCell {
    pub row: usize,
    pub col: usize,
    /// LUT utilization fraction (0.0–1.0)
    pub lut_util: f64,
    /// Flip-flop utilization fraction (0.0–1.0)
    pub ff_util: f64,
    /// BRAM utilization fraction (0.0–1.0)
    pub bram_util: f64,
    /// DSP utilization fraction (0.0–1.0)
    pub dsp_util: f64,
    /// Estimated power in milliwatts
    pub power_mw: f64,
}

/// Grid of resource utilization and power estimates, one cell per `(row, col)`.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ResourceHeatmap {
    pub rows: usize,
    pub cols: usize,
    pub cells: Vec<HeatmapCell>,
}

/// Distributes `SynthReport` utilization data across a `rows × cols` grid.
///
/// Distribution patterns:
/// - DSP: 2-D Gaussian centered on the array (MAT_CORE cluster in the chip center).
/// - LUT/FF: smooth sinusoidal stripe variation to reflect pipeline columns.
/// - BRAM: sparse diagonal band (scratchpad / FIFO placement).
/// - Power: linear combination of the above.
///
/// All values are deterministic (no RNG) so the panel is stable across renders.
pub fn generate_heatmap(report: &SynthReport, rows: usize, cols: usize) -> ResourceHeatmap {
    if rows == 0 || cols == 0 {
        return ResourceHeatmap {
            rows,
            cols,
            cells: Vec::new(),
        };
    }

    let u = &report.utilisation;

    // Overall device-level utilization fractions (clamped to [0, 1]).
    let lut_frac = (u.total_luts as f64 / DEVICE_LUTS as f64).min(1.0);
    let ff_frac = (u.ffs as f64 / DEVICE_FFS as f64).min(1.0);
    let bram_frac =
        ((u.rams_36 + u.rams_18 / 2 + u.urams * 4) as f64 / DEVICE_BRAM as f64).min(1.0);
    let dsp_frac = (u.dsps as f64 / DEVICE_DSP as f64).min(1.0);

    let cr = (rows as f64 - 1.0) / 2.0;
    let cc = (cols as f64 - 1.0) / 2.0;

    // Gaussian half-widths: DSP cluster fits in ~30 % of the array.
    let sigma_r = (rows as f64) * 0.30;
    let sigma_c = (cols as f64) * 0.30;

    let mut cells = Vec::with_capacity(rows * cols);

    for r in 0..rows {
        for c in 0..cols {
            let dr = (r as f64 - cr) / sigma_r.max(0.01);
            let dc = (c as f64 - cc) / sigma_c.max(0.01);
            let gauss = (-0.5 * (dr * dr + dc * dc)).exp();

            // DSP: concentrated near center (Gaussian).
            let dsp_weight = gauss;

            // LUT/FF: smooth column-stripe pattern (pipeline columns).
            let col_phase = (c as f64 / cols as f64) * std::f64::consts::PI * 4.0;
            let row_phase = (r as f64 / rows as f64) * std::f64::consts::PI * 2.0;
            let lut_weight = 0.65 + 0.25 * col_phase.sin() + 0.10 * row_phase.cos();
            let lut_weight = lut_weight.max(0.0);
            let ff_weight = 0.60 + 0.30 * (col_phase + 0.5).sin() + 0.10 * row_phase.sin();
            let ff_weight = ff_weight.max(0.0);

            // BRAM: sparse diagonal band.
            let bram_weight = if (r + c) % 3 == 0 { 1.0 } else { 0.0 };

            // Normalize weights per-metric against the per-cell mean so
            // the average value reconstructs the global fraction.
            // For Gaussian / sinusoidal the analytic mean is computed
            // below; we scale cell values so sum(cell_val) == total_val.
            // We defer normalization to a post-pass.
            cells.push((r, c, lut_weight, ff_weight, bram_weight, dsp_weight));
        }
    }

    // Post-pass: normalize each metric to ensure sum = global fraction * n.
    let n = (rows * cols) as f64;
    let sum_lut: f64 = cells.iter().map(|x| x.2).sum();
    let sum_ff: f64 = cells.iter().map(|x| x.3).sum();
    let sum_bram: f64 = cells.iter().map(|x| x.4).sum();
    let sum_dsp: f64 = cells.iter().map(|x| x.5).sum();

    let scale_lut = if sum_lut > 0.0 {
        lut_frac * n / sum_lut
    } else {
        0.0
    };
    let scale_ff = if sum_ff > 0.0 {
        ff_frac * n / sum_ff
    } else {
        0.0
    };
    let scale_bram = if sum_bram > 0.0 {
        bram_frac * n / sum_bram
    } else {
        0.0
    };
    let scale_dsp = if sum_dsp > 0.0 {
        dsp_frac * n / sum_dsp
    } else {
        0.0
    };

    // KV260 ZU5EV total design power budget (~8 W typical under load).
    // Power density per cell is a weighted mix of resource utilization.
    let total_power_mw = 8_000.0 * (0.3 * lut_frac + 0.5 * dsp_frac + 0.2 * bram_frac);

    let result_cells: Vec<HeatmapCell> = cells
        .into_iter()
        .map(|(r, c, lw, fw, bw, dw)| {
            let lut_cell = (lw * scale_lut).min(1.0);
            let ff_cell = (fw * scale_ff).min(1.0);
            let bram_cell = (bw * scale_bram).min(1.0);
            let dsp_cell = (dw * scale_dsp).min(1.0);
            let power_cell =
                total_power_mw / n * (0.4 * lut_cell + 0.5 * dsp_cell + 0.1 * bram_cell);
            HeatmapCell {
                row: r,
                col: c,
                lut_util: lut_cell,
                ff_util: ff_cell,
                bram_util: bram_cell,
                dsp_util: dsp_cell,
                power_mw: power_cell,
            }
        })
        .collect();
    ResourceHeatmap {
        rows,
        cols,
        cells: result_cells,
    }
}

#[cfg(test)]
mod heatmap_tests {
    use super::*;

    fn mock_report(luts: u64, ffs: u64, brams: u64, dsps: u64) -> SynthReport {
        SynthReport {
            utilisation: UtilSummary {
                top_module: "NPU_Top".into(),
                total_luts: luts,
                logic_luts: luts,
                ffs,
                rams_36: brams,
                rams_18: 0,
                urams: 0,
                dsps,
            },
            timing: TimingSummary::default(),
            device: "xczu5ev-sfvc784-2-e".into(),
        }
    }

    #[test]
    fn test_heatmap_cell_count() {
        let r = mock_report(60_000, 100_000, 80, 900);
        let hm = generate_heatmap(&r, 8, 12);
        assert_eq!(hm.rows, 8);
        assert_eq!(hm.cols, 12);
        assert_eq!(hm.cells.len(), 8 * 12);
    }

    #[test]
    fn test_zero_dimensions_returns_empty() {
        let r = mock_report(1000, 1000, 10, 100);
        let hm0 = generate_heatmap(&r, 0, 8);
        assert!(hm0.cells.is_empty());
        let hm1 = generate_heatmap(&r, 8, 0);
        assert!(hm1.cells.is_empty());
    }

    #[test]
    fn test_all_values_non_negative() {
        let r = mock_report(70_000, 140_000, 90, 1000);
        let hm = generate_heatmap(&r, 6, 8);
        for cell in &hm.cells {
            assert!(
                cell.lut_util >= 0.0,
                "lut_util negative at ({},{})",
                cell.row,
                cell.col
            );
            assert!(
                cell.ff_util >= 0.0,
                "ff_util negative at ({},{})",
                cell.row,
                cell.col
            );
            assert!(
                cell.bram_util >= 0.0,
                "bram_util negative at ({},{})",
                cell.row,
                cell.col
            );
            assert!(
                cell.dsp_util >= 0.0,
                "dsp_util negative at ({},{})",
                cell.row,
                cell.col
            );
            assert!(
                cell.power_mw >= 0.0,
                "power_mw negative at ({},{})",
                cell.row,
                cell.col
            );
        }
    }

    #[test]
    fn test_dsp_hotspot_at_center() {
        let r = mock_report(50_000, 100_000, 60, 800);
        let rows = 10_usize;
        let cols = 10_usize;
        let hm = generate_heatmap(&r, rows, cols);
        let center = hm
            .cells
            .iter()
            .find(|c| c.row == rows / 2 && c.col == cols / 2)
            .unwrap();
        let corner = hm.cells.iter().find(|c| c.row == 0 && c.col == 0).unwrap();
        assert!(
            center.dsp_util > corner.dsp_util,
            "center DSP {} should exceed corner DSP {}",
            center.dsp_util,
            corner.dsp_util,
        );
    }

    #[test]
    fn test_lut_util_sum_reconstructs_global_fraction() {
        let luts = 70_000_u64;
        let r = mock_report(luts, 150_000, 80, 900);
        let rows = 8_usize;
        let cols = 8_usize;
        let hm = generate_heatmap(&r, rows, cols);
        let n = (rows * cols) as f64;
        let sum: f64 = hm.cells.iter().map(|c| c.lut_util).sum();
        let expected = luts as f64 / DEVICE_LUTS as f64 * n;
        // Allow 1 % relative error from f64 floating-point accumulation.
        let err = (sum - expected).abs() / expected.max(1e-9);
        assert!(
            err < 0.01,
            "LUT sum={:.4} expected={:.4} rel_err={:.4}",
            sum,
            expected,
            err
        );
    }
}
