package telemetry

import (
	"context"
	"errors"
	"testing"
	"time"
)

func TestNewTracerDefaultEndpoint(t *testing.T) {
	t.Setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
	tr := NewTracer("orchestrator")
	if tr.service != "orchestrator" {
		t.Errorf("service = %q, want orchestrator", tr.service)
	}
}

func TestNewTracerCustomEndpoint(t *testing.T) {
	t.Setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "collector:4317")
	tr := NewTracer("svc")
	if tr.service != "svc" {
		t.Errorf("service = %q, want svc", tr.service)
	}
}

func TestStartSpan(t *testing.T) {
	tr := NewTracer("svc")
	ctx := context.Background()

	span, gotCtx := tr.StartSpan(ctx, "task.submit")
	if span == nil {
		t.Fatal("StartSpan returned nil span")
	}
	if gotCtx != ctx {
		t.Error("StartSpan should return the passed context")
	}
	if span.Name != "task.submit" {
		t.Errorf("name = %q, want task.submit", span.Name)
	}
	if span.Service != "svc" {
		t.Errorf("service = %q, want svc", span.Service)
	}
	if span.Status != "ok" {
		t.Errorf("status = %q, want ok", span.Status)
	}
	if span.TraceID == "" || span.SpanID == "" {
		t.Error("span ids should be populated")
	}
	if span.Tags == nil {
		t.Error("tags map should be initialized")
	}
	if span.StartTime.IsZero() {
		t.Error("start time should be set")
	}
	if len(tr.spans) != 1 {
		t.Errorf("tracer should record 1 span, got %d", len(tr.spans))
	}
}

func TestEndSpan(t *testing.T) {
	tr := NewTracer("svc")
	span, _ := tr.StartSpan(context.Background(), "op")
	span.StartTime = time.Now().Add(-10 * time.Millisecond)

	tr.EndSpan(span)

	if span.EndTime.IsZero() {
		t.Error("end time should be set")
	}
	if span.Duration <= 0 {
		t.Errorf("duration = %v, want > 0", span.Duration)
	}
}

func TestSetError(t *testing.T) {
	tr := NewTracer("svc")
	span, _ := tr.StartSpan(context.Background(), "op")

	SetError(span, errors.New("boom"))

	if span.Status != "error" {
		t.Errorf("status = %q, want error", span.Status)
	}
	if span.Tags["error"] != "boom" {
		t.Errorf("error tag = %q, want boom", span.Tags["error"])
	}
}

func TestGenerateID(t *testing.T) {
	id := generateID()
	if len(id) != 8 {
		t.Errorf("generateID length = %d, want 8", len(id))
	}
}

func TestSpanNameConstants(t *testing.T) {
	if SpanTaskSubmit != "task.submit" {
		t.Errorf("SpanTaskSubmit = %q", SpanTaskSubmit)
	}
	if SpanDBQuery != "db.query" {
		t.Errorf("SpanDBQuery = %q", SpanDBQuery)
	}
}
