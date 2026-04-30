// Module Boundary: core/
// Cycle estimation engine for the pccx NPU simulator.
use crate::hw_model::HardwareModel;

/// Describes a single tiled GEMM (General Matrix Multiply) operation.
pub struct TileOperation {
    /// Rows of matrix A (and output C).
    pub m: u32,
    /// Columns of matrix B (and output C).
    pub n: u32,
    /// Inner (shared) dimension.
    pub k: u32,
    /// Element size in bytes (e.g. 2 for BF16/FP16, 1 for INT8, 4 for FP32).
    pub bytes_per_element: u32,
}

impl Default for TileOperation {
    fn default() -> Self {
        Self {
            m: 64,
            n: 64,
            k: 64,
            bytes_per_element: 2,
        }
    }
}

/// Describes a Transformer Attention operation (MQA/GQA support).
pub struct AttentionOperation {
    pub seq_len_q: u32,
    pub seq_len_kv: u32,
    pub head_dim: u32,
    pub num_queries: u32,
    pub kv_groups: u32,
    pub bytes_per_element: u32,
}

impl Default for AttentionOperation {
    fn default() -> Self {
        Self {
            seq_len_q: 1,
            seq_len_kv: 1024,
            head_dim: 128,
            num_queries: 32,
            kv_groups: 4,
            bytes_per_element: 2,
        }
    }
}

/// Stateless cycle estimator bound to a [`HardwareModel`].
pub struct CycleEstimator<'a> {
    pub hw: &'a HardwareModel,
}

impl<'a> CycleEstimator<'a> {
    pub fn new(hw: &'a HardwareModel) -> Self {
        Self { hw }
    }

    // ─── GEMM Estimation ────────────────────────────────────────────────────

    /// Estimates the wall-clock cycles for a single tiled GEMM on **one** core.
    ///
    /// Uses the roofline model: the bottleneck is the maximum of compute, BRAM
    /// read, and BRAM write bandwidth, plus pipeline fill latency.
    pub fn estimate_gemm_cycles(&self, op: &TileOperation) -> u64 {
        let bpe = op.bytes_per_element as u64;

        // Computation: every output element requires `k` MAC ops.
        let total_mac_ops = op.m as u64 * op.n as u64 * op.k as u64;
        let macs_per_cycle = self.hw.mac.rows as u64 * self.hw.mac.cols as u64;
        let compute_cycles = (total_mac_ops + macs_per_cycle - 1) / macs_per_cycle;

        // Memory: read A (m×k) + B (k×n), write C (m×n)
        let bytes_read = (op.m as u64 * op.k as u64 + op.k as u64 * op.n as u64) * bpe;
        let bytes_write = op.m as u64 * op.n as u64 * bpe;

        let bram_read_bw =
            self.hw.bram.read_bandwidth_bytes_per_cycle as u64 * self.hw.bram.read_ports as u64;
        let bram_write_bw = self.hw.bram.write_bandwidth_bytes_per_cycle as u64;

        let read_cycles = (bytes_read + bram_read_bw - 1) / bram_read_bw;
        let write_cycles = (bytes_write + bram_write_bw - 1) / bram_write_bw;

        // Roofline: bound by the slowest resource (assuming perfect overlap).
        let bound_cycles = compute_cycles.max(read_cycles).max(write_cycles);

        // Pipeline fill / drain latency
        bound_cycles + self.hw.mac.pipeline_depth as u64
    }

    /// Estimates cycles for a Transformer Attention block (Q @ K^T, then @ V)
    /// modeling MQA/GQA memory sharing efficiency.
    pub fn estimate_attention_cycles(&self, op: &AttentionOperation) -> u64 {
        let bpe = op.bytes_per_element as u64;

        // Compute MAC ops: (Q @ K) + (Attn @ V)
        // Q: [seq_len_q, num_queries, head_dim]
        // K, V: [seq_len_kv, kv_groups, head_dim]
        let ops_qk =
            op.seq_len_q as u64 * op.seq_len_kv as u64 * op.head_dim as u64 * op.num_queries as u64;
        let ops_av =
            op.seq_len_q as u64 * op.head_dim as u64 * op.seq_len_kv as u64 * op.num_queries as u64;
        let total_mac_ops = ops_qk + ops_av;

        let macs_per_cycle = self.hw.mac.rows as u64 * self.hw.mac.cols as u64;
        let compute_cycles = (total_mac_ops + macs_per_cycle - 1) / macs_per_cycle;

        // Memory: Read Q, K, V. Write O.
        // Importantly, K and V are shared across (num_queries / kv_groups) heads!
        let bytes_q = op.seq_len_q as u64 * op.num_queries as u64 * op.head_dim as u64 * bpe;
        let bytes_kv = 2 * (op.seq_len_kv as u64 * op.kv_groups as u64 * op.head_dim as u64 * bpe);
        let bytes_o = op.seq_len_q as u64 * op.num_queries as u64 * op.head_dim as u64 * bpe;

        let bram_read_bw =
            self.hw.bram.read_bandwidth_bytes_per_cycle as u64 * self.hw.bram.read_ports as u64;
        let bram_write_bw = self.hw.bram.write_bandwidth_bytes_per_cycle as u64;

        let read_cycles = (bytes_q + bytes_kv + bram_read_bw - 1) / bram_read_bw;
        let write_cycles = (bytes_o + bram_write_bw - 1) / bram_write_bw;

        let bound_cycles = compute_cycles.max(read_cycles).max(write_cycles);
        bound_cycles + self.hw.mac.pipeline_depth as u64
    }

    // ─── DMA (AXI bus) Estimation ───────────────────────────────────────────

    /// Estimates AXI DMA transfer cycles for `bytes` over a **single** port.
    ///
    /// Models burst packetisation and the fixed per-transaction overhead
    /// stored in [`AxiBusConfig::transaction_overhead_cycles`].
    pub fn estimate_dma_cycles(&self, bytes: u32) -> u64 {
        if bytes == 0 {
            return 0;
        }
        let bw = self.hw.axi.bandwidth_bytes_per_cycle as u64;
        let burst = self.hw.axi.burst_length as u64;
        let overhead = self.hw.axi.transaction_overhead_cycles as u64;

        // Number of AXI bursts required
        let burst_bytes = bw * burst;
        let num_bursts = (bytes as u64 + burst_bytes - 1) / burst_bytes;
        let transfer_cycles = (bytes as u64 + bw - 1) / bw;

        // Each burst incurs one address-phase overhead slot
        transfer_cycles + num_bursts * overhead
    }

    /// Estimates DMA cycles when `active_cores` cores all drive the AXI bus
    /// simultaneously using an M/D/1 Stochastic Queuing Delay model.
    pub fn estimate_dma_cycles_contended(&self, bytes: u32, active_cores: u32) -> u64 {
        if active_cores == 0 || bytes == 0 {
            return 0;
        }

        let bw = self.hw.axi.bandwidth_bytes_per_cycle as u64;
        let burst = self.hw.axi.burst_length as u64;
        let overhead = self.hw.axi.transaction_overhead_cycles as u64;

        let burst_bytes = bw * burst;
        let num_bursts = (bytes as u64 + burst_bytes - 1) / burst_bytes;
        let ideal_transfer_cycles = (bytes as u64 + bw - 1) / bw;
        let ideal_total = ideal_transfer_cycles + num_bursts * overhead;

        // M/D/1 Model Setup
        // Traffic intensity rho = lambda / mu.
        // We approximate rho based on active_cores contending for the single AXI resource.
        // If active_cores == 1, rho is 0. As active_cores approaches max_cores, rho approaches 1.0.
        // Safety: Cap rho at 0.999 to avoid infinite wait time panic.
        let max_cores = self.hw.num_cores as f64;
        let rho_base = (active_cores as f64 - 1.0) / max_cores.max(1.0);
        let rho = rho_base.clamp(0.0, 0.999);

        // M/D/1 wait time factor W = rho / (2.0 * (1.0 - rho))
        // The delay multiplies the ideal duration by the congestion factor.
        let m_d_1_factor = rho / (2.0 * (1.0 - rho));
        let queuing_delay = (ideal_total as f64 * m_d_1_factor).ceil() as u64;

        ideal_total + queuing_delay
    }

    // ─── Utilisation Metrics ─────────────────────────────────────────────────

    /// Compute arithmetic intensity (MAC ops per byte transferred via BRAM).
    pub fn arithmetic_intensity(&self, op: &TileOperation) -> f64 {
        let bpe = op.bytes_per_element as f64;
        let mac_ops = op.m as f64 * op.n as f64 * op.k as f64;
        let bytes_io = (op.m as f64 * op.k as f64 + op.k as f64 * op.n as f64) * bpe;
        if bytes_io == 0.0 {
            0.0
        } else {
            mac_ops / bytes_io
        }
    }

    /// Returns whether a given tile operation is compute-bound (true) or
    /// memory-bandwidth-bound (false) on this hardware.
    pub fn is_compute_bound(&self, op: &TileOperation) -> bool {
        let peak_mac_intensity = {
            let macs_per_cycle = self.hw.mac.rows as f64 * self.hw.mac.cols as f64;
            let bram_bw =
                self.hw.bram.read_bandwidth_bytes_per_cycle as f64 * self.hw.bram.read_ports as f64;
            macs_per_cycle / bram_bw
        };
        self.arithmetic_intensity(op) >= peak_mac_intensity
    }
}
