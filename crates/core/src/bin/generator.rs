/// pccx-generator: Generates a demo .pccx trace file for development and testing.
///
/// Usage:
///   cargo run --bin generator -- [output_path] [tiles] [cores]
fn main() -> anyhow::Result<()> {
    let args: Vec<String> = std::env::args().collect();

    let output_path = args
        .get(1)
        .map(String::as_str)
        .unwrap_or("dummy_trace.pccx");
    let tiles: u32 = args.get(2).and_then(|s| s.parse().ok()).unwrap_or(100);
    let cores: u32 = args.get(3).and_then(|s| s.parse().ok()).unwrap_or(32);

    println!("pccx Trace Generator");
    println!("  Output    : {output_path}");
    println!("  Tiles     : {tiles}");
    println!("  Cores     : {cores}");
    println!("Generating...");

    let cfg = pccx_core::simulator::SimConfig {
        tiles,
        cores,
        bytes_per_element: 2, // BF16
        tile_m: 64,
        tile_n: 64,
        tile_k: 64,
    };

    let trace = pccx_core::simulator::generate_realistic_trace(&cfg);
    let payload = trace.to_payload();

    let hw = pccx_core::hw_model::HardwareModel::pccx_reference();

    let header = pccx_core::pccx_format::PccxHeader {
        pccx_lab_version: "v0.4.0-contention-aware".to_string(),
        arch: pccx_core::pccx_format::ArchConfig {
            mac_dims: (hw.mac.rows, hw.mac.cols),
            isa_version: "1.1".to_string(),
            peak_tops: (hw.peak_tops() * 100.0).round() / 100.0,
        },
        trace: pccx_core::pccx_format::TraceConfig {
            cycles: trace.total_cycles,
            cores: cfg.cores,
            clock_mhz: hw.clock_mhz,
        },
        payload: pccx_core::pccx_format::PayloadConfig {
            encoding: "bincode".to_string(),
            byte_length: payload.len() as u64,
            checksum_fnv64: Some(pccx_core::pccx_format::fnv1a_64(&payload)),
        },
        format_minor: pccx_core::pccx_format::MINOR_VERSION,
    };

    let pccx_file = pccx_core::pccx_format::PccxFile { header, payload };
    let mut file = std::fs::File::create(output_path)?;
    pccx_file.write(&mut file)?;

    let wall_us = hw.cycles_to_us(trace.total_cycles);
    println!("Written {output_path}");
    println!("  Total events  : {}", trace.events.len());
    println!("  Total cycles  : {}", trace.total_cycles);
    println!("  Wall-time est.: {wall_us:.2} µs @ {} MHz", hw.clock_mhz);
    println!("  Peak TOPS     : {:.2}", hw.peak_tops());

    Ok(())
}
