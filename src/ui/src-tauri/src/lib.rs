use pccx_core::pccx_format::{PccxFile, PccxHeader};
use pccx_ai_copilot::{Extension, get_available_extensions};
use std::fs::File;
use std::thread;
use std::time::Duration;

#[tauri::command]
fn load_pccx(path: &str) -> Result<PccxHeader, String> {
    let mut file = File::open(path).map_err(|e| e.to_string())?;
    let pccx = PccxFile::read(&mut file).map_err(|e| e.to_string())?;
    Ok(pccx.header)
}

#[tauri::command]
fn get_extensions() -> Vec<Extension> {
    get_available_extensions()
}

#[tauri::command]
async fn generate_report() -> Result<String, String> {
    // Simulate long-running PDF generation task
    thread::sleep(Duration::from_secs(2));
    Ok("Enterprise Report successfully generated and saved to output.pdf!".into())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![load_pccx, get_extensions, generate_report])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
