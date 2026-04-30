// Module Boundary: core/
// .pccx binary file format specification — read & write implementation.
//
// File layout (little-endian throughout):
//  [0..4]   Magic "PCCX"
//  [4]      Major spec version (u8)
//  [5]      Minor spec version (u8) — backward compatible within same major
//  [6..8]   Reserved (2 bytes, zeroed)
//  [8..16]  JSON header length (u64)
//  [16..N]  UTF-8 JSON header (N bytes)
//  [N..]    Binary payload (M bytes, format described in header.payload.encoding)
use serde::{Deserialize, Serialize};
use std::io::{Read, Write};
use thiserror::Error;

/// Current format major version. Increment on breaking changes.
pub const MAJOR_VERSION: u8 = 0x01;
/// Current format minor version. Increment on additive changes.
pub const MINOR_VERSION: u8 = 0x01;

const MAGIC_NUMBER: &[u8; 4] = b"PCCX";

#[derive(Error, Debug)]
pub enum PccxError {
    #[error("Invalid magic number — expected 'PCCX', got '{0:?}'")]
    InvalidMagicNumber([u8; 4]),
    #[error("Unsupported major version: expected {expected}, got {got}")]
    UnsupportedMajorVersion { expected: u8, got: u8 },
    #[error("IO error: {0}")]
    IoError(#[from] std::io::Error),
    #[error("JSON error: {0}")]
    JsonError(#[from] serde_json::Error),
    #[error("Payload length mismatch: header declares {declared} bytes, read {actual}")]
    PayloadLengthMismatch { declared: u64, actual: usize },
}

// ─── Header Structs ───────────────────────────────────────────────────────────

#[derive(Debug, Serialize, Deserialize, Default, Clone)]
pub struct ArchConfig {
    /// MAC array dimensions as (rows, cols).
    pub mac_dims: (u32, u32),
    pub isa_version: String,
    /// Peak TOPS (informational, derived at write time).
    #[serde(default)]
    pub peak_tops: f64,
}

#[derive(Debug, Serialize, Deserialize, Default, Clone)]
pub struct TraceConfig {
    /// Total simulation cycles.
    pub cycles: u64,
    /// Number of simulated cores.
    pub cores: u32,
    /// Clock frequency in MHz at which the trace was generated.
    #[serde(default = "default_clock_mhz")]
    pub clock_mhz: u32,
}

fn default_clock_mhz() -> u32 {
    1000
}

#[derive(Debug, Serialize, Deserialize, Default, Clone)]
pub struct PayloadConfig {
    /// Encoding of the binary payload: "bincode" | "flatbuf" | "raw"
    pub encoding: String,
    /// Byte length of the payload blob.
    pub byte_length: u64,
    /// Optional FNV-1a 64-bit checksum of the payload for integrity checks.
    #[serde(default)]
    pub checksum_fnv64: Option<u64>,
}

#[derive(Debug, Serialize, Deserialize, Default, Clone)]
pub struct PccxHeader {
    pub pccx_lab_version: String,

    #[serde(default)]
    pub arch: ArchConfig,

    #[serde(default)]
    pub trace: TraceConfig,

    #[serde(default)]
    pub payload: PayloadConfig,

    /// Minor version of the format spec used to write this file (informational).
    #[serde(default)]
    pub format_minor: u8,
}

// ─── File I/O ────────────────────────────────────────────────────────────────

pub struct PccxFile {
    pub header: PccxHeader,
    /// Raw binary payload (encoding specified in `header.payload.encoding`).
    pub payload: Vec<u8>,
}

impl PccxFile {
    pub fn write<W: Write>(&self, w: &mut W) -> Result<(), PccxError> {
        // Magic number
        w.write_all(MAGIC_NUMBER)?;

        // Version bytes
        w.write_all(&[MAJOR_VERSION, MINOR_VERSION])?;

        // Reserved (2 bytes)
        w.write_all(&[0x00, 0x00])?;

        // JSON header
        let json_header = serde_json::to_vec(&self.header)?;
        let header_len = json_header.len() as u64;
        w.write_all(&header_len.to_le_bytes())?;
        w.write_all(&json_header)?;

        // Binary payload
        w.write_all(&self.payload)?;

        Ok(())
    }

    pub fn read<R: Read>(r: &mut R) -> Result<Self, PccxError> {
        // Magic number
        let mut magic = [0u8; 4];
        r.read_exact(&mut magic)?;
        if &magic != MAGIC_NUMBER {
            return Err(PccxError::InvalidMagicNumber(magic));
        }

        // Major version check (forward compatibility: any MINOR_VERSION is accepted)
        let mut version = [0u8; 2];
        r.read_exact(&mut version)?;
        let major = version[0];
        if major != MAJOR_VERSION {
            return Err(PccxError::UnsupportedMajorVersion {
                expected: MAJOR_VERSION,
                got: major,
            });
        }
        // Minor version is noted but not validated (backward compatible)
        let _minor = version[1];

        // Reserved
        let mut reserved = [0u8; 2];
        r.read_exact(&mut reserved)?;

        // Header length + JSON header
        let mut header_len_buf = [0u8; 8];
        r.read_exact(&mut header_len_buf)?;
        let header_length = u64::from_le_bytes(header_len_buf);

        let mut json_header = vec![0u8; header_length as usize];
        r.read_exact(&mut json_header)?;
        let header: PccxHeader = serde_json::from_slice(&json_header)?;

        // Payload
        let declared_len = header.payload.byte_length as usize;
        let mut payload = vec![0u8; declared_len];
        r.read_exact(&mut payload)?;

        // Optional checksum verification
        if let Some(expected_checksum) = header.payload.checksum_fnv64 {
            let actual = fnv1a_64(&payload);
            if actual != expected_checksum {
                // Non-fatal for now — log but don't abort (future: configurable)
                eprintln!(
                    "[pccx_format] WARNING: payload checksum mismatch \
                    (expected {:#018x}, got {:#018x})",
                    expected_checksum, actual
                );
            }
        }

        Ok(Self { header, payload })
    }
}

// ─── Utility ──────────────────────────────────────────────────────────────────

/// FNV-1a 64-bit hash for fast payload integrity checking.
pub fn fnv1a_64(data: &[u8]) -> u64 {
    const BASIS: u64 = 0xcbf29ce484222325;
    const PRIME: u64 = 0x00000100000001b3;
    data.iter()
        .fold(BASIS, |h, &b| (h ^ b as u64).wrapping_mul(PRIME))
}
