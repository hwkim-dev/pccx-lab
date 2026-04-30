// Module Boundary: core/
// UVM coverage merger — consumes JSONL run dumps and produces a
// merged view (hits-per-bin across groups, plus cross tuples) that
// the UI's VerificationSuite panel can render without hand-coded
// literals.
//
// JSONL schema (one object per line) — see `hw/sim/coverage/schema.md`:
//   Bin entry:   {"group":"gemm_tile_shape","bin":"32x32","hits":17,"goal":20}
//   Cross entry: {"cross":["gemm_k_stride","mem_hp_backpressure"],
//                  "a_bin":"4","b_bin":"hi","hits":5,"goal":8}
//
// `goal` is optional; when absent, we carry forward the largest goal
// seen across runs (0 if none was ever supplied). `hits` are summed
// across runs, matching Accellera UCIS merge semantics for
// count-based bins.

use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::fs;
use std::path::Path;
use thiserror::Error;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct CovBin {
    pub id: String,
    pub hits: u64,
    pub goal: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct CovGroup {
    pub name: String,
    pub bins: Vec<CovBin>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct CrossTuple {
    pub a_group: String,
    pub b_group: String,
    pub a_bin: String,
    pub b_bin: String,
    pub hits: u64,
    pub goal: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default, PartialEq, Eq)]
pub struct MergedCoverage {
    pub groups: Vec<CovGroup>,
    pub crosses: Vec<CrossTuple>,
}

#[derive(Error, Debug)]
pub enum CoverageError {
    #[error("IO error on {path}: {source}")]
    IoError {
        path: String,
        source: std::io::Error,
    },
    #[error("JSON error on {path} line {line}: {source}")]
    JsonError {
        path: String,
        line: usize,
        source: serde_json::Error,
    },
}

// ─── Raw JSONL record ────────────────────────────────────────────────────────
//
// One schema covers both bin and cross records. Field presence
// disambiguates: `group` present → bin; `cross` present → cross tuple.

#[derive(Debug, Deserialize)]
struct RawRecord {
    #[serde(default)]
    group: Option<String>,
    #[serde(default)]
    bin: Option<String>,
    #[serde(default)]
    cross: Option<(String, String)>,
    #[serde(default)]
    a_bin: Option<String>,
    #[serde(default)]
    b_bin: Option<String>,
    #[serde(default)]
    hits: u64,
    #[serde(default)]
    goal: Option<u64>,
}

/// Merges one or more JSONL coverage dumps into a single
/// `MergedCoverage`. Ordering of groups and bins is stable across
/// runs (BTreeMap ensures deterministic output regardless of input
/// order — important for snapshot tests).
pub fn merge_jsonl(paths: &[&Path]) -> Result<MergedCoverage, CoverageError> {
    // group -> bin -> (hits, goal)
    let mut bin_map: BTreeMap<String, BTreeMap<String, (u64, u64)>> = BTreeMap::new();
    // (a_group, b_group, a_bin, b_bin) -> (hits, goal)
    let mut cross_map: BTreeMap<(String, String, String, String), (u64, u64)> = BTreeMap::new();

    for path in paths {
        let path_str = path.display().to_string();
        let text = fs::read_to_string(path).map_err(|e| CoverageError::IoError {
            path: path_str.clone(),
            source: e,
        })?;

        for (line_no, raw_line) in text.lines().enumerate() {
            let line = raw_line.trim();
            if line.is_empty() || line.starts_with('#') {
                continue;
            }
            let rec: RawRecord =
                serde_json::from_str(line).map_err(|e| CoverageError::JsonError {
                    path: path_str.clone(),
                    line: line_no + 1,
                    source: e,
                })?;

            if let Some((a_group, b_group)) = rec.cross {
                let a_bin = rec.a_bin.unwrap_or_default();
                let b_bin = rec.b_bin.unwrap_or_default();
                let key = (a_group, b_group, a_bin, b_bin);
                let slot = cross_map.entry(key).or_insert((0, 0));
                slot.0 += rec.hits;
                slot.1 = slot.1.max(rec.goal.unwrap_or(0));
            } else if let (Some(group), Some(bin)) = (rec.group, rec.bin) {
                let slot = bin_map
                    .entry(group)
                    .or_default()
                    .entry(bin)
                    .or_insert((0, 0));
                slot.0 += rec.hits;
                slot.1 = slot.1.max(rec.goal.unwrap_or(0));
            }
            // Silently drop records that match neither shape — the
            // schema doc marks them as reserved for future extensions.
        }
    }

    let groups = bin_map
        .into_iter()
        .map(|(name, bins)| CovGroup {
            name,
            bins: bins
                .into_iter()
                .map(|(id, (hits, goal))| CovBin { id, hits, goal })
                .collect(),
        })
        .collect();

    let crosses = cross_map
        .into_iter()
        .map(
            |((a_group, b_group, a_bin, b_bin), (hits, goal))| CrossTuple {
                a_group,
                b_group,
                a_bin,
                b_bin,
                hits,
                goal,
            },
        )
        .collect();

    Ok(MergedCoverage { groups, crosses })
}

/*────────────────────────────────────────*/
// Tests
/*────────────────────────────────────────*/

#[cfg(test)]
mod merge {
    use super::*;
    use std::io::Write;

    fn write_tmp(name: &str, body: &str) -> std::path::PathBuf {
        let mut path = std::env::temp_dir();
        path.push(format!("pccx_cov_{}_{}", std::process::id(), name));
        let mut f = fs::File::create(&path).unwrap();
        f.write_all(body.as_bytes()).unwrap();
        path
    }

    #[test]
    fn merge_empty_input_is_empty() {
        let merged = merge_jsonl(&[]).unwrap();
        assert!(merged.groups.is_empty());
        assert!(merged.crosses.is_empty());
    }

    #[test]
    fn merge_single_run_preserves_bins() {
        let p = write_tmp(
            "single.jsonl",
            concat!(
                r#"{"group":"gemm_tile_shape","bin":"32x32","hits":5,"goal":10}"#,
                "\n",
                r#"{"group":"gemm_tile_shape","bin":"16x16","hits":2,"goal":4}"#,
                "\n",
            ),
        );
        let merged = merge_jsonl(&[p.as_path()]).unwrap();
        assert_eq!(merged.groups.len(), 1);
        let g = &merged.groups[0];
        assert_eq!(g.name, "gemm_tile_shape");
        assert_eq!(g.bins.len(), 2);
        // BTreeMap ordering: "16x16" < "32x32" lexically.
        assert_eq!(g.bins[0].id, "16x16");
        assert_eq!(g.bins[0].hits, 2);
        assert_eq!(g.bins[0].goal, 4);
        assert_eq!(g.bins[1].id, "32x32");
        assert_eq!(g.bins[1].hits, 5);
    }

    #[test]
    fn merge_three_runs_sums_hits_and_keeps_max_goal() {
        let a = write_tmp(
            "a.jsonl",
            r#"{"group":"gemv_lane_sel","bin":"L0","hits":3,"goal":10}"#,
        );
        let b = write_tmp(
            "b.jsonl",
            r#"{"group":"gemv_lane_sel","bin":"L0","hits":4,"goal":12}"#,
        );
        let c = write_tmp(
            "c.jsonl",
            r#"{"group":"gemv_lane_sel","bin":"L0","hits":1}"#,
        ); // no goal field
        let merged = merge_jsonl(&[a.as_path(), b.as_path(), c.as_path()]).unwrap();
        assert_eq!(merged.groups.len(), 1);
        let bin = &merged.groups[0].bins[0];
        assert_eq!(bin.hits, 8, "3+4+1 summed across runs");
        assert_eq!(bin.goal, 12, "max goal across runs");
    }

    #[test]
    fn merge_cross_tuples_accumulate() {
        let p = write_tmp(
            "cross.jsonl",
            concat!(
                r#"{"cross":["gemm_k_stride","mem_hp_backpressure"],"a_bin":"4","b_bin":"hi","hits":3,"goal":10}"#,
                "\n",
                r#"{"cross":["gemm_k_stride","mem_hp_backpressure"],"a_bin":"4","b_bin":"hi","hits":2,"goal":10}"#,
                "\n",
                r#"{"cross":["gemm_k_stride","mem_hp_backpressure"],"a_bin":"8","b_bin":"lo","hits":1,"goal":6}"#,
                "\n",
            ),
        );
        let merged = merge_jsonl(&[p.as_path()]).unwrap();
        assert_eq!(merged.crosses.len(), 2);
        let a = &merged.crosses[0];
        assert_eq!(a.a_bin, "4");
        assert_eq!(a.b_bin, "hi");
        assert_eq!(a.hits, 5);
        assert_eq!(a.goal, 10);
    }

    #[test]
    fn merge_blank_and_comment_lines_are_ignored() {
        let p = write_tmp(
            "commented.jsonl",
            concat!(
                "# comment line\n",
                "\n",
                r#"{"group":"sfu_op_kind","bin":"exp","hits":7,"goal":8}"#,
                "\n",
            ),
        );
        let merged = merge_jsonl(&[p.as_path()]).unwrap();
        assert_eq!(merged.groups.len(), 1);
        assert_eq!(merged.groups[0].bins[0].hits, 7);
    }

    #[test]
    fn merge_bad_json_returns_error_with_path_and_line() {
        let p = write_tmp("bad.jsonl", "{not json}\n");
        let err = merge_jsonl(&[p.as_path()]).unwrap_err();
        match err {
            CoverageError::JsonError { line, .. } => assert_eq!(line, 1),
            other => panic!("unexpected error kind: {other:?}"),
        }
    }

    /// Multiple distinct groups from one file must each appear in the
    /// merged output, sorted by group name (BTreeMap ordering).
    #[test]
    fn merge_multiple_groups() {
        let p = write_tmp(
            "multi_group.jsonl",
            concat!(
                r#"{"group":"gemm_tile_shape","bin":"32x32","hits":3,"goal":10}"#,
                "\n",
                r#"{"group":"sfu_op_kind","bin":"exp","hits":7,"goal":8}"#,
                "\n",
                r#"{"group":"dma_burst_len","bin":"16","hits":2,"goal":4}"#,
                "\n",
            ),
        );
        let merged = merge_jsonl(&[p.as_path()]).unwrap();
        assert_eq!(merged.groups.len(), 3);
        // BTreeMap sorts lexically: dma < gemm < sfu
        assert_eq!(merged.groups[0].name, "dma_burst_len");
        assert_eq!(merged.groups[1].name, "gemm_tile_shape");
        assert_eq!(merged.groups[2].name, "sfu_op_kind");
    }

    /// Cross tuples from different group pairs must remain distinct
    /// in the merged output.
    #[test]
    fn merge_cross_product_distinct_pairs() {
        let p = write_tmp(
            "cross_pairs.jsonl",
            concat!(
                r#"{"cross":["g1","g2"],"a_bin":"a","b_bin":"b","hits":1,"goal":5}"#,
                "\n",
                r#"{"cross":["g3","g4"],"a_bin":"x","b_bin":"y","hits":2,"goal":6}"#,
                "\n",
            ),
        );
        let merged = merge_jsonl(&[p.as_path()]).unwrap();
        assert_eq!(merged.crosses.len(), 2);
        assert_eq!(merged.crosses[0].a_group, "g1");
        assert_eq!(merged.crosses[1].a_group, "g3");
    }

    /// Overlapping bins from two separate files must sum hits and take
    /// the maximum goal — the UCIS merge semantics contract.
    #[test]
    fn merge_overlapping_bins_from_separate_files() {
        let f1 = write_tmp(
            "overlap1.jsonl",
            r#"{"group":"tile","bin":"8x8","hits":5,"goal":10}"#,
        );
        let f2 = write_tmp(
            "overlap2.jsonl",
            r#"{"group":"tile","bin":"8x8","hits":3,"goal":15}"#,
        );
        let merged = merge_jsonl(&[f1.as_path(), f2.as_path()]).unwrap();
        assert_eq!(merged.groups.len(), 1);
        let bin = &merged.groups[0].bins[0];
        assert_eq!(bin.hits, 8, "5 + 3 = 8 across files");
        assert_eq!(bin.goal, 15, "max(10, 15) = 15");
    }

    /// A missing file path must return CoverageError::IoError with the
    /// offending path.
    #[test]
    fn merge_missing_file_returns_io_error() {
        let bad = std::path::Path::new("/tmp/pccx_cov_does_not_exist_42.jsonl");
        let err = merge_jsonl(&[bad]).unwrap_err();
        match err {
            CoverageError::IoError { path, .. } => {
                assert!(
                    path.contains("does_not_exist"),
                    "error must reference the missing path"
                );
            }
            other => panic!("expected IoError, got: {other:?}"),
        }
    }

    /// Records that match neither the bin shape (group + bin) nor the
    /// cross shape (cross array) are silently dropped per the schema's
    /// "reserved for future extensions" rule.
    #[test]
    fn merge_reserved_shape_records_are_dropped() {
        let p = write_tmp(
            "reserved.jsonl",
            concat!(
                r#"{"hits":99}"#,
                "\n",
                r#"{"group":"g","hits":5}"#,
                "\n",
                r#"{"group":"real","bin":"b","hits":1}"#,
                "\n",
            ),
        );
        let merged = merge_jsonl(&[p.as_path()]).unwrap();
        // Only the last line has both group and bin — others are silently dropped.
        assert_eq!(merged.groups.len(), 1);
        assert_eq!(merged.groups[0].bins[0].hits, 1);
        assert!(merged.crosses.is_empty());
    }

    /// Goal field is optional. When absent from all records for a bin,
    /// the merged goal must be 0.
    #[test]
    fn merge_absent_goal_defaults_to_zero() {
        let p = write_tmp("no_goal.jsonl", r#"{"group":"g","bin":"b","hits":7}"#);
        let merged = merge_jsonl(&[p.as_path()]).unwrap();
        assert_eq!(merged.groups[0].bins[0].goal, 0);
    }
}
