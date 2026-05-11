// Seven Desktop App — Tauri v2 native entrypoint.
// Provides secure HTTP bridge commands so the bundled HTML/JS frontend
// can talk to the SWARM leader without CORS issues.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde_json::Value;
use tauri::command;

#[command]
async fn api_get(url: String) -> Result<Value, String> {
    let client = reqwest::Client::new();
    let resp = client
        .get(&url)
        .timeout(std::time::Duration::from_secs(15))
        .send()
        .await
        .map_err(|e| format!("request failed: {}", e))?;

    if !resp.status().is_success() {
        return Err(format!("HTTP {}", resp.status()));
    }
    let json: Value = resp
        .json()
        .await
        .map_err(|e| format!("parse failed: {}", e))?;
    Ok(json)
}

#[command]
async fn api_post(url: String, body: Value) -> Result<Value, String> {
    let client = reqwest::Client::new();
    let resp = client
        .post(&url)
        .json(&body)
        .timeout(std::time::Duration::from_secs(30))
        .send()
        .await
        .map_err(|e| format!("request failed: {}", e))?;

    if !resp.status().is_success() {
        return Err(format!("HTTP {}", resp.status()));
    }
    let json: Value = resp
        .json()
        .await
        .map_err(|e| format!("parse failed: {}", e))?;
    Ok(json)
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_http::init())
        .invoke_handler(tauri::generate_handler![api_get, api_post])
        .run(tauri::generate_context!())
        .expect("error while running Seven Desktop");
}
