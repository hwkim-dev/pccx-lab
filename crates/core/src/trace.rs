// Module Boundary: core/
// NPU Trace data structures and serialization utilities.
use serde::{Deserialize, Serialize};
use crate::typed::{CycleCount, CoreId, EventTypeId};

/// Canonical event type IDs used in the flat binary buffer.
/// These MUST be kept in sync with the JS DataView parsing logic.
pub mod event_type_id {
    pub const UNKNOWN: u32 = 0;
    pub const MAC_COMPUTE: u32 = 1;
    pub const DMA_READ: u32 = 2;
    pub const DMA_WRITE: u32 = 3;
    pub const SYSTOLIC_STALL: u32 = 4;
    pub const BARRIER_SYNC: u32 = 5;
    /// Driver-surface `uca_*` API boundary crossing. Mirrors CUPTI's
    /// `CUpti_ActivityAPI` record shape: one event per entry/exit pair,
    /// with `api_name` carrying the qualified call identifier. See
    /// research_findings.md Gap 4 (CUPTI / ROCTracer / Canopy SOSP 2017).
    pub const API_CALL: u32 = 6;
}

/// Canonical event-type names, indexed by `event_type_id::*`. Exposed
/// so UI parsers and writers share one source of truth (keeps
/// `FlameGraph.tsx:EVENT_TYPE_NAMES` in lock-step with Rust).
pub const EVENT_TYPE_NAMES: &[(&str, u32)] = &[
    ("UNKNOWN",        event_type_id::UNKNOWN),
    ("MAC_COMPUTE",    event_type_id::MAC_COMPUTE),
    ("DMA_READ",       event_type_id::DMA_READ),
    ("DMA_WRITE",      event_type_id::DMA_WRITE),
    ("SYSTOLIC_STALL", event_type_id::SYSTOLIC_STALL),
    ("BARRIER_SYNC",   event_type_id::BARRIER_SYNC),
    ("API_CALL",       event_type_id::API_CALL),
];

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NpuEvent {
    pub core_id: CoreId,
    pub start_cycle: CycleCount,
    pub duration: CycleCount,
    /// String tag — canonical values: "MAC_COMPUTE", "DMA_READ", "DMA_WRITE",
    /// "SYSTOLIC_STALL", "BARRIER_SYNC", "API_CALL"
    pub event_type: String,
    /// Qualified API name (e.g. `"uca_submit_cmd"`) when
    /// `event_type == "API_CALL"`, otherwise `None`. Mirrors
    /// CUPTI's `CUpti_ActivityAPI.cbid` / callback-id resolution.
    #[serde(default)]
    pub api_name: Option<String>,
}

impl NpuEvent {
    /// Returns the numeric event-type ID for this event.
    /// Centralising this lookup ensures flat_buffer and any future codec stay in sync.
    pub fn type_id(&self) -> EventTypeId {
        EventTypeId::new(match self.event_type.as_str() {
            "MAC_COMPUTE"    => event_type_id::MAC_COMPUTE,
            "DMA_READ"       => event_type_id::DMA_READ,
            "DMA_WRITE"      => event_type_id::DMA_WRITE,
            "SYSTOLIC_STALL" => event_type_id::SYSTOLIC_STALL,
            "BARRIER_SYNC"   => event_type_id::BARRIER_SYNC,
            "API_CALL"       => event_type_id::API_CALL,
            _                => event_type_id::UNKNOWN,
        })
    }

    /// Constructs a non-API event (the common case). `api_name` stays
    /// `None` so the extra field in `NpuEvent` never leaks into
    /// callers that pre-date the API_CALL variant.
    pub fn new(core_id: u32, start_cycle: u64, duration: u64, event_type: impl Into<String>) -> Self {
        Self {
            core_id: CoreId::new(core_id),
            start_cycle: CycleCount::new(start_cycle),
            duration: CycleCount::new(duration),
            event_type: event_type.into(),
            api_name: None,
        }
    }

    /// Constructs an `API_CALL` event tagged with the qualified `uca_*`
    /// name. Duration is the measured entry→exit span in cycles.
    pub fn api_call(core_id: u32, start_cycle: u64, duration: u64, api_name: impl Into<String>) -> Self {
        Self {
            core_id: CoreId::new(core_id),
            start_cycle: CycleCount::new(start_cycle),
            duration: CycleCount::new(duration),
            event_type: "API_CALL".into(),
            api_name: Some(api_name.into()),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NpuTrace {
    pub total_cycles: u64,
    pub events: Vec<NpuEvent>,
}

impl NpuTrace {
    /// Serialises the trace into a high-performance binary payload using Bincode.
    pub fn to_payload(&self) -> Vec<u8> {
        bincode::serialize(self).unwrap_or_default()
    }

    pub fn from_payload(payload: &[u8]) -> Result<Self, bincode::Error> {
        bincode::deserialize(payload)
    }

    /// Creates a flat binary buffer optimised for WebGL / JS TypedArray mapping.
    ///
    /// ## V2 layout (Round-4 T-3)
    ///
    /// Fixed-stride per-event section is unchanged — 24 bytes little-endian:
    /// | Offset | Size | Field            |
    /// |--------|------|------------------|
    /// |  0     |  4   | core_id: u32     |
    /// |  4     |  8   | start_cycle: u64 |
    /// | 12     |  8   | duration: u64    |
    /// | 20     |  4   | event_type_id: u32 |
    ///
    /// After `n_events * 24` bytes, an optional `name_table` trailer is
    /// appended when at least one event carries an `api_name`:
    ///
    /// | Offset (relative) | Size | Field                     |
    /// |-------------------|------|---------------------------|
    /// |  0                |  4   | magic: u32 = 0x3243_4350 ("PCC2" LE) |
    /// |  4                |  4   | name_count: u32           |
    /// |  8…               |  …   | entries[name_count]       |
    ///
    /// Each `entry`:
    /// - `event_index: u32` (0-based index into the events array)
    /// - `len: u16` (byte length of the UTF-8 name, 0–65535)
    /// - `utf8 bytes[len]`
    ///
    /// V1 readers that scan `events_len * 24` bytes and stop at EOF
    /// continue to work — they simply ignore the trailer.  V2 readers
    /// call `from_flat_buffer_v2` to round-trip the names.
    pub const FLAT_BUFFER_V2_MAGIC: u32 = 0x3243_4350; // "PCC2" little-endian

    pub fn to_flat_buffer(&self) -> Vec<u8> {
        // Pre-size: fixed-section + (worst-case) trailer header.
        let mut buf = Vec::with_capacity(self.events.len() * 24 + 8);
        for ev in &self.events {
            buf.extend_from_slice(&ev.core_id.get().to_le_bytes());
            buf.extend_from_slice(&ev.start_cycle.get().to_le_bytes());
            buf.extend_from_slice(&ev.duration.get().to_le_bytes());
            buf.extend_from_slice(&ev.type_id().get().to_le_bytes());
        }

        // Collect only events that actually have an `api_name` — keeps
        // v2 payloads tiny for compute-dominated traces where most
        // events are MAC_COMPUTE / DMA_* with no qualified name.
        let named: Vec<(u32, &str)> = self
            .events
            .iter()
            .enumerate()
            .filter_map(|(i, ev)| ev.api_name.as_deref().map(|n| (i as u32, n)))
            .collect();

        if !named.is_empty() {
            buf.extend_from_slice(&Self::FLAT_BUFFER_V2_MAGIC.to_le_bytes());
            buf.extend_from_slice(&(named.len() as u32).to_le_bytes());
            for (idx, name) in &named {
                let bytes = name.as_bytes();
                // Clamp at u16::MAX (65535) — no legitimate `uca_*` symbol
                // approaches this, so the truncation is theoretical.
                let len = bytes.len().min(u16::MAX as usize) as u16;
                buf.extend_from_slice(&idx.to_le_bytes());
                buf.extend_from_slice(&len.to_le_bytes());
                buf.extend_from_slice(&bytes[..len as usize]);
            }
        }
        buf
    }

    /// Produces a flat buffer with events sorted by `start_cycle`
    /// (ascending). Required by `MmapTrace::viewport` which uses binary
    /// search on the start_cycle column. The original event order is not
    /// preserved — use `to_flat_buffer` when insertion order matters.
    pub fn to_flat_buffer_sorted(&self) -> Vec<u8> {
        let mut sorted = self.events.clone();
        sorted.sort_by_key(|ev| ev.start_cycle.get());
        let sorted_trace = NpuTrace {
            total_cycles: self.total_cycles,
            events: sorted,
        };
        sorted_trace.to_flat_buffer()
    }

    /// Reverses `to_flat_buffer`: reconstructs an `NpuTrace` from the
    /// v2 binary payload, populating `api_name` entries from the
    /// trailer when present.  A buffer without the `PCC2` trailer
    /// decodes cleanly (all `api_name == None`) so v1 payloads remain
    /// readable during the one-round migration window.
    ///
    /// `total_cycles` is reconstructed as `max(start_cycle + duration)`
    /// — the flat encoding never carried a standalone total, so the
    /// roundtrip value may differ from the original `NpuTrace` when
    /// trailing idle cycles are present.
    pub fn from_flat_buffer_v2(bytes: &[u8]) -> Self {
        const STRIDE: usize = 24;
        let mut events = Vec::new();
        let mut total: u64 = 0;

        // Decide where the event section ends.  If the trailer magic
        // is present at a 24-byte-aligned boundary, stop there;
        // otherwise consume the whole buffer.
        let mut event_end = (bytes.len() / STRIDE) * STRIDE;
        if event_end >= 8 {
            // Scan aligned positions for the magic.
            let mut off = 0;
            while off + 8 <= bytes.len() {
                let magic = u32::from_le_bytes(bytes[off..off + 4].try_into().unwrap());
                if magic == Self::FLAT_BUFFER_V2_MAGIC && off % STRIDE == 0 {
                    event_end = off;
                    break;
                }
                off += STRIDE;
            }
        }

        let mut off = 0;
        while off + STRIDE <= event_end {
            let raw_core    = u32::from_le_bytes(bytes[off..off + 4].try_into().unwrap());
            let raw_start   = u64::from_le_bytes(bytes[off + 4..off + 12].try_into().unwrap());
            let raw_dur     = u64::from_le_bytes(bytes[off + 12..off + 20].try_into().unwrap());
            let type_id     = u32::from_le_bytes(bytes[off + 20..off + 24].try_into().unwrap());
            total = total.max(raw_start.saturating_add(raw_dur));
            let event_type = match type_id {
                event_type_id::MAC_COMPUTE    => "MAC_COMPUTE",
                event_type_id::DMA_READ       => "DMA_READ",
                event_type_id::DMA_WRITE      => "DMA_WRITE",
                event_type_id::SYSTOLIC_STALL => "SYSTOLIC_STALL",
                event_type_id::BARRIER_SYNC   => "BARRIER_SYNC",
                event_type_id::API_CALL       => "API_CALL",
                _                             => "UNKNOWN",
            };
            events.push(NpuEvent {
                core_id: CoreId::new(raw_core),
                start_cycle: CycleCount::new(raw_start),
                duration: CycleCount::new(raw_dur),
                event_type: event_type.into(),
                api_name: None,
            });
            off += STRIDE;
        }

        // Trailer — tolerate absence (v1) or truncation (malformed v2).
        if event_end + 8 <= bytes.len() {
            let magic = u32::from_le_bytes(bytes[event_end..event_end + 4].try_into().unwrap());
            if magic == Self::FLAT_BUFFER_V2_MAGIC {
                let count = u32::from_le_bytes(
                    bytes[event_end + 4..event_end + 8].try_into().unwrap()
                ) as usize;
                let mut cur = event_end + 8;
                for _ in 0..count {
                    if cur + 6 > bytes.len() { break; }
                    let idx = u32::from_le_bytes(bytes[cur..cur + 4].try_into().unwrap()) as usize;
                    let len = u16::from_le_bytes(bytes[cur + 4..cur + 6].try_into().unwrap()) as usize;
                    cur += 6;
                    if cur + len > bytes.len() { break; }
                    let name = std::str::from_utf8(&bytes[cur..cur + len])
                        .unwrap_or("")
                        .to_owned();
                    if let Some(ev) = events.get_mut(idx) {
                        ev.api_name = Some(name);
                    }
                    cur += len;
                }
            }
        }

        NpuTrace { total_cycles: total, events }
    }

    /// Returns per-core utilisation in [0.0, 1.0] over the entire trace window.
    pub fn core_utilisation(&self) -> Vec<(u32, f64)> {
        if self.total_cycles == 0 {
            return vec![];
        }
        // Accumulate active (compute) cycles per core.
        let mut compute_map: std::collections::HashMap<u32, u64> = std::collections::HashMap::new();
        for ev in &self.events {
            if ev.event_type == "MAC_COMPUTE" {
                *compute_map.entry(ev.core_id.get()).or_insert(0) += ev.duration.get();
            }
        }
        let mut result: Vec<(u32, f64)> = compute_map
            .into_iter()
            .map(|(core, cycles)| {
                let util = (cycles as f64) / (self.total_cycles as f64);
                (core, util.min(1.0))
            })
            .collect();
        result.sort_by_key(|(core, _)| *core);
        result
    }

    /// Identifies events where DMA bandwidth occupancy exceeds the given ratio threshold
    /// compared to the compute window, flagging potential bottleneck intervals.
    pub fn dma_bottleneck_intervals(&self, threshold_ratio: f64) -> Vec<&NpuEvent> {
        self.events
            .iter()
            .filter(|ev| {
                (ev.event_type == "DMA_READ" || ev.event_type == "DMA_WRITE")
                    && (ev.duration.get() as f64) > threshold_ratio * (self.total_cycles as f64 / 100.0)
            })
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::typed::{CoreId, CycleCount};

    /// Three `API_CALL` events — `api_name` must survive encode/decode
    /// and the fixed 24-byte-per-event stride remains byte-identical
    /// to the v1 encoding for the head section.
    #[test]
    fn flat_buffer_v2_roundtrip() {
        let trace = NpuTrace {
            total_cycles: 4096,
            events: vec![
                NpuEvent::api_call(0, 0,    42,  "uca_init"),
                NpuEvent::new      (1, 100,  50, "MAC_COMPUTE"),
                NpuEvent::api_call(0, 200, 17,  "uca_alloc_buffer"),
                NpuEvent::api_call(2, 512, 128, "uca_submit_cmd"),
            ],
        };
        let buf = trace.to_flat_buffer();

        // Head section: 4 events × 24 = 96 bytes — identical to v1.
        assert_eq!(&buf[0..96].len(), &96usize);
        // Trailer magic follows at offset 96.
        let magic = u32::from_le_bytes(buf[96..100].try_into().unwrap());
        assert_eq!(magic, NpuTrace::FLAT_BUFFER_V2_MAGIC,
            "trailer magic 'PCC2' must appear immediately after the event array");

        let round = NpuTrace::from_flat_buffer_v2(&buf);
        assert_eq!(round.events.len(), 4);
        assert_eq!(round.events[0].api_name.as_deref(), Some("uca_init"));
        assert_eq!(round.events[1].api_name, None,
            "non-API_CALL events must not carry a name after roundtrip");
        assert_eq!(round.events[2].api_name.as_deref(), Some("uca_alloc_buffer"));
        assert_eq!(round.events[3].api_name.as_deref(), Some("uca_submit_cmd"));
        // total_cycles is reconstructed from the max end cycle.
        assert_eq!(round.total_cycles, 512 + 128);
    }

    /// A trace with zero `api_name` events must not emit a trailer —
    /// this keeps v2 buffers byte-identical to v1 for compute-only
    /// workloads so existing v1 decoders continue to work untouched.
    #[test]
    fn flat_buffer_v2_omits_trailer_when_no_names() {
        let trace = NpuTrace {
            total_cycles: 500,
            events: vec![
                NpuEvent::new(0, 0,   100, "MAC_COMPUTE"),
                NpuEvent::new(1, 100, 200, "DMA_READ"),
            ],
        };
        let buf = trace.to_flat_buffer();
        assert_eq!(buf.len(), 48, "2 events × 24 bytes, no trailer");

        let round = NpuTrace::from_flat_buffer_v2(&buf);
        assert_eq!(round.events.len(), 2);
        assert!(round.events.iter().all(|e| e.api_name.is_none()));
    }

    /// V1 buffers (raw 24-byte-per-event stream, no trailer) must
    /// decode cleanly via `from_flat_buffer_v2`.  The per-round
    /// migration contract in the roadmap depends on this.
    #[test]
    fn flat_buffer_v2_decodes_v1_payload() {
        // Hand-built v1 buffer: single MAC_COMPUTE event.
        let mut buf = Vec::with_capacity(24);
        buf.extend_from_slice(&7u32.to_le_bytes());   // core_id
        buf.extend_from_slice(&99u64.to_le_bytes());  // start_cycle
        buf.extend_from_slice(&33u64.to_le_bytes());  // duration
        buf.extend_from_slice(&event_type_id::MAC_COMPUTE.to_le_bytes());

        let round = NpuTrace::from_flat_buffer_v2(&buf);
        assert_eq!(round.events.len(), 1);
        assert_eq!(round.events[0].core_id, CoreId::new(7));
        assert_eq!(round.events[0].start_cycle, CycleCount::new(99));
        assert_eq!(round.events[0].duration, CycleCount::new(33));
        assert_eq!(round.events[0].event_type, "MAC_COMPUTE");
        assert_eq!(round.events[0].api_name, None);
    }
}
