// AGOS Go Orchestrator — Preemptive Agent Scheduler
// Priority-based scheduler with token budgets, preemption, and starvation prevention.

package scheduler

import (
	"log"
	"sync"
	"time"
)

// Priority levels (P0 = critical, P4 = background).
const (
	PriorityCritical   uint8 = 0
	PriorityHardware   uint8 = 1
	PriorityUser       uint8 = 2
	PrioritySystem     uint8 = 3
	PriorityBackground uint8 = 4
)

// AgentState represents the execution state of an agent.
type AgentState int

const (
	StateReady     AgentState = iota
	StateRunning
	StateSuspended
	StateCompleted
	StateFailed
)

// AgentProcess represents a scheduled agent.
type AgentProcess struct {
	ID              uint64
	Name            string
	Priority        uint8
	State           AgentState
	TokenBudget     int64       // Total tokens allocated
	TokensUsed      int64       // Tokens consumed so far
	TokensRemaining int64       // Tokens left
	CreatedAt       time.Time
	LastScheduled   time.Time
	AgingBoost      int64       // Starvation prevention counter
}

// SchedulerStats for telemetry.
type SchedulerStats struct {
	ActiveAgents    int
	ReadyAgents     int
	SuspendedAgents int
	TotalScheduled  uint64
	Preemptions     uint64
}

// Scheduler manages agent execution with priority-based preemption.
type Scheduler struct {
	mu              sync.RWMutex
	agents          map[uint64]*AgentProcess
	activeAgent     *AgentProcess // Currently executing agent
	nextID          uint64
	totalScheduled  uint64
	preemptions     uint64
	agingInterval   time.Duration
	stopAging       chan struct{}
	OnPreempt       func(suspendedID, incomingID uint64)
}

// New creates a new Scheduler.
func New() *Scheduler {
	s := &Scheduler{
		agents:        make(map[uint64]*AgentProcess),
		nextID:        1,
		agingInterval: 5 * time.Second,
		stopAging:     make(chan struct{}),
	}

	// Start starvation prevention goroutine.
	go s.agingLoop()

	log.Println("[SCHEDULER] Initialized with starvation prevention")
	return s
}

// Submit adds a new agent to the scheduler queue.
func (s *Scheduler) Submit(name string, priority uint8, tokenBudget int64) uint64 {
	s.mu.Lock()
	defer s.mu.Unlock()

	id := s.nextID
	s.nextID++

	agent := &AgentProcess{
		ID:              id,
		Name:            name,
		Priority:        priority,
		State:           StateReady,
		TokenBudget:     tokenBudget,
		TokensUsed:      0,
		TokensRemaining: tokenBudget,
		CreatedAt:       time.Now(),
		LastScheduled:   time.Time{},
		AgingBoost:      0,
	}

	s.agents[id] = agent
	log.Printf("[SCHEDULER] Agent submitted: id=%d name=%s priority=P%d tokens=%d", id, name, priority, tokenBudget)

	// Check if we should preempt the active agent.
	if s.activeAgent != nil && s.effectivePriority(agent) < s.effectivePriority(s.activeAgent) {
		s.preempt(agent)
	}

	return id
}

// Schedule selects the next agent to run.
func (s *Scheduler) Schedule() *AgentProcess {
	s.mu.Lock()
	defer s.mu.Unlock()

	var best *AgentProcess
	for _, agent := range s.agents {
		if agent.State != StateReady || agent.TokensRemaining <= 0 {
			continue
		}
		if best == nil || s.effectivePriority(agent) < s.effectivePriority(best) {
			best = agent
		}
	}

	if best != nil {
		best.State = StateRunning
		best.LastScheduled = time.Now()
		s.activeAgent = best
		s.totalScheduled++
		log.Printf("[SCHEDULER] Scheduled: id=%d name=%s priority=P%d", best.ID, best.Name, best.Priority)
	}

	return best
}

// ConsumeTokens records token usage for the active agent.
func (s *Scheduler) ConsumeTokens(agentID uint64, tokens int64) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if agent, ok := s.agents[agentID]; ok {
		agent.TokensUsed += tokens
		agent.TokensRemaining -= tokens

		if agent.TokensRemaining <= 0 {
			agent.State = StateCompleted
			if s.activeAgent != nil && s.activeAgent.ID == agentID {
				s.activeAgent = nil
			}
			log.Printf("[SCHEDULER] Agent exhausted budget: id=%d name=%s", agentID, agent.Name)
		}
	}
}

// Suspend suspends an agent.
func (s *Scheduler) Suspend(agentID uint64) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if agent, ok := s.agents[agentID]; ok {
		agent.State = StateSuspended
		if s.activeAgent != nil && s.activeAgent.ID == agentID {
			s.activeAgent = nil
		}
		log.Printf("[SCHEDULER] Suspended: id=%d name=%s", agentID, agent.Name)
	}
}

// Resume resumes a suspended agent.
func (s *Scheduler) Resume(agentID uint64) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if agent, ok := s.agents[agentID]; ok && agent.State == StateSuspended {
		agent.State = StateReady
		log.Printf("[SCHEDULER] Resumed: id=%d name=%s", agentID, agent.Name)
	}
}

// Complete marks an agent as completed.
func (s *Scheduler) Complete(agentID uint64) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if agent, ok := s.agents[agentID]; ok {
		agent.State = StateCompleted
		if s.activeAgent != nil && s.activeAgent.ID == agentID {
			s.activeAgent = nil
		}
		log.Printf("[SCHEDULER] Completed: id=%d name=%s", agentID, agent.Name)
	}
}

// GetStats returns scheduler statistics.
func (s *Scheduler) GetStats() SchedulerStats {
	s.mu.RLock()
	defer s.mu.RUnlock()

	stats := SchedulerStats{
		TotalScheduled: s.totalScheduled,
		Preemptions:    s.preemptions,
	}

	for _, agent := range s.agents {
		switch agent.State {
		case StateRunning:
			stats.ActiveAgents++
		case StateReady:
			stats.ReadyAgents++
		case StateSuspended:
			stats.SuspendedAgents++
		}
	}

	return stats
}

// GetAgent returns an agent by ID.
func (s *Scheduler) GetAgent(id uint64) (*AgentProcess, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	agent, ok := s.agents[id]
	return agent, ok
}

// ListAgents returns all agents.
func (s *Scheduler) ListAgents() []*AgentProcess {
	s.mu.RLock()
	defer s.mu.RUnlock()

	result := make([]*AgentProcess, 0, len(s.agents))
	for _, a := range s.agents {
		result = append(result, a)
	}
	return result
}

// Stop shuts down the scheduler.
func (s *Scheduler) Stop() {
	close(s.stopAging)
	log.Println("[SCHEDULER] Stopped")
}

// --- Internal ---

// preempt suspends the current active agent and schedules the higher-priority one.
func (s *Scheduler) preempt(incoming *AgentProcess) {
	if s.activeAgent == nil {
		return
	}

	oldID := s.activeAgent.ID
	log.Printf("[SCHEDULER] PREEMPT: suspending id=%d (P%d) for id=%d (P%d)",
		s.activeAgent.ID, s.activeAgent.Priority,
		incoming.ID, incoming.Priority)

	s.activeAgent.State = StateSuspended
	s.activeAgent = incoming
	incoming.State = StateRunning
	incoming.LastScheduled = time.Now()
	s.preemptions++
	s.totalScheduled++

	if s.OnPreempt != nil {
		s.OnPreempt(oldID, incoming.ID)
	}
}

// effectivePriority returns the effective priority (lower = higher priority).
// Includes aging boost to prevent starvation.
func (s *Scheduler) effectivePriority(agent *AgentProcess) int64 {
	return int64(agent.Priority)*1000 - agent.AgingBoost
}

// agingLoop periodically boosts the priority of starved agents.
func (s *Scheduler) agingLoop() {
	ticker := time.NewTicker(s.agingInterval)
	defer ticker.Stop()

	for {
		select {
		case <-s.stopAging:
			return
		case <-ticker.C:
			s.mu.Lock()
			for _, agent := range s.agents {
				if agent.State == StateReady {
					agent.AgingBoost += 100 // Boost starved agents
				}
			}
			s.mu.Unlock()
		}
	}
}
