// Module Boundary: remote/
// pccx-remote: secure backend daemon for Phase 3.
//
// Scaffold only.  The real implementation stack — WireGuard / QUIC
// tunnel, OIDC SSO + hardware 2FA, per-user RBAC, audit log, session
// sandbox — lands during Phase 3 after the core workspace has
// stabilised.  Landing the crate now keeps the dependency graph
// coherent and gives downstream Cargo resolution a stable member list.

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
