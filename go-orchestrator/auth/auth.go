// AGOS Go — Auth Service
// OAuth2, JWT, API key management.

package auth

import (
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/hex"
	"fmt"
	"log"
	"strings"
	"time"

	"golang.org/x/crypto/bcrypt"
)

// User represents a registered user.
type User struct {
	ID            string    `json:"id"`
	Email         string    `json:"email"`
	DisplayName   string    `json:"display_name"`
	Role          string    `json:"role"`
	Tier          string    `json:"tier"`
	AuthProvider  string    `json:"auth_provider"`
	IsActive      bool      `json:"is_active"`
	IsVerified    bool      `json:"is_verified"`
	LastLoginAt   time.Time `json:"last_login_at"`
	CreatedAt     time.Time `json:"created_at"`
}

// JWTClaims for access tokens.
type JWTClaims struct {
	UserID    string   `json:"sub"`
	Email     string   `json:"email"`
	Role      string   `json:"role"`
	OrgID     string   `json:"org_id"`
	Scopes    []string `json:"scopes"`
	IssuedAt  int64    `json:"iat"`
	ExpiresAt int64    `json:"exp"`
}

// APIKey represents a developer API key.
type APIKey struct {
	ID        string   `json:"id"`
	KeyPrefix string   `json:"key_prefix"`
	Name      string   `json:"name"`
	Scopes    []string `json:"scopes"`
	RateLimit int      `json:"rate_limit_rpm"`
	UserID    string   `json:"user_id"`
	OrgID     string   `json:"org_id"`
}

// AuthService handles authentication and authorization.
type AuthService struct {
	jwtSecret   []byte
	tokenExpiry time.Duration
}

// NewAuthService creates a new auth service.
func NewAuthService(jwtSecret string) *AuthService {
	return &AuthService{
		jwtSecret:   []byte(jwtSecret),
		tokenExpiry: 24 * time.Hour,
	}
}

// GenerateAPIKey creates a new API key with the format "agos_sk_<random>".
func (a *AuthService) GenerateAPIKey() (plainKey string, keyHash string, prefix string) {
	// Generate 32 bytes of random data.
	b := make([]byte, 32)
	if _, err := rand.Read(b); err != nil {
		log.Fatalf("[AUTH] Failed to generate API key: %v", err)
	}

	plainKey = fmt.Sprintf("agos_sk_%s", hex.EncodeToString(b))
	prefix = plainKey[:12]

	hash := sha256.Sum256([]byte(plainKey))
	keyHash = hex.EncodeToString(hash[:])

	return plainKey, keyHash, prefix
}

// ValidateAPIKeyHash validates a key against its stored SHA-256 hash using a
// constant-time comparison to avoid leaking the hash via timing.
func (a *AuthService) ValidateAPIKeyHash(plainKey string, storedHash string) bool {
	hash := sha256.Sum256([]byte(plainKey))
	computedHash := hex.EncodeToString(hash[:])
	return subtle.ConstantTimeCompare([]byte(computedHash), []byte(storedHash)) == 1
}

// HashPassword hashes a password using bcrypt (DefaultCost).
func (a *AuthService) HashPassword(password string) (string, error) {
	hash, err := bcrypt.GenerateFromPassword([]byte(password), bcrypt.DefaultCost)
	if err != nil {
		return "", fmt.Errorf("hash password: %w", err)
	}
	return string(hash), nil
}

// VerifyPassword reports whether password matches the stored bcrypt hash.
func (a *AuthService) VerifyPassword(password, storedHash string) bool {
	return bcrypt.CompareHashAndPassword([]byte(storedHash), []byte(password)) == nil
}

// CheckPermission verifies if a role has access to an action.
func (a *AuthService) CheckPermission(role string, action string) bool {
	permissions := map[string][]string{
		"admin":     {"*"},
		"developer": {"agents.read", "agents.write", "agents.execute", "tasks.read", "tasks.write", "memory.read", "memory.write"},
		"user":      {"agents.read", "agents.execute", "tasks.read", "tasks.write", "memory.read"},
		"viewer":    {"agents.read", "tasks.read", "memory.read"},
	}

	allowed, ok := permissions[role]
	if !ok {
		return false
	}

	for _, perm := range allowed {
		if perm == "*" || perm == action {
			return true
		}
		// Wildcard matching: "agents.*" matches "agents.read"
		if strings.HasSuffix(perm, ".*") {
			prefix := strings.TrimSuffix(perm, ".*")
			if strings.HasPrefix(action, prefix) {
				return true
			}
		}
	}

	return false
}

// ValidateScope checks if scopes include the required action.
func (a *AuthService) ValidateScope(scopes []string, required string) bool {
	for _, s := range scopes {
		if s == "*" || s == required {
			return true
		}
	}
	return false
}
