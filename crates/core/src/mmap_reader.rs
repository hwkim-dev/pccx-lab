// Module Boundary: core/
// Memory-mapped .pccx trace reader for production-scale (100 MB+) traces.
//
// Opens the file with memmap2, parses only the fixed-size header on
// construction, and leaves the flat-buffer payload mapped but untouched
// until a viewport or tile query arrives. This avoids the multi-second
// heap allocation that PccxFile::read incurs on large traces.
//
// REQUIREMENT: the payload must use the "flatbuf" encoding (24-byte
// fixed-stride events). Bincode payloads are variable-length and
// cannot be binary-searched; attempting to open one returns an error.
//
// Events in the flat buffer MUST be sorted by start_cycle (ascending)
// for viewport binary search to produce correct results. Use
// `NpuTrace::to_flat_buffer_sorted` when writing files destined for
// MmapTrace consumption — it sorts before serialising. The unsorted
// `to_flat_buffer` preserves insertion order for v1/v2 roundtrip
// compatibility but is NOT suitable for binary-searched viewports.

use std::fs::File;
use std::path::Path;

use memmap2::Mmap;

use crate::pccx_format::{PccxError, PccxHeader, MAJOR_VERSION};
use crate::trace::{event_type_id, NpuEvent, NpuTrace};
use crate::typed::{CoreId, CycleCount};

/// Size of one event record in the flat buffer (bytes).
const EVENT_STRIDE: usize = 24;

/// V2 trailer magic ("PCC2" little-endian).
const V2_MAGIC: u32 = NpuTrace::FLAT_BUFFER_V2_MAGIC;

/*────────────────────────────────────────────────────────────────────*/

/// Memory-mapped reader for `.pccx` files with flat-buffer payloads.
///
/// Holds a read-only mmap for the file's lifetime. The header is parsed
/// eagerly on `open`; the payload is accessed on demand via `viewport`,
/// `tile`, or `event_count`. Drop is handled automatically by
/// `memmap2::Mmap` (munmap on the kernel side).
impl std::fmt::Debug for MmapTrace {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("MmapTrace")
            .field("payload_offset", &self.payload_offset)
            .field("event_section_len", &self.event_section_len)
            .field("event_count", &(self.event_section_len / EVENT_STRIDE))
            .finish_non_exhaustive()
    }
}

pub struct MmapTrace {
    /// Kept alive so the mmap remains valid for the struct's lifetime.
    _file: File,
    mmap: Mmap,
    header: PccxHeader,
    /// Byte offset within the mmap where the flat-buffer payload begins.
    payload_offset: usize,
    /// Byte length of the event section (excludes the optional V2 trailer).
    /// Always a multiple of EVENT_STRIDE.
    event_section_len: usize,
}

impl MmapTrace {
    /// Opens a `.pccx` file and memory-maps it.
    ///
    /// Only the fixed header (magic, version, JSON) is parsed eagerly.
    /// Returns an error if:
    /// - the file is too small to contain a valid header
    /// - the magic number or major version is wrong
    /// - `payload.encoding` is not `"flatbuf"`
    /// - the declared payload length exceeds the mapped region
    pub fn open(path: impl AsRef<Path>) -> Result<Self, PccxError> {
        let file = File::open(path.as_ref())?;
        let metadata = file.metadata()?;
        let file_len = metadata.len() as usize;

        // Minimum valid file: 4 (magic) + 2 (version) + 2 (reserved)
        //                    + 8 (header-len) = 16 bytes, plus at least
        //                    1 byte of JSON header.
        if file_len < 17 {
            return Err(PccxError::IoError(std::io::Error::new(
                std::io::ErrorKind::UnexpectedEof,
                format!("file too small ({file_len} bytes) to contain a valid .pccx header"),
            )));
        }

        // SAFETY: the file is opened read-only and we hold `_file` for
        // the lifetime of the mmap. The OS guarantees coherent reads for
        // a read-only private mapping.
        let mmap = unsafe { Mmap::map(&file)? };

        // ── Magic ────────────────────────────────────────────────────
        let magic: [u8; 4] = mmap[0..4].try_into().unwrap();
        if &magic != b"PCCX" {
            return Err(PccxError::InvalidMagicNumber(magic));
        }

        // ── Version ──────────────────────────────────────────────────
        let major = mmap[4];
        if major != MAJOR_VERSION {
            return Err(PccxError::UnsupportedMajorVersion {
                expected: MAJOR_VERSION,
                got: major,
            });
        }
        // minor (mmap[5]) and reserved (mmap[6..8]) are informational.

        // ── JSON header ──────────────────────────────────────────────
        let header_len = u64::from_le_bytes(mmap[8..16].try_into().unwrap()) as usize;
        let header_end = 16 + header_len;
        if header_end > file_len {
            return Err(PccxError::IoError(std::io::Error::new(
                std::io::ErrorKind::UnexpectedEof,
                format!(
                    "JSON header declares {header_len} bytes but only {} remain after fixed prefix",
                    file_len.saturating_sub(16)
                ),
            )));
        }
        let header: PccxHeader = serde_json::from_slice(&mmap[16..header_end])?;

        // ── Encoding gate ────────────────────────────────────────────
        if header.payload.encoding != "flatbuf" {
            return Err(PccxError::IoError(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!(
                    "MmapTrace requires flatbuf encoding, got {:?}",
                    header.payload.encoding
                ),
            )));
        }

        let payload_offset = header_end;
        let payload_len = file_len - payload_offset;

        // Validate declared length vs actual mapped region.
        let declared = header.payload.byte_length as usize;
        if declared > payload_len {
            return Err(PccxError::PayloadLengthMismatch {
                declared: declared as u64,
                actual: payload_len,
            });
        }

        // ── Locate V2 trailer ────────────────────────────────────────
        // Walk 24-byte-aligned offsets to find the PCC2 magic, matching
        // the scan logic in NpuTrace::from_flat_buffer_v2.
        let effective_payload = &mmap[payload_offset..payload_offset + declared];
        let event_section_len = find_event_section_end(effective_payload);

        Ok(Self {
            _file: file,
            mmap,
            header,
            payload_offset,
            event_section_len,
        })
    }

    /// Parsed header (read once at open time).
    pub fn header(&self) -> &PccxHeader {
        &self.header
    }

    /// Total number of events in the trace, derived from the event
    /// section length without deserialising any records.
    pub fn event_count(&self) -> usize {
        self.event_section_len / EVENT_STRIDE
    }

    /// Returns events whose time range intersects `[start_cycle, end_cycle)`.
    ///
    /// Uses binary search (partition_point) on the sorted start_cycle
    /// column to skip irrelevant prefix/suffix. Events are materialised
    /// only within the matching window.
    ///
    /// Precondition: events in the flat buffer are sorted by start_cycle
    /// ascending. If this invariant is violated the result is unspecified
    /// (but safe — no UB, just wrong output).
    pub fn viewport(&self, start_cycle: u64, end_cycle: u64) -> Vec<NpuEvent> {
        if start_cycle >= end_cycle {
            return Vec::new();
        }
        let n = self.event_count();
        if n == 0 {
            return Vec::new();
        }

        let payload = self.event_payload();

        // Binary search for the first event whose start_cycle >= start_cycle.
        // We also need events that START before start_cycle but EXTEND into
        // the window (start + duration > start_cycle). To catch those, we
        // search for events starting at start_cycle and then scan backwards
        // from the found index, stopping when an event cannot possibly
        // overlap (start + duration < start_cycle).
        //
        // However, since duration is variable we cannot do a tight backward
        // bound without scanning. Instead we find the first event with
        // start_cycle >= end_cycle (everything past here is guaranteed
        // outside) and scan forward from index 0 only up to that point.
        // For the left bound, find the first event with start_cycle
        // >= start_cycle, then walk backwards to capture overlapping events.

        // Right bound: first event starting at or after end_cycle. Everything
        // at this index and beyond starts too late to overlap the window.
        let right = partition_point_start_cycle(payload, n, end_cycle);

        // Left bound: find the first event starting at or after start_cycle.
        let mid = partition_point_start_cycle(payload, n, start_cycle);

        // Scan backwards from `mid` to catch events that start before
        // start_cycle but whose tail (start + duration) extends into the
        // window. We bound the backward scan — events whose end is before
        // start_cycle are skipped.
        let mut left = mid;
        while left > 0 {
            let sc = read_start_cycle(payload, left - 1);
            let dur = read_duration(payload, left - 1);
            if sc.saturating_add(dur) > start_cycle {
                left -= 1;
            } else {
                break;
            }
        }

        let mut result = Vec::with_capacity(right.saturating_sub(left));
        for i in left..right {
            let ev = decode_event(payload, i);
            let ev_end = ev.start_cycle.get().saturating_add(ev.duration.get());
            // Final filter: the event must actually overlap [start_cycle, end_cycle).
            if ev_end > start_cycle && ev.start_cycle.get() < end_cycle {
                result.push(ev);
            }
        }
        result
    }

    /// Raw byte slice into the payload for zero-copy IPC transfer.
    ///
    /// `offset` and `count` are byte offsets/lengths relative to the
    /// payload start. Returns `None` if the requested range exceeds the
    /// declared payload length.
    pub fn tile(&self, offset: usize, count: usize) -> Option<&[u8]> {
        let end = offset.checked_add(count)?;
        let declared = self.header.payload.byte_length as usize;
        if end > declared {
            return None;
        }
        Some(&self.mmap[self.payload_offset + offset..self.payload_offset + end])
    }

    /// Convenience: slice of the event section only (excludes trailer).
    fn event_payload(&self) -> &[u8] {
        &self.mmap[self.payload_offset..self.payload_offset + self.event_section_len]
    }
}

/*────────────────────────────────────────────────────────────────────*/
// Internal helpers — operate on raw &[u8] slices, no allocation.

/// Locates the end of the 24-byte event section within the payload.
/// Scans for the V2 trailer magic at stride-aligned positions; if not
/// found, assumes the entire payload (rounded down to stride) is events.
fn find_event_section_end(payload: &[u8]) -> usize {
    let aligned = (payload.len() / EVENT_STRIDE) * EVENT_STRIDE;
    let mut off = 0;
    while off + 8 <= payload.len() {
        let magic = u32::from_le_bytes(payload[off..off + 4].try_into().unwrap());
        if magic == V2_MAGIC {
            return off;
        }
        off += EVENT_STRIDE;
    }
    aligned
}

/// Reads the start_cycle (u64 LE) of event `i` without constructing an NpuEvent.
#[inline]
fn read_start_cycle(payload: &[u8], i: usize) -> u64 {
    let base = i * EVENT_STRIDE + 4;
    u64::from_le_bytes(payload[base..base + 8].try_into().unwrap())
}

/// Reads the duration (u64 LE) of event `i`.
#[inline]
fn read_duration(payload: &[u8], i: usize) -> u64 {
    let base = i * EVENT_STRIDE + 12;
    u64::from_le_bytes(payload[base..base + 8].try_into().unwrap())
}

/// Decodes event `i` from the flat buffer into an NpuEvent.
fn decode_event(payload: &[u8], i: usize) -> NpuEvent {
    let off = i * EVENT_STRIDE;
    let core_id = u32::from_le_bytes(payload[off..off + 4].try_into().unwrap());
    let start = u64::from_le_bytes(payload[off + 4..off + 12].try_into().unwrap());
    let dur = u64::from_le_bytes(payload[off + 12..off + 20].try_into().unwrap());
    let type_id = u32::from_le_bytes(payload[off + 20..off + 24].try_into().unwrap());
    let event_type = match type_id {
        event_type_id::MAC_COMPUTE => "MAC_COMPUTE",
        event_type_id::DMA_READ => "DMA_READ",
        event_type_id::DMA_WRITE => "DMA_WRITE",
        event_type_id::SYSTOLIC_STALL => "SYSTOLIC_STALL",
        event_type_id::BARRIER_SYNC => "BARRIER_SYNC",
        event_type_id::API_CALL => "API_CALL",
        _ => "UNKNOWN",
    };
    NpuEvent {
        core_id: CoreId::new(core_id),
        start_cycle: CycleCount::new(start),
        duration: CycleCount::new(dur),
        event_type: event_type.into(),
        api_name: None, // V2 trailer names resolved separately if needed
    }
}

/// Binary search: returns the index of the first event whose
/// start_cycle >= `target`. Equivalent to `partition_point`.
fn partition_point_start_cycle(payload: &[u8], n: usize, target: u64) -> usize {
    let mut lo = 0usize;
    let mut hi = n;
    while lo < hi {
        let mid = lo + (hi - lo) / 2;
        if read_start_cycle(payload, mid) < target {
            lo = mid + 1;
        } else {
            hi = mid;
        }
    }
    lo
}

/*────────────────────────────────────────────────────────────────────*/

#[cfg(test)]
mod tests {
    use super::*;
    use crate::pccx_format::{
        fnv1a_64, ArchConfig, PayloadConfig, PccxFile, PccxHeader, TraceConfig, MAJOR_VERSION,
        MINOR_VERSION,
    };
    use crate::trace::{NpuEvent, NpuTrace};
    use std::io::Write as IoWrite;

    /// Writes a .pccx file with flatbuf encoding to a temp path and
    /// returns the path handle (cleaned up on drop).
    fn write_flatbuf_pccx(events: Vec<NpuEvent>, total_cycles: u64) -> tempfile::NamedTempFile {
        let trace = NpuTrace {
            total_cycles,
            events,
        };
        let payload = trace.to_flat_buffer_sorted();
        let header = PccxHeader {
            pccx_lab_version: "test".into(),
            arch: ArchConfig::default(),
            trace: TraceConfig {
                cycles: total_cycles,
                cores: 2,
                clock_mhz: 200,
            },
            payload: PayloadConfig {
                encoding: "flatbuf".into(),
                byte_length: payload.len() as u64,
                checksum_fnv64: Some(fnv1a_64(&payload)),
            },
            format_minor: MINOR_VERSION,
        };
        let pccx = PccxFile { header, payload };
        let mut tmp = tempfile::NamedTempFile::new().unwrap();
        pccx.write(&mut tmp).unwrap();
        tmp.flush().unwrap();
        tmp
    }

    #[test]
    fn open_and_event_count() {
        // 4 sorted events across 2 cores.
        let events = vec![
            NpuEvent::new(0, 0, 100, "MAC_COMPUTE"),
            NpuEvent::new(1, 50, 80, "DMA_READ"),
            NpuEvent::new(0, 200, 150, "MAC_COMPUTE"),
            NpuEvent::new(1, 300, 60, "DMA_WRITE"),
        ];
        let tmp = write_flatbuf_pccx(events, 500);
        let mt = MmapTrace::open(tmp.path()).unwrap();
        assert_eq!(mt.event_count(), 4);
        assert_eq!(mt.header().trace.cycles, 500);
    }

    #[test]
    fn viewport_returns_overlapping_events() {
        // Events sorted by start_cycle.
        let events = vec![
            NpuEvent::new(0, 0, 50, "MAC_COMPUTE"),   // [0, 50)
            NpuEvent::new(0, 50, 100, "DMA_READ"),    // [50, 150)
            NpuEvent::new(0, 200, 80, "MAC_COMPUTE"), // [200, 280)
            NpuEvent::new(0, 400, 60, "DMA_WRITE"),   // [400, 460)
        ];
        let tmp = write_flatbuf_pccx(events, 500);
        let mt = MmapTrace::open(tmp.path()).unwrap();

        // Window [40, 210) should catch events 0, 1, 2:
        //  event 0: [0,50) overlaps [40,210) — tail at 50 > 40
        //  event 1: [50,150) overlaps
        //  event 2: [200,280) — starts at 200 < 210
        //  event 3: [400,460) — starts at 400 >= 210, excluded
        let vp = mt.viewport(40, 210);
        assert_eq!(vp.len(), 3);
        assert_eq!(vp[0].start_cycle.get(), 0);
        assert_eq!(vp[1].start_cycle.get(), 50);
        assert_eq!(vp[2].start_cycle.get(), 200);
    }

    #[test]
    fn viewport_empty_range() {
        let events = vec![NpuEvent::new(0, 100, 50, "MAC_COMPUTE")];
        let tmp = write_flatbuf_pccx(events, 200);
        let mt = MmapTrace::open(tmp.path()).unwrap();
        // start >= end: empty
        assert!(mt.viewport(100, 100).is_empty());
        assert!(mt.viewport(200, 100).is_empty());
    }

    #[test]
    fn viewport_no_overlap() {
        let events = vec![
            NpuEvent::new(0, 0, 50, "MAC_COMPUTE"),
            NpuEvent::new(0, 200, 50, "DMA_READ"),
        ];
        let tmp = write_flatbuf_pccx(events, 300);
        let mt = MmapTrace::open(tmp.path()).unwrap();
        // Window [60, 190) misses both events.
        let vp = mt.viewport(60, 190);
        assert!(vp.is_empty());
    }

    #[test]
    fn tile_extraction() {
        let events = vec![
            NpuEvent::new(0, 0, 100, "MAC_COMPUTE"),
            NpuEvent::new(0, 50, 80, "DMA_READ"),
        ];
        let tmp = write_flatbuf_pccx(events, 200);
        let mt = MmapTrace::open(tmp.path()).unwrap();

        // First event (24 bytes).
        let slice = mt.tile(0, 24).unwrap();
        assert_eq!(slice.len(), 24);
        let core = u32::from_le_bytes(slice[0..4].try_into().unwrap());
        assert_eq!(core, 0);

        // Out of bounds.
        assert!(mt.tile(0, 9999).is_none());
        // Zero-length tile at offset 0.
        assert_eq!(mt.tile(0, 0).unwrap().len(), 0);
    }

    #[test]
    fn empty_payload() {
        let tmp = write_flatbuf_pccx(vec![], 0);
        let mt = MmapTrace::open(tmp.path()).unwrap();
        assert_eq!(mt.event_count(), 0);
        assert!(mt.viewport(0, 1000).is_empty());
        assert_eq!(mt.tile(0, 0).unwrap().len(), 0);
    }

    #[test]
    fn rejects_bincode_encoding() {
        // Build a file with bincode encoding — MmapTrace must reject it.
        let trace = NpuTrace {
            total_cycles: 100,
            events: vec![NpuEvent::new(0, 0, 50, "MAC_COMPUTE")],
        };
        let payload = trace.to_payload(); // bincode
        let header = PccxHeader {
            pccx_lab_version: "test".into(),
            arch: ArchConfig::default(),
            trace: TraceConfig {
                cycles: 100,
                cores: 1,
                clock_mhz: 200,
            },
            payload: PayloadConfig {
                encoding: "bincode".into(),
                byte_length: payload.len() as u64,
                checksum_fnv64: None,
            },
            format_minor: MINOR_VERSION,
        };
        let pccx = PccxFile { header, payload };
        let mut tmp = tempfile::NamedTempFile::new().unwrap();
        pccx.write(&mut tmp).unwrap();
        tmp.flush().unwrap();

        let err = MmapTrace::open(tmp.path()).unwrap_err();
        let msg = format!("{err}");
        assert!(
            msg.contains("flatbuf"),
            "error should mention flatbuf: {msg}"
        );
    }

    #[test]
    fn v2_trailer_does_not_inflate_event_count() {
        // Events with api_name produce a V2 trailer — event_count must
        // not include the trailer bytes.
        let events = vec![
            NpuEvent::api_call(0, 0, 100, "uca_init"),
            NpuEvent::new(0, 200, 50, "MAC_COMPUTE"),
            NpuEvent::api_call(0, 400, 30, "uca_submit_cmd"),
        ];
        let tmp = write_flatbuf_pccx(events, 500);
        let mt = MmapTrace::open(tmp.path()).unwrap();
        assert_eq!(mt.event_count(), 3);
    }

    #[test]
    fn file_too_small_errors_cleanly() {
        let mut tmp = tempfile::NamedTempFile::new().unwrap();
        tmp.write_all(b"PCC").unwrap(); // 3 bytes — too small
        tmp.flush().unwrap();
        assert!(MmapTrace::open(tmp.path()).is_err());
    }
}
