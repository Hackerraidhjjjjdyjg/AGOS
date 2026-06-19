// AGOS Go — WebSocket Server for Real-Time Agent Events
package api

import (
	"encoding/json"
	"log"
	"net/http"
	"sync"
	"time"

	"golang.org/x/net/websocket"
)

// WSEvent represents a real-time event sent to clients.
type WSEvent struct {
	Type      string      `json:"type"`      // task_update, agent_status, metric, error
	TaskID    string      `json:"task_id,omitempty"`
	AgentID   string      `json:"agent_id,omitempty"`
	Payload   interface{} `json:"payload"`
	Timestamp int64       `json:"timestamp"`
}

// WSHub manages WebSocket connections.
type WSHub struct {
	mu      sync.RWMutex
	clients map[*websocket.Conn]bool
}

// NewWSHub creates a new WebSocket hub.
func NewWSHub() *WSHub {
	return &WSHub{
		clients: make(map[*websocket.Conn]bool),
	}
}

// Register adds a WebSocket connection.
func (h *WSHub) Register(ws *websocket.Conn) {
	h.mu.Lock()
	h.clients[ws] = true
	h.mu.Unlock()
	log.Printf("[WS] Client connected: %s (total: %d)", ws.RemoteAddr(), len(h.clients))
}

// Unregister removes a WebSocket connection.
func (h *WSHub) Unregister(ws *websocket.Conn) {
	h.mu.Lock()
	delete(h.clients, ws)
	h.mu.Unlock()
	log.Printf("[WS] Client disconnected: %s (total: %d)", ws.RemoteAddr(), len(h.clients))
}

// Broadcast sends an event to all connected clients.
func (h *WSHub) Broadcast(event WSEvent) {
	event.Timestamp = time.Now().UnixMilli()
	data, err := json.Marshal(event)
	if err != nil {
		return
	}

	h.mu.RLock()
	defer h.mu.RUnlock()

	for ws := range h.clients {
		if _, err := ws.Write(data); err != nil {
			log.Printf("[WS] Write error: %v", err)
			go h.Unregister(ws)
		}
	}
}

// Handler returns an http.Handler for WebSocket connections.
// Requires a valid token as a query parameter: ?token=<jwt>
func (h *WSHub) Handler() http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		token := r.URL.Query().Get("token")
		if token == "" {
			http.Error(w, `{"error":"missing token query parameter"}`, http.StatusUnauthorized)
			return
		}
		if _, valid := validateToken(token); !valid {
			http.Error(w, `{"error":"invalid or expired token"}`, http.StatusUnauthorized)
			return
		}
		websocket.Handler(func(ws *websocket.Conn) {
			h.Register(ws)
			defer h.Unregister(ws)

			welcome := WSEvent{
				Type:    "connected",
				Payload: map[string]string{"message": "AGOS real-time stream connected"},
			}
			data, _ := json.Marshal(welcome)
			ws.Write(data)

			buf := make([]byte, 4096)
			for {
				n, err := ws.Read(buf)
				if err != nil {
					break
				}
				var msg map[string]string
				if err := json.Unmarshal(buf[:n], &msg); err == nil {
					log.Printf("[WS] Received: %v", msg)
				}
			}
		}).ServeHTTP(w, r)
	})
}

// Global hub instance
var Hub = NewWSHub()
