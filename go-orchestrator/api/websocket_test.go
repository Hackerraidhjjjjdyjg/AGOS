package api

import (
	"encoding/json"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"golang.org/x/net/websocket"
)

func TestNewWSHub(t *testing.T) {
	h := NewWSHub()
	if h.clients == nil {
		t.Fatal("clients map not initialized")
	}
	if len(h.clients) != 0 {
		t.Errorf("expected 0 clients, got %d", len(h.clients))
	}
}

func TestBroadcastNoClients(t *testing.T) {
	h := NewWSHub()
	// Should be a no-op and must not panic.
	h.Broadcast(WSEvent{Type: "task_update", Payload: map[string]string{"a": "b"}})
}

func TestWSHubHandlerLifecycle(t *testing.T) {
	h := NewWSHub()
	srv := httptest.NewServer(h.Handler())
	defer srv.Close()

	wsURL := "ws" + strings.TrimPrefix(srv.URL, "http")
	conn, err := websocket.Dial(wsURL, "", srv.URL)
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	defer conn.Close()

	// First message should be the welcome event.
	var welcome WSEvent
	conn.SetReadDeadline(time.Now().Add(2 * time.Second))
	if err := receiveJSON(conn, &welcome); err != nil {
		t.Fatalf("read welcome: %v", err)
	}
	if welcome.Type != "connected" {
		t.Errorf("welcome type = %q, want connected", welcome.Type)
	}

	// The hub should now report exactly one client.
	if got := waitForClientCount(h, 1); got != 1 {
		t.Fatalf("client count = %d, want 1 after connect", got)
	}

	// Broadcast an event and confirm the client receives it.
	h.Broadcast(WSEvent{Type: "task_update", TaskID: "t1", Payload: map[string]string{"k": "v"}})
	var ev WSEvent
	conn.SetReadDeadline(time.Now().Add(2 * time.Second))
	if err := receiveJSON(conn, &ev); err != nil {
		t.Fatalf("read broadcast: %v", err)
	}
	if ev.Type != "task_update" || ev.TaskID != "t1" {
		t.Errorf("broadcast event = %+v, want task_update/t1", ev)
	}
	if ev.Timestamp == 0 {
		t.Error("broadcast should stamp a timestamp")
	}

	// Closing the connection should trigger Unregister on the hub.
	conn.Close()
	if got := waitForClientCount(h, 0); got != 0 {
		t.Errorf("client count = %d, want 0 after disconnect", got)
	}
}

func receiveJSON(conn *websocket.Conn, v interface{}) error {
	var data []byte
	if err := websocket.Message.Receive(conn, &data); err != nil {
		return err
	}
	return json.Unmarshal(data, v)
}

func waitForClientCount(h *WSHub, want int) int {
	deadline := time.Now().Add(2 * time.Second)
	for {
		h.mu.RLock()
		n := len(h.clients)
		h.mu.RUnlock()
		if n == want || time.Now().After(deadline) {
			return n
		}
		time.Sleep(10 * time.Millisecond)
	}
}
