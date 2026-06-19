package scheduler

import (
	"testing"
	"time"
)

func TestNew(t *testing.T) {
	s := New()
	defer s.Stop()

	if s.agents == nil {
		t.Fatal("agents map not initialized")
	}
	if s.nextID != 1 {
		t.Errorf("nextID = %d, want 1", s.nextID)
	}
	if len(s.agents) != 0 {
		t.Errorf("expected no agents, got %d", len(s.agents))
	}
}

func TestSubmitAssignsIncrementingIDs(t *testing.T) {
	s := New()
	defer s.Stop()

	id1 := s.Submit("a", PriorityUser, 1000)
	id2 := s.Submit("b", PriorityUser, 1000)

	if id1 != 1 || id2 != 2 {
		t.Fatalf("ids = %d, %d, want 1, 2", id1, id2)
	}

	agent, ok := s.GetAgent(id1)
	if !ok {
		t.Fatal("agent 1 not found")
	}
	if agent.Name != "a" {
		t.Errorf("name = %q, want a", agent.Name)
	}
	if agent.State != StateReady {
		t.Errorf("state = %v, want StateReady", agent.State)
	}
	if agent.TokenBudget != 1000 || agent.TokensRemaining != 1000 {
		t.Errorf("budget=%d remaining=%d, want 1000/1000", agent.TokenBudget, agent.TokensRemaining)
	}
}

func TestSchedulePicksHighestPriority(t *testing.T) {
	s := New()
	defer s.Stop()

	s.Submit("bg", PriorityBackground, 1000)
	critID := s.Submit("crit", PriorityCritical, 1000)
	s.Submit("user", PriorityUser, 1000)

	best := s.Schedule()
	if best == nil {
		t.Fatal("Schedule returned nil")
	}
	if best.ID != critID {
		t.Errorf("scheduled id=%d, want %d (critical)", best.ID, critID)
	}
	if best.State != StateRunning {
		t.Errorf("state = %v, want StateRunning", best.State)
	}
	if s.activeAgent == nil || s.activeAgent.ID != critID {
		t.Error("activeAgent not set to scheduled agent")
	}
}

func TestScheduleSkipsExhaustedAndNonReady(t *testing.T) {
	s := New()
	defer s.Stop()

	id := s.Submit("only", PriorityUser, 0) // no tokens
	if got := s.Schedule(); got != nil {
		t.Fatalf("Schedule returned agent %d with no tokens", got.ID)
	}

	s.Suspend(id)
	if got := s.Schedule(); got != nil {
		t.Fatal("Schedule returned a suspended/exhausted agent")
	}
}

func TestScheduleReturnsNilWhenEmpty(t *testing.T) {
	s := New()
	defer s.Stop()
	if got := s.Schedule(); got != nil {
		t.Fatalf("Schedule on empty scheduler returned %v", got)
	}
}

func TestConsumeTokensExhaustsBudget(t *testing.T) {
	s := New()
	defer s.Stop()

	id := s.Submit("a", PriorityUser, 100)
	s.Schedule()

	s.ConsumeTokens(id, 40)
	agent, _ := s.GetAgent(id)
	if agent.TokensUsed != 40 || agent.TokensRemaining != 60 {
		t.Errorf("used=%d remaining=%d, want 40/60", agent.TokensUsed, agent.TokensRemaining)
	}
	if agent.State == StateCompleted {
		t.Error("agent completed prematurely")
	}

	s.ConsumeTokens(id, 60)
	agent, _ = s.GetAgent(id)
	if agent.State != StateCompleted {
		t.Errorf("state = %v, want StateCompleted after budget exhausted", agent.State)
	}
	if s.activeAgent != nil {
		t.Error("activeAgent should be cleared when active agent exhausts budget")
	}
}

func TestConsumeTokensUnknownAgentNoop(t *testing.T) {
	s := New()
	defer s.Stop()
	s.ConsumeTokens(999, 10) // must not panic
}

func TestSuspendResume(t *testing.T) {
	s := New()
	defer s.Stop()

	id := s.Submit("a", PriorityUser, 100)
	s.Schedule()

	s.Suspend(id)
	agent, _ := s.GetAgent(id)
	if agent.State != StateSuspended {
		t.Fatalf("state = %v, want StateSuspended", agent.State)
	}
	if s.activeAgent != nil {
		t.Error("activeAgent should be cleared after suspending active agent")
	}

	s.Resume(id)
	agent, _ = s.GetAgent(id)
	if agent.State != StateReady {
		t.Errorf("state = %v, want StateReady after resume", agent.State)
	}
}

func TestResumeOnlyAffectsSuspended(t *testing.T) {
	s := New()
	defer s.Stop()

	id := s.Submit("a", PriorityUser, 100)
	s.Resume(id) // ready -> should stay ready
	agent, _ := s.GetAgent(id)
	if agent.State != StateReady {
		t.Errorf("state = %v, want StateReady", agent.State)
	}
}

func TestComplete(t *testing.T) {
	s := New()
	defer s.Stop()

	id := s.Submit("a", PriorityUser, 100)
	s.Schedule()
	s.Complete(id)

	agent, _ := s.GetAgent(id)
	if agent.State != StateCompleted {
		t.Errorf("state = %v, want StateCompleted", agent.State)
	}
	if s.activeAgent != nil {
		t.Error("activeAgent should be cleared after completing active agent")
	}
}

func TestSubmitPreemptsLowerPriorityActiveAgent(t *testing.T) {
	s := New()
	defer s.Stop()

	var preemptedOld, preemptedNew uint64
	s.OnPreempt = func(oldID, newID uint64) {
		preemptedOld, preemptedNew = oldID, newID
	}

	lowID := s.Submit("low", PriorityBackground, 1000)
	s.Schedule() // low becomes active

	highID := s.Submit("high", PriorityCritical, 1000) // should preempt

	low, _ := s.GetAgent(lowID)
	high, _ := s.GetAgent(highID)
	if low.State != StateSuspended {
		t.Errorf("low priority agent state = %v, want StateSuspended", low.State)
	}
	if high.State != StateRunning {
		t.Errorf("high priority agent state = %v, want StateRunning", high.State)
	}
	if s.activeAgent == nil || s.activeAgent.ID != highID {
		t.Error("activeAgent should be the high priority agent")
	}
	if preemptedOld != lowID || preemptedNew != highID {
		t.Errorf("OnPreempt got (%d,%d), want (%d,%d)", preemptedOld, preemptedNew, lowID, highID)
	}

	stats := s.GetStats()
	if stats.Preemptions != 1 {
		t.Errorf("preemptions = %d, want 1", stats.Preemptions)
	}
}

func TestSubmitNoPreemptForLowerPriority(t *testing.T) {
	s := New()
	defer s.Stop()

	highID := s.Submit("high", PriorityCritical, 1000)
	s.Schedule()

	s.Submit("low", PriorityBackground, 1000) // must NOT preempt

	if s.activeAgent == nil || s.activeAgent.ID != highID {
		t.Error("higher priority active agent should not be preempted by a lower priority submit")
	}
	if s.GetStats().Preemptions != 0 {
		t.Error("no preemption expected")
	}
}

func TestGetStats(t *testing.T) {
	s := New()
	defer s.Stop()

	// Distinct priorities make Schedule() deterministic (it would otherwise
	// pick an arbitrary agent among equal-priority ones due to map iteration).
	s.Submit("r", PriorityCritical, 1000)
	s.Submit("ready", PriorityUser, 1000)
	suspended := s.Submit("s", PrioritySystem, 1000)

	if best := s.Schedule(); best == nil || best.Name != "r" {
		t.Fatalf("expected critical agent to be scheduled, got %v", best)
	}
	s.Suspend(suspended)

	stats := s.GetStats()
	if stats.ActiveAgents != 1 {
		t.Errorf("active = %d, want 1", stats.ActiveAgents)
	}
	if stats.SuspendedAgents != 1 {
		t.Errorf("suspended = %d, want 1", stats.SuspendedAgents)
	}
	if stats.ReadyAgents != 1 {
		t.Errorf("ready = %d, want 1", stats.ReadyAgents)
	}
	if stats.TotalScheduled != 1 {
		t.Errorf("totalScheduled = %d, want 1", stats.TotalScheduled)
	}
}

func TestGetAgentNotFound(t *testing.T) {
	s := New()
	defer s.Stop()
	if _, ok := s.GetAgent(42); ok {
		t.Error("expected GetAgent to report not found")
	}
}

func TestListAgents(t *testing.T) {
	s := New()
	defer s.Stop()

	s.Submit("a", PriorityUser, 1000)
	s.Submit("b", PriorityUser, 1000)

	list := s.ListAgents()
	if len(list) != 2 {
		t.Errorf("ListAgents len = %d, want 2", len(list))
	}
}

func TestEffectivePriorityWithAging(t *testing.T) {
	s := New()
	defer s.Stop()

	base := &AgentProcess{Priority: PriorityBackground}
	if got := s.effectivePriority(base); got != 4000 {
		t.Errorf("effectivePriority = %d, want 4000", got)
	}

	aged := &AgentProcess{Priority: PriorityBackground, AgingBoost: 1500}
	if got := s.effectivePriority(aged); got != 2500 {
		t.Errorf("aged effectivePriority = %d, want 2500", got)
	}
	if s.effectivePriority(aged) >= s.effectivePriority(base) {
		t.Error("aging boost should lower effective priority value")
	}
}

func TestAgingLoopBoostsReadyAgents(t *testing.T) {
	s := &Scheduler{
		agents:        make(map[uint64]*AgentProcess),
		nextID:        1,
		agingInterval: 5 * time.Millisecond,
		stopAging:     make(chan struct{}),
	}
	s.agents[1] = &AgentProcess{ID: 1, State: StateReady}
	s.agents[2] = &AgentProcess{ID: 2, State: StateRunning}

	go s.agingLoop()
	defer s.Stop()

	// Poll until the ready agent is boosted (robust to scheduler timing).
	deadline := time.Now().Add(2 * time.Second)
	var readyBoost, runningBoost int64
	for time.Now().Before(deadline) {
		s.mu.RLock()
		readyBoost = s.agents[1].AgingBoost
		runningBoost = s.agents[2].AgingBoost
		s.mu.RUnlock()
		if readyBoost > 0 {
			break
		}
		time.Sleep(5 * time.Millisecond)
	}

	if readyBoost <= 0 {
		t.Error("ready agent should have received an aging boost")
	}
	if runningBoost != 0 {
		t.Error("running agent should not be boosted")
	}
}
