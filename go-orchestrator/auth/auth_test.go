package auth

import (
	"crypto/sha256"
	"encoding/hex"
	"strings"
	"testing"
)

func TestGenerateAPIKey(t *testing.T) {
	a := NewAuthService("secret")

	plain, hash, prefix := a.GenerateAPIKey()

	if !strings.HasPrefix(plain, "agos_sk_") {
		t.Errorf("plain key = %q, want agos_sk_ prefix", plain)
	}
	// "agos_sk_" (8) + 64 hex chars = 72
	if len(plain) != 72 {
		t.Errorf("plain key length = %d, want 72", len(plain))
	}
	if prefix != plain[:12] {
		t.Errorf("prefix = %q, want %q", prefix, plain[:12])
	}

	want := sha256.Sum256([]byte(plain))
	if hash != hex.EncodeToString(want[:]) {
		t.Error("returned hash does not match sha256 of plain key")
	}
	if !a.ValidateAPIKeyHash(plain, hash) {
		t.Error("generated key should validate against its own hash")
	}
}

func TestGenerateAPIKeyUnique(t *testing.T) {
	a := NewAuthService("secret")
	p1, _, _ := a.GenerateAPIKey()
	p2, _, _ := a.GenerateAPIKey()
	if p1 == p2 {
		t.Error("two generated keys should not be identical")
	}
}

func TestValidateAPIKeyHash(t *testing.T) {
	a := NewAuthService("secret")
	plain, hash, _ := a.GenerateAPIKey()

	if a.ValidateAPIKeyHash("agos_sk_wrong", hash) {
		t.Error("wrong key validated against hash")
	}
	if !a.ValidateAPIKeyHash(plain, hash) {
		t.Error("correct key failed validation")
	}
}

func TestHashPasswordAndVerify(t *testing.T) {
	a := NewAuthService("secret")

	h1, err := a.HashPassword("hunter2")
	if err != nil {
		t.Fatalf("HashPassword error: %v", err)
	}
	h2, err := a.HashPassword("hunter2")
	if err != nil {
		t.Fatalf("HashPassword error: %v", err)
	}
	// bcrypt salts every hash, so the same password yields distinct hashes.
	if h1 == h2 {
		t.Error("bcrypt hashes of the same password should differ (per-hash salt)")
	}
	if !a.VerifyPassword("hunter2", h1) {
		t.Error("correct password should verify against its hash")
	}
	if a.VerifyPassword("different", h1) {
		t.Error("wrong password should not verify")
	}
}

func TestCheckPermission(t *testing.T) {
	a := NewAuthService("secret")

	cases := []struct {
		role   string
		action string
		want   bool
	}{
		{"admin", "anything.at.all", true},
		{"developer", "agents.write", true},
		{"developer", "billing.admin", false},
		{"user", "agents.execute", true},
		{"user", "agents.write", false},
		{"viewer", "memory.read", true},
		{"viewer", "memory.write", false},
		{"nonexistent", "agents.read", false},
	}

	for _, c := range cases {
		if got := a.CheckPermission(c.role, c.action); got != c.want {
			t.Errorf("CheckPermission(%q, %q) = %v, want %v", c.role, c.action, got, c.want)
		}
	}
}

func TestValidateScope(t *testing.T) {
	a := NewAuthService("secret")

	if !a.ValidateScope([]string{"agents.read", "tasks.read"}, "tasks.read") {
		t.Error("expected matching scope to validate")
	}
	if !a.ValidateScope([]string{"*"}, "anything") {
		t.Error("wildcard scope should validate any action")
	}
	if a.ValidateScope([]string{"agents.read"}, "tasks.write") {
		t.Error("missing scope should not validate")
	}
	if a.ValidateScope(nil, "x") {
		t.Error("empty scopes should not validate")
	}
}
