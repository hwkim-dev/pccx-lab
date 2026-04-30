// Module Boundary: remote/
// pccx-remote: secure backend daemon for remote pccx-lab access.
//
// Provides an HTTP server (axum) that exposes trace analysis, session
// management, and health endpoints.  Run the companion `pccx-server`
// binary to start a standalone daemon, or call `serve()` / `create_router()`
// from the Tauri host to embed the server in-process.

use axum::{extract::State as AxumState, http::StatusCode, routing::get, Json, Router};
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

// ─── connection config ────────────────────────────────────────────

/// Configuration for connecting to a remote pccx-lab daemon.
/// Used by the Tauri client to establish a session over the
/// WireGuard / QUIC tunnel (Phase 3).
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ConnectionConfig {
    pub host: String,
    pub port: u16,
    /// Bearer token from the OIDC + WebAuthn auth flow.
    /// `None` for local / dev connections that bypass auth.
    pub auth_token: Option<String>,
    /// Connection timeout in milliseconds.
    pub timeout_ms: u32,
}

impl Default for ConnectionConfig {
    fn default() -> Self {
        Self {
            host: "localhost".to_string(),
            port: 9400,
            auth_token: None,
            timeout_ms: 30_000,
        }
    }
}

// ─── remote session ───────────────────────────────────────────────

/// Lifecycle state of a `RemoteSession`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SessionState {
    Connected,
    Disconnected,
}

/// Client-side handle to a remote daemon session.
/// Currently a stub — real I/O lands with M3.1 (WireGuard control plane).
#[derive(Debug, Clone)]
pub struct RemoteSession {
    pub id: String,
    pub config: ConnectionConfig,
    pub state: SessionState,
}

impl RemoteSession {
    /// Create a new session in `Disconnected` state.
    pub fn new(config: ConnectionConfig) -> Self {
        Self {
            id: Uuid::new_v4().to_string(),
            config,
            state: SessionState::Disconnected,
        }
    }

    /// Attempt to connect to the remote daemon.
    /// Stub: flips state to `Connected` without real I/O.
    pub fn connect(&mut self) -> Result<(), String> {
        if self.state == SessionState::Connected {
            return Err("already connected".to_string());
        }
        // TODO(M3.1): WireGuard handshake + TLS upgrade
        self.state = SessionState::Connected;
        Ok(())
    }

    /// Disconnect from the remote daemon.
    /// Stub: flips state to `Disconnected`.
    pub fn disconnect(&mut self) -> Result<(), String> {
        if self.state == SessionState::Disconnected {
            return Err("not connected".to_string());
        }
        self.state = SessionState::Disconnected;
        Ok(())
    }

    /// Returns `true` when the session is in `Connected` state.
    pub fn is_alive(&self) -> bool {
        self.state == SessionState::Connected
    }
}

// ─── trace stream protocol ────────────────────────────────────────

/// Wire-level message types for the trace tile streaming protocol.
/// Travels inside the authenticated tunnel; the outer transport
/// (WireGuard / QUIC) handles encryption.
///
/// Frame layout (big-endian, network byte order):
///   byte 0      : msg_type (u8)
///   bytes 1..5  : payload_len (u32)
///   bytes 5..   : payload (payload_len bytes)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u8)]
pub enum MessageType {
    /// Client requests a range of trace tiles.
    TileRequest = 0x01,
    /// Server responds with tile data.
    TileResponse = 0x02,
    /// Keep-alive ping / pong (25s interval per Phase 3 spec).
    Heartbeat = 0x03,
    /// Error report from either side.
    Error = 0x04,
}

impl MessageType {
    pub fn as_u8(self) -> u8 {
        self as u8
    }

    pub fn try_from_u8(val: u8) -> Result<Self, ProtocolError> {
        match val {
            0x01 => Ok(Self::TileRequest),
            0x02 => Ok(Self::TileResponse),
            0x03 => Ok(Self::Heartbeat),
            0x04 => Ok(Self::Error),
            other => Err(ProtocolError::UnknownMessageType(other)),
        }
    }
}

/// Protocol-level errors during frame encode / decode.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ProtocolError {
    /// Input buffer shorter than the 5-byte header.
    BufferTooShort,
    /// Header declares a message type we don't recognise.
    UnknownMessageType(u8),
    /// Header says N payload bytes, but the buffer has fewer.
    PayloadLengthMismatch { expected: u32, actual: u32 },
}

impl std::fmt::Display for ProtocolError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::BufferTooShort => write!(f, "buffer shorter than 5-byte frame header"),
            Self::UnknownMessageType(t) => write!(f, "unknown message type: 0x{:02x}", t),
            Self::PayloadLengthMismatch { expected, actual } => {
                write!(
                    f,
                    "payload length mismatch: header says {} bytes, buffer has {}",
                    expected, actual
                )
            }
        }
    }
}

/// Header size in bytes: 1 (msg_type) + 4 (payload_len).
pub const FRAME_HEADER_SIZE: usize = 5;

/// A single decoded protocol frame.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Frame {
    pub msg_type: MessageType,
    pub payload: Vec<u8>,
}

impl Frame {
    /// Encode this frame into a byte vector (big-endian wire format).
    pub fn encode(&self) -> Vec<u8> {
        let payload_len = self.payload.len() as u32;
        let mut buf = Vec::with_capacity(FRAME_HEADER_SIZE + self.payload.len());
        buf.push(self.msg_type.as_u8());
        buf.extend_from_slice(&payload_len.to_be_bytes());
        buf.extend_from_slice(&self.payload);
        buf
    }

    /// Decode a frame from a byte buffer.  The buffer must contain
    /// exactly one complete frame (header + payload).
    pub fn decode(buf: &[u8]) -> Result<Self, ProtocolError> {
        if buf.len() < FRAME_HEADER_SIZE {
            return Err(ProtocolError::BufferTooShort);
        }
        let msg_type = MessageType::try_from_u8(buf[0])?;
        let payload_len = u32::from_be_bytes([buf[1], buf[2], buf[3], buf[4]]);
        let payload_start = FRAME_HEADER_SIZE;
        let available = (buf.len() - payload_start) as u32;
        if available < payload_len {
            return Err(ProtocolError::PayloadLengthMismatch {
                expected: payload_len,
                actual: available,
            });
        }
        let payload = buf[payload_start..payload_start + payload_len as usize].to_vec();
        Ok(Self { msg_type, payload })
    }
}

// ─── health check ─────────────────────────────────────────────────

/// Domain-level health snapshot for the daemon.  Distinct from
/// `HealthResponse` (which is the HTTP handler's JSON shape) — this
/// struct carries richer state for internal consumers and the
/// planned `/v1/events` WebSocket subscription.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct HealthCheck {
    /// Seconds since the daemon process started.
    pub uptime_secs: u64,
    /// Crate version (`CARGO_PKG_VERSION`).
    pub version: String,
    /// Names of .pccx traces currently loaded in memory.
    pub loaded_traces: Vec<String>,
}

impl HealthCheck {
    /// Snapshot from the current process.  `loaded_traces` is supplied
    /// by the caller (the session manager knows what's loaded).
    pub fn now(start_time: std::time::Instant, loaded_traces: Vec<String>) -> Self {
        Self {
            uptime_secs: start_time.elapsed().as_secs(),
            version: env!("CARGO_PKG_VERSION").to_string(),
            loaded_traces,
        }
    }
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

// ─── M3.1 / M3.2: session lifecycle + RBAC + audit log ────────────

/// Returns current UNIX time in whole seconds.  Used throughout the
/// session manager so tests can manipulate `last_active` directly
/// rather than sleeping.
fn now_secs() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}

// ─── identity newtypes ────────────────────────────────────────────

#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct SessionId(pub String);

#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct UserId(pub String);

#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct ProjectId(pub String);

// ─── RBAC ─────────────────────────────────────────────────────────

/// Roles a user may hold within a project.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Role {
    Owner,
    Maintainer,
    Viewer,
}

/// Actions that can be performed against a project resource.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Action {
    Read,
    Write,
    Execute,
    Admin,
}

/// A single rule associating a role with the actions it permits.
#[derive(Debug, Clone)]
pub struct RbacRule {
    pub role: Role,
    pub actions: Vec<Action>,
}

/// Casbin-style policy table.  Look up with `can()` or `check()`.
#[derive(Debug, Clone)]
pub struct RbacPolicy {
    rules: Vec<RbacRule>,
}

/// Returned when an RBAC check fails.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AccessDenied {
    pub role: Role,
    pub action: Action,
    pub reason: String,
}

impl std::fmt::Display for AccessDenied {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "{:?} may not perform {:?}: {}",
            self.role, self.action, self.reason
        )
    }
}

impl RbacPolicy {
    /// Default policy:
    ///   Owner     — Read, Write, Execute, Admin
    ///   Maintainer — Read, Write, Execute
    ///   Viewer     — Read
    pub fn default() -> Self {
        Self {
            rules: vec![
                RbacRule {
                    role: Role::Owner,
                    actions: vec![Action::Read, Action::Write, Action::Execute, Action::Admin],
                },
                RbacRule {
                    role: Role::Maintainer,
                    actions: vec![Action::Read, Action::Write, Action::Execute],
                },
                RbacRule {
                    role: Role::Viewer,
                    actions: vec![Action::Read],
                },
            ],
        }
    }

    /// Returns `true` if `role` is permitted to perform `action`.
    pub fn can(&self, role: &Role, action: &Action) -> bool {
        self.rules
            .iter()
            .filter(|r| &r.role == role)
            .any(|r| r.actions.contains(action))
    }

    /// Checks whether the session's role permits `action`.
    /// Returns `Ok(())` or an `Err(AccessDenied)`.
    pub fn check(&self, session: &ManagedSession, action: &Action) -> Result<(), AccessDenied> {
        if self.can(&session.role, action) {
            Ok(())
        } else {
            Err(AccessDenied {
                role: session.role,
                action: *action,
                reason: "role does not include this action".to_string(),
            })
        }
    }
}

// ─── managed session ──────────────────────────────────────────────

/// Lifecycle state of a `ManagedSession` inside the `SessionManager`.
///
/// Named `ManagedSessionState` to avoid colliding with the existing
/// `SessionState { Connected, Disconnected }` used by `RemoteSession`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ManagedSessionState {
    Active,
    Idle,
    Terminated,
}

/// A server-side session tracked by `SessionManager`.
#[derive(Debug, Clone)]
pub struct ManagedSession {
    pub id: SessionId,
    pub user: UserId,
    pub project: ProjectId,
    pub role: Role,
    /// UNIX timestamp (seconds) when the session was created.
    pub created_at: u64,
    /// UNIX timestamp (seconds) of the most recent activity.
    /// `pub` so tests can back-date it without sleeping.
    pub last_active: u64,
    pub state: ManagedSessionState,
}

// ─── session errors ───────────────────────────────────────────────

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SessionError {
    MaxSessionsReached,
    NotFound,
    AlreadyTerminated,
}

impl std::fmt::Display for SessionError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::MaxSessionsReached => write!(f, "session limit reached"),
            Self::NotFound => write!(f, "session not found"),
            Self::AlreadyTerminated => write!(f, "session is already terminated"),
        }
    }
}

// ─── session manager ──────────────────────────────────────────────

/// Tracks all managed sessions, enforces the session cap, and reaps
/// sessions that have been idle longer than `idle_timeout`.
pub struct SessionManager {
    sessions: HashMap<SessionId, ManagedSession>,
    max_sessions: usize,
    idle_timeout: std::time::Duration,
}

impl SessionManager {
    pub fn new(max_sessions: usize, idle_timeout: std::time::Duration) -> Self {
        Self {
            sessions: HashMap::new(),
            max_sessions,
            idle_timeout,
        }
    }

    /// Create and register a new `ManagedSession`.
    /// Returns `Err(SessionError::MaxSessionsReached)` when the cap is hit.
    pub fn create_session(
        &mut self,
        user: UserId,
        project: ProjectId,
        role: Role,
    ) -> Result<SessionId, SessionError> {
        let active = self
            .sessions
            .values()
            .filter(|s| s.state != ManagedSessionState::Terminated)
            .count();
        if active >= self.max_sessions {
            return Err(SessionError::MaxSessionsReached);
        }
        let id = SessionId(Uuid::new_v4().to_string());
        let now = now_secs();
        let session = ManagedSession {
            id: id.clone(),
            user,
            project,
            role,
            created_at: now,
            last_active: now,
            state: ManagedSessionState::Active,
        };
        self.sessions.insert(id.clone(), session);
        Ok(id)
    }

    /// Look up a session by id.
    pub fn get_session(&self, id: &SessionId) -> Option<&ManagedSession> {
        self.sessions.get(id)
    }

    /// Update `last_active` to now; sets state to `Active` if it was `Idle`.
    /// Returns `Err(SessionError::NotFound)` for unknown ids.
    pub fn touch_session(&mut self, id: &SessionId) -> Result<(), SessionError> {
        let sess = self.sessions.get_mut(id).ok_or(SessionError::NotFound)?;
        if sess.state == ManagedSessionState::Terminated {
            return Err(SessionError::AlreadyTerminated);
        }
        sess.last_active = now_secs();
        sess.state = ManagedSessionState::Active;
        Ok(())
    }

    /// Terminate a session.  Idempotent: calling on an already-terminated
    /// session returns `Err(SessionError::AlreadyTerminated)`.
    pub fn terminate_session(&mut self, id: &SessionId) -> Result<(), SessionError> {
        let sess = self.sessions.get_mut(id).ok_or(SessionError::NotFound)?;
        if sess.state == ManagedSessionState::Terminated {
            return Err(SessionError::AlreadyTerminated);
        }
        sess.state = ManagedSessionState::Terminated;
        Ok(())
    }

    /// Terminate all sessions whose `last_active` is older than `idle_timeout`.
    /// Returns the ids of sessions that were reaped.
    pub fn reap_idle_sessions(&mut self) -> Vec<SessionId> {
        let cutoff = now_secs().saturating_sub(self.idle_timeout.as_secs());
        let mut reaped = Vec::new();
        for sess in self.sessions.values_mut() {
            if sess.state != ManagedSessionState::Terminated && sess.last_active < cutoff {
                sess.state = ManagedSessionState::Terminated;
                reaped.push(sess.id.clone());
            }
        }
        reaped
    }

    /// Number of sessions that are not yet terminated.
    pub fn active_count(&self) -> usize {
        self.sessions
            .values()
            .filter(|s| s.state != ManagedSessionState::Terminated)
            .count()
    }
}

// ─── audit log ────────────────────────────────────────────────────

/// Result of an audited action.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum AuditResult {
    Allowed,
    Denied(String),
}

/// One entry in the append-only audit log.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AuditEntry {
    /// UNIX timestamp (seconds) when the event was recorded.
    pub timestamp: u64,
    pub session_id: String,
    pub user: String,
    pub action: String,
    pub result: AuditResult,
}

/// Append-only in-memory audit log.  In Phase 3 M3.3 this will be
/// backed by SQLite WAL + S3 replication; the interface is stable now.
pub struct AuditLog {
    entries: Vec<AuditEntry>,
}

impl AuditLog {
    pub fn new() -> Self {
        Self {
            entries: Vec::new(),
        }
    }

    /// Append an entry.  Entries are never removed.
    pub fn record(&mut self, entry: AuditEntry) {
        self.entries.push(entry);
    }

    /// All entries belonging to `session_id`, in insertion order.
    pub fn entries_for_session<'a>(&'a self, id: &str) -> Vec<&'a AuditEntry> {
        self.entries.iter().filter(|e| e.session_id == id).collect()
    }

    /// All entries whose `timestamp >= since`, in insertion order.
    pub fn entries_since(&self, since: u64) -> Vec<&AuditEntry> {
        self.entries
            .iter()
            .filter(|e| e.timestamp >= since)
            .collect()
    }
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

    // ─── connection config tests ──────────────────────────────────

    #[test]
    fn connection_config_default_values() {
        let cfg = ConnectionConfig::default();
        assert_eq!(cfg.host, "localhost");
        assert_eq!(cfg.port, 9400);
        assert!(cfg.auth_token.is_none());
        assert_eq!(cfg.timeout_ms, 30_000);
    }

    #[test]
    fn connection_config_with_auth_token() {
        let cfg = ConnectionConfig {
            host: "remote.example.com".to_string(),
            port: 8443,
            auth_token: Some("ey.jwt.token".to_string()),
            timeout_ms: 5_000,
        };
        assert_eq!(cfg.auth_token.as_deref(), Some("ey.jwt.token"));
    }

    #[test]
    fn connection_config_json_round_trip() {
        let cfg = ConnectionConfig {
            host: "10.0.0.1".to_string(),
            port: 9400,
            auth_token: Some("tok".to_string()),
            timeout_ms: 15_000,
        };
        let json = serde_json::to_string(&cfg).unwrap();
        let restored: ConnectionConfig = serde_json::from_str(&json).unwrap();
        assert_eq!(cfg, restored);
    }

    // ─── remote session tests ─────────────────────────────────────

    #[test]
    fn remote_session_connect_disconnect_lifecycle() {
        let mut sess = RemoteSession::new(ConnectionConfig::default());
        assert!(!sess.is_alive());
        assert_eq!(sess.state, SessionState::Disconnected);

        sess.connect().unwrap();
        assert!(sess.is_alive());
        assert_eq!(sess.state, SessionState::Connected);

        sess.disconnect().unwrap();
        assert!(!sess.is_alive());
    }

    #[test]
    fn remote_session_double_connect_errors() {
        let mut sess = RemoteSession::new(ConnectionConfig::default());
        sess.connect().unwrap();
        assert!(sess.connect().is_err());
    }

    #[test]
    fn remote_session_disconnect_when_not_connected_errors() {
        let mut sess = RemoteSession::new(ConnectionConfig::default());
        assert!(sess.disconnect().is_err());
    }

    #[test]
    fn remote_session_has_uuid_id() {
        let sess = RemoteSession::new(ConnectionConfig::default());
        // UUID v4 is 36 chars with hyphens (8-4-4-4-12).
        assert_eq!(sess.id.len(), 36);
        assert_eq!(sess.id.chars().filter(|c| *c == '-').count(), 4);
    }

    // ─── protocol frame tests ─────────────────────────────────────

    #[test]
    fn frame_encode_decode_round_trip_with_payload() {
        let original = Frame {
            msg_type: MessageType::TileResponse,
            payload: vec![0xDE, 0xAD, 0xBE, 0xEF, 0x01, 0x02],
        };
        let wire = original.encode();
        // Header: 1 byte type + 4 bytes length = 5, plus 6 payload bytes.
        assert_eq!(wire.len(), FRAME_HEADER_SIZE + 6);
        let decoded = Frame::decode(&wire).unwrap();
        assert_eq!(decoded, original);
    }

    #[test]
    fn frame_encode_decode_round_trip_empty_payload() {
        let original = Frame {
            msg_type: MessageType::Heartbeat,
            payload: vec![],
        };
        let wire = original.encode();
        assert_eq!(wire.len(), FRAME_HEADER_SIZE);
        let decoded = Frame::decode(&wire).unwrap();
        assert_eq!(decoded, original);
    }

    #[test]
    fn frame_decode_rejects_truncated_header() {
        // Only 3 bytes — less than the 5-byte header.
        let buf = [0x01, 0x00, 0x00];
        assert_eq!(Frame::decode(&buf), Err(ProtocolError::BufferTooShort));
    }

    #[test]
    fn frame_decode_rejects_truncated_payload() {
        // Valid header claiming 10 payload bytes, but only 2 present.
        let mut buf = vec![MessageType::TileRequest.as_u8()];
        buf.extend_from_slice(&10u32.to_be_bytes());
        buf.extend_from_slice(&[0xAA, 0xBB]);
        match Frame::decode(&buf) {
            Err(ProtocolError::PayloadLengthMismatch {
                expected: 10,
                actual: 2,
            }) => {}
            other => panic!("expected PayloadLengthMismatch, got {:?}", other),
        }
    }

    #[test]
    fn frame_decode_rejects_unknown_message_type() {
        let mut buf = vec![0xFF]; // invalid type
        buf.extend_from_slice(&0u32.to_be_bytes());
        assert_eq!(
            Frame::decode(&buf),
            Err(ProtocolError::UnknownMessageType(0xFF))
        );
    }

    #[test]
    fn message_type_round_trip_all_variants() {
        for &mt in &[
            MessageType::TileRequest,
            MessageType::TileResponse,
            MessageType::Heartbeat,
            MessageType::Error,
        ] {
            let byte = mt.as_u8();
            let restored = MessageType::try_from_u8(byte).unwrap();
            assert_eq!(restored, mt);
        }
    }

    #[test]
    fn frame_big_endian_wire_order() {
        let frame = Frame {
            msg_type: MessageType::TileRequest,
            payload: vec![0x00; 256],
        };
        let wire = frame.encode();
        // payload_len = 256 = 0x00000100 in big-endian.
        assert_eq!(&wire[1..5], &[0x00, 0x00, 0x01, 0x00]);
    }

    // ─── health check tests ──────────────────────────────────────

    #[test]
    fn health_check_json_round_trip() {
        let hc = HealthCheck {
            uptime_secs: 3600,
            version: "0.1.0".to_string(),
            loaded_traces: vec!["matmul.pccx".to_string(), "conv2d.pccx".to_string()],
        };
        let json = serde_json::to_string(&hc).unwrap();
        let restored: HealthCheck = serde_json::from_str(&json).unwrap();
        assert_eq!(hc, restored);
    }

    #[test]
    fn health_check_now_captures_uptime() {
        let start = std::time::Instant::now();
        let hc = HealthCheck::now(start, vec!["test.pccx".to_string()]);
        // Just started, so uptime should be 0 or 1.
        assert!(hc.uptime_secs <= 1);
        assert_eq!(hc.loaded_traces, vec!["test.pccx"]);
        assert!(!hc.version.is_empty());
    }

    #[test]
    fn health_check_empty_traces() {
        let hc = HealthCheck {
            uptime_secs: 0,
            version: "0.1.0".to_string(),
            loaded_traces: vec![],
        };
        let json = serde_json::to_string(&hc).unwrap();
        assert!(json.contains("\"loaded_traces\":[]"));
    }

    // ─── session manager tests ───────────────────────────────────

    fn make_manager(max: usize) -> SessionManager {
        SessionManager::new(max, std::time::Duration::from_secs(1800))
    }

    fn uid(s: &str) -> UserId {
        UserId(s.to_string())
    }
    fn pid(s: &str) -> ProjectId {
        ProjectId(s.to_string())
    }

    #[test]
    fn session_create_and_get() {
        let mut mgr = make_manager(10);
        let id = mgr
            .create_session(uid("alice"), pid("proj-a"), Role::Viewer)
            .unwrap();
        let sess = mgr.get_session(&id).unwrap();
        assert_eq!(sess.id, id);
        assert_eq!(sess.user, uid("alice"));
        assert_eq!(sess.role, Role::Viewer);
        assert_eq!(sess.state, ManagedSessionState::Active);
    }

    #[test]
    fn session_max_cap_enforced() {
        let mut mgr = make_manager(2);
        mgr.create_session(uid("u1"), pid("p"), Role::Viewer)
            .unwrap();
        mgr.create_session(uid("u2"), pid("p"), Role::Viewer)
            .unwrap();
        let err = mgr
            .create_session(uid("u3"), pid("p"), Role::Viewer)
            .unwrap_err();
        assert_eq!(err, SessionError::MaxSessionsReached);
    }

    #[test]
    fn session_terminated_slot_is_not_counted() {
        let mut mgr = make_manager(2);
        let id1 = mgr
            .create_session(uid("u1"), pid("p"), Role::Viewer)
            .unwrap();
        mgr.create_session(uid("u2"), pid("p"), Role::Viewer)
            .unwrap();
        // Terminate one slot, then the cap should allow a new creation.
        mgr.terminate_session(&id1).unwrap();
        assert_eq!(mgr.active_count(), 1);
        mgr.create_session(uid("u3"), pid("p"), Role::Owner)
            .unwrap();
        assert_eq!(mgr.active_count(), 2);
    }

    #[test]
    fn session_terminate_unknown_errors() {
        let mut mgr = make_manager(10);
        let fake = SessionId("does-not-exist".to_string());
        assert_eq!(mgr.terminate_session(&fake), Err(SessionError::NotFound));
    }

    #[test]
    fn session_double_terminate_errors() {
        let mut mgr = make_manager(10);
        let id = mgr
            .create_session(uid("alice"), pid("p"), Role::Owner)
            .unwrap();
        mgr.terminate_session(&id).unwrap();
        assert_eq!(
            mgr.terminate_session(&id),
            Err(SessionError::AlreadyTerminated)
        );
    }

    #[test]
    fn session_touch_updates_last_active() {
        let mut mgr = make_manager(10);
        let id = mgr
            .create_session(uid("alice"), pid("p"), Role::Maintainer)
            .unwrap();
        // Back-date the session.
        mgr.sessions.get_mut(&id).unwrap().last_active = 1_000_000;
        mgr.touch_session(&id).unwrap();
        let sess = mgr.get_session(&id).unwrap();
        // last_active should now be close to now, not 1_000_000.
        assert!(sess.last_active > 1_000_000);
        assert_eq!(sess.state, ManagedSessionState::Active);
    }

    #[test]
    fn session_touch_on_terminated_errors() {
        let mut mgr = make_manager(10);
        let id = mgr
            .create_session(uid("alice"), pid("p"), Role::Owner)
            .unwrap();
        mgr.terminate_session(&id).unwrap();
        assert_eq!(mgr.touch_session(&id), Err(SessionError::AlreadyTerminated));
    }

    #[test]
    fn reap_idle_sessions_terminates_old_sessions() {
        let mut mgr = SessionManager::new(10, std::time::Duration::from_secs(600));
        let id_old = mgr
            .create_session(uid("alice"), pid("p"), Role::Viewer)
            .unwrap();
        let id_new = mgr
            .create_session(uid("bob"), pid("p"), Role::Viewer)
            .unwrap();

        // Back-date alice's session to be older than the 600 s timeout.
        mgr.sessions.get_mut(&id_old).unwrap().last_active = now_secs() - 700;
        // bob's session remains fresh (default last_active = now).

        let reaped = mgr.reap_idle_sessions();
        assert_eq!(reaped.len(), 1);
        assert_eq!(reaped[0], id_old);
        assert_eq!(
            mgr.get_session(&id_old).unwrap().state,
            ManagedSessionState::Terminated
        );
        assert_eq!(
            mgr.get_session(&id_new).unwrap().state,
            ManagedSessionState::Active
        );
        assert_eq!(mgr.active_count(), 1);
    }

    #[test]
    fn reap_does_not_touch_already_terminated() {
        let mut mgr = SessionManager::new(10, std::time::Duration::from_secs(60));
        let id = mgr
            .create_session(uid("u"), pid("p"), Role::Viewer)
            .unwrap();
        mgr.sessions.get_mut(&id).unwrap().last_active = now_secs() - 200;
        mgr.terminate_session(&id).unwrap();
        // Already terminated; reap should report 0 newly reaped.
        let reaped = mgr.reap_idle_sessions();
        assert!(reaped.is_empty());
    }

    // ─── RBAC tests ───────────────────────────────────────────────

    #[test]
    fn rbac_all_role_action_combinations() {
        let policy = RbacPolicy::default();
        // (role, action, expected)
        let matrix: &[(Role, Action, bool)] = &[
            // Owner can do everything.
            (Role::Owner, Action::Read, true),
            (Role::Owner, Action::Write, true),
            (Role::Owner, Action::Execute, true),
            (Role::Owner, Action::Admin, true),
            // Maintainer: Read/Write/Execute but not Admin.
            (Role::Maintainer, Action::Read, true),
            (Role::Maintainer, Action::Write, true),
            (Role::Maintainer, Action::Execute, true),
            (Role::Maintainer, Action::Admin, false),
            // Viewer: Read only.
            (Role::Viewer, Action::Read, true),
            (Role::Viewer, Action::Write, false),
            (Role::Viewer, Action::Execute, false),
            (Role::Viewer, Action::Admin, false),
        ];
        for (role, action, expected) in matrix {
            assert_eq!(
                policy.can(role, action),
                *expected,
                "{:?} + {:?} should be {}",
                role,
                action,
                expected
            );
        }
    }

    #[test]
    fn rbac_check_ok_for_permitted_action() {
        let policy = RbacPolicy::default();
        let sess = ManagedSession {
            id: SessionId("s1".to_string()),
            user: uid("alice"),
            project: pid("p"),
            role: Role::Maintainer,
            created_at: 0,
            last_active: 0,
            state: ManagedSessionState::Active,
        };
        assert!(policy.check(&sess, &Action::Write).is_ok());
    }

    #[test]
    fn rbac_check_denied_for_forbidden_action() {
        let policy = RbacPolicy::default();
        let sess = ManagedSession {
            id: SessionId("s2".to_string()),
            user: uid("bob"),
            project: pid("p"),
            role: Role::Viewer,
            created_at: 0,
            last_active: 0,
            state: ManagedSessionState::Active,
        };
        let err = policy.check(&sess, &Action::Write).unwrap_err();
        assert_eq!(err.role, Role::Viewer);
        assert_eq!(err.action, Action::Write);
    }

    // ─── audit log tests ──────────────────────────────────────────

    fn make_entry(session_id: &str, user: &str, action: &str, ts: u64, ok: bool) -> AuditEntry {
        AuditEntry {
            timestamp: ts,
            session_id: session_id.to_string(),
            user: user.to_string(),
            action: action.to_string(),
            result: if ok {
                AuditResult::Allowed
            } else {
                AuditResult::Denied("forbidden".to_string())
            },
        }
    }

    #[test]
    fn audit_log_record_and_entries_for_session() {
        let mut log = AuditLog::new();
        log.record(make_entry("s1", "alice", "Read", 100, true));
        log.record(make_entry("s2", "bob", "Write", 200, false));
        log.record(make_entry("s1", "alice", "Execute", 300, true));

        let s1 = log.entries_for_session("s1");
        assert_eq!(s1.len(), 2);
        assert_eq!(s1[0].action, "Read");
        assert_eq!(s1[1].action, "Execute");

        let s2 = log.entries_for_session("s2");
        assert_eq!(s2.len(), 1);
        assert!(matches!(s2[0].result, AuditResult::Denied(_)));
    }

    #[test]
    fn audit_log_entries_since() {
        let mut log = AuditLog::new();
        log.record(make_entry("s1", "alice", "Read", 100, true));
        log.record(make_entry("s1", "alice", "Write", 500, true));
        log.record(make_entry("s1", "alice", "Admin", 1000, false));

        let since_400 = log.entries_since(400);
        assert_eq!(since_400.len(), 2);
        assert_eq!(since_400[0].timestamp, 500);
        assert_eq!(since_400[1].timestamp, 1000);

        let since_1000 = log.entries_since(1000);
        assert_eq!(since_1000.len(), 1);

        let since_9999 = log.entries_since(9999);
        assert!(since_9999.is_empty());
    }

    #[test]
    fn audit_log_is_append_only() {
        let mut log = AuditLog::new();
        for i in 0..5 {
            log.record(make_entry("s1", "alice", "Read", i * 100, true));
        }
        assert_eq!(log.entries_for_session("s1").len(), 5);
        // Verify entries remain in insertion order.
        let entries = log.entries_for_session("s1");
        let timestamps: Vec<u64> = entries.iter().map(|e| e.timestamp).collect();
        assert_eq!(timestamps, vec![0, 100, 200, 300, 400]);
    }
}
