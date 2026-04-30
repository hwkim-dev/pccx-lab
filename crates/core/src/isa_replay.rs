// Module Boundary: core/
// ISA replay diff engine — consumes a Spike `--log-commits` style
// commit log and emits per-instruction (expected, actual) cycle
// pairs.  Pattern: the ISS emits a ground-truth cycle count per
// retired op; a `.pccx` DUT log gives the actual cycle; the diff
// is the classic `riscv-dv iss_sim_compare.py` contract parameterised
// for the pccx NPU latency table (hw/rtl/pipeline_pkg).
//
// Expected log line format (Spike `--log-commits`):
//
//   core   0: 0x0000000080001000 (0x00400513) li      a0, 4
//   core   0: 0x0000000080001004 (0x00000013) nop
//
// We parse:
//   - pc         := 0x<hex>  (after "core N:")
//   - insn_hex   := (0x<hex>) inside parens
//   - mnemonic   := first whitespace-delimited token after the parens
//   - operands   := rest of the line (joined with single spaces)
//
// The expected cycle count comes from a small NPU latency table keyed
// by mnemonic prefix; a mnemonic of `mac`, `gemm`, `ld`, etc. maps
// to the pipeline latency.  Unknown mnemonics default to 1 cycle.
//
// The actual cycle count is what the DUT reported.  If the log line
// does not carry a `;cycles=<N>` suffix (Spike default), we treat
// `actual == expected` as PASS (we have no DUT evidence).  When the
// suffix is present, PASS iff equal, WARN iff within ±10 %, FAIL
// otherwise.

use serde::{Deserialize, Serialize};

/// A single replay row: one retired instruction with its expected
/// and actual cycle counts and a status verdict.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct IsaResult {
    /// Mnemonic + operands joined: "ld.tile.l2 [r3], brm_0".
    pub inst: String,
    /// `0x<hex>` opcode string (machine-code word).
    pub opcode: String,
    /// Golden-model cycle count (from the NPU latency table).
    pub expected_cycles: u64,
    /// DUT-reported cycle count (from the log, else == expected).
    pub actual_cycles: u64,
    /// PASS | WARN | FAIL.
    pub status: IsaStatus,
    /// Human-readable decode hint.
    pub decode: String,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "UPPERCASE")]
pub enum IsaStatus {
    Pass,
    Warn,
    Fail,
}

/// Returns the NPU pipeline latency for a given mnemonic.  The table
/// is intentionally small and prefix-keyed so it survives operand
/// variations (e.g. `mac.arr.32x32` vs. `mac.scalar`).  Values are
/// taken from `hw/rtl/pipeline_pkg` (see docs/ISA.md for the full
/// matrix); unknown mnemonics default to 1.
fn expected_cycles_for(mnemonic: &str) -> (u64, &'static str) {
    let m = mnemonic.to_ascii_lowercase();
    if m.starts_with("mac.arr") || m.starts_with("gemm") {
        (1024, "32x32 MAC Array Multiply-Accumulate")
    } else if m.starts_with("ld.tile") {
        (128, "Load Tile from L2 mapping")
    } else if m.starts_with("st.wb") || m.starts_with("st.tile") {
        (48, "Store Write-Back to DDR")
    } else if m.starts_with("dma") {
        (64, "AXI Burst Memory Access")
    } else if m.starts_with("sync") || m.starts_with("barrier") {
        (16, "Tile Synchronization Barrier")
    } else if m.starts_with("ld") {
        (8, "Scalar Load")
    } else if m.starts_with("st") {
        (8, "Scalar Store")
    } else if m.starts_with("br") || m.starts_with("j") {
        (4, "Branch / Jump")
    } else {
        (1, "Scalar ALU")
    }
}

/// Parses one Spike-style commit log line.  Returns `None` if the
/// line does not match the expected shape (comments, blank lines,
/// non-commit trace messages).
fn parse_commit_line(line: &str) -> Option<IsaResult> {
    let t = line.trim();
    if t.is_empty() || t.starts_with('#') || t.starts_with("//") {
        return None;
    }
    // Expect leading "core N:" — skip past it.
    let rest = t.strip_prefix("core").unwrap_or(t).trim_start();
    // Drop the "N:" core-id segment.
    let rest = match rest.find(':') {
        Some(i) => rest[i + 1..].trim_start(),
        None => return None,
    };
    // Now expect: "0x<pc> (0x<insn>) <mnemonic> [operands...]".
    let mut parts = rest.splitn(2, char::is_whitespace);
    let pc = parts.next()?;
    if !pc.starts_with("0x") {
        return None;
    }
    let tail = parts.next()?.trim_start();
    // Opcode is the `(0x....)` segment.
    let open = tail.find('(')?;
    let close = tail.find(')')?;
    if close <= open + 1 {
        return None;
    }
    let opcode = tail[open + 1..close].to_string();
    if !opcode.starts_with("0x") {
        return None;
    }
    let after = tail[close + 1..].trim_start();
    if after.is_empty() {
        return None;
    }
    let mut it = after.splitn(2, char::is_whitespace);
    let mnemonic = it.next()?.to_string();
    let operands = it.next().unwrap_or("").trim();
    let inst = if operands.is_empty() {
        mnemonic.clone()
    } else {
        format!("{} {}", mnemonic, operands)
    };

    // Optional `;cycles=<N>` suffix carries the DUT's actual count.
    // Spike baseline does not emit it; the pccx testbench does.
    let (inst_clean, actual_opt) = match inst.rfind(";cycles=") {
        Some(i) => {
            let n = inst[i + ";cycles=".len()..]
                .trim()
                .trim_end_matches(|c: char| !c.is_ascii_digit())
                .parse::<u64>()
                .ok();
            (inst[..i].trim_end().to_string(), n)
        }
        None => (inst, None),
    };

    let (expected, decode) = expected_cycles_for(&mnemonic);
    let actual = actual_opt.unwrap_or(expected);
    let status = if actual == expected {
        IsaStatus::Pass
    } else {
        let delta = (actual as i64 - expected as i64).unsigned_abs();
        if delta * 10 <= expected {
            IsaStatus::Warn
        } else {
            IsaStatus::Fail
        }
    };
    Some(IsaResult {
        inst: inst_clean,
        opcode,
        expected_cycles: expected,
        actual_cycles: actual,
        status,
        decode: decode.to_string(),
    })
}

/// Parses a full Spike-style commit log (as a single UTF-8 string)
/// and returns one `IsaResult` per commit line.
pub fn parse_commit_log(log: &str) -> Vec<IsaResult> {
    log.lines().filter_map(parse_commit_line).collect()
}

/// Convenience wrapper that reads the log from a file.
pub fn parse_commit_log_file(path: &std::path::Path) -> std::io::Result<Vec<IsaResult>> {
    let txt = std::fs::read_to_string(path)?;
    Ok(parse_commit_log(&txt))
}

// ─── Tests ────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_single_commit_line_to_pass() {
        // Spike default format — no ;cycles suffix, so actual == expected, PASS.
        let line = "core   0: 0x0000000080001000 (0x00400513) ld.tile.l2 [r3], brm_0";
        let r = parse_commit_line(line).expect("should parse");
        assert_eq!(r.opcode, "0x00400513");
        assert_eq!(r.inst, "ld.tile.l2 [r3], brm_0");
        assert_eq!(r.expected_cycles, 128);
        assert_eq!(r.actual_cycles, 128);
        assert_eq!(r.status, IsaStatus::Pass);
    }

    #[test]
    fn detects_stall_as_fail_when_cycles_suffix_exceeds_10pct() {
        // DMA opcode; expected 64, actual 256 → 400 % over → FAIL.
        let line = "core   0: 0x80001004 (0x11112222) dma.axi.burst 64, req_1 ;cycles=256";
        let r = parse_commit_line(line).expect("should parse");
        assert_eq!(r.expected_cycles, 64);
        assert_eq!(r.actual_cycles, 256);
        assert_eq!(r.status, IsaStatus::Fail);
    }

    #[test]
    fn marks_small_jitter_as_warn() {
        // sync.barrier expected 16, actual 18 → within ±10 % (delta 2, 10% of 16 is 1.6 → delta*10=20 > 16 → FAIL? )
        // Use a tighter case: expected 16, actual 17, delta 1, delta*10=10 ≤ 16 → WARN.
        let line = "core   0: 0x80001008 (0x33334444) sync.barrier tile_mask ;cycles=17";
        let r = parse_commit_line(line).expect("should parse");
        assert_eq!(r.expected_cycles, 16);
        assert_eq!(r.actual_cycles, 17);
        assert_eq!(r.status, IsaStatus::Warn);
    }

    #[test]
    fn parses_multi_line_log_and_skips_comments() {
        let log = "\
# This is a comment line.
core   0: 0x80001000 (0x00400513) ld.tile.l2 [r3], brm_0
random noise line without 'core' prefix
core   0: 0x80001004 (0x11112222) mac.arr.32x32 m_a, m_b
core   1: 0x80002000 (0x22223333) st.wb.ddr [r9], acc_z ;cycles=48
";
        let rows = parse_commit_log(log);
        assert_eq!(rows.len(), 3);
        assert_eq!(rows[0].expected_cycles, 128);
        assert_eq!(rows[1].expected_cycles, 1024);
        assert_eq!(rows[2].status, IsaStatus::Pass);
    }

    #[test]
    fn empty_log_returns_empty_vec() {
        assert!(parse_commit_log("").is_empty());
        assert!(parse_commit_log("\n\n# nothing here\n").is_empty());
    }

    #[test]
    fn file_roundtrip_reads_and_parses() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("commit.log");
        std::fs::write(
            &path,
            "core   0: 0x80001000 (0xaabbccdd) gemm.tile ;cycles=1024\n",
        )
        .unwrap();
        let rows = parse_commit_log_file(&path).unwrap();
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].expected_cycles, 1024);
        assert_eq!(rows[0].actual_cycles, 1024);
        assert_eq!(rows[0].status, IsaStatus::Pass);
    }
}
