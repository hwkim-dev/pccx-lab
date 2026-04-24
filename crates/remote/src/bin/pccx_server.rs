#[tokio::main]
async fn main() {
    let addr = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "0.0.0.0:9400".to_string());

    println!("Starting pccx-lab remote server...");
    if let Err(e) = pccx_remote::serve(&addr).await {
        eprintln!("Server error: {}", e);
        std::process::exit(1);
    }
}
