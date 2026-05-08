// AGOS Kernel — Error Types
// Canonical error enum for all kernel operations.

use thiserror::Error;

use crate::memory::pager::PageId;

#[derive(Error, Debug)]
pub enum KernelError {
    #[error("Page not found: {0}")]
    PageNotFound(PageId),

    #[error("Page fault: page {0} is in cold storage")]
    PageFault(PageId),

    #[error("Out of memory: hot storage exhausted")]
    OutOfMemory,

    #[error("Security violation: {0}")]
    SecurityViolation(String),

    #[error("Tool not allowed: {0}")]
    ToolForbidden(String),

    #[error("Invalid argument: {0}")]
    InvalidArgument(String),

    #[error("Agent not found: {0}")]
    AgentNotFound(u64),

    #[error("IPC error: {0}")]
    IpcError(String),

    #[error("Crypto error: {0}")]
    CryptoError(String),

    #[error("IO error: {0}")]
    IoError(#[from] std::io::Error),

    #[error("JSON error: {0}")]
    JsonError(#[from] serde_json::Error),
}

/// Result type alias for kernel operations.
pub type KernelResult<T> = Result<T, KernelError>;
