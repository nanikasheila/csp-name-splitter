/// Python sidecar bridge for JSON-RPC communication.
///
/// Why: Tauri cannot call Python directly. This module manages
///      the Python sidecar process lifecycle and relays JSON-RPC
///      messages between the Svelte frontend and Python core.
/// How: Spawns the Python bridge as a sidecar process, reads
///      stdout line-by-line for responses/notifications, and
///      forwards progress events to the frontend via Tauri events.
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use tauri::{AppHandle, Emitter, Manager};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;
use tokio::sync::{mpsc, Mutex, oneshot};

/// State shared across Tauri commands for bridge management.
pub struct BridgeState {
    /// Sender to dispatch JSON-RPC requests to the writer task.
    request_tx: Mutex<Option<mpsc::Sender<BridgeRequest>>>,
    /// Child process handle for lifecycle management.
    child: Mutex<Option<CommandChild>>,
    /// Monotonic counter for unique JSON-RPC request IDs.
    next_id: AtomicU64,
}

/// Internal request envelope: the JSON line to send plus a
/// channel to deliver the response back to the caller.
struct BridgeRequest {
    /// Unique request ID for matching the JSON-RPC response.
    id: u64,
    json_line: String,
    response_tx: oneshot::Sender<Value>,
}

/// Progress event payload forwarded to the Svelte frontend.
#[derive(Clone, Serialize, Deserialize)]
pub struct ProgressPayload {
    pub phase: String,
    pub done: i64,
    pub total: i64,
    pub message: String,
    pub elapsed_seconds: f64,
    pub pages_per_second: f64,
    pub eta_seconds: Option<f64>,
}

impl BridgeState {
    pub fn new() -> Self {
        Self {
            request_tx: Mutex::new(None),
            child: Mutex::new(None),
            next_id: AtomicU64::new(1),
        }
    }
}

/// Start the Python sidecar bridge process.
///
/// Why: The bridge must be running before any RPC calls.
/// How: In dev mode (debug_assertions), spawns Python directly
///      via `python -m name_splitter.bridge` so no compiled
///      sidecar binary is needed. In release mode, uses the
///      tauri-plugin-shell sidecar API.
#[tauri::command]
pub async fn start_bridge(app: AppHandle) -> Result<String, String> {
    let state = app.state::<Arc<BridgeState>>();

    // Why: Check if already running to prevent double-start
    {
        let existing = state.child.lock().await;
        if existing.is_some() {
            return Ok("Bridge already running".to_string());
        }
    }

    let shell = app.shell();

    // Why: In dev mode the sidecar binary does not exist yet.
    //      Spawn Python directly from the project root.
    // How: Detect debug build via cfg! and use Command::new()
    //      with the Python module path instead of sidecar().
    let (mut rx, child) = if cfg!(debug_assertions) {
        // Why: cwd might be tauri-app/src-tauri/ or tauri-app/.
        //      Walk up until we find .venv to locate the project root.
        let mut project_root = std::env::current_dir()
            .map_err(|e| format!("Failed to get cwd: {e}"))?;
        for _ in 0..5 {
            if project_root.join(".venv").exists()
                || project_root.join("name_splitter").exists()
            {
                break;
            }
            if let Some(parent) = project_root.parent() {
                project_root = parent.to_path_buf();
            } else {
                break;
            }
        }
        eprintln!("[bridge] dev mode project root: {}", project_root.display());
        // Try to find .venv Python first, fall back to "python"
        let venv_python = if cfg!(target_os = "windows") {
            project_root.join(".venv").join("Scripts").join("python.exe")
        } else {
            project_root.join(".venv").join("bin").join("python")
        };
        let python = if venv_python.exists() {
            venv_python.to_string_lossy().to_string()
        } else {
            "python".to_string()
        };
        eprintln!("[bridge] spawning: {} -m name_splitter.bridge", python);
        shell
            .command(&python)
            .args(["-m", "name_splitter.bridge"])
            .current_dir(project_root)
            .spawn()
            .map_err(|e| format!("Failed to spawn Python bridge (dev): {e}"))?
    } else {
        shell
            .sidecar("binaries/csp-bridge")
            .map_err(|e| format!("Failed to create sidecar command: {e}"))?
            .spawn()
            .map_err(|e| format!("Failed to spawn sidecar: {e}"))?
    };

    // Store the child process handle
    {
        let mut child_lock = state.child.lock().await;
        *child_lock = Some(child);
    }

    // Channel for sending requests to the stdin-writer
    let (request_tx, mut request_rx) = mpsc::channel::<BridgeRequest>(32);
    {
        let mut tx_lock = state.request_tx.lock().await;
        *tx_lock = Some(request_tx);
    }

    // Background task: read stdout events and dispatch
    let app_handle = app.clone();
    let state_clone = Arc::clone(&*state);
    tokio::spawn(async move {
        // Why: Map request id → response sender for correct routing
        // How: HashMap keyed by the unique u64 id from each request
        let pending: Arc<Mutex<HashMap<u64, oneshot::Sender<Value>>>> =
            Arc::new(Mutex::new(HashMap::new()));
        let pending_for_writer = Arc::clone(&pending);

        // Writer task: takes requests from the channel and writes to stdin
        let state_for_writer = Arc::clone(&state_clone);
        tokio::spawn(async move {
            while let Some(req) = request_rx.recv().await {
                // Store the response sender keyed by request id
                {
                    let mut p = pending_for_writer.lock().await;
                    p.insert(req.id, req.response_tx);
                }
                // Write to stdin
                let mut child_lock = state_for_writer.child.lock().await;
                if let Some(ref mut child) = *child_lock {
                    let line = format!("{}\n", req.json_line);
                    let _ = child.write(line.as_bytes());
                }
            }
        });

        // Reader loop: process stdout events
        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(line_bytes) => {
                    let line = String::from_utf8_lossy(&line_bytes);
                    let line = line.trim();
                    if line.is_empty() {
                        continue;
                    }
                    if let Ok(msg) = serde_json::from_str::<Value>(line) {
                        // Progress notification (no "id" field)
                        if msg.get("method").and_then(|m| m.as_str())
                            == Some("progress")
                        {
                            if let Some(params) = msg.get("params") {
                                if let Ok(payload) =
                                    serde_json::from_value::<ProgressPayload>(
                                        params.clone(),
                                    )
                                {
                                    let _ = app_handle.emit("bridge-progress", payload);
                                }
                            }
                        } else if let Some(resp_id) = msg.get("id").and_then(|v| v.as_u64()) {
                            // Why: Match response to the correct caller by id
                            let mut p = pending.lock().await;
                            if let Some(sender) = p.remove(&resp_id) {
                                let _ = sender.send(msg);
                            }
                        }
                    }
                }
                CommandEvent::Stderr(line_bytes) => {
                    let line = String::from_utf8_lossy(&line_bytes);
                    eprintln!("[bridge stderr] {}", line.trim());
                }
                CommandEvent::Terminated(status) => {
                    eprintln!("[bridge] process terminated: {:?}", status);
                    // Why: Clear state so start_bridge can restart
                    {
                        let mut child_lock = state_clone.child.lock().await;
                        *child_lock = None;
                    }
                    {
                        let mut tx_lock = state_clone.request_tx.lock().await;
                        *tx_lock = None;
                    }
                    let _ = app_handle.emit("bridge-terminated", ());
                    break;
                }
                _ => {}
            }
        }
    });

    Ok("Bridge started".to_string())
}

/// Send a JSON-RPC request to the Python bridge and await the response.
///
/// Why: Every frontend action (preview, run job, etc.) needs to
///      call the Python core via RPC.
/// How: Serialises the request, sends it through the channel,
///      and awaits the response on a oneshot channel.
#[tauri::command]
pub async fn send_rpc(
    app: AppHandle,
    method: String,
    params: Value,
) -> Result<Value, String> {
    let state = app.state::<Arc<BridgeState>>();
    let tx_lock = state.request_tx.lock().await;
    let tx = tx_lock
        .as_ref()
        .ok_or_else(|| "Bridge not started".to_string())?
        .clone();
    drop(tx_lock);

    // Why: Unique id ensures concurrent RPC responses are routed correctly
    let id = state.next_id.fetch_add(1, Ordering::Relaxed);
    let request = serde_json::json!({
        "jsonrpc": "2.0",
        "id": id,
        "method": method,
        "params": params,
    });
    let json_line = serde_json::to_string(&request)
        .map_err(|e| format!("Serialisation error: {e}"))?;

    let (response_tx, response_rx) = oneshot::channel();
    tx.send(BridgeRequest {
        id,
        json_line,
        response_tx,
    })
    .await
    .map_err(|_| "Failed to send request to bridge".to_string())?;

    let response = response_rx
        .await
        .map_err(|_| "Bridge response channel closed".to_string())?;

    // Check for JSON-RPC error
    if let Some(error) = response.get("error") {
        return Err(error.to_string());
    }

    Ok(response
        .get("result")
        .cloned()
        .unwrap_or(Value::Null))
}

/// Stop the Python bridge sidecar process.
///
/// Why: Clean shutdown on app exit to prevent orphan processes.
/// How: Kills the child process and clears state.
#[tauri::command]
pub async fn stop_bridge(app: AppHandle) -> Result<String, String> {
    let state = app.state::<Arc<BridgeState>>();

    // Drop the request sender to signal the writer task to stop
    {
        let mut tx_lock = state.request_tx.lock().await;
        *tx_lock = None;
    }

    // Kill the child process
    {
        let mut child_lock = state.child.lock().await;
        if let Some(child) = child_lock.take() {
            let _ = child.kill();
        }
    }

    Ok("Bridge stopped".to_string())
}
