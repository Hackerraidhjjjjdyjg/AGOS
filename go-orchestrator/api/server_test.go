package api

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"golang.org/x/crypto/bcrypt"
)

// restoreGlobals snapshots the mutable package-level state the handler tests
// touch (token store, agent registry, audit log, metrics counters, start time,
// admin creds) and restores it via t.Cleanup, so tests stay hermetic regardless
// of execution order or -count.
func restoreGlobals(t *testing.T) {
	t.Helper()

	savedTokens := map[any]any{}
	tokenStore.Range(func(k, v any) bool {
		savedTokens[k] = v
		return true
	})

	agentMu.Lock()
	savedAgents := make(map[string]AgentInfo, len(agentRegistry))
	for k, v := range agentRegistry {
		savedAgents[k] = v
	}
	agentMu.Unlock()

	auditMu.Lock()
	savedAudit := append([]AuditEntry(nil), auditLog...)
	auditMu.Unlock()

	metrics.mu.Lock()
	savedReq, savedSub := metrics.RequestCount, metrics.TasksSubmitted
	savedComp, savedFail := metrics.TasksCompleted, metrics.TasksFailed
	savedActive := metrics.ActiveAgents
	metrics.mu.Unlock()

	savedStart := startTime
	savedEmail, savedHash := adminEmail, adminPasswordHash

	t.Cleanup(func() {
		tokenStore.Range(func(k, _ any) bool {
			tokenStore.Delete(k)
			return true
		})
		for k, v := range savedTokens {
			tokenStore.Store(k, v)
		}

		agentMu.Lock()
		for k := range agentRegistry {
			delete(agentRegistry, k)
		}
		for k, v := range savedAgents {
			agentRegistry[k] = v
		}
		agentMu.Unlock()

		auditMu.Lock()
		auditLog = savedAudit
		auditMu.Unlock()

		metrics.mu.Lock()
		metrics.RequestCount, metrics.TasksSubmitted = savedReq, savedSub
		metrics.TasksCompleted, metrics.TasksFailed = savedComp, savedFail
		metrics.ActiveAgents = savedActive
		metrics.mu.Unlock()

		startTime = savedStart
		adminEmail, adminPasswordHash = savedEmail, savedHash
	})
}

// configureAdmin sets admin login credentials for the test; pair with
// restoreGlobals(t) to undo the mutation afterwards.
func configureAdmin(t *testing.T, email, password string) {
	t.Helper()
	// MinCost keeps the test fast (the handler verifies with bcrypt regardless
	// of the cost baked into the hash).
	hash, err := bcrypt.GenerateFromPassword([]byte(password), bcrypt.MinCost)
	if err != nil {
		t.Fatalf("bcrypt: %v", err)
	}
	adminEmail = email
	adminPasswordHash = string(hash)
}

func TestRateLimiterAllow(t *testing.T) {
	rl := NewRateLimiter(3)

	for i := 0; i < 3; i++ {
		if !rl.Allow("client") {
			t.Fatalf("request %d should be allowed", i+1)
		}
	}
	if rl.Allow("client") {
		t.Error("4th request should be blocked")
	}
	// Different key has its own budget.
	if !rl.Allow("other") {
		t.Error("different key should have an independent budget")
	}
}

func TestGenerateAndValidateToken(t *testing.T) {
	restoreGlobals(t)
	token := generateToken("u1", "u@example.com", "admin")
	claims, ok := validateToken(token)
	if !ok {
		t.Fatal("freshly generated token should validate")
	}
	if claims.UserID != "u1" || claims.Role != "admin" {
		t.Errorf("claims = %+v, want UserID u1 / Role admin", claims)
	}
}

func TestValidateTokenUnknown(t *testing.T) {
	if _, ok := validateToken("nope-not-a-token"); ok {
		t.Error("unknown token should not validate")
	}
}

func TestValidateTokenExpired(t *testing.T) {
	restoreGlobals(t)
	tokenStore.Store("expired-token", Claims{
		UserID: "u1",
		Exp:    time.Now().Add(-time.Hour).Unix(),
	})
	if _, ok := validateToken("expired-token"); ok {
		t.Error("expired token should not validate")
	}
	if _, present := tokenStore.Load("expired-token"); present {
		t.Error("expired token should be evicted from the store")
	}
}

func TestHandleHealth(t *testing.T) {
	restoreGlobals(t)
	startTime = time.Now()
	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	rec := httptest.NewRecorder()

	handleHealth(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200", rec.Code)
	}
	var body map[string]interface{}
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("invalid JSON: %v", err)
	}
	if body["status"] != "healthy" {
		t.Errorf("status = %v, want healthy", body["status"])
	}
}

func TestHandleLoginSuccess(t *testing.T) {
	restoreGlobals(t)
	configureAdmin(t, "admin@agos.dev", "s3cret-pass")

	body := strings.NewReader(`{"email":"admin@agos.dev","password":"s3cret-pass"}`)
	req := httptest.NewRequest(http.MethodPost, "/api/v1/auth/login", body)
	rec := httptest.NewRecorder()

	handleLogin(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200", rec.Code)
	}
	var resp map[string]interface{}
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("invalid JSON: %v", err)
	}
	if resp["access_token"] == nil || resp["access_token"] == "" {
		t.Error("expected an access_token in the response")
	}
}

func TestHandleLoginBadCredentials(t *testing.T) {
	restoreGlobals(t)
	configureAdmin(t, "admin@agos.dev", "s3cret-pass")

	body := strings.NewReader(`{"email":"admin@agos.dev","password":"wrong"}`)
	req := httptest.NewRequest(http.MethodPost, "/api/v1/auth/login", body)
	rec := httptest.NewRecorder()

	handleLogin(rec, req)

	if rec.Code != http.StatusUnauthorized {
		t.Errorf("status = %d, want 401", rec.Code)
	}
}

func TestHandleLoginNotConfigured(t *testing.T) {
	restoreGlobals(t)
	adminEmail, adminPasswordHash = "", ""

	body := strings.NewReader(`{"email":"admin@agos.dev","password":"whatever"}`)
	req := httptest.NewRequest(http.MethodPost, "/api/v1/auth/login", body)
	rec := httptest.NewRecorder()

	handleLogin(rec, req)

	if rec.Code != http.StatusServiceUnavailable {
		t.Errorf("status = %d, want 503 when admin login is unconfigured", rec.Code)
	}
}

func TestHandleLoginBadBody(t *testing.T) {
	req := httptest.NewRequest(http.MethodPost, "/api/v1/auth/login", strings.NewReader(`{bad`))
	rec := httptest.NewRecorder()

	handleLogin(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Errorf("status = %d, want 400", rec.Code)
	}
}

func TestAuthMiddlewareMissingHeader(t *testing.T) {
	called := false
	h := authMiddleware(func(http.ResponseWriter, *http.Request) { called = true })

	req := httptest.NewRequest(http.MethodGet, "/x", nil)
	rec := httptest.NewRecorder()
	h(rec, req)

	if rec.Code != http.StatusUnauthorized {
		t.Errorf("status = %d, want 401", rec.Code)
	}
	if called {
		t.Error("next handler should not run without auth")
	}
}

func TestAuthMiddlewareValidToken(t *testing.T) {
	restoreGlobals(t)
	token := generateToken("u42", "u@example.com", "user")
	var gotUser string
	h := authMiddleware(func(w http.ResponseWriter, r *http.Request) {
		gotUser = r.Header.Get("X-User-ID")
	})

	req := httptest.NewRequest(http.MethodGet, "/x", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	rec := httptest.NewRecorder()
	h(rec, req)

	if rec.Code != http.StatusOK {
		t.Errorf("status = %d, want 200", rec.Code)
	}
	if gotUser != "u42" {
		t.Errorf("X-User-ID = %q, want u42", gotUser)
	}
}

func TestAuthMiddlewareInvalidToken(t *testing.T) {
	called := false
	h := authMiddleware(func(http.ResponseWriter, *http.Request) { called = true })

	req := httptest.NewRequest(http.MethodGet, "/x", nil)
	req.Header.Set("Authorization", "Bearer not-valid")
	rec := httptest.NewRecorder()
	h(rec, req)

	if rec.Code != http.StatusUnauthorized {
		t.Errorf("status = %d, want 401", rec.Code)
	}
	if called {
		t.Error("next handler should not run for invalid token")
	}
}

func TestAuthMiddlewareAPIKey(t *testing.T) {
	called := false
	h := authMiddleware(func(http.ResponseWriter, *http.Request) { called = true })

	req := httptest.NewRequest(http.MethodGet, "/x", nil)
	req.Header.Set("Authorization", "Bearer agos_sk_abcdef")
	rec := httptest.NewRecorder()
	h(rec, req)

	if !called {
		t.Error("API key auth should call next handler")
	}
}

func TestCorsMiddlewareOptions(t *testing.T) {
	h := corsMiddleware(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Error("OPTIONS should short-circuit before reaching the handler")
	}))

	req := httptest.NewRequest(http.MethodOptions, "/x", nil)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Errorf("status = %d, want 200", rec.Code)
	}
	if rec.Header().Get("Access-Control-Allow-Origin") != "*" {
		t.Error("CORS origin header not set")
	}
}

func TestCorsMiddlewarePassThrough(t *testing.T) {
	called := false
	h := corsMiddleware(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		called = true
	}))

	req := httptest.NewRequest(http.MethodGet, "/x", nil)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)

	if !called {
		t.Error("non-OPTIONS request should reach the wrapped handler")
	}
}

func TestRateLimitMiddleware(t *testing.T) {
	rl := NewRateLimiter(1)
	h := rateLimitMiddleware(rl, func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})

	req := httptest.NewRequest(http.MethodGet, "/x", nil)
	req.Header.Set("X-User-ID", "u-rl")

	rec1 := httptest.NewRecorder()
	h(rec1, req)
	if rec1.Code != http.StatusOK {
		t.Errorf("first request status = %d, want 200", rec1.Code)
	}

	rec2 := httptest.NewRecorder()
	h(rec2, req)
	if rec2.Code != http.StatusTooManyRequests {
		t.Errorf("second request status = %d, want 429", rec2.Code)
	}
	if rec2.Header().Get("Retry-After") == "" {
		t.Error("Retry-After header should be set on rate limit")
	}
}

func TestHandleSubmitTask(t *testing.T) {
	restoreGlobals(t)
	body := strings.NewReader(`{"intent":"do x","priority":2,"agent_id":"system"}`)
	req := httptest.NewRequest(http.MethodPost, "/api/v1/tasks", body)
	rec := httptest.NewRecorder()

	handleSubmitTask(rec, req)

	var resp map[string]interface{}
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("invalid JSON: %v", err)
	}
	if resp["status"] != "queued" {
		t.Errorf("status = %v, want queued", resp["status"])
	}
	if !strings.HasPrefix(resp["task_id"].(string), "task_") {
		t.Errorf("task_id = %v, want task_ prefix", resp["task_id"])
	}
}

func TestHandleSubmitTaskBadBody(t *testing.T) {
	restoreGlobals(t)
	req := httptest.NewRequest(http.MethodPost, "/api/v1/tasks", strings.NewReader(`{bad`))
	rec := httptest.NewRecorder()
	handleSubmitTask(rec, req)
	if rec.Code != http.StatusBadRequest {
		t.Errorf("status = %d, want 400", rec.Code)
	}
}

func TestHandleRegisterAndListAgents(t *testing.T) {
	restoreGlobals(t)
	body := strings.NewReader(`{"name":"Test Agent","model":"m","priority":1,"capabilities":["x"]}`)
	req := httptest.NewRequest(http.MethodPost, "/api/v1/agents", body)
	rec := httptest.NewRecorder()
	handleRegisterAgent(rec, req)

	var resp map[string]interface{}
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("invalid JSON: %v", err)
	}
	if resp["status"] != "registered" {
		t.Errorf("status = %v, want registered", resp["status"])
	}

	listReq := httptest.NewRequest(http.MethodGet, "/api/v1/agents", nil)
	listRec := httptest.NewRecorder()
	handleListAgents(listRec, listReq)

	var listResp struct {
		Agents []AgentInfo `json:"agents"`
	}
	if err := json.Unmarshal(listRec.Body.Bytes(), &listResp); err != nil {
		t.Fatalf("invalid JSON: %v", err)
	}
	if len(listResp.Agents) < 1 {
		t.Error("expected at least one registered agent")
	}
}

func TestHandleRegisterAgentBadBody(t *testing.T) {
	restoreGlobals(t)
	req := httptest.NewRequest(http.MethodPost, "/api/v1/agents", strings.NewReader(`{bad`))
	rec := httptest.NewRecorder()
	handleRegisterAgent(rec, req)
	if rec.Code != http.StatusBadRequest {
		t.Errorf("status = %d, want 400", rec.Code)
	}
}

func TestHandleCreateAPIKey(t *testing.T) {
	restoreGlobals(t)
	req := httptest.NewRequest(http.MethodPost, "/api/v1/keys", nil)
	rec := httptest.NewRecorder()
	handleCreateAPIKey(rec, req)

	var resp map[string]interface{}
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("invalid JSON: %v", err)
	}
	key, _ := resp["key"].(string)
	if !strings.HasPrefix(key, "agos_sk_") {
		t.Errorf("key = %q, want agos_sk_ prefix", key)
	}
	if resp["key_prefix"] != key[:12] {
		t.Errorf("key_prefix = %v, want %q", resp["key_prefix"], key[:12])
	}
}

func TestHandleMetrics(t *testing.T) {
	restoreGlobals(t)
	req := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	rec := httptest.NewRecorder()
	handleMetrics(rec, req)

	if ct := rec.Header().Get("Content-Type"); !strings.HasPrefix(ct, "text/plain") {
		t.Errorf("content-type = %q, want text/plain", ct)
	}
	if !strings.Contains(rec.Body.String(), "agos_requests_total") {
		t.Error("metrics output missing agos_requests_total")
	}
}

func TestHandleAuditLog(t *testing.T) {
	restoreGlobals(t)
	logAudit("u1", "act", "res", "allowed")

	req := httptest.NewRequest(http.MethodGet, "/api/v1/audit", nil)
	rec := httptest.NewRecorder()
	handleAuditLog(rec, req)

	var resp struct {
		Entries []AuditEntry `json:"entries"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("invalid JSON: %v", err)
	}
	if len(resp.Entries) < 1 {
		t.Error("expected at least one audit entry")
	}
}

func TestMetricsInc(t *testing.T) {
	restoreGlobals(t)
	before := metrics.RequestCount
	metricsInc("requests")
	if metrics.RequestCount != before+1 {
		t.Errorf("RequestCount = %d, want %d", metrics.RequestCount, before+1)
	}

	beforeSub := metrics.TasksSubmitted
	metricsInc("submitted")
	if metrics.TasksSubmitted != beforeSub+1 {
		t.Errorf("TasksSubmitted = %d, want %d", metrics.TasksSubmitted, beforeSub+1)
	}
}

func TestNewServer(t *testing.T) {
	restoreGlobals(t)
	srv := NewServer(9999)
	if srv.Addr != ":9999" {
		t.Errorf("Addr = %q, want :9999", srv.Addr)
	}
	if srv.Handler == nil {
		t.Error("handler should be set")
	}
}
