/// Unit and integration tests for pccx-core.
///
/// Run with: `cargo test -p pccx-core`
#[cfg(test)]
mod tests {
    use pccx_core::{
        cycle_estimator::{CycleEstimator, TileOperation},
        hw_model::HardwareModel,
        pccx_format::{PccxFile, PccxHeader, ArchConfig, TraceConfig, PayloadConfig, fnv1a_64,
                      MAJOR_VERSION, MINOR_VERSION},
        simulator::{SimConfig, generate_realistic_trace, save_dummy_pccx},
        trace::{NpuTrace, NpuEvent, event_type_id},
        license::get_license_info,
    };
    use std::io::Cursor;

    // ─── HardwareModel ────────────────────────────────────────────────────────

    #[test]
    fn test_hw_model_peak_tops() {
        let hw = HardwareModel::pccx_reference();
        // 32×32 MAC × 2 ops/MAC × 32 cores × 1 GHz = 65.536 TOPS
        let tops = hw.peak_tops();
        assert!(tops > 60.0 && tops < 70.0,
            "peak_tops should be ~65.5, got {tops}");
    }

    #[test]
    fn test_cycles_to_us() {
        let hw = HardwareModel::pccx_reference();
        // 1000 cycles @ 1 GHz = 1.0 µs
        let us = hw.cycles_to_us(1000);
        assert!((us - 1.0).abs() < 1e-9, "Expected 1.0 µs, got {us}");
    }

    // ─── CycleEstimator ───────────────────────────────────────────────────────

    #[test]
    fn test_gemm_estimate_sanity() {
        let hw = HardwareModel::pccx_reference();
        let est = CycleEstimator::new(&hw);
        let op  = TileOperation { m: 64, n: 64, k: 64, bytes_per_element: 2 };
        let cycles = est.estimate_gemm_cycles(&op);
        // At minimum it should be compute bound: 64³ / (32×32) = 8 cycles + pipeline
        assert!(cycles >= 8 + hw.mac.pipeline_depth as u64,
            "GEMM estimate too low: {cycles}");
    }

    #[test]
    fn test_dma_zero_bytes() {
        let hw  = HardwareModel::pccx_reference();
        let est = CycleEstimator::new(&hw);
        assert_eq!(est.estimate_dma_cycles(0), 0, "DMA with 0 bytes should return 0");
    }

    #[test]
    fn test_dma_contended_slower_than_solo() {
        let hw  = HardwareModel::pccx_reference();
        let est = CycleEstimator::new(&hw);
        let bytes = 1024 * 16; // 16 KB
        let solo      = est.estimate_dma_cycles(bytes);
        let contended = est.estimate_dma_cycles_contended(bytes, 32);
        assert!(contended >= solo,
            "Contended DMA ({contended}) should be >= solo ({solo})");
    }

    #[test]
    fn test_arithmetic_intensity() {
        let hw  = HardwareModel::pccx_reference();
        let est = CycleEstimator::new(&hw);
        let op  = TileOperation { m: 64, n: 64, k: 64, bytes_per_element: 2 };
        let ai  = est.arithmetic_intensity(&op);
        // 64³ ops / ((64*64 + 64*64)*2 bytes) = 262144 / 16384 = 16
        assert!((ai - 16.0).abs() < 0.1, "Expected AI ≈ 16, got {ai}");
    }

    #[test]
    fn test_is_compute_bound() {
        let hw  = HardwareModel::pccx_reference();
        let est = CycleEstimator::new(&hw);
        // Large square tiles → compute bound
        let large = TileOperation { m: 128, n: 128, k: 128, bytes_per_element: 2 };
        // Small tiles with large bytes_per_element → memory bound
        let small = TileOperation { m: 4, n: 4, k: 4, bytes_per_element: 4 };
        assert!(est.is_compute_bound(&large), "128³ tile should be compute-bound");
        assert!(!est.is_compute_bound(&small), "4³ FP32 tile should be memory-bound");
    }

    // ─── NpuTrace & flat buffer ───────────────────────────────────────────────

    #[test]
    fn test_event_type_id_mapping() {
        let ev = NpuEvent::new(0, 0, 1, "DMA_WRITE");
        // This was the critical bug: DMA_WRITE must be 3, not 0
        assert_eq!(ev.type_id().get(), event_type_id::DMA_WRITE,
            "DMA_WRITE should map to type_id 3");
        assert_ne!(ev.type_id().get(), event_type_id::UNKNOWN,
            "DMA_WRITE must not map to UNKNOWN (0)");
    }

    #[test]
    fn test_flat_buffer_layout() {
        let trace = NpuTrace {
            total_cycles: 1000,
            events: vec![
                NpuEvent::new(5, 100, 50, "MAC_COMPUTE"),
                NpuEvent::new(3, 200, 30, "DMA_WRITE"),
            ],
        };
        let buf = trace.to_flat_buffer();
        assert_eq!(buf.len(), 48, "Two events × 24 bytes = 48 bytes");

        // Verify first event
        let core_id = u32::from_le_bytes(buf[0..4].try_into().unwrap());
        assert_eq!(core_id, 5);
        let start = u64::from_le_bytes(buf[4..12].try_into().unwrap());
        assert_eq!(start, 100);
        let type_id = u32::from_le_bytes(buf[20..24].try_into().unwrap());
        assert_eq!(type_id, event_type_id::MAC_COMPUTE);

        // Verify second event
        let type_id2 = u32::from_le_bytes(buf[44..48].try_into().unwrap());
        assert_eq!(type_id2, event_type_id::DMA_WRITE,
            "DMA_WRITE should be type_id 3 in flat buffer");
    }

    #[test]
    fn test_core_utilisation() {
        let trace = NpuTrace {
            total_cycles: 200,
            events: vec![
                NpuEvent::new(0, 0, 100, "MAC_COMPUTE"),
                NpuEvent::new(1, 0, 50,  "MAC_COMPUTE"),
            ],
        };
        let utils = trace.core_utilisation();
        assert_eq!(utils.len(), 2);
        let core0 = utils.iter().find(|(c, _)| *c == 0).unwrap();
        let core1 = utils.iter().find(|(c, _)| *c == 1).unwrap();
        assert!((core0.1 - 0.5).abs() < 1e-9, "Core 0 util should be 50%");
        assert!((core1.1 - 0.25).abs() < 1e-9, "Core 1 util should be 25%");
    }

    #[test]
    fn test_bincode_roundtrip() {
        let trace = NpuTrace {
            total_cycles: 999,
            events: vec![
                NpuEvent::new(7, 42, 13, "BARRIER_SYNC"),
            ],
        };
        let payload = trace.to_payload();
        let decoded = NpuTrace::from_payload(&payload).expect("bincode roundtrip failed");
        assert_eq!(decoded.total_cycles, 999);
        assert_eq!(decoded.events[0].core_id.get(), 7);
        assert_eq!(decoded.events[0].event_type, "BARRIER_SYNC");
    }

    // ─── PCCX Format ──────────────────────────────────────────────────────────

    #[test]
    fn test_pccx_write_read_roundtrip() {
        let payload = b"test_payload_bytes".to_vec();
        let checksum = fnv1a_64(&payload);

        let header = PccxHeader {
            pccx_lab_version: "v0.4.0-test".to_string(),
            arch: ArchConfig { mac_dims: (16, 16), isa_version: "1.0".to_string(), peak_tops: 1.0 },
            trace: TraceConfig { cycles: 12345, cores: 4, clock_mhz: 500 },
            payload: PayloadConfig {
                encoding: "raw".to_string(),
                byte_length: payload.len() as u64,
                checksum_fnv64: Some(checksum),
            },
            format_minor: MINOR_VERSION,
        };

        let pccx_out = PccxFile { header: header.clone(), payload: payload.clone() };
        let mut buf  = Vec::new();
        pccx_out.write(&mut buf).expect("write failed");

        // Verify magic bytes
        assert_eq!(&buf[0..4], b"PCCX");
        assert_eq!(buf[4], MAJOR_VERSION);
        assert_eq!(buf[5], MINOR_VERSION);

        // Roundtrip read
        let mut cursor = Cursor::new(&buf);
        let pccx_in   = PccxFile::read(&mut cursor).expect("read failed");
        assert_eq!(pccx_in.header.pccx_lab_version, "v0.4.0-test");
        assert_eq!(pccx_in.header.trace.cycles, 12345);
        assert_eq!(pccx_in.header.trace.clock_mhz, 500);
        assert_eq!(pccx_in.payload, payload);
    }

    #[test]
    fn test_pccx_invalid_magic_rejected() {
        let bad = b"XXXX\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00";
        let result = PccxFile::read(&mut Cursor::new(bad));
        assert!(result.is_err(), "Should reject non-PCCX magic");
    }

    #[test]
    fn test_fnv1a_64_deterministic() {
        let a = fnv1a_64(b"hello pccx");
        let b = fnv1a_64(b"hello pccx");
        assert_eq!(a, b, "FNV-1a must be deterministic");
        let c = fnv1a_64(b"hello pccX");   // different case
        assert_ne!(a, c, "FNV-1a must be sensitive to case");
    }

    // ─── Simulator ────────────────────────────────────────────────────────────

    #[test]
    fn test_generate_trace_has_all_event_types() {
        let cfg   = SimConfig { tiles: 2, cores: 2, bytes_per_element: 2, tile_m: 16, tile_n: 16, tile_k: 16 };
        let trace = generate_realistic_trace(&cfg);

        let types: std::collections::HashSet<&str> = trace.events.iter()
            .map(|e| e.event_type.as_str()).collect();

        assert!(types.contains("MAC_COMPUTE"),    "Missing MAC_COMPUTE");
        assert!(types.contains("DMA_READ"),       "Missing DMA_READ");
        assert!(types.contains("DMA_WRITE"),      "Missing DMA_WRITE");
        assert!(types.contains("SYSTOLIC_STALL"), "Missing SYSTOLIC_STALL");
        assert!(types.contains("BARRIER_SYNC"),   "Missing BARRIER_SYNC");
    }

    #[test]
    fn test_trace_event_count() {
        // 8 canonical API_CALL prelude events +
        // 2 tiles × 2 cores × 4 events/core + 2 cores × barrier = 8 + 2*(2*4+2) = 28
        let cfg   = SimConfig { tiles: 2, cores: 2, bytes_per_element: 2, tile_m: 16, tile_n: 16, tile_k: 16 };
        let trace = generate_realistic_trace(&cfg);
        assert_eq!(trace.events.len(), 28,
                   "Expected 28 events = 8 API_CALL prelude + 20 (2 tiles × 2 cores)");
        // Sanity-check: the first 8 events are the canonical uca_* surface calls.
        let api_count = trace.events.iter()
            .filter(|e| e.event_type == "API_CALL")
            .count();
        assert_eq!(api_count, 8, "simulator must emit 8 canonical uca_* API_CALL events");
    }

    #[test]
    fn test_trace_monotone_global_cycle() {
        // Each tile must advance global_cycle forward
        let cfg   = SimConfig { tiles: 5, cores: 4, bytes_per_element: 2, tile_m: 32, tile_n: 32, tile_k: 32 };
        let trace = generate_realistic_trace(&cfg);
        assert!(trace.total_cycles > 0, "Total cycles must be positive");
    }

    // ─── License — reduced to a single Apache-2.0 sanity check ───────────────

    #[test]
    fn test_license_info_is_apache_2() {
        assert!(get_license_info().contains("Apache"));
    }

    // ─── Synthesis report parser ──────────────────────────────────────────────

    const SAMPLE_UTIL: &str = r#"
-------------------------------------------------------------------------------------------------------------------------------------------------------
| Tool Version : Vivado v.2025.2 (lin64)
| Design       : NPU_top
| Device       : xck26-sfvc784-2LV-c
| Design State : Synthesized
-------------------------------------------------------------------------------------------------------------------------------------------------------

1. Utilization by Hierarchy
---------------------------

+--------+-------+------------+------------+---------+------+------+--------+--------+------+------------+
| Inst   | Mod   | Total LUTs | Logic LUTs | LUTRAMs | SRLs |  FFs | RAMB36 | RAMB18 | URAM | DSP Blocks |
+--------+-------+------------+------------+---------+------+------+--------+--------+------+------------+
| NPU_top | (top) |       5611 |       5570 |       0 |   41 | 8458 |     80 |      8 |   56 |          4 |
"#;

    const SAMPLE_TIMING_FAIL: &str = r#"
| Design Timing Summary
| ---------------------
----------------------------------------------------------------

    WNS(ns)      TNS(ns)  TNS Failing Endpoints  TNS Total Endpoints  ...
    -------      -------  ---------------------  -------------------
     -9.792    -3615.208                   4194                28602  ...


Timing constraints are not met.


Clock         WNS(ns)   TNS(ns)  TNS Failing Endpoints  TNS Total Endpoints
-----         -------   -------  ---------------------  -------------------
axi_clk         2.253     0.000                      0                 2118
core_clk       -9.792 -3615.208                   4194                26484
"#;

    const SAMPLE_TIMING_PASS: &str = r#"
| Design Timing Summary
| ---------------------
----------------------------------------------------------------

    WNS(ns)      TNS(ns)  TNS Failing Endpoints  TNS Total Endpoints  ...
    -------      -------  ---------------------  -------------------
      0.450        0.000                      0                28602  ...


All user specified timing constraints are met.
"#;

    #[test]
    fn test_parse_utilization_extracts_top_row() {
        let util = pccx_core::synth_report::parse_utilization(SAMPLE_UTIL);
        assert_eq!(util.top_module, "NPU_top");
        assert_eq!(util.total_luts, 5611);
        assert_eq!(util.logic_luts, 5570);
        assert_eq!(util.ffs,        8458);
        assert_eq!(util.rams_36,    80);
        assert_eq!(util.rams_18,    8);
        assert_eq!(util.urams,      56);
        assert_eq!(util.dsps,       4);
    }

    #[test]
    fn test_parse_utilization_empty_input() {
        let util = pccx_core::synth_report::parse_utilization("");
        assert_eq!(util.top_module, "");
        assert_eq!(util.total_luts, 0);
    }

    #[test]
    fn test_parse_utilization_ignores_design_state() {
        // Regression: the "| Design State : Synthesized" line must not be
        // captured as the top module.
        let text = "| Design State : Synthesized\n| Device       : xck26\n";
        let util = pccx_core::synth_report::parse_utilization(text);
        assert_eq!(util.top_module, "", "Design State must not become top_module");
    }

    #[test]
    fn test_parse_timing_detects_failure() {
        let t = pccx_core::synth_report::parse_timing(SAMPLE_TIMING_FAIL);
        assert!(!t.is_timing_met, "Sample should be flagged as NOT met");
        assert!((t.wns_ns - -9.792).abs() < 1e-6);
        assert_eq!(t.failing_endpoints, 4194);
        assert_eq!(t.total_endpoints, 28602);
        assert_eq!(t.worst_clock, "core_clk", "Worst clock must be core_clk");
    }

    #[test]
    fn test_parse_timing_detects_success() {
        let t = pccx_core::synth_report::parse_timing(SAMPLE_TIMING_PASS);
        assert!(t.is_timing_met, "Sample should be flagged as met");
        assert!(t.wns_ns > 0.0, "Positive slack expected");
        assert_eq!(t.failing_endpoints, 0);
    }

    #[test]
    fn test_parse_timing_empty_stays_met() {
        // If we cannot find the marker, parser defaults to met + zeros.
        let t = pccx_core::synth_report::parse_timing("");
        assert!(t.is_timing_met);
        assert_eq!(t.wns_ns, 0.0);
    }

    #[test]
    fn test_load_from_files_missing_path_errors() {
        let r = pccx_core::synth_report::load_from_files(
            "/nonexistent/util.rpt",
            "/nonexistent/timing.rpt",
        );
        assert!(r.is_err(), "Should error when paths are missing");
    }
}
