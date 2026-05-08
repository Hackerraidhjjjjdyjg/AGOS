// AGOS Go — OpenTelemetry Tracing
package telemetry

import (
	"context"
	"log"
	"os"
	"time"
)

// Span represents a trace span.
type Span struct {
	TraceID   string            `json:"trace_id"`
	SpanID    string            `json:"span_id"`
	ParentID  string            `json:"parent_id,omitempty"`
	Name      string            `json:"name"`
	Service   string            `json:"service"`
	StartTime time.Time         `json:"start_time"`
	EndTime   time.Time         `json:"end_time,omitempty"`
	Duration  time.Duration     `json:"duration_ms,omitempty"`
	Status    string            `json:"status"` // ok, error
	Tags      map[string]string `json:"tags"`
}

// Tracer provides distributed tracing.
type Tracer struct {
	service string
	spans   []Span
}

// NewTracer creates a tracer for a service.
func NewTracer(service string) *Tracer {
	endpoint := os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
	if endpoint == "" {
		endpoint = "localhost:4317"
	}
	log.Printf("[TELEMETRY] Tracer initialized for service=%s endpoint=%s", service, endpoint)
	return &Tracer{service: service}
}

// StartSpan begins a new trace span.
func (t *Tracer) StartSpan(ctx context.Context, name string) (*Span, context.Context) {
	span := &Span{
		TraceID:   generateID(),
		SpanID:    generateID(),
		Name:      name,
		Service:   t.service,
		StartTime: time.Now(),
		Status:    "ok",
		Tags:      make(map[string]string),
	}
	t.spans = append(t.spans, *span)
	return span, ctx
}

// EndSpan completes a span.
func (t *Tracer) EndSpan(span *Span) {
	span.EndTime = time.Now()
	span.Duration = span.EndTime.Sub(span.StartTime)
	log.Printf("[TRACE] %s.%s duration=%dms status=%s",
		span.Service, span.Name, span.Duration.Milliseconds(), span.Status)
	// TODO: Export to OTLP collector
}

// SetError marks a span as errored.
func SetError(span *Span, err error) {
	span.Status = "error"
	span.Tags["error"] = err.Error()
}

func generateID() string {
	b := make([]byte, 8)
	// Simple ID generation — production uses crypto/rand
	for i := range b {
		b[i] = byte(time.Now().UnixNano() >> (i * 8))
	}
	return string(b)
}

// Predefined span names
const (
	SpanTaskSubmit    = "task.submit"
	SpanTaskExecute   = "task.execute"
	SpanLLMCall       = "llm.call"
	SpanToolExec      = "tool.execute"
	SpanKernelPageIn  = "kernel.page_in"
	SpanKernelIPC     = "kernel.ipc"
	SpanFirewall      = "kernel.firewall"
	SpanDBQuery       = "db.query"
)
