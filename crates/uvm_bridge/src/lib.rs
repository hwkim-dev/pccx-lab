// Module Boundary: uvm_bridge/
// Depends on: core/ (via pccx-core crate)
//
// This module provides C-ABI DPI-C exports for SystemVerilog integration,
// allowing UVM testbenches to drive the pccx cycle estimator directly.
//
// Usage from SystemVerilog:
//   import "DPI-C" function int pccx_estimate_gemm_cycles(
//     input int m, input int n, input int k, input int bpe,
//     output longint cycles
//   );

use pccx_core::cycle_estimator::{CycleEstimator, TileOperation};
use pccx_core::hw_model::HardwareModel;

// ─── Error Codes (return values for DPI-C calls) ──────────────────────────────
const PCCX_OK: i32 = 0;
const PCCX_ERROR: i32 = 1;

// ─── DPI-C Exports ────────────────────────────────────────────────────────────

/// Estimates GEMM cycles for a tile operation.
///
/// # Safety
/// `out_cycles` must be a valid non-null pointer to a `u64` that the caller
/// owns for the duration of the call. This is guaranteed by the DPI-C ABI.
///
/// Returns PCCX_OK (0) on success, PCCX_ERROR (1) on invalid arguments.
#[no_mangle]
pub unsafe extern "C" fn pccx_estimate_gemm_cycles(
    m: u32,
    n: u32,
    k: u32,
    bpe: u32, // bytes per element: 1 (INT8), 2 (BF16/FP16), 4 (FP32)
    out_cycles: *mut u64,
) -> i32 {
    if out_cycles.is_null() || m == 0 || n == 0 || k == 0 || bpe == 0 {
        return PCCX_ERROR;
    }
    let hw = HardwareModel::pccx_reference();
    let est = CycleEstimator::new(&hw);
    let op = TileOperation {
        m,
        n,
        k,
        bytes_per_element: bpe,
    };
    *out_cycles = est.estimate_gemm_cycles(&op);
    PCCX_OK
}

/// Estimates AXI DMA transfer cycles for a given byte count.
///
/// # Safety
/// `out_cycles` must be a valid non-null pointer.
#[no_mangle]
pub unsafe extern "C" fn pccx_estimate_dma_cycles(bytes: u32, out_cycles: *mut u64) -> i32 {
    if out_cycles.is_null() {
        return PCCX_ERROR;
    }
    let hw = HardwareModel::pccx_reference();
    let est = CycleEstimator::new(&hw);
    *out_cycles = est.estimate_dma_cycles(bytes);
    PCCX_OK
}

/// Estimates AXI DMA cycles under multi-core bus contention.
///
/// # Safety
/// `out_cycles` must be a valid non-null pointer.
#[no_mangle]
pub unsafe extern "C" fn pccx_estimate_dma_cycles_contended(
    bytes: u32,
    active_cores: u32,
    out_cycles: *mut u64,
) -> i32 {
    if out_cycles.is_null() || active_cores == 0 {
        return PCCX_ERROR;
    }
    let hw = HardwareModel::pccx_reference();
    let est = CycleEstimator::new(&hw);
    *out_cycles = est.estimate_dma_cycles_contended(bytes, active_cores);
    PCCX_OK
}

/// Returns 1 if the given tile operation is compute-bound, 0 if memory-bound,
/// or PCCX_ERROR on invalid arguments.
#[no_mangle]
pub unsafe extern "C" fn pccx_is_compute_bound(m: u32, n: u32, k: u32, bpe: u32) -> i32 {
    if m == 0 || n == 0 || k == 0 || bpe == 0 {
        return PCCX_ERROR;
    }
    let hw = HardwareModel::pccx_reference();
    let est = CycleEstimator::new(&hw);
    let op = TileOperation {
        m,
        n,
        k,
        bytes_per_element: bpe,
    };
    if est.is_compute_bound(&op) {
        1
    } else {
        0
    }
}

/// Returns the peak TOPS of the reference NPU (×100 for integer representation,
/// e.g. 205 = 2.05 TOPS).
#[no_mangle]
pub extern "C" fn pccx_peak_tops_x100() -> u32 {
    let hw = HardwareModel::pccx_reference();
    (hw.peak_tops() * 100.0).round() as u32
}

/// Returns the reference clock frequency in MHz.
#[no_mangle]
pub extern "C" fn pccx_clock_mhz() -> u32 {
    HardwareModel::pccx_reference().clock_mhz
}

// ─── Rust-side convenience wrappers (non-DPI-C) ────────────────────────────────

/// High-level Rust API: returns GEMM cycle estimate without unsafe raw pointers.
pub fn estimate_gemm(m: u32, n: u32, k: u32, bpe: u32) -> u64 {
    let hw = HardwareModel::pccx_reference();
    let est = CycleEstimator::new(&hw);
    est.estimate_gemm_cycles(&TileOperation {
        m,
        n,
        k,
        bytes_per_element: bpe,
    })
}

/// High-level Rust API: returns DMA cycle estimate.
pub fn estimate_dma(bytes: u32, cores: u32) -> u64 {
    let hw = HardwareModel::pccx_reference();
    let est = CycleEstimator::new(&hw);
    if cores > 1 {
        est.estimate_dma_cycles_contended(bytes, cores)
    } else {
        est.estimate_dma_cycles(bytes)
    }
}
