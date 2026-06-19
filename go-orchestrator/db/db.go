// AGOS Go — Standardized V4 Database Models
package db

import (
	"os"
	"time"
)

type Config struct {
	Host     string
	Port     int
	User     string
	Password string
	DBName   string
	SSLMode  string
	MaxConns int
}

func getenvDefault(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

// DefaultConfig builds the Postgres config from the environment. The password
// is read from AGOS_DB_PASSWORD (falling back to POSTGRES_PASSWORD) and is
// never hardcoded; everything else has a sensible local-dev default.
func DefaultConfig() Config {
	return Config{
		Host:     getenvDefault("AGOS_DB_HOST", "localhost"),
		Port:     5432,
		User:     getenvDefault("AGOS_DB_USER", "agos"),
		Password: getenvDefault("AGOS_DB_PASSWORD", os.Getenv("POSTGRES_PASSWORD")),
		DBName:   getenvDefault("AGOS_DB_NAME", "agos_db"),
		SSLMode:  getenvDefault("AGOS_DB_SSLMODE", "disable"),
		MaxConns: 20,
	}
}

type User struct {
	ID          string    `json:"id"`
	Email       string    `json:"email"`
	DisplayName string    `json:"display_name"`
	Role        string    `json:"role"`
	Tier        string    `json:"tier"`
	CreatedAt   time.Time `json:"created_at"`
}

type Task struct {
	ID          string    `json:"id"`
	AgentUUID   string    `json:"agent_uuid"`
	Intent      string    `json:"intent"`
	Status      string    `json:"status"`
	Priority    int       `json:"priority"`
	Output      string    `json:"output"`
	Error       string    `json:"error"`
	TokensUsed  int       `json:"tokens_used"`
	CostUSD     float64   `json:"cost_usd"`
	TTFTMs      int       `json:"ttft_ms"`
	ITLMs       int       `json:"itl_ms"`
	CreatedAt   time.Time `json:"created_at"`
	CompletedAt *time.Time `json:"completed_at"`
}

type AuditEntry struct {
	ID      int    `json:"id"`
	TaskID  string `json:"task_id"`
	Event   string `json:"event"`
	Details string `json:"details"`
	Time    string `json:"time"`
}
