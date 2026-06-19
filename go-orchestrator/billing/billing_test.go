package billing

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestPlansDefined(t *testing.T) {
	for _, id := range []string{"free", "pro", "enterprise"} {
		p, ok := Plans[id]
		if !ok {
			t.Fatalf("plan %q not defined", id)
		}
		if p.ID != id {
			t.Errorf("plan %q has ID %q", id, p.ID)
		}
		if p.TokenLimit <= 0 {
			t.Errorf("plan %q has non-positive token limit", id)
		}
	}
	if Plans["free"].PriceMonthly != 0 {
		t.Error("free plan should cost 0")
	}
	if Plans["enterprise"].TokenLimit <= Plans["pro"].TokenLimit {
		t.Error("enterprise token limit should exceed pro")
	}
}

func TestUsageTracker(t *testing.T) {
	ut := NewUsageTracker()
	if ut.GetUsage("org1") != 0 {
		t.Error("new org should have zero usage")
	}

	ut.RecordUsage("org1", 100, "llama")
	ut.RecordUsage("org1", 50, "llama")
	if got := ut.GetUsage("org1"); got != 150 {
		t.Errorf("usage = %d, want 150", got)
	}
	// independent orgs
	if ut.GetUsage("org2") != 0 {
		t.Error("org2 usage should be unaffected by org1")
	}
}

func TestCheckQuota(t *testing.T) {
	ut := NewUsageTracker()
	plan := Plans["free"] // TokenLimit 10_000

	if !ut.CheckQuota("org1", plan) {
		t.Error("org under quota should pass")
	}
	ut.RecordUsage("org1", 10_000, "llama")
	if ut.CheckQuota("org1", plan) {
		t.Error("org at/over quota should fail")
	}
}

func TestCreateCheckoutSessionRequiresKey(t *testing.T) {
	t.Setenv("STRIPE_SECRET_KEY", "")
	if _, err := CreateCheckoutSession("pro", "u@example.com"); err == nil {
		t.Error("expected error when STRIPE_SECRET_KEY is unset")
	}
}

func TestCreateCheckoutSessionUnknownPlan(t *testing.T) {
	t.Setenv("STRIPE_SECRET_KEY", "sk_test_123")
	if _, err := CreateCheckoutSession("does-not-exist", "u@example.com"); err == nil {
		t.Error("expected error for unknown plan")
	}
}

func TestCreateCheckoutSessionSuccess(t *testing.T) {
	t.Setenv("STRIPE_SECRET_KEY", "sk_test_123")
	url, err := CreateCheckoutSession("pro", "u@example.com")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !strings.HasPrefix(url, "https://checkout.stripe.com/agos_pro_") {
		t.Errorf("url = %q, want checkout.stripe.com/agos_pro_ prefix", url)
	}
}

func TestStripeWebhookHandlerValidEvent(t *testing.T) {
	body := strings.NewReader(`{"type":"invoice.paid","data":{}}`)
	req := httptest.NewRequest(http.MethodPost, "/webhook", body)
	rec := httptest.NewRecorder()

	StripeWebhookHandler(rec, req)

	if rec.Code != http.StatusOK {
		t.Errorf("status = %d, want 200", rec.Code)
	}
}

func TestStripeWebhookHandlerUnhandledEvent(t *testing.T) {
	body := strings.NewReader(`{"type":"some.unknown.event","data":{}}`)
	req := httptest.NewRequest(http.MethodPost, "/webhook", body)
	rec := httptest.NewRecorder()

	StripeWebhookHandler(rec, req)

	if rec.Code != http.StatusOK {
		t.Errorf("status = %d, want 200", rec.Code)
	}
}

func TestStripeWebhookHandlerInvalidPayload(t *testing.T) {
	body := strings.NewReader(`{not json`)
	req := httptest.NewRequest(http.MethodPost, "/webhook", body)
	rec := httptest.NewRecorder()

	StripeWebhookHandler(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Errorf("status = %d, want 400", rec.Code)
	}
}
