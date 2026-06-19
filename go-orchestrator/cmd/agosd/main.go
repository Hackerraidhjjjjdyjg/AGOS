// Command agosd is the AGOS Go orchestrator daemon entry point.
//
// It wires together the long-lived components of the orchestrator:
//   - the SQLite task/audit store
//   - the priority-based agent scheduler
//   - the HTTP API server (health, metrics, auth, tasks, agents, WebSocket)
//
// The Rust kernel bridge (package kernel) is intentionally not initialized
// here: it links against libagos_kernel via CGo and is only available in a
// fully built macOS bundle. The daemon starts and serves the API without it,
// and kernel wiring can be enabled behind a build tag once the dylib is
// present.
package main

import (
	"context"
	"flag"
	"log"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"

	"agos-orchestrator/api"
	"agos-orchestrator/db"
	"agos-orchestrator/scheduler"
)

func main() {
	port := flag.Int("port", envInt("AGOS_PORT", 8080), "HTTP API listen port")
	flag.Parse()

	log.Println("AGOS Daemon (agosd) starting...")

	// 1. Task/audit persistence.
	store, err := db.NewSQLiteStore()
	if err != nil {
		log.Fatalf("[AGOS] failed to open SQLite store: %v", err)
	}
	defer store.Close()
	log.Println("[AGOS] SQLite store ready")

	// 2. Agent scheduler (starts its own aging/starvation-prevention loop).
	sched := scheduler.New()
	defer sched.Stop()

	// 3. HTTP API server.
	srv := api.NewServer(*port)

	serverErr := make(chan error, 1)
	go func() {
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			serverErr <- err
		}
	}()
	log.Printf("[AGOS] agosd ready, serving API on %s", srv.Addr)

	// Block until the server fails or we receive a termination signal.
	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)

	select {
	case err := <-serverErr:
		log.Fatalf("[AGOS] API server error: %v", err)
	case sig := <-stop:
		log.Printf("[AGOS] received signal %s, shutting down gracefully...", sig)
	}

	// Graceful shutdown with a bounded timeout.
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := srv.Shutdown(ctx); err != nil {
		log.Printf("[AGOS] graceful shutdown failed: %v", err)
	}
	log.Println("[AGOS] agosd stopped")
}

// envInt returns the integer value of an environment variable, or fallback if
// it is unset or not a valid integer.
func envInt(key string, fallback int) int {
	if v := os.Getenv(key); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return fallback
}
