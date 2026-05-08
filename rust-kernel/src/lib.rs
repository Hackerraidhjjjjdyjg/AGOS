// AGOS Kernel — Library Root
// Exposes all kernel subsystems and C-FFI interface for Go bridge.

pub mod crypto;
pub mod error;
pub mod ipc;
pub mod memory;
pub mod security;

use std::collections::HashMap;
use std::ffi::{CStr, CString};
use std::os::raw::c_char;
use std::sync::OnceLock;

use memory::pager::{Pager, Priority};
use ipc::bus::Bus;
use security::firewall::Firewall;
use crypto::attestation::Attestation;

// ─── Global Kernel State ──────────────────────────────────────────────────────
// Singleton instances accessed by C-FFI functions from Go.
// OnceLock ensures thread-safe one-time initialization.

static PAGER: OnceLock<Pager> = OnceLock::new();
static BUS: OnceLock<Bus> = OnceLock::new();
static FIREWALL: OnceLock<Firewall> = OnceLock::new();
static ATTESTATION: OnceLock<Attestation> = OnceLock::new();

// ─── C-FFI Exports ────────────────────────────────────────────────────────────
// These functions are called by the Go orchestrator via CGo.
// All use extern "C" ABI with C-compatible types.

/// Initialize the kernel with the given capacity (bytes) and manifest JSON.
#[no_mangle]
pub extern "C" fn agos_kernel_init(capacity_mb: u32, manifest_json: *const c_char) -> i32 {
    env_logger::try_init().ok();

    let capacity = (capacity_mb as usize) * 1024 * 1024;
    PAGER.get_or_init(|| Pager::new(capacity));
    BUS.get_or_init(|| Bus::new(1024));
    ATTESTATION.get_or_init(Attestation::new);

    // Parse manifest JSON.
    if !manifest_json.is_null() {
        let json_str = unsafe { CStr::from_ptr(manifest_json).to_string_lossy().into_owned() };
        match Firewall::from_json(&json_str) {
            Ok(fw) => { FIREWALL.get_or_init(|| fw); }
            Err(e) => {
                log::error!("Failed to load manifest: {}", e);
                FIREWALL.get_or_init(Firewall::default_deny);
                return -1;
            }
        }
    } else {
        FIREWALL.get_or_init(Firewall::default_deny);
    }

    log::info!("AGOS Kernel initialized: capacity={}MB", capacity_mb);
    0 // Success
}

/// Allocate a memory page for an agent.
#[no_mangle]
pub extern "C" fn agos_page_in(agent_id: u64, data: *const u8, data_len: u32, priority: u8) -> i64 {
    let pager = match PAGER.get() {
        Some(p) => p,
        None => return -1,
    };

    let data_slice = unsafe { std::slice::from_raw_parts(data, data_len as usize) };
    let pri = match priority {
        0 => Priority::Critical,
        1 => Priority::Hardware,
        2 => Priority::User,
        3 => Priority::System,
        _ => Priority::Background,
    };

    match pager.page_in(agent_id, data_slice.to_vec(), pri) {
        Ok(page_id) => page_id as i64,
        Err(_) => -1,
    }
}

/// Page in data for an EXISTING page ID (reloading from cold storage).
#[no_mangle]
pub extern "C" fn agos_page_in_with_id(page_id: u64, agent_id: u64, data: *const u8, data_len: u32, priority: u8) -> i32 {
    let pager = match PAGER.get() {
        Some(p) => p,
        None => return -1,
    };

    let data_slice = unsafe { std::slice::from_raw_parts(data, data_len as usize) };
    let pri = match priority {
        0 => Priority::Critical,
        1 => Priority::Hardware,
        2 => Priority::User,
        3 => Priority::System,
        _ => Priority::Background,
    };

    // Use a modified pager call or ensure pager handles ID reuse (AGOS kernel specific)
    match pager.page_in_with_id(page_id, agent_id, data_slice.to_vec(), pri) {
        Ok(_) => 0,
        Err(_) => -1,
    }
}

/// Represents a data buffer returned from the kernel.
#[repr(C)]
pub struct KernelBuffer {
    pub data: *mut u8,
    pub len: u32,
}

/// Evict a page to cold storage. Returns KernelBuffer. 
/// Caller MUST free the buffer using agos_free_buffer.
#[no_mangle]
pub extern "C" fn agos_page_out(page_id: u64) -> KernelBuffer {
    let pager = match PAGER.get() {
        Some(p) => p,
        None => return KernelBuffer { data: std::ptr::null_mut(), len: 0 },
    };

    match pager.page_out(page_id) {
        Ok(data) => {
            let mut boxed_slice = data.into_boxed_slice();
            let len = boxed_slice.len() as u32;
            let data_ptr = boxed_slice.as_mut_ptr();
            std::mem::forget(boxed_slice); // Hand over ownership to C-FFI
            KernelBuffer { data: data_ptr, len }
        }
        Err(_) => KernelBuffer { data: std::ptr::null_mut(), len: 0 },
    }
}

/// Free a buffer allocated by the kernel.
#[no_mangle]
pub extern "C" fn agos_free_buffer(data: *mut u8, len: u32) {
    if !data.is_null() {
        unsafe {
            let _ = Box::from_raw(std::slice::from_raw_parts_mut(data, len as usize));
        }
    }
}

/// Publish a message to the IPC bus. Returns message ID or -1.
#[no_mangle]
pub extern "C" fn agos_ipc_publish(sender: u64, topic: *const c_char, data: *const u8, data_len: u32) -> i64 {
    let bus = match BUS.get() {
        Some(b) => b,
        None => return -1,
    };

    let topic_str = unsafe { CStr::from_ptr(topic).to_string_lossy().into_owned() };
    let data_slice = unsafe { std::slice::from_raw_parts(data, data_len as usize) };

    match bus.publish(sender, &topic_str, data_slice.to_vec()) {
        Ok(msg_id) => msg_id as i64,
        Err(_) => -1,
    }
}

/// Validate a tool action against the firewall. Returns 0 if allowed, -1 if blocked.
#[no_mangle]
pub extern "C" fn agos_firewall_validate(agent_id: u64, tool: *const c_char, args_json: *const c_char) -> i32 {
    let fw = match FIREWALL.get() {
        Some(f) => f,
        None => return -1,
    };

    let tool_str = unsafe { CStr::from_ptr(tool).to_string_lossy().into_owned() };
    let args_str = unsafe { CStr::from_ptr(args_json).to_string_lossy().into_owned() };

    let args: HashMap<String, String> = serde_json::from_str(&args_str).unwrap_or_default();

    match fw.validate(agent_id, &tool_str, &args) {
        Ok(()) => 0,
        Err(_) => -1,
    }
}

/// Register an agent. Returns agent ID.
#[no_mangle]
pub extern "C" fn agos_register_agent(name: *const c_char) -> u64 {
    let att = match ATTESTATION.get() {
        Some(a) => a,
        None => return 0,
    };

    let name_str = unsafe { CStr::from_ptr(name).to_string_lossy().into_owned() };
    att.register_agent(&name_str, vec![])
}

/// Get kernel version string. Caller must free the returned pointer.
#[no_mangle]
pub extern "C" fn agos_kernel_version() -> *mut c_char {
    let version = CString::new("AGOS Kernel v0.1.0 (Rust)").unwrap();
    version.into_raw()
}

/// Free a string allocated by the kernel.
#[no_mangle]
pub extern "C" fn agos_free_string(ptr: *mut c_char) {
    if !ptr.is_null() {
        unsafe { drop(CString::from_raw(ptr)); }
    }
}

