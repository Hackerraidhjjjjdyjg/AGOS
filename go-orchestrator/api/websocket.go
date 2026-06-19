// AGOS Go — WebSocket Server for Real-Time Agent Events
package api

import (
	"encoding/json"
	"log"
	"net/http"
	"sync"
	"time"

	"github.com/gorilla/websocket"
)

// WSEvent represents a real-time event sent to clients.
type WSEvent struct {
	Type      string      `json:"type"` // task_update, agent_status, metric, error
	TaskID    string      `json:"task_id,omitempty"`
	AgentID   string      `json:"agent_id,omitempty"`
	Payload   interface{} `json:"payload"`
	Timestamp int64       `json:"timestamp"`
}

// wsClient wraps a connection with a write mutex. The gorilla/websocket
// library does not permit concurrent writes to a single connection, so every
// write must be serialized through send.
type wsClient struct {
	conn *websocket.Conn
	mu   sync.Mutex
}

func (c *wsClient) send(data []byte) error {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.conn.WriteMessage(websocket.TextMessage, data)
}

// WSHub manages WebSocket connections.
type WSHub struct {
	mu       sync.RWMutex
	clients  map[*wsClient]bool
	upgrader websocket.Upgrader
}

// NewWSHub creates a new WebSocket hub.
func NewWSHub() *WSHub {
	return &WSHub{
		clients: make(map[*wsClient]bool),
		upgrader: websocket.Upgrader{
			ReadBufferSize:  4096,
			WriteBufferSize: 4096,
			// Origin checks are enforced by the HTTP layer (CORS middleware /
			// reverse proxy). Allowing all origins here keeps the upgrade from
			// rejecting same-origin browser clients during local development.
			CheckOrigin: func(r *http.Request) bool { return true },
		},
	}
}

// register adds a WebSocket connection.
func (h *WSHub) register(c *wsClient) {
	h.mu.Lock()
	h.clients[c] = true
	total := len(h.clients)
	h.mu.Unlock()
	log.Printf("[WS] Client connected: %s (total: %d)", c.conn.RemoteAddr(), total)
}

// unregister removes a WebSocket connection and closes it.
func (h *WSHub) unregister(c *wsClient) {
	h.mu.Lock()
	if _, ok := h.clients[c]; ok {
		delete(h.clients, c)
	}
	total := len(h.clients)
	h.mu.Unlock()
	c.conn.Close()
	log.Printf("[WS] Client disconnected: %s (total: %d)", c.conn.RemoteAddr(), total)
}

// Broadcast sends an event to all connected clients.
func (h *WSHub) Broadcast(event WSEvent) {
	event.Timestamp = time.Now().UnixMilli()
	data, err := json.Marshal(event)
	if err != nil {
		log.Printf("[WS] Marshal error: %v", err)
		return
	}

	h.mu.RLock()
	targets := make([]*wsClient, 0, len(h.clients))
	for c := range h.clients {
		targets = append(targets, c)
	}
	h.mu.RUnlock()

	for _, c := range targets {
		if err := c.send(data); err != nil {
			log.Printf("[WS] Write error: %v", err)
			go h.unregister(c)
		}
	}
}

// Handler returns an http.HandlerFunc that upgrades requests to WebSocket.
func (h *WSHub) Handler() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		conn, err := h.upgrader.Upgrade(w, r, nil)
		if err != nil {
			log.Printf("[WS] Upgrade failed: %v", err)
			return
		}
		client := &wsClient{conn: conn}
		h.register(client)
		defer h.unregister(client)

		// Send welcome message.
		welcome := WSEvent{
			Type:      "connected",
			Payload:   map[string]string{"message": "AGOS real-time stream connected"},
			Timestamp: time.Now().UnixMilli(),
		}
		if data, err := json.Marshal(welcome); err == nil {
			_ = client.send(data)
		}

		// Keep connection alive + read client messages.
		for {
			_, payload, err := conn.ReadMessage()
			if err != nil {
				break
			}
			var msg map[string]string
			if err := json.Unmarshal(payload, &msg); err == nil {
				log.Printf("[WS] Received: %v", msg)
			}
		}
	}
}

// Global hub instance.
var Hub = NewWSHub()
