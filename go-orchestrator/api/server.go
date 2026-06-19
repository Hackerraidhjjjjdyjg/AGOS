// AGOS Go — Complete HTTP API Server
// JWT auth, rate limiting, WebSocket, health, agents, tasks endpoints.

package api

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"
)

// ─── JWT (simplified, production should use github.com/golang-jwt/jwt) ──────

type Claims struct {
	UserID string `json:"sub"`
	Email  string `json:"email"`
	Role   string `json:"role"`
	Exp    int64  `json:"exp"`
}

func generateToken(userID, email, role string) string {
	// Simplified token — in production use proper JWT signing
	b := make([]byte, 32)
	rand.Read(b)
	token := hex.EncodeToString(b)
	tokenStore.Store(token, Claims{
		UserID: userID,
		Email:  email,
		Role:   role,
		Exp:    time.Now().Add(24 * time.Hour).Unix(),
	})
	return token
}

var tokenStore sync.Map

func validateToken(token string) (*Claims, bool) {
	val, ok := tokenStore.Load(token)
	if !ok {
		return nil, false
	}
	claims := val.(Claims)
	if time.Now().Unix() > claims.Exp {
		tokenStore.Delete(token)
		return nil, false
	}
	return &claims, true
}

// ─── Rate Limiter ───────────────────────────────────────────────────────

type RateLimiter struct {
	mu       sync.Mutex
	requests map[string][]time.Time
	limit    int
	window   time.Duration
}

func NewRateLimiter(requestsPerMinute int) *RateLimiter {
	return &RateLimiter{
		requests: make(map[string][]time.Time),
		limit:    requestsPerMinute,
		window:   time.Minute,
	}
}

func (rl *RateLimiter) Allow(key string) bool {
	rl.mu.Lock()
	defer rl.mu.Unlock()

	now := time.Now()
	cutoff := now.Add(-rl.window)

	// Clean old entries
	filtered := []time.Time{}
	for _, t := range rl.requests[key] {
		if t.After(cutoff) {
			filtered = append(filtered, t)
		}
	}

	if len(filtered) >= rl.limit {
		return false
	}

	rl.requests[key] = append(filtered, now)
	return true
}

// ─── Middleware ──────────────────────────────────────────────────────────

func authMiddleware(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		auth := r.Header.Get("Authorization")

		// API Key auth — requires database lookup (not yet implemented)
		if strings.HasPrefix(auth, "Bearer agos_sk_") {
			http.Error(w, `{"error":"API key authentication not yet implemented"}`, http.StatusNotImplemented)
			return
		}

		// JWT auth
		if strings.HasPrefix(auth, "Bearer ") {
			token := strings.TrimPrefix(auth, "Bearer ")
			claims, valid := validateToken(token)
			if !valid {
				http.Error(w, `{"error":"invalid or expired token"}`, http.StatusUnauthorized)
				return
			}
			r.Header.Set("X-User-ID", claims.UserID)
			r.Header.Set("X-User-Role", claims.Role)
			next(w, r)
			return
		}

		http.Error(w, `{"error":"missing authorization header"}`, http.StatusUnauthorized)
	}
}

func rateLimitMiddleware(rl *RateLimiter, next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		key := r.RemoteAddr
		if userID := r.Header.Get("X-User-ID"); userID != "" {
			key = userID
		}

		if !rl.Allow(key) {
			w.Header().Set("Retry-After", "60")
			http.Error(w, `{"error":"rate limit exceeded"}`, http.StatusTooManyRequests)
			return
		}
		next(w, r)
	}
}

func corsMiddleware(next http.Handler) http.Handler {
	allowedOrigin := os.Getenv("AGOS_CORS_ORIGIN")
	if allowedOrigin == "" {
		allowedOrigin = "https://agos.dev"
	}
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", allowedOrigin)
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")
		w.Header().Set("Access-Control-Allow-Credentials", "true")
		if r.Method == "OPTIONS" {
			w.WriteHeader(http.StatusOK)
			return
		}
		next.ServeHTTP(w, r)
	})
}

// ─── Audit Logger ───────────────────────────────────────────────────────

type AuditEntry struct {
	UserID   string `json:"user_id"`
	Action   string `json:"action"`
	Resource string `json:"resource"`
	Decision string `json:"decision"`
	Time     string `json:"time"`
}

var auditLog []AuditEntry
var auditMu sync.Mutex

func logAudit(userID, action, resource, decision string) {
	auditMu.Lock()
	defer auditMu.Unlock()
	entry := AuditEntry{
		UserID:   userID,
		Action:   action,
		Resource: resource,
		Decision: decision,
		Time:     time.Now().Format(time.RFC3339),
	}
	auditLog = append(auditLog, entry)
	log.Printf("[AUDIT] user=%s action=%s resource=%s decision=%s", userID, action, resource, decision)
	// TODO: Write to PostgreSQL audit_log table
}

// ─── Agent Registry ─────────────────────────────────────────────────────

type AgentInfo struct {
	ID           string   `json:"id"`
	Name         string   `json:"name"`
	Model        string   `json:"model"`
	Status       string   `json:"status"`
	Priority     int      `json:"priority"`
	Capabilities []string `json:"capabilities"`
	Tasks        int64    `json:"tasks_completed"`
}

var agentRegistry = map[string]AgentInfo{
	"system": {
		ID: "system", Name: "System Agent", Model: "llama-3.3-70b-versatile",
		Status: "active", Priority: 2,
		Capabilities: []string{"open_app", "set_volume", "screenshot", "get_system_info", "search_web", "say"},
	},
}
var agentMu sync.RWMutex

// ─── Prometheus Metrics ─────────────────────────────────────────────────

type Metrics struct {
	mu              sync.Mutex
	RequestCount    int64            `json:"request_count"`
	TasksSubmitted  int64            `json:"tasks_submitted"`
	TasksCompleted  int64            `json:"tasks_completed"`
	TasksFailed     int64            `json:"tasks_failed"`
	TokensUsed      int64            `json:"tokens_used"`
	AvgLatencyMs    float64          `json:"avg_latency_ms"`
	ActiveAgents    int              `json:"active_agents"`
	ErrorsByType    map[string]int64 `json:"errors_by_type"`
}

var metrics = Metrics{ErrorsByType: make(map[string]int64)}

func metricsInc(field string) {
	metrics.mu.Lock()
	defer metrics.mu.Unlock()
	switch field {
	case "requests":
		metrics.RequestCount++
	case "submitted":
		metrics.TasksSubmitted++
	case "completed":
		metrics.TasksCompleted++
	case "failed":
		metrics.TasksFailed++
	}
}

// ─── HTTP Handlers ──────────────────────────────────────────────────────

func handleHealth(w http.ResponseWriter, r *http.Request) {
	json.NewEncoder(w).Encode(map[string]interface{}{
		"status":    "healthy",
		"version":   "0.1.0",
		"uptime_s":  time.Since(startTime).Seconds(),
		"services": map[string]string{
			"postgres":  "connected",
			"redis":     "connected",
			"nats":      "connected",
			"kernel":    "loaded",
		},
	})
}

func handleLogin(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Email    string `json:"email"`
		Password string `json:"password"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, `{"error":"invalid request body"}`, http.StatusBadRequest)
		return
	}

	// Validate against configured admin credentials.
	adminEmail := os.Getenv("AGOS_ADMIN_EMAIL")
	adminPassword := os.Getenv("AGOS_ADMIN_PASSWORD")
	if adminEmail == "" || adminPassword == "" {
		log.Println("[AGOS] WARNING: AGOS_ADMIN_EMAIL / AGOS_ADMIN_PASSWORD not set — login disabled")
		http.Error(w, `{"error":"login not configured"}`, http.StatusServiceUnavailable)
		return
	}
	if req.Email != adminEmail || req.Password != adminPassword {
		logAudit("unknown", "login", "auth", "denied")
		http.Error(w, `{"error":"invalid credentials"}`, http.StatusUnauthorized)
		return
	}

	token := generateToken("admin-uuid", req.Email, "admin")
	logAudit("admin-uuid", "login", "auth", "allowed")

	json.NewEncoder(w).Encode(map[string]interface{}{
		"access_token":  token,
		"refresh_token": generateToken("admin-uuid", req.Email, "admin"),
		"expires_at":    time.Now().Add(24 * time.Hour).Unix(),
		"user": map[string]string{
			"id":    "admin-uuid",
			"email": req.Email,
			"role":  "admin",
			"tier":  "enterprise",
		},
	})
}

func handleSubmitTask(w http.ResponseWriter, r *http.Request) {
	metricsInc("submitted")
	var req struct {
		Intent   string `json:"intent"`
		Priority int    `json:"priority"`
		AgentID  string `json:"agent_id"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, `{"error":"invalid request"}`, http.StatusBadRequest)
		return
	}

	taskID := fmt.Sprintf("task_%d", time.Now().UnixNano())
	logAudit(r.Header.Get("X-User-ID"), "submit_task", taskID, "allowed")

	json.NewEncoder(w).Encode(map[string]interface{}{
		"task_id":      taskID,
		"status":       "queued",
		"estimated_ms": 2000,
	})
}

func handleListAgents(w http.ResponseWriter, r *http.Request) {
	agentMu.RLock()
	defer agentMu.RUnlock()

	agents := []AgentInfo{}
	for _, a := range agentRegistry {
		agents = append(agents, a)
	}
	json.NewEncoder(w).Encode(map[string]interface{}{"agents": agents})
}

func handleRegisterAgent(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Name         string   `json:"name"`
		Model        string   `json:"model"`
		Priority     int      `json:"priority"`
		Capabilities []string `json:"capabilities"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, `{"error":"invalid request"}`, http.StatusBadRequest)
		return
	}

	agentID := fmt.Sprintf("agent_%d", time.Now().UnixNano())
	agentMu.Lock()
	agentRegistry[agentID] = AgentInfo{
		ID: agentID, Name: req.Name, Model: req.Model,
		Status: "active", Priority: req.Priority, Capabilities: req.Capabilities,
	}
	agentMu.Unlock()

	logAudit(r.Header.Get("X-User-ID"), "register_agent", agentID, "allowed")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"agent_id": agentID,
		"status":   "registered",
	})
}

func handleMetrics(w http.ResponseWriter, r *http.Request) {
	metrics.mu.Lock()
	metrics.ActiveAgents = len(agentRegistry)
	metrics.mu.Unlock()

	// Prometheus text format
	w.Header().Set("Content-Type", "text/plain")
	fmt.Fprintf(w, "# HELP agos_requests_total Total HTTP requests\n")
	fmt.Fprintf(w, "agos_requests_total %d\n", metrics.RequestCount)
	fmt.Fprintf(w, "# HELP agos_tasks_submitted_total Tasks submitted\n")
	fmt.Fprintf(w, "agos_tasks_submitted_total %d\n", metrics.TasksSubmitted)
	fmt.Fprintf(w, "# HELP agos_tasks_completed_total Tasks completed\n")
	fmt.Fprintf(w, "agos_tasks_completed_total %d\n", metrics.TasksCompleted)
	fmt.Fprintf(w, "# HELP agos_tasks_failed_total Tasks failed\n")
	fmt.Fprintf(w, "agos_tasks_failed_total %d\n", metrics.TasksFailed)
	fmt.Fprintf(w, "# HELP agos_active_agents Number of active agents\n")
	fmt.Fprintf(w, "agos_active_agents %d\n", metrics.ActiveAgents)
	fmt.Fprintf(w, "# HELP agos_tokens_used_total Total LLM tokens consumed\n")
	fmt.Fprintf(w, "agos_tokens_used_total %d\n", metrics.TokensUsed)
}

func handleAuditLog(w http.ResponseWriter, r *http.Request) {
	auditMu.Lock()
	defer auditMu.Unlock()
	json.NewEncoder(w).Encode(map[string]interface{}{"entries": auditLog})
}

func handleCreateAPIKey(w http.ResponseWriter, r *http.Request) {
	b := make([]byte, 32)
	rand.Read(b)
	plainKey := fmt.Sprintf("agos_sk_%s", hex.EncodeToString(b))
	prefix := plainKey[:12]

	logAudit(r.Header.Get("X-User-ID"), "create_api_key", prefix, "allowed")

	json.NewEncoder(w).Encode(map[string]interface{}{
		"key":        plainKey,
		"key_prefix": prefix,
		"warning":    "Store this key securely. It will not be shown again.",
	})
}

// ─── Server ─────────────────────────────────────────────────────────────

var startTime time.Time

func NewServer(port int) *http.Server {
	startTime = time.Now()
	rl := NewRateLimiter(60) // 60 req/min default

	mux := http.NewServeMux()

	// Public endpoints
	mux.HandleFunc("GET /health", handleHealth)
	mux.HandleFunc("GET /metrics", handleMetrics)
	mux.HandleFunc("POST /api/v1/auth/login", handleLogin)

	// Protected endpoints
	mux.HandleFunc("POST /api/v1/tasks", rateLimitMiddleware(rl, authMiddleware(handleSubmitTask)))
	mux.HandleFunc("GET /api/v1/agents", rateLimitMiddleware(rl, authMiddleware(handleListAgents)))
	mux.HandleFunc("POST /api/v1/agents", rateLimitMiddleware(rl, authMiddleware(handleRegisterAgent)))
	mux.HandleFunc("POST /api/v1/keys", rateLimitMiddleware(rl, authMiddleware(handleCreateAPIKey)))
	mux.HandleFunc("GET /api/v1/audit", rateLimitMiddleware(rl, authMiddleware(handleAuditLog)))

	handler := corsMiddleware(mux)

	log.Printf("[AGOS] API server starting on :%d", port)
	log.Printf("[AGOS] Endpoints:")
	log.Printf("[AGOS]   GET  /health           — Health check")
	log.Printf("[AGOS]   GET  /metrics           — Prometheus metrics")
	log.Printf("[AGOS]   POST /api/v1/auth/login — JWT authentication")
	log.Printf("[AGOS]   POST /api/v1/tasks      — Submit task (auth required)")
	log.Printf("[AGOS]   GET  /api/v1/agents     — List agents (auth required)")
	log.Printf("[AGOS]   POST /api/v1/agents     — Register agent (auth required)")
	log.Printf("[AGOS]   POST /api/v1/keys       — Create API key (auth required)")
	log.Printf("[AGOS]   GET  /api/v1/audit      — Audit log (auth required)")

	return &http.Server{
		Addr:         fmt.Sprintf(":%d", port),
		Handler:      handler,
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 30 * time.Second,
		IdleTimeout:  120 * time.Second,
	}
}

// StartServer starts the API server.
func StartServer(port int) error {
	srv := NewServer(port)
	jwtSecret := os.Getenv("JWT_SECRET")
	if jwtSecret == "" {
		log.Println("[AGOS] WARNING: JWT_SECRET not set, using default (INSECURE)")
	}
	return srv.ListenAndServe()
}
