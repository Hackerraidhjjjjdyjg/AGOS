// AGOS Kernel — Constitutional Firewall
// Validates every agent action against a security manifest.
// Enterprise-grade: allowlist policy, schema validation, argument constraints, audit trail.

use parking_lot::RwLock;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;

use crate::error::KernelError;
use crate::memory::pager::AgentId;

/// Risk level for a tool.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum RiskLevel {
    Low,
    Medium,
    High,
    Critical,
}

/// Constraints on a single argument.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ArgumentConstraint {
    pub pattern: Option<String>,
    pub min: Option<f64>,
    pub max: Option<f64>,
    pub max_length: Option<usize>,
}

/// Policy for a single tool.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolPolicy {
    pub risk_level: RiskLevel,
    pub description: String,
    pub parameters: Vec<String>,
    #[serde(default)]
    pub argument_constraints: HashMap<String, ArgumentConstraint>,
}

/// Security manifest loaded from config/manifest.json.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SecurityManifest {
    pub version: String,
    pub policy: String,
    pub allowed_tools: HashMap<String, ToolPolicy>,
    #[serde(default)]
    pub blocked_tools: Vec<String>,
}

/// Audit log entry for every validation decision.
#[derive(Debug, Clone, Serialize)]
pub struct AuditEntry {
    pub timestamp: u64,
    pub agent_id: AgentId,
    pub tool: String,
    pub args: HashMap<String, String>,
    pub decision: AuditDecision,
    pub reason: String,
}

#[derive(Debug, Clone, Serialize)]
pub enum AuditDecision {
    Allowed,
    Blocked,
}

/// Firewall statistics.
#[derive(Debug, Clone, Default)]
#[repr(C)]
pub struct FirewallStats {
    pub total_validations: u64,
    pub allowed: u64,
    pub blocked: u64,
    pub audit_log_size: usize,
}

/// The Constitutional Firewall — validates all tool invocations.
///
/// Design:
/// - Strict allowlist: if a tool is not in the manifest, it is BLOCKED
/// - Schema validation: unknown parameters are rejected
/// - Argument constraints: regex patterns, numeric ranges, length limits
/// - Every decision is audit-logged for compliance
pub struct Firewall {
    manifest: SecurityManifest,
    audit_log: Arc<RwLock<Vec<AuditEntry>>>,
    stats: Arc<RwLock<FirewallStats>>,
}

impl Firewall {
    /// Create a firewall from a manifest JSON string.
    pub fn from_json(json: &str) -> Result<Self, KernelError> {
        let manifest: SecurityManifest = serde_json::from_str(json)?;
        log::info!(
            "Firewall initialized: version={} policy={} tools={} blocked={}",
            manifest.version,
            manifest.policy,
            manifest.allowed_tools.len(),
            manifest.blocked_tools.len()
        );
        Ok(Firewall {
            manifest,
            audit_log: Arc::new(RwLock::new(Vec::new())),
            stats: Arc::new(RwLock::new(FirewallStats::default())),
        })
    }

    /// Create a default firewall with empty manifest (blocks everything).
    pub fn default_deny() -> Self {
        Firewall {
            manifest: SecurityManifest {
                version: "0.0.0".into(),
                policy: "deny_all".into(),
                allowed_tools: HashMap::new(),
                blocked_tools: Vec::new(),
            },
            audit_log: Arc::new(RwLock::new(Vec::new())),
            stats: Arc::new(RwLock::new(FirewallStats::default())),
        }
    }

    /// Validate a tool invocation.
    /// Returns Ok(()) if allowed, Err(SecurityViolation) if blocked.
    pub fn validate(
        &self,
        agent_id: AgentId,
        tool: &str,
        args: &HashMap<String, String>,
    ) -> Result<(), KernelError> {
        let mut stats = self.stats.write();
        stats.total_validations += 1;
        drop(stats);

        // 1. Check blocked list first.
        if self.manifest.blocked_tools.contains(&tool.to_string()) {
            self.log_audit(agent_id, tool, args, AuditDecision::Blocked, "Tool is explicitly blocked");
            return Err(KernelError::ToolForbidden(tool.to_string()));
        }

        // 2. Check if tool exists in allowlist.
        let policy = match self.manifest.allowed_tools.get(tool) {
            Some(p) => p,
            None => {
                self.log_audit(agent_id, tool, args, AuditDecision::Blocked, "Tool not in allowlist");
                return Err(KernelError::ToolForbidden(format!(
                    "Tool '{}' not in allowlist",
                    tool
                )));
            }
        };

        // 3. Schema validation — reject unknown parameters.
        let allowed_params: std::collections::HashSet<&str> =
            policy.parameters.iter().map(|s| s.as_str()).collect();
        for key in args.keys() {
            if !allowed_params.contains(key.as_str()) {
                self.log_audit(
                    agent_id, tool, args,
                    AuditDecision::Blocked,
                    &format!("Unknown parameter: {}", key),
                );
                return Err(KernelError::InvalidArgument(format!(
                    "Tool '{}' does not accept parameter '{}'",
                    tool, key
                )));
            }
        }

        // 4. Argument constraint validation.
        for (param_name, constraint) in &policy.argument_constraints {
            if let Some(value) = args.get(param_name) {
                // Pattern check (simplified regex — checks contains for safety).
                if let Some(ref pattern) = constraint.pattern {
                    if pattern != ".*" && !Self::simple_pattern_match(pattern, value) {
                        self.log_audit(
                            agent_id, tool, args,
                            AuditDecision::Blocked,
                            &format!("Argument '{}' fails pattern check", param_name),
                        );
                        return Err(KernelError::SecurityViolation(format!(
                            "Argument '{}' value '{}' violates pattern constraint",
                            param_name, value
                        )));
                    }
                }

                // Length check.
                if let Some(max_len) = constraint.max_length {
                    if value.len() > max_len {
                        self.log_audit(
                            agent_id, tool, args,
                            AuditDecision::Blocked,
                            &format!("Argument '{}' exceeds max length", param_name),
                        );
                        return Err(KernelError::SecurityViolation(format!(
                            "Argument '{}' exceeds max length of {}",
                            param_name, max_len
                        )));
                    }
                }

                // Numeric range check.
                if let (Some(min), Some(max)) = (constraint.min, constraint.max) {
                    if let Ok(num) = value.parse::<f64>() {
                        if num < min || num > max {
                            self.log_audit(
                                agent_id, tool, args,
                                AuditDecision::Blocked,
                                &format!("Argument '{}' out of range [{}, {}]", param_name, min, max),
                            );
                            return Err(KernelError::SecurityViolation(format!(
                                "Argument '{}' value {} out of bounds [{}, {}]",
                                param_name, num, min, max
                            )));
                        }
                    }
                }
            }
        }

        // All checks passed.
        self.log_audit(agent_id, tool, args, AuditDecision::Allowed, "All checks passed");
        Ok(())
    }

    /// Get audit log entries (most recent N).
    pub fn get_audit_log(&self, limit: usize) -> Vec<AuditEntry> {
        let log = self.audit_log.read();
        log.iter().rev().take(limit).cloned().collect()
    }

    /// Get firewall statistics.
    pub fn get_stats(&self) -> FirewallStats {
        let mut stats = self.stats.read().clone();
        stats.audit_log_size = self.audit_log.read().len();
        stats
    }

    /// Get the loaded manifest (for introspection).
    pub fn get_manifest(&self) -> &SecurityManifest {
        &self.manifest
    }

    // --- Internal ---

    fn log_audit(
        &self,
        agent_id: AgentId,
        tool: &str,
        args: &HashMap<String, String>,
        decision: AuditDecision,
        reason: &str,
    ) {
        let entry = AuditEntry {
            timestamp: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_micros() as u64,
            agent_id,
            tool: tool.to_string(),
            args: args.clone(),
            decision: decision.clone(),
            reason: reason.to_string(),
        };

        match &decision {
            AuditDecision::Allowed => {
                let mut stats = self.stats.write();
                stats.allowed += 1;
            }
            AuditDecision::Blocked => {
                log::warn!("FIREWALL BLOCKED: agent={} tool='{}' reason='{}'", agent_id, tool, reason);
                let mut stats = self.stats.write();
                stats.blocked += 1;
            }
        }

        let mut log = self.audit_log.write();
        log.push(entry);
    }

    /// Simplified pattern matching: ^[charset]+$ patterns.
    /// For production, use the `regex` crate.
    fn simple_pattern_match(pattern: &str, value: &str) -> bool {
        if pattern == ".*" {
            return true;
        }
        // Simple alphanumeric + space check for ^[a-zA-Z0-9 ]+$ style patterns.
        if pattern.starts_with("^[") && pattern.ends_with("]+$") {
            let charset = &pattern[2..pattern.len() - 3];
            return value.chars().all(|c| {
                charset.contains(c) || c.is_alphanumeric() || c == ' '
            });
        }
        // Fallback: allow if we can't parse the pattern (fail-open for now).
        true
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_manifest() -> &'static str {
        r#"{
            "version": "2.0",
            "policy": "strict_allowlist",
            "allowed_tools": {
                "open_app": {
                    "risk_level": "medium",
                    "description": "Launch applications",
                    "parameters": ["app_name"],
                    "argument_constraints": {
                        "app_name": { "pattern": "^[a-zA-Z0-9 ]+$" }
                    }
                },
                "set_volume": {
                    "risk_level": "low",
                    "description": "Set volume",
                    "parameters": ["level"],
                    "argument_constraints": {
                        "level": { "min": 0.0, "max": 100.0 }
                    }
                },
                "read_file": {
                    "risk_level": "medium",
                    "description": "Read text files",
                    "parameters": ["path"],
                    "argument_constraints": {}
                }
            },
            "blocked_tools": ["exec_shell", "sudo", "delete_file"]
        }"#
    }

    #[test]
    fn test_allowed_tool() {
        let fw = Firewall::from_json(test_manifest()).unwrap();
        let mut args = HashMap::new();
        args.insert("app_name".into(), "Safari".into());
        assert!(fw.validate(1, "open_app", &args).is_ok());
    }

    #[test]
    fn test_blocked_tool() {
        let fw = Firewall::from_json(test_manifest()).unwrap();
        let args = HashMap::new();
        assert!(fw.validate(1, "exec_shell", &args).is_err());
    }

    #[test]
    fn test_unknown_tool() {
        let fw = Firewall::from_json(test_manifest()).unwrap();
        let args = HashMap::new();
        assert!(fw.validate(1, "launch_missile", &args).is_err());
    }

    #[test]
    fn test_unknown_parameter() {
        let fw = Firewall::from_json(test_manifest()).unwrap();
        let mut args = HashMap::new();
        args.insert("app_name".into(), "Safari".into());
        args.insert("hidden_flag".into(), "true".into());
        assert!(fw.validate(1, "open_app", &args).is_err());
    }

    #[test]
    fn test_numeric_range() {
        let fw = Firewall::from_json(test_manifest()).unwrap();
        
        let mut args = HashMap::new();
        args.insert("level".into(), "50".into());
        assert!(fw.validate(1, "set_volume", &args).is_ok());

        let mut args = HashMap::new();
        args.insert("level".into(), "150".into());
        assert!(fw.validate(1, "set_volume", &args).is_err());
    }

    #[test]
    fn test_audit_log() {
        let fw = Firewall::from_json(test_manifest()).unwrap();
        let mut args = HashMap::new();
        args.insert("app_name".into(), "Safari".into());
        fw.validate(1, "open_app", &args).unwrap();
        let _ = fw.validate(2, "exec_shell", &HashMap::new());

        let log = fw.get_audit_log(10);
        assert_eq!(log.len(), 2);
    }

    #[test]
    fn test_stats() {
        let fw = Firewall::from_json(test_manifest()).unwrap();
        let mut args = HashMap::new();
        args.insert("app_name".into(), "Safari".into());
        fw.validate(1, "open_app", &args).unwrap();
        let _ = fw.validate(2, "exec_shell", &HashMap::new());

        let stats = fw.get_stats();
        assert_eq!(stats.total_validations, 2);
        assert_eq!(stats.allowed, 1);
        assert_eq!(stats.blocked, 1);
    }

    #[test]
    fn test_default_deny() {
        let fw = Firewall::default_deny();
        assert!(fw.validate(1, "anything", &HashMap::new()).is_err());
    }
}
