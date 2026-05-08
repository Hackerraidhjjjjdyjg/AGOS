package db

import (
	"database/sql"
	"os"
	"path/filepath"

	_ "github.com/mattn/go-sqlite3"
)

type SQLiteStore struct {
	db *sql.DB
}

func NewSQLiteStore() (*SQLiteStore, error) {
	home, _ := os.UserHomeDir()
	dbDir := filepath.Join(home, ".agos")
	os.MkdirAll(dbDir, 0755)
	dbPath := filepath.Join(dbDir, "agos.db")

	db, err := sql.Open("sqlite3", dbPath+"?_journal_mode=WAL&_synchronous=NORMAL")
	if err != nil {
		return nil, err
	}

	s := &SQLiteStore{db: db}
	if err := s.migrate(); err != nil {
		return nil, err
	}

	return s, nil
}

func (s *SQLiteStore) migrate() error {
	queries := []string{
		`CREATE TABLE IF NOT EXISTS tasks (
			id TEXT PRIMARY KEY,
			agent_uuid TEXT,
			intent TEXT,
			status TEXT,
			priority INTEGER,
			output TEXT,
			error TEXT,
			tokens_used INTEGER,
			cost_usd REAL,
			ttft_ms INTEGER,
			itl_ms INTEGER,
			created_at DATETIME DEFAULT CURRENT_TIMESTAMP
		)`,
		`CREATE TABLE IF NOT EXISTS audit_log (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			task_id TEXT,
			event TEXT,
			details TEXT,
			created_at DATETIME DEFAULT CURRENT_TIMESTAMP
		)`,
	}
	for _, q := range queries {
		if _, err := s.db.Exec(q); err != nil {
			return err
		}
	}
	return nil
}

func (s *SQLiteStore) AddTask(id, uuid, intent, status string, priority int) error {
	_, err := s.db.Exec(
		"INSERT INTO tasks (id, agent_uuid, intent, status, priority) VALUES (?, ?, ?, ?, ?)",
		id, uuid, intent, status, priority,
	)
	return err
}

func (s *SQLiteStore) UpdateTask(id, status, output, errStr string, tokens, ttft, itl int, cost float64) error {
	_, err := s.db.Exec(
		"UPDATE tasks SET status = ?, output = ?, error = ?, tokens_used = ?, ttft_ms = ?, itl_ms = ?, cost_usd = ? WHERE id = ?",
		status, output, errStr, tokens, ttft, itl, cost, id,
	)
	return err
}

func (s *SQLiteStore) GetTask(id string) (map[string]interface{}, error) {
	row := s.db.QueryRow("SELECT id, agent_uuid, intent, status, output, tokens_used, cost_usd, error, ttft_ms, itl_ms, created_at FROM tasks WHERE id = ?", id)
	var tID, uuid, intent, status, createdAt string
	var out, e sql.NullString
	var tokens, ttft, itl int
	var cost float64
	if err := row.Scan(&tID, &uuid, &intent, &status, &out, &tokens, &cost, &e, &ttft, &itl, &createdAt); err != nil {
		return nil, err
	}
	return map[string]interface{}{
		"id": tID, "agent_uuid": uuid, "intent": intent, "status": status,
		"output": out.String, "tokens_used": tokens, "cost_usd": cost, "error": e.String,
		"ttft_ms": ttft, "itl_ms": itl, "created_at": createdAt,
	}, nil
}

func (s *SQLiteStore) ListTasks() ([]map[string]interface{}, error) {
	rows, err := s.db.Query("SELECT id, intent, status, created_at FROM tasks ORDER BY created_at DESC LIMIT 50")
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var tasks []map[string]interface{}
	for rows.Next() {
		var id, intent, status, created string
		if err := rows.Scan(&id, &intent, &status, &created); err != nil {
			return nil, err
		}
		tasks = append(tasks, map[string]interface{}{"id": id, "intent": intent, "status": status, "created_at": created})
	}
	return tasks, nil
}

func (s *SQLiteStore) AddAuditEntry(taskID, event, details string) error {
	_, err := s.db.Exec("INSERT INTO audit_log (task_id, event, details) VALUES (?, ?, ?)", taskID, event, details)
	return err
}

func (s *SQLiteStore) ListAuditEntries() ([]AuditEntry, error) {
	rows, err := s.db.Query("SELECT id, task_id, event, details, created_at FROM audit_log ORDER BY id DESC LIMIT 100")
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var entries []AuditEntry
	for rows.Next() {
		var ae AuditEntry
		var created string
		if err := rows.Scan(&ae.ID, &ae.TaskID, &ae.Event, &ae.Details, &created); err != nil {
			return nil, err
		}
		ae.Time = created
		entries = append(entries, ae)
	}
	return entries, nil
}

func (s *SQLiteStore) Close() error { return s.db.Close() }
