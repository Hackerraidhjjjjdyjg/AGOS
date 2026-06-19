package db

import "testing"

// newTestStore isolates the on-disk database by pointing HOME at a temp dir,
// since NewSQLiteStore writes to ~/.agos/agos.db.
func newTestStore(t *testing.T) *SQLiteStore {
	t.Helper()
	t.Setenv("HOME", t.TempDir())
	s, err := NewSQLiteStore()
	if err != nil {
		t.Fatalf("NewSQLiteStore: %v", err)
	}
	t.Cleanup(func() { s.Close() })
	return s
}

func TestAddAndGetTask(t *testing.T) {
	s := newTestStore(t)

	if err := s.AddTask("t1", "uuid-1", "do thing", "queued", 2); err != nil {
		t.Fatalf("AddTask: %v", err)
	}
	// AddTask leaves the numeric columns NULL; GetTask can only scan them once
	// UpdateTask has populated them (see TestGetTaskBeforeUpdate).
	if err := s.UpdateTask("t1", "queued", "", "", 0, 0, 0, 0); err != nil {
		t.Fatalf("UpdateTask: %v", err)
	}

	got, err := s.GetTask("t1")
	if err != nil {
		t.Fatalf("GetTask: %v", err)
	}
	if got["id"] != "t1" {
		t.Errorf("id = %v, want t1", got["id"])
	}
	if got["agent_uuid"] != "uuid-1" {
		t.Errorf("agent_uuid = %v, want uuid-1", got["agent_uuid"])
	}
	if got["intent"] != "do thing" {
		t.Errorf("intent = %v, want 'do thing'", got["intent"])
	}
	if got["status"] != "queued" {
		t.Errorf("status = %v, want queued", got["status"])
	}
}

// TestGetTaskBeforeUpdate documents current behavior: GetTask scans
// tokens_used/cost_usd/ttft_ms/itl_ms into non-nullable Go types, so a task
// that has only been inserted via AddTask (leaving those columns NULL) cannot
// be read back until UpdateTask sets them. This is a known limitation in the
// source, captured here so a future fix (e.g. sql.NullInt64) is intentional.
func TestGetTaskBeforeUpdate(t *testing.T) {
	s := newTestStore(t)
	if err := s.AddTask("t1", "uuid-1", "do thing", "queued", 2); err != nil {
		t.Fatalf("AddTask: %v", err)
	}
	if _, err := s.GetTask("t1"); err == nil {
		t.Skip("GetTask now handles NULL numeric columns; update this test")
	}
}

func TestGetTaskNotFound(t *testing.T) {
	s := newTestStore(t)
	if _, err := s.GetTask("missing"); err == nil {
		t.Error("expected error for missing task")
	}
}

func TestUpdateTask(t *testing.T) {
	s := newTestStore(t)
	if err := s.AddTask("t1", "uuid-1", "intent", "queued", 1); err != nil {
		t.Fatal(err)
	}

	if err := s.UpdateTask("t1", "completed", "the output", "", 1234, 50, 10, 0.5); err != nil {
		t.Fatalf("UpdateTask: %v", err)
	}

	got, err := s.GetTask("t1")
	if err != nil {
		t.Fatal(err)
	}
	if got["status"] != "completed" {
		t.Errorf("status = %v, want completed", got["status"])
	}
	if got["output"] != "the output" {
		t.Errorf("output = %v, want 'the output'", got["output"])
	}
	if got["tokens_used"] != 1234 {
		t.Errorf("tokens_used = %v, want 1234", got["tokens_used"])
	}
	if got["cost_usd"] != 0.5 {
		t.Errorf("cost_usd = %v, want 0.5", got["cost_usd"])
	}
}

func TestListTasks(t *testing.T) {
	s := newTestStore(t)
	if err := s.AddTask("t1", "u", "first", "queued", 1); err != nil {
		t.Fatal(err)
	}
	if err := s.AddTask("t2", "u", "second", "queued", 1); err != nil {
		t.Fatal(err)
	}

	tasks, err := s.ListTasks()
	if err != nil {
		t.Fatalf("ListTasks: %v", err)
	}
	if len(tasks) != 2 {
		t.Errorf("ListTasks len = %d, want 2", len(tasks))
	}
}

func TestAuditLog(t *testing.T) {
	s := newTestStore(t)

	if err := s.AddAuditEntry("t1", "submit", "details here"); err != nil {
		t.Fatalf("AddAuditEntry: %v", err)
	}
	if err := s.AddAuditEntry("t2", "complete", "more"); err != nil {
		t.Fatal(err)
	}

	entries, err := s.ListAuditEntries()
	if err != nil {
		t.Fatalf("ListAuditEntries: %v", err)
	}
	if len(entries) != 2 {
		t.Fatalf("entries len = %d, want 2", len(entries))
	}
	// Most recent first (ORDER BY id DESC)
	if entries[0].TaskID != "t2" {
		t.Errorf("first entry task = %q, want t2", entries[0].TaskID)
	}
	if entries[0].Event != "complete" {
		t.Errorf("first entry event = %q, want complete", entries[0].Event)
	}
	if entries[0].Time == "" {
		t.Error("entry time should be populated")
	}
}
