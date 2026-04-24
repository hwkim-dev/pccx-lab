// Module Boundary: remote/
// pccx-remote: secure backend daemon for remote pccx-lab access.
//
// Provides an HTTP server (axum) that exposes trace analysis, session
// management, and health endpoints.  Run the companion `pccx-server`
// binary to start a standalone daemon, or call `serve()` / `create_router()`
// from the Tauri host to embed the server in-process.

use axum::{
    extract::State as AxumState,
    http::StatusCode,
    routing::get,
    Json, Router,
};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use uuid::Uuid;

// ─── preserved scaffold constants ──────────────────────────────────

/// Placeholder until the Phase 3 auth layer lands.  Currently returns
/// a static string identifying the crate for feature-gate discovery.
pub const SCAFFOLD_TAG: &str = "pccx-remote: Phase 3 scaffold";

/// OpenAPI 3.0 specification of the planned REST surface.  No
/// endpoints are implemented yet — the schema is authored ahead of
/// time so the pccx-ide + web client can generate typed clients
/// against a stable contract from day one.
///
/// See `openapi.yaml` alongside this file for the full document.
pub const OPENAPI_SPEC: &str = include_str!("../openapi.yaml");

/// Endpoint families the Phase 3 implementation will expose.  Lives
/// here as an `enum` so the pccx-ide can feature-gate UI affordances
/// on the subset that is live on a given server.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EndpointFamily {
    Auth,
    Sessions,
    Traces,
    Reports,
    Events,
}

impl EndpointFamily {
    pub const ALL: &'static [EndpointFamily] = &[
        Self::Auth,
        Self::Sessions,
        Self::Traces,
        Self::Reports,
        Self::Events,
    ];

    pub const fn path_prefix(self) -> &'static str {
        match self {
            Self::Auth => "/v1/auth",
            Self::Sessions => "/v1/sessions",
            Self::Traces => "/v1/traces",
            Self::Reports => "/v1/reports",
            Self::Events => "/v1/events",
        }
    }
}

// ─── server types ──────────────────────────────────────────────────

#[derive(Clone)]
pub struct AppState {
    sessions: Arc<Mutex<HashMap<String, Session>>>,
}

#[derive(Clone, Serialize, Deserialize)]
pub struct Session {
    pub id: String,
    pub created_at: u64,
    pub client_ip: String,
}

#[derive(Serialize)]
pub struct HealthResponse {
    pub status: String,
    pub version: String,
    pub uptime_secs: u64,
}

#[derive(Serialize)]
pub struct SessionResponse {
    pub session_id: String,
    pub message: String,
}

#[derive(Deserialize)]
pub struct TraceUploadRequest {
    pub name: String,
    pub format: String,
}

// ─── handlers ──────────────────────────────────────────────────────

async fn health() -> Json<HealthResponse> {
    Json(HealthResponse {
        status: "ok".to_string(),
        version: env!("CARGO_PKG_VERSION").to_string(),
        uptime_secs: 0, // TODO: track actual uptime
    })
}

async fn create_session(
    AxumState(state): AxumState<AppState>,
) -> (StatusCode, Json<SessionResponse>) {
    let id = Uuid::new_v4().to_string();
    let session = Session {
        id: id.clone(),
        created_at: std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs(),
        client_ip: "unknown".to_string(),
    };
    state.sessions.lock().unwrap().insert(id.clone(), session);
    (
        StatusCode::CREATED,
        Json(SessionResponse {
            session_id: id,
            message: "Session created".to_string(),
        }),
    )
}

async fn list_sessions(AxumState(state): AxumState<AppState>) -> Json<Vec<Session>> {
    let sessions = state.sessions.lock().unwrap();
    Json(sessions.values().cloned().collect())
}

async fn api_spec() -> &'static str {
    OPENAPI_SPEC
}

// ─── router / server ───────────────────────────────────────────────

pub fn create_router() -> Router {
    let state = AppState {
        sessions: Arc::new(Mutex::new(HashMap::new())),
    };

    Router::new()
        .route("/health", get(health))
        .route("/api/spec", get(api_spec))
        .route("/api/v1/sessions", get(list_sessions).post(create_session))
        .with_state(state)
}

/// Start the remote server on the given address.
/// Call this from a binary or from the Tauri app.
pub async fn serve(addr: &str) -> Result<(), Box<dyn std::error::Error>> {
    let app = create_router();
    let listener = tokio::net::TcpListener::bind(addr).await?;
    println!("pccx-lab remote server listening on {}", addr);
    axum::serve(listener, app).await?;
    Ok(())
}

// ─── tests ─────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn scaffold_tag_is_non_empty() {
        assert!(!SCAFFOLD_TAG.is_empty());
    }

    #[test]
    fn openapi_spec_is_valid_yaml_header() {
        assert!(OPENAPI_SPEC.starts_with("openapi: "));
        assert!(OPENAPI_SPEC.contains("pccx-remote"));
    }

    #[test]
    fn all_endpoint_families_have_distinct_prefixes() {
        let mut seen = std::collections::HashSet::new();
        for fam in EndpointFamily::ALL {
            assert!(seen.insert(fam.path_prefix()), "duplicate prefix");
        }
    }
}
