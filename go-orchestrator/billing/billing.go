// AGOS Go — Stripe Billing Integration
package billing

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"math"
	"net/http"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"
)

// Plan represents a subscription tier.
type Plan struct {
	ID             string  `json:"id"`
	Name           string  `json:"name"`
	PriceMonthly   float64 `json:"price_monthly"`
	TokenLimit     int64   `json:"token_limit_daily"`
	AgentLimit     int     `json:"agent_limit"`
	RateLimitRPM   int     `json:"rate_limit_rpm"`
	Features       []string `json:"features"`
}

// Predefined plans
var Plans = map[string]Plan{
	"free": {
		ID: "free", Name: "Free", PriceMonthly: 0,
		TokenLimit: 10_000, AgentLimit: 2, RateLimitRPM: 10,
		Features: []string{"basic_agents", "community_support"},
	},
	"pro": {
		ID: "pro", Name: "Pro", PriceMonthly: 29,
		TokenLimit: 500_000, AgentLimit: 10, RateLimitRPM: 60,
		Features: []string{"all_agents", "priority_support", "api_access", "custom_models"},
	},
	"enterprise": {
		ID: "enterprise", Name: "Enterprise", PriceMonthly: 199,
		TokenLimit: 10_000_000, AgentLimit: 100, RateLimitRPM: 1000,
		Features: []string{"all_agents", "sla", "sso", "audit_log", "custom_models", "dedicated_support", "on_prem"},
	},
}

// UsageTracker tracks token usage per org. It is safe for concurrent use.
type UsageTracker struct {
	mu    sync.RWMutex
	usage map[string]int64 // orgID -> tokens used today
}

func NewUsageTracker() *UsageTracker {
	return &UsageTracker{usage: make(map[string]int64)}
}

// RecordUsage records token usage.
func (ut *UsageTracker) RecordUsage(orgID string, tokens int64, model string) {
	ut.mu.Lock()
	ut.usage[orgID] += tokens
	total := ut.usage[orgID]
	ut.mu.Unlock()
	log.Printf("[BILLING] org=%s tokens=%d model=%s total=%d", orgID, tokens, model, total)
	// TODO: Write to usage_records table in PostgreSQL
}

// CheckQuota returns true if org is within their token limit.
func (ut *UsageTracker) CheckQuota(orgID string, plan Plan) bool {
	ut.mu.RLock()
	defer ut.mu.RUnlock()
	return ut.usage[orgID] < plan.TokenLimit
}

// GetUsage returns current usage for an org.
func (ut *UsageTracker) GetUsage(orgID string) int64 {
	ut.mu.RLock()
	defer ut.mu.RUnlock()
	return ut.usage[orgID]
}

// StripeWebhookHandler handles Stripe webhook events.
func StripeWebhookHandler(w http.ResponseWriter, r *http.Request) {
	stripeSecret := os.Getenv("STRIPE_WEBHOOK_SECRET")
	if stripeSecret == "" {
		log.Println("[BILLING] STRIPE_WEBHOOK_SECRET not set — rejecting webhook")
		http.Error(w, "webhook not configured", http.StatusServiceUnavailable)
		return
	}

	body, err := io.ReadAll(io.LimitReader(r.Body, 1<<20)) // 1 MB limit
	if err != nil {
		http.Error(w, "read error", http.StatusBadRequest)
		return
	}

	sigHeader := r.Header.Get("Stripe-Signature")
	if !verifyStripeSignature(body, sigHeader, stripeSecret) {
		log.Println("[BILLING] Webhook signature verification failed")
		http.Error(w, "invalid signature", http.StatusForbidden)
		return
	}

	var event struct {
		Type string          `json:"type"`
		Data json.RawMessage `json:"data"`
	}
	if err := json.Unmarshal(body, &event); err != nil {
		http.Error(w, "invalid payload", http.StatusBadRequest)
		return
	}

	switch event.Type {
	case "checkout.session.completed":
		log.Printf("[BILLING] New subscription created")
		// TODO: Update billing_accounts table
	case "invoice.paid":
		log.Printf("[BILLING] Invoice paid")
	case "customer.subscription.deleted":
		log.Printf("[BILLING] Subscription cancelled")
		// TODO: Downgrade to free tier
	default:
		log.Printf("[BILLING] Unhandled event: %s", event.Type)
	}

	w.WriteHeader(http.StatusOK)
}

// CreateCheckoutSession creates a Stripe checkout URL.
func CreateCheckoutSession(planID string, customerEmail string) (string, error) {
	stripeKey := os.Getenv("STRIPE_SECRET_KEY")
	if stripeKey == "" {
		return "", fmt.Errorf("STRIPE_SECRET_KEY not set")
	}

	// TODO: Use Stripe Go SDK
	// For now, return a placeholder
	log.Printf("[BILLING] Creating checkout for plan=%s email=%s", planID, customerEmail)

	plan, ok := Plans[planID]
	if !ok {
		return "", fmt.Errorf("unknown plan: %s", planID)
	}

	_ = plan
	return fmt.Sprintf("https://checkout.stripe.com/agos_%s_%d", planID, time.Now().Unix()), nil
}

// verifyStripeSignature verifies the Stripe-Signature header (v1 scheme).
func verifyStripeSignature(payload []byte, sigHeader, secret string) bool {
	if sigHeader == "" {
		return false
	}

	var timestamp string
	var signatures []string
	for _, part := range strings.Split(sigHeader, ",") {
		kv := strings.SplitN(strings.TrimSpace(part), "=", 2)
		if len(kv) != 2 {
			continue
		}
		switch kv[0] {
		case "t":
			timestamp = kv[1]
		case "v1":
			signatures = append(signatures, kv[1])
		}
	}

	if timestamp == "" || len(signatures) == 0 {
		return false
	}

	// Reject timestamps older than 5 minutes to prevent replay attacks
	ts, err := strconv.ParseInt(timestamp, 10, 64)
	if err != nil {
		return false
	}
	if math.Abs(float64(time.Now().Unix()-ts)) > 300 {
		return false
	}

	// Compute expected signature: HMAC-SHA256(secret, "timestamp.payload")
	signed := fmt.Sprintf("%s.%s", timestamp, string(payload))
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write([]byte(signed))
	expected := hex.EncodeToString(mac.Sum(nil))

	for _, sig := range signatures {
		if hmac.Equal([]byte(expected), []byte(sig)) {
			return true
		}
	}
	return false
}
