# Changelog

All notable changes to Loki Mode will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2025-12-27

### Added
- **Example PRDs** - 4 test PRDs for users to try before implementing:
  - `examples/simple-todo-app.md` - Quick functionality test (~10 min)
  - `examples/api-only.md` - Backend agent testing
  - `examples/static-landing-page.md` - Frontend/marketing testing
  - `examples/full-stack-demo.md` - Comprehensive test (~30-60 min)

- **Comprehensive Test Suite** - 41 tests across 5 test files:
  - `tests/test-bootstrap.sh` - Directory structure, state initialization (8 tests)
  - `tests/test-task-queue.sh` - Queue operations, priorities (8 tests)
  - `tests/test-circuit-breaker.sh` - Failure handling, recovery (8 tests)
  - `tests/test-agent-timeout.sh` - Timeout, stuck process handling (9 tests)
  - `tests/test-state-recovery.sh` - Checkpoints, recovery (8 tests)
  - `tests/run-all-tests.sh` - Main test runner

- **Timeout and Stuck Agent Handling** - New section in SKILL.md:
  - Task timeout configuration per action type (build: 10min, test: 15min, deploy: 30min)
  - macOS-compatible timeout wrapper with Perl fallback
  - Heartbeat-based stuck agent detection
  - Watchdog pattern for long operations
  - Graceful termination handling with SIGTERM/SIGKILL

### Changed
- Updated README with example PRDs and test instructions
- Tests are macOS compatible (Perl-based timeout fallback when `timeout` command unavailable)

## [1.1.0] - 2025-12-27

### Fixed
- **macOS Compatibility** - Bootstrap script now works on macOS:
  - Uses `uuidgen` on macOS, falls back to `/proc/sys/kernel/random/uuid` on Linux
  - Fixed `sed -i` syntax for macOS (uses `sed -i ''`)

- **Agent Count** - Fixed README to show correct agent count (37 agents)

- **Username Placeholder** - Replaced placeholder username with actual GitHub username

## [1.0.1] - 2025-12-27

### Changed
- Minor README formatting updates

## [1.0.0] - 2025-12-27

### Added
- **Initial Release** of Loki Mode skill for Claude Code

- **Multi-Agent Architecture** - 37 specialized agents across 6 swarms:
  - Engineering Swarm (8 agents): frontend, backend, database, mobile, API, QA, perf, infra
  - Operations Swarm (8 agents): devops, security, monitor, incident, release, cost, SRE, compliance
  - Business Swarm (8 agents): marketing, sales, finance, legal, support, HR, investor, partnerships
  - Data Swarm (3 agents): ML, engineering, analytics
  - Product Swarm (3 agents): PM, design, techwriter
  - Growth Swarm (4 agents): hacker, community, success, lifecycle
  - Review Swarm (3 agents): code, business, security

- **Distributed Task Queue** with:
  - Priority-based task scheduling
  - Exponential backoff for retries
  - Dead letter queue for failed tasks
  - Idempotency keys for duplicate prevention
  - File-based locking for atomic operations

- **Circuit Breakers** for failure isolation:
  - Per-agent-type failure thresholds
  - Automatic cooldown and recovery
  - Half-open state for testing recovery

- **8 Execution Phases**:
  1. Bootstrap - Initialize `.loki/` structure
  2. Discovery - Parse PRD, competitive research
  3. Architecture - Tech stack selection
  4. Infrastructure - Cloud provisioning, CI/CD
  5. Development - TDD implementation with parallel code review
  6. QA - 14 quality gates
  7. Deployment - Blue-green, canary releases
  8. Business Operations - Marketing, sales, legal setup
  9. Growth Loop - Continuous optimization

- **Parallel Code Review** - 3 reviewers running simultaneously:
  - Code quality reviewer
  - Business logic reviewer
  - Security reviewer

- **State Recovery** - Checkpoint-based recovery for rate limits:
  - Automatic checkpointing
  - Orphaned task detection and re-queuing
  - Agent heartbeat monitoring

- **Deployment Support** for multiple platforms:
  - Vercel, Netlify, Railway, Render
  - AWS (ECS, Lambda, RDS)
  - GCP (Cloud Run, GKE)
  - Azure (Container Apps)
  - Kubernetes (manifests, Helm charts)

- **Reference Documentation**:
  - `references/agents.md` - Complete agent definitions
  - `references/deployment.md` - Cloud deployment guides
  - `references/business-ops.md` - Business operation workflows

[2.0.0]: https://github.com/asklokesh/claudeskill-loki-mode/compare/v1.1.0...v2.0.0
[1.1.0]: https://github.com/asklokesh/claudeskill-loki-mode/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/asklokesh/claudeskill-loki-mode/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/asklokesh/claudeskill-loki-mode/releases/tag/v1.0.0
