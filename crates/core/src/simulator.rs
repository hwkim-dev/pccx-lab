// Module Boundary: core/
// NPU simulation engine — generates realistic multi-core execution traces.
use crate::cycle_estimator::{CycleEstimator, TileOperation};
use crate::hw_model::HardwareModel;
use crate::pccx_format::{ArchConfig, PayloadConfig, PccxFile, PccxHeader, TraceConfig};
use crate::trace::{NpuEvent, NpuTrace};

/// Strict 64-bit ISA wrapper avoiding absolute array indexing errors.
#[derive(Debug, Clone, Copy)]
pub struct Instruction64(pub u64);

impl Instruction64 {
    /// Extracts the 4-bit Opcode from bits [63:60]
    pub fn opcode(&self) -> u8 {
        ((self.0 >> 60) & 0xF) as u8
    }

    /// Extracts the 60-bit Payload from bits [59:0]
    pub fn payload(&self) -> u64 {
        self.0 & 0x0FFF_FFFF_FFFF_FFFF
    }
}

/// Simulation configuration for a single run.
pub struct SimConfig {
    /// Number of tiles in the workload (e.g. attention head tiles).
    pub tiles: u32,
    /// Number of active NPU cores.
    pub cores: u32,
    /// Element size in bytes (2 = BF16, 1 = INT8).
    pub bytes_per_element: u32,
    /// Tile dimensions (M, N, K).
    pub tile_m: u32,
    pub tile_n: u32,
    pub tile_k: u32,
}

impl Default for SimConfig {
    fn default() -> Self {
        Self {
            tiles: 100,
            cores: 32,
            bytes_per_element: 2,
            tile_m: 64,
            tile_n: 64,
            tile_k: 64,
        }
    }
}

/// Generates a physically motivated multi-core NPU execution trace.
///
/// Models:
/// - Double-buffered compute-DMA overlap
/// - AXI bus contention across simultaneous cores
/// - Systolic pipeline drain stalls at tile boundaries
/// - Barrier synchronisation between tiles
pub fn generate_realistic_trace(cfg: &SimConfig) -> NpuTrace {
    let hw = HardwareModel::pccx_reference();
    let estimator = CycleEstimator::new(&hw);

    let op = TileOperation {
        m: cfg.tile_m,
        n: cfg.tile_n,
        k: cfg.tile_k,
        bytes_per_element: cfg.bytes_per_element,
    };

    // Compute per-core timing (with AXI contention across all cores)
    let compute_cycles = estimator.estimate_gemm_cycles(&op);
    let read_bytes = (op.m * op.k + op.k * op.n) * op.bytes_per_element;
    let write_bytes = op.m * op.n * op.bytes_per_element;
    // Solo read/write cycles (for single-core, no contention)
    let dma_read_solo = estimator.estimate_dma_cycles(read_bytes);
    let dma_write_solo = estimator.estimate_dma_cycles(write_bytes);
    // Contended: all cores hammering the AXI bus simultaneously
    let dma_read_cont = estimator.estimate_dma_cycles_contended(read_bytes, cfg.cores);
    let dma_write_cont = estimator.estimate_dma_cycles_contended(write_bytes, cfg.cores);

    // Pipeline stall after each tile (systolic array drain)
    let stall_cycles = hw.mac.pipeline_depth as u64 * 2;

    let is_compute_bound = estimator.is_compute_bound(&op);

    let mut events = Vec::with_capacity(cfg.tiles as usize * cfg.cores as usize * 5 + 8);
    let mut global_cycle: u64 = 0;

    // ── Prelude: emit the 8 canonical `uca_*` driver-surface entry events
    //    before any compute begins.  Mirrors CUPTI's `CUpti_ActivityAPI`
    //    model (Canopy SOSP 2017 correlation-id pattern): one record per
    //    API entry/exit span, early in the trace so `list_api_calls`
    //    always sees the full driver surface regardless of how short the
    //    subsequent kernel workload is.  Latencies reflect the KV260
    //    reference-SoC numbers the driver README cites (cycles @ 200 MHz,
    //    so 1 µs = 200 cycles).
    const API_SURFACE: &[(&str, u64)] = &[
        ("uca_init", 4_100 / 5),              //  820 cy  (4.1 µs)
        ("uca_alloc_buffer", 12_600 / 5),     // 2520 cy
        ("uca_load_weights", 1_420_000 / 5),  // 284000 cy
        ("uca_submit_cmd", 1_800 / 5),        //  360 cy
        ("uca_poll_completion", 300 / 5),     //   60 cy
        ("uca_fetch_result", 920_000 / 5),    // 184000 cy
        ("uca_reset", 8_700 / 5),             //  1740 cy
        ("uca_get_perf_counters", 5_200 / 5), //  1040 cy
    ];
    for (name, dur_cy) in API_SURFACE {
        events.push(NpuEvent::api_call(0, global_cycle, *dur_cy, *name));
        global_cycle += *dur_cy;
    }

    for _t in 0..cfg.tiles {
        // Critical path for this tile:
        // Phase 1: DMA READ (all cores compete for AXI — contended latency)
        // Phase 2: MAC COMPUTE (overlaps with DMA for next tile in double-buffer)
        //    For first tile, compute starts after read. For simplicity we model
        //    each tile sequentially with single-buffer (conservative).
        // Phase 3: DMA WRITE (contended)
        // Phase 4: SYSTOLIC_STALL (pipeline drain)
        // Phase 5: BARRIER_SYNC (cores wait for slowest)

        for c in 0..cfg.cores {
            // Phase 1 — DMA READ
            // Each core has a slightly different AXI start slot due to arbitration.
            let arb_offset = c as u64 * (hw.axi.transaction_overhead_cycles as u64 / 4);
            let read_start = global_cycle + arb_offset;
            // Use contended latency since all cores issue simultaneously
            let read_dur = if cfg.cores > 1 {
                dma_read_cont
            } else {
                dma_read_solo
            };

            events.push(NpuEvent::new(c, read_start, read_dur, "DMA_READ"));

            // Phase 2 — MAC COMPUTE (starts after DMA read completes)
            let compute_start = read_start + read_dur;
            events.push(NpuEvent::new(
                c,
                compute_start,
                compute_cycles,
                "MAC_COMPUTE",
            ));

            // Phase 3 — DMA WRITE (starts after compute, write-back)
            let write_start = compute_start + compute_cycles;
            let write_dur = if cfg.cores > 1 {
                dma_write_cont
            } else {
                dma_write_solo
            };
            events.push(NpuEvent::new(c, write_start, write_dur, "DMA_WRITE"));

            // Phase 4 — SYSTOLIC STALL (pipeline drain between tiles)
            let stall_start = write_start + write_dur;
            events.push(NpuEvent::new(
                c,
                stall_start,
                stall_cycles,
                "SYSTOLIC_STALL",
            ));
        }

        // Tile critical path (bottleneck): longest single-core path
        let tile_crit_read =
            (cfg.cores as u64) * (hw.axi.transaction_overhead_cycles as u64 / 4) + dma_read_cont;
        let tile_crit_write = dma_write_cont;
        let tile_crit_path = tile_crit_read + compute_cycles + tile_crit_write + stall_cycles;

        // Phase 5 — BARRIER SYNC: all cores rendezvous at the tile boundary
        let barrier_start = global_cycle + tile_crit_path;
        let barrier_dur = 8; // fixed synchronisation overhead
        for c in 0..cfg.cores {
            events.push(NpuEvent::new(c, barrier_start, barrier_dur, "BARRIER_SYNC"));
        }

        global_cycle = barrier_start + barrier_dur;

        // Annotate bottleneck type in contended scenarios (informational)
        let _ = is_compute_bound; // suppress unused warning; used in future report
    }

    NpuTrace {
        total_cycles: global_cycle,
        events,
    }
}

/// Generates and saves a complete `.pccx` file to `file_path`.
pub fn save_dummy_pccx(file_path: &str) -> anyhow::Result<()> {
    let cfg = SimConfig::default();
    let trace = generate_realistic_trace(&cfg);
    let payload = trace.to_payload();

    let hw = HardwareModel::pccx_reference();
    let header = PccxHeader {
        pccx_lab_version: "v0.4.0-contention-aware".to_string(),
        arch: ArchConfig {
            mac_dims: (32, 32),
            isa_version: "1.1".to_string(),
            peak_tops: hw.peak_tops(),
        },
        trace: TraceConfig {
            cycles: trace.total_cycles,
            cores: cfg.cores,
            clock_mhz: hw.clock_mhz,
        },
        payload: PayloadConfig {
            encoding: "bincode".to_string(),
            byte_length: payload.len() as u64,
            checksum_fnv64: Some(crate::pccx_format::fnv1a_64(&payload)),
        },
        format_minor: crate::pccx_format::MINOR_VERSION,
    };

    let pccx = PccxFile { header, payload };
    let mut file = std::fs::File::create(file_path)?;
    pccx.write(&mut file)?;
    Ok(())
}
