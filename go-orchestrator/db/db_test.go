package db

import "testing"

func TestDefaultConfig(t *testing.T) {
	c := DefaultConfig()
	if c.Host != "localhost" {
		t.Errorf("Host = %q, want localhost", c.Host)
	}
	if c.Port != 5432 {
		t.Errorf("Port = %d, want 5432", c.Port)
	}
	if c.User != "agos" {
		t.Errorf("User = %q, want agos", c.User)
	}
	if c.DBName != "agos_db" {
		t.Errorf("DBName = %q, want agos_db", c.DBName)
	}
	if c.SSLMode != "disable" {
		t.Errorf("SSLMode = %q, want disable", c.SSLMode)
	}
	if c.MaxConns != 20 {
		t.Errorf("MaxConns = %d, want 20", c.MaxConns)
	}
}
