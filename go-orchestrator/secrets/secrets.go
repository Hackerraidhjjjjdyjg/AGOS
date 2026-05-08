// AGOS Go — Secrets Manager (macOS Keychain + Env)
package secrets

import (
	"fmt"
	"log"
	"os"
	"os/exec"
	"strings"
)

// Manager handles secret storage and retrieval.
type Manager struct {
	prefix string
}

// New creates a secrets manager.
func New(prefix string) *Manager {
	return &Manager{prefix: prefix}
}

// Get retrieves a secret: Keychain first, then env var.
func (m *Manager) Get(key string) (string, error) {
	// 1. Try macOS Keychain
	val, err := m.keychainGet(key)
	if err == nil && val != "" {
		return val, nil
	}

	// 2. Fall back to environment variable
	envKey := fmt.Sprintf("%s_%s", strings.ToUpper(m.prefix), strings.ToUpper(key))
	val = os.Getenv(envKey)
	if val != "" {
		return val, nil
	}

	return "", fmt.Errorf("secret '%s' not found in Keychain or env (%s)", key, envKey)
}

// Set stores a secret in macOS Keychain.
func (m *Manager) Set(key, value string) error {
	service := fmt.Sprintf("%s-%s", m.prefix, key)
	// Delete existing
	exec.Command("security", "delete-generic-password", "-s", service).Run()
	// Add new
	cmd := exec.Command("security", "add-generic-password",
		"-s", service,
		"-a", m.prefix,
		"-w", value,
		"-U",
	)
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("keychain set failed: %w", err)
	}
	log.Printf("[SECRETS] Stored '%s' in Keychain", key)
	return nil
}

// Delete removes a secret from Keychain.
func (m *Manager) Delete(key string) error {
	service := fmt.Sprintf("%s-%s", m.prefix, key)
	return exec.Command("security", "delete-generic-password", "-s", service).Run()
}

// keychainGet reads from macOS Keychain.
func (m *Manager) keychainGet(key string) (string, error) {
	service := fmt.Sprintf("%s-%s", m.prefix, key)
	out, err := exec.Command("security", "find-generic-password",
		"-s", service,
		"-w",
	).Output()
	if err != nil {
		return "", err
	}
	return strings.TrimSpace(string(out)), nil
}

// MustGet retrieves a secret or panics.
func (m *Manager) MustGet(key string) string {
	val, err := m.Get(key)
	if err != nil {
		log.Fatalf("[SECRETS] FATAL: %v", err)
	}
	return val
}

// Required keys for AGOS
var RequiredSecrets = []string{
	"groq_api_key",
	"jwt_secret",
	"postgres_password",
	"redis_password",
	"stripe_secret_key",
}
