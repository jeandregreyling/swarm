// Seven's Swarm — Tauri desktop wrapper entrypoint.
// The window simply loads the local Flask UI at http://localhost:5050.
// The Flask backend itself is expected to be running via the
// `swarm-terminal.service` systemd unit on the Dell OptiPlex 7090.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .run(tauri::generate_context!())
        .expect("error while running Seven's Swarm desktop wrapper");
}
