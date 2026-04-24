// Module Boundary: core/plugin
// pccx-core plugin scaffold.
//
// Phase 1 M1.3 — minimum viable plugin-registry primitive that every
// pccx-lab crate can hang its trait-object plugins off.  The actual
// dylib-loading machinery (libloading + C ABI `register()` symbol +
// safe drop on unload) lands during Phase 2/4 once a real plugin
// ships.  Until then the registry is an in-process Vec<Box<dyn T>>.
//
// SEMVER NOTE: unstable until pccx-lab v0.3.

/// Plugin ABI version.  Bumped whenever the registry contract changes
/// in a way that breaks out-of-tree dylibs.  Hosts MUST refuse to load
/// plugins that declare a different value.
pub const PLUGIN_API_VERSION: u32 = 1;

/// Shared metadata every plugin exposes to the registry.  Intentionally
/// &'static str — dylibs provide these as link-time constants so the
/// host can inspect them without allocating or copying.
#[derive(Debug, Clone, Copy)]
pub struct PluginMetadata {
    /// Stable plugin identifier (e.g. `"markdown"`, `"html-furo"`).
    pub id: &'static str,
    /// ABI version the plugin was built against.  Must equal
    /// `PLUGIN_API_VERSION` or the host rejects the plugin.
    pub api_version: u32,
    /// One-line human-readable description.
    pub description: &'static str,
}

/// Supertrait every registrable plugin implements.  Kept separate from
/// the concrete trait objects (ReportFormat, VerificationGate, …) so a
/// single registry can house multiple plugin kinds if needed.
pub trait Plugin {
    fn metadata(&self) -> PluginMetadata;
}

/// Simple in-process plugin registry.  Plugins of type `P` land here
/// via `register`; callers iterate via `all` or look up by id with
/// `find`.  Thread-safety is the caller's responsibility — wrap in a
/// `Mutex` / `RwLock` when shared across threads.
pub struct PluginRegistry<P: Plugin> {
    plugins: Vec<P>,
}

impl<P: Plugin> PluginRegistry<P> {
    pub fn new() -> Self {
        Self { plugins: Vec::new() }
    }

    /// Register a plugin.  Returns an error only if the plugin declares
    /// a mismatched API version.  Duplicate ids are permitted — first
    /// registration wins on `find`.
    pub fn register(&mut self, plugin: P) -> Result<(), PluginError> {
        let meta = plugin.metadata();
        if meta.api_version != PLUGIN_API_VERSION {
            return Err(PluginError::ApiMismatch {
                expected: PLUGIN_API_VERSION,
                got: meta.api_version,
                id: meta.id,
            });
        }
        self.plugins.push(plugin);
        Ok(())
    }

    pub fn all(&self) -> &[P] {
        &self.plugins
    }

    pub fn find(&self, id: &str) -> Option<&P> {
        self.plugins.iter().find(|p| p.metadata().id == id)
    }

    pub fn len(&self) -> usize {
        self.plugins.len()
    }

    pub fn is_empty(&self) -> bool {
        self.plugins.is_empty()
    }
}

impl<P: Plugin> Default for PluginRegistry<P> {
    fn default() -> Self {
        Self::new()
    }
}

/// Error surface.  `ApiMismatch` is the only runtime error today; dylib
/// load failures (symbol missing, ABI mismatch on the C side, unload
/// panic) land here when the Phase 2/4 loader arrives.
#[derive(Debug, Clone, thiserror::Error)]
pub enum PluginError {
    #[error("plugin '{id}' declares API version {got}; host expects {expected}")]
    ApiMismatch {
        expected: u32,
        got: u32,
        id: &'static str,
    },
}

#[cfg(test)]
mod tests {
    use super::*;

    struct DummyPlugin {
        id: &'static str,
        api_version: u32,
    }

    impl Plugin for DummyPlugin {
        fn metadata(&self) -> PluginMetadata {
            PluginMetadata {
                id: self.id,
                api_version: self.api_version,
                description: "test plugin",
            }
        }
    }

    #[test]
    fn register_accepts_matching_api_version() {
        let mut reg = PluginRegistry::<DummyPlugin>::new();
        assert!(reg
            .register(DummyPlugin { id: "a", api_version: PLUGIN_API_VERSION })
            .is_ok());
        assert_eq!(reg.len(), 1);
    }

    #[test]
    fn register_rejects_mismatched_api_version() {
        let mut reg = PluginRegistry::<DummyPlugin>::new();
        let err = reg
            .register(DummyPlugin { id: "a", api_version: 999 })
            .unwrap_err();
        match err {
            PluginError::ApiMismatch { expected, got, id } => {
                assert_eq!(expected, PLUGIN_API_VERSION);
                assert_eq!(got, 999);
                assert_eq!(id, "a");
            }
        }
    }

    #[test]
    fn find_returns_first_registered() {
        let mut reg = PluginRegistry::<DummyPlugin>::new();
        reg.register(DummyPlugin { id: "a", api_version: PLUGIN_API_VERSION }).unwrap();
        reg.register(DummyPlugin { id: "b", api_version: PLUGIN_API_VERSION }).unwrap();
        assert!(reg.find("a").is_some());
        assert!(reg.find("b").is_some());
        assert!(reg.find("missing").is_none());
    }

    #[test]
    fn all_returns_every_registered_plugin_in_order() {
        let mut reg = PluginRegistry::<DummyPlugin>::new();
        for id in ["one", "two", "three"] {
            reg.register(DummyPlugin { id, api_version: PLUGIN_API_VERSION }).unwrap();
        }
        let ids: Vec<&str> = reg.all().iter().map(|p| p.metadata().id).collect();
        assert_eq!(ids, vec!["one", "two", "three"]);
    }
}
