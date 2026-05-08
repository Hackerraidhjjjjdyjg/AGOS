// AGOS Kernel — Agent Identity & Attestation
// Ed25519 signing for agent identity, capability tokens, and cryptographic audit trails.

use ed25519_dalek::{Signer, SigningKey, Verifier, VerifyingKey};
use parking_lot::RwLock;
use rand::rngs::OsRng;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::sync::Arc;

use crate::error::KernelError;
use crate::memory::pager::AgentId;

/// Capability token granting an agent specific permissions.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CapabilityToken {
    pub agent_id: AgentId,
    pub capabilities: Vec<String>,
    pub issued_at: u64,
    pub expires_at: u64,
    pub signature: Vec<u8>,
}

/// Registered agent identity.
#[derive(Debug, Clone)]
pub struct AgentIdentity {
    pub agent_id: AgentId,
    pub name: String,
    pub public_key: Vec<u8>,
    pub registered_at: u64,
    pub capabilities: Vec<String>,
}

/// The Attestation service — manages agent identities and capability tokens.
pub struct Attestation {
    /// Kernel signing key (Ed25519).
    kernel_key: SigningKey,
    /// Kernel verifying key (public).
    kernel_pub: VerifyingKey,
    /// Registered agent identities.
    agents: Arc<RwLock<HashMap<AgentId, AgentIdentity>>>,
    /// Next agent ID counter.
    next_id: Arc<RwLock<AgentId>>,
}

impl Attestation {
    /// Create a new attestation service with a fresh kernel keypair.
    pub fn new() -> Self {
        let mut csprng = OsRng;
        let kernel_key = SigningKey::generate(&mut csprng);
        let kernel_pub = kernel_key.verifying_key();
        log::info!("Attestation initialized: kernel pubkey={:?}", &kernel_pub.as_bytes()[..8]);
        Attestation {
            kernel_key,
            kernel_pub,
            agents: Arc::new(RwLock::new(HashMap::new())),
            next_id: Arc::new(RwLock::new(1)),
        }
    }

    /// Register a new agent. Returns its assigned AgentId.
    pub fn register_agent(&self, name: &str, capabilities: Vec<String>) -> AgentId {
        let agent_id = {
            let mut id = self.next_id.write();
            let aid = *id;
            *id += 1;
            aid
        };

        // Generate a keypair for the agent.
        let mut csprng = OsRng;
        let agent_key = SigningKey::generate(&mut csprng);

        let identity = AgentIdentity {
            agent_id,
            name: name.to_string(),
            public_key: agent_key.verifying_key().as_bytes().to_vec(),
            registered_at: Self::now_ts(),
            capabilities,
        };

        let mut agents = self.agents.write();
        agents.insert(agent_id, identity);

        log::info!("Agent registered: id={} name='{}'", agent_id, name);
        agent_id
    }

    /// Issue a capability token for an agent.
    pub fn issue_token(
        &self,
        agent_id: AgentId,
        capabilities: Vec<String>,
        ttl_seconds: u64,
    ) -> Result<CapabilityToken, KernelError> {
        // Verify agent exists.
        {
            let agents = self.agents.read();
            if !agents.contains_key(&agent_id) {
                return Err(KernelError::AgentNotFound(agent_id));
            }
        }

        let now = Self::now_ts();
        let expires_at = now + (ttl_seconds * 1_000_000); // Microseconds

        // Create token payload for signing.
        let payload = format!(
            "{}:{}:{}:{}",
            agent_id,
            capabilities.join(","),
            now,
            expires_at
        );
        let payload_hash = Sha256::digest(payload.as_bytes());

        // Sign with kernel key.
        let signature = self.kernel_key.sign(&payload_hash);

        Ok(CapabilityToken {
            agent_id,
            capabilities,
            issued_at: now,
            expires_at,
            signature: signature.to_bytes().to_vec(),
        })
    }

    /// Verify a capability token is valid and not expired.
    pub fn verify_token(&self, token: &CapabilityToken) -> Result<bool, KernelError> {
        let now = Self::now_ts();
        if now > token.expires_at {
            return Err(KernelError::SecurityViolation("Token expired".into()));
        }

        // Reconstruct payload hash.
        let payload = format!(
            "{}:{}:{}:{}",
            token.agent_id,
            token.capabilities.join(","),
            token.issued_at,
            token.expires_at
        );
        let payload_hash = Sha256::digest(payload.as_bytes());

        // Verify signature.
        let sig_bytes: [u8; 64] = token
            .signature
            .clone()
            .try_into()
            .map_err(|_| KernelError::CryptoError("Invalid signature length".into()))?;

        let signature = ed25519_dalek::Signature::from_bytes(&sig_bytes);

        self.kernel_pub
            .verify(&payload_hash, &signature)
            .map_err(|_| KernelError::CryptoError("Signature verification failed".into()))?;

        Ok(true)
    }

    /// Check if an agent has a specific capability.
    pub fn has_capability(&self, agent_id: AgentId, capability: &str) -> bool {
        let agents = self.agents.read();
        agents
            .get(&agent_id)
            .map(|a| a.capabilities.contains(&capability.to_string()))
            .unwrap_or(false)
    }

    /// Get agent identity by ID.
    pub fn get_agent(&self, agent_id: AgentId) -> Option<AgentIdentity> {
        let agents = self.agents.read();
        agents.get(&agent_id).cloned()
    }

    /// List all registered agents.
    pub fn list_agents(&self) -> Vec<AgentIdentity> {
        let agents = self.agents.read();
        agents.values().cloned().collect()
    }

    /// Get kernel public key bytes (for external verification).
    pub fn kernel_public_key(&self) -> Vec<u8> {
        self.kernel_pub.as_bytes().to_vec()
    }

    fn now_ts() -> u64 {
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_micros() as u64
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_register_agent() {
        let att = Attestation::new();
        let id = att.register_agent("test-agent", vec!["read".into(), "write".into()]);
        assert_eq!(id, 1);
        
        let identity = att.get_agent(id).unwrap();
        assert_eq!(identity.name, "test-agent");
        assert_eq!(identity.capabilities.len(), 2);
    }

    #[test]
    fn test_issue_and_verify_token() {
        let att = Attestation::new();
        let id = att.register_agent("agent-a", vec!["execute".into()]);
        
        let token = att.issue_token(id, vec!["execute".into()], 3600).unwrap();
        assert!(att.verify_token(&token).is_ok());
    }

    #[test]
    fn test_expired_token() {
        let att = Attestation::new();
        let id = att.register_agent("agent-b", vec![]);
        
        let mut token = att.issue_token(id, vec![], 3600).unwrap();
        token.expires_at = 0; // Force expiry.
        assert!(att.verify_token(&token).is_err());
    }

    #[test]
    fn test_capability_check() {
        let att = Attestation::new();
        let id = att.register_agent("agent-c", vec!["read".into(), "search".into()]);
        
        assert!(att.has_capability(id, "read"));
        assert!(att.has_capability(id, "search"));
        assert!(!att.has_capability(id, "delete"));
    }

    #[test]
    fn test_unknown_agent_token() {
        let att = Attestation::new();
        assert!(att.issue_token(999, vec![], 3600).is_err());
    }

    #[test]
    fn test_list_agents() {
        let att = Attestation::new();
        att.register_agent("a1", vec![]);
        att.register_agent("a2", vec![]);
        att.register_agent("a3", vec![]);
        
        assert_eq!(att.list_agents().len(), 3);
    }
}
