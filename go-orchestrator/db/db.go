// AGOS Go — Standardized V4 Database Models
package db

import (
	"os"
	"strconv"
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

func DefaultConfig() Config {
	port := 5432
	if p := os.Getenv("AGOS_DB_PORT"); p != "" {
		if v, err := strconv.Atoi(p); err == nil {
			port = v
		}
	}
	return Config{
		Host:     envOrDefault("AGOS_DB_HOST", "localhost"),
		Port:     port,
		User:     envOrDefault("AGOS_DB_USER", "agos"),
		Password: os.Getenv("AGOS_DB_PASSWORD"),
		DBName:   envOrDefault("AGOS_DB_NAME", "agos_db"),
		SSLMode:  envOrDefault("AGOS_DB_SSLMODE", "disable"),
		MaxConns: 20,
	}
}

func envOrDefault(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
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
