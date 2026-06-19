package secrets

import "testing"

func TestNew(t *testing.T) {
	m := New("agos")
	if m.prefix != "agos" {
		t.Errorf("prefix = %q, want agos", m.prefix)
	}
}

// On non-macOS hosts (and CI before a value is stored), the Keychain lookup
// fails and Get falls back to the environment variable.
func TestGetFallsBackToEnv(t *testing.T) {
	m := New("agos")
	t.Setenv("AGOS_GROQ_API_KEY", "env-value")

	got, err := m.Get("groq_api_key")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got != "env-value" {
		t.Errorf("Get = %q, want env-value", got)
	}
}

func TestGetUppercasesEnvKey(t *testing.T) {
	m := New("agos")
	t.Setenv("AGOS_MIXED_CASE", "ok")
	got, err := m.Get("mixed_case")
	if err != nil || got != "ok" {
		t.Errorf("Get(mixed_case) = %q, %v; want ok, nil", got, err)
	}
}

func TestGetMissingReturnsError(t *testing.T) {
	m := New("agos")
	if _, err := m.Get("definitely_not_set_xyz"); err == nil {
		t.Error("expected error for missing secret")
	}
}

func TestMustGetReturnsValue(t *testing.T) {
	m := New("agos")
	t.Setenv("AGOS_JWT_SECRET", "topsecret")
	if got := m.MustGet("jwt_secret"); got != "topsecret" {
		t.Errorf("MustGet = %q, want topsecret", got)
	}
}

func TestRequiredSecrets(t *testing.T) {
	want := map[string]bool{
		"groq_api_key":      true,
		"jwt_secret":        true,
		"postgres_password": true,
		"redis_password":    true,
		"stripe_secret_key": true,
	}
	if len(RequiredSecrets) != len(want) {
		t.Fatalf("RequiredSecrets len = %d, want %d", len(RequiredSecrets), len(want))
	}
	for _, k := range RequiredSecrets {
		if !want[k] {
			t.Errorf("unexpected required secret %q", k)
		}
	}
}
