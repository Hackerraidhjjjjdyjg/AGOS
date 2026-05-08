// AGOS Go — Kernel Bridge (CGo FFI)
// Connects Go orchestrator to the Rust kernel via C-FFI.

package kernel

/*
#cgo LDFLAGS: -L../../rust-kernel/target/release -lagos_kernel
#cgo CFLAGS: -I../../rust-kernel

#include <stdlib.h>

typedef struct {
    unsigned char* data;
    unsigned int len;
} KernelBuffer;

extern int agos_kernel_init(unsigned int capacity_mb, const char* manifest_json);
extern long long agos_page_in(unsigned long long agent_id, const unsigned char* data, unsigned int data_len, unsigned char priority);
extern int agos_page_in_with_id(unsigned long long page_id, unsigned long long agent_id, const unsigned char* data, unsigned int data_len, unsigned char priority);
extern KernelBuffer agos_page_out(unsigned long long page_id);
extern void agos_free_buffer(unsigned char* data, unsigned int len);
extern long long agos_ipc_publish(unsigned long long sender, const char* topic, const unsigned char* data, unsigned int data_len);
extern int agos_firewall_validate(unsigned long long agent_id, const char* tool, const char* args_json);
extern unsigned long long agos_register_agent(const char* name);
extern char* agos_kernel_version();
extern void agos_free_string(char* ptr);
*/
import "C"

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"fmt"
	"io"
	"log"
	"os"
	"path/filepath"
	"unsafe"
)

var (
	swapDir = filepath.Join(os.Getenv("HOME"), ".agos", "swap")
	// MASTER_KEY for AES-256-GCM. In production, this would come from KMS/Vault.
	masterKey = []byte("BRUTAL_AGOS_SOVEREIGN_KEY_32BYTE") 
)

func init() {
	os.MkdirAll(swapDir, 0700)
}

// Init initializes the Rust kernel with a capacity and manifest.
func Init(capacityMB uint32, manifestJSON string) error {
	cManifest := C.CString(manifestJSON)
	defer C.free(unsafe.Pointer(cManifest))

	result := C.agos_kernel_init(C.uint(capacityMB), cManifest)
	if result != 0 {
		return fmt.Errorf("kernel init failed with code %d", result)
	}
	log.Printf("[KERNEL] Rust kernel initialized (cap=%dMB)", capacityMB)
	return nil
}

// PageIn allocates a memory page for an agent.
func PageIn(agentID uint64, data []byte, priority uint8) (int64, error) {
	if len(data) == 0 {
		return 0, fmt.Errorf("cannot page in empty data")
	}

	pageID := C.agos_page_in(
		C.ulonglong(agentID),
		(*C.uchar)(unsafe.Pointer(&data[0])),
		C.uint(len(data)),
		C.uchar(priority),
	)

	if pageID < 0 {
		return 0, fmt.Errorf("page_in failed for agent %d", agentID)
	}
	return int64(pageID), nil
}

// PageOut evicts a page from hot to cold storage (disk).
// Encrypts data with AES-256-GCM before writing to ~/.agos/swap/.
func PageOut(pageID uint64) error {
	kBuf := C.agos_page_out(C.ulonglong(pageID))
	if kBuf.data == nil {
		return fmt.Errorf("page_out failed for page %d (kernel returned null)", pageID)
	}
	defer C.agos_free_buffer(kBuf.data, kBuf.len)

	data := C.GoBytes(unsafe.Pointer(kBuf.data), C.int(kBuf.len))
	
	// Encrypt
	encrypted, err := encrypt(data)
	if err != nil {
		return fmt.Errorf("encryption failed for page %d: %v", pageID, err)
	}

	// Persist to disk
	path := filepath.Join(swapDir, fmt.Sprintf("page_%d.bin", pageID))
	if err := os.WriteFile(path, encrypted, 0600); err != nil {
		return fmt.Errorf("persistence failed for page %d: %v", pageID, err)
	}

	log.Printf("[KERNEL] Page %d paged-out, encrypted, and persisted to disk", pageID)
	return nil
}

// PageInWithID reloads a page from disk into hot storage.
func PageInWithID(pageID uint64, agentID uint64, priority uint8) error {
	path := filepath.Join(swapDir, fmt.Sprintf("page_%d.bin", pageID))
	encrypted, err := os.ReadFile(path)
	if err != nil {
		return fmt.Errorf("could not read page %d from disk: %v", pageID, err)
	}

	// Decrypt
	data, err := decrypt(encrypted)
	if err != nil {
		return fmt.Errorf("decryption failed for page %d: %v", pageID, err)
	}

	result := C.agos_page_in_with_id(
		C.ulonglong(pageID),
		C.ulonglong(agentID),
		(*C.uchar)(unsafe.Pointer(&data[0])),
		C.uint(len(data)),
		C.uchar(priority),
	)

	if result != 0 {
		return fmt.Errorf("page_in_with_id failed for page %d", pageID)
	}

	log.Printf("[KERNEL] Page %d reloaded from disk and decrypted", pageID)
	return nil
}

// Publish sends a message on the IPC bus.
func Publish(sender uint64, topic string, data []byte) (int64, error) {
	cTopic := C.CString(topic)
	defer C.free(unsafe.Pointer(cTopic))
	
	var pData *C.uchar
	if len(data) > 0 {
		pData = (*C.uchar)(unsafe.Pointer(&data[0]))
	}

	msgID := C.agos_ipc_publish(
		C.ulonglong(sender),
		cTopic,
		pData,
		C.uint(len(data)),
	)
	
	if msgID < 0 {
		return 0, fmt.Errorf("publish failed on topic %s", topic)
	}
	return int64(msgID), nil
}

// ValidateToolCall checks a tool call against the Constitutional Firewall.
func ValidateToolCall(agentID uint64, toolName, argsJSON string) bool {
	cTool := C.CString(toolName)
	defer C.free(unsafe.Pointer(cTool))
	cArgs := C.CString(argsJSON)
	defer C.free(unsafe.Pointer(cArgs))

	return C.agos_firewall_validate(C.ulonglong(agentID), cTool, cArgs) == 0
}

// RegisterAgent registers an agent with the kernel and returns a kernel-assigned ID.
func RegisterAgent(name string) (uint64, error) {
	cName := C.CString(name)
	defer C.free(unsafe.Pointer(cName))

	agentID := C.agos_register_agent(cName)
	if agentID == 0 {
		return 0, fmt.Errorf("agent registration failed for %s", name)
	}
	log.Printf("[KERNEL] Agent registered: %s (ID: %d)", name, agentID)
	return uint64(agentID), nil
}

// GetVersion returns the kernel version string.
func GetVersion() string {
	cStr := C.agos_kernel_version()
	defer C.agos_free_string(cStr)
	return C.GoString(cStr)
}

// --- Internal Security Helpers ---

func encrypt(data []byte) ([]byte, error) {
	block, err := aes.NewCipher(masterKey)
	if err != nil {
		return nil, err
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, err
	}
	nonce := make([]byte, gcm.NonceSize())
	if _, err := io.ReadFull(rand.Reader, nonce); err != nil {
		return nil, err
	}
	return gcm.Seal(nonce, nonce, data, nil), nil
}

func decrypt(data []byte) ([]byte, error) {
	block, err := aes.NewCipher(masterKey)
	if err != nil {
		return nil, err
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, err
	}
	nonceSize := gcm.NonceSize()
	if len(data) < nonceSize {
		return nil, fmt.Errorf("ciphertext too short")
	}
	nonce, ciphertext := data[:nonceSize], data[nonceSize:]
	return gcm.Open(nil, nonce, ciphertext, nil)
}

