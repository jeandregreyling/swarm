.PHONY: test lint fmt audit restart sync help wake-dev wake-uat sleep-dev sleep-uat sleep-all status excellent bullshit seed doctor health hooks preflight integ-health log-summary

PYTHON ?= python3

help:  ## Show this help
	@grep -E '^[a-z][a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*##' '{printf "  %-18s %s\n", $$1, $$2}'

bootstrap:  ## One-command setup: venv, deps, .env, DB
	@bash bootstrap.sh --auto

docker-build:  ## Build the production Docker image
	@docker build -t swarm:latest .

docker-up:  ## Start SWARM in Docker Compose
	@docker compose up -d

docker-down:  ## Stop Docker Compose
	@docker compose down

docker-logs:  ## Tail Docker Compose logs
	@docker compose logs -f swarm

test:  ## Run pytest
	$(PYTHON) -m pytest tests/ -x -q --tb=short

lint:  ## Syntax-check all Python files
	@find frontend/blueprints utils core fridays -name '*.py' -print0 | xargs -0 -n1 $(PYTHON) -m py_compile

fmt:  ## Format with black
	$(PYTHON) -m black --line-length 120 frontend/blueprints/ utils/ core/ fridays/

audit:  ## Run full auto-audit (pytest + lint) and store result
	$(PYTHON) -c "import sys; sys.path.insert(0,'.'); from frontend.blueprints.auto_audit import run_audit; r=run_audit(); print(r['summary'])"

bullshit:  ## Run the bullshit detector (Seven's quality scanner)
	@rm -f .swarm/bullshit_report.json
	$(PYTHON) -m ops.bullshit_detector

seed:  ## Seed the four pillars with a small demo dataset
	$(PYTHON) -m ops.seed_demo

doctor:  ## Single-shot health/readiness CLI (detector + tests + /api/health + DB)
	$(PYTHON) -m ops.doctor

health:  ## Curl the live aggregated /api/health endpoint
	@curl -s http://localhost:5050/api/health | $(PYTHON) -m json.tool || echo 'server not running on :5050'

hooks:  ## Install the pre-commit hook (detector aborts on RED)
	@bash scripts/install-hooks.sh

preflight:  ## One-shot integration preflight (compile + node + focused pytest + integ-health)
	@echo "→ python compile"
	@find frontend/blueprints utils core fridays ops -name '*.py' -print0 | xargs -0 -n1 $(PYTHON) -m py_compile
	@echo "→ node syntax (changed views)"
	@for f in frontend/static/js/views/orbs.js frontend/static/js/views/home-chat.js frontend/static/js/views/localai.js frontend/static/js/views/access.js ; do \
		[ -f "$$f" ] || continue ; \
		node --check "$$f" || exit 1 ; \
	done
	@echo "→ focused pytest (runtime + scheduled_tasks)"
	@$(PYTHON) -m pytest tests/test_runtime_health_badges.py tests/test_runtime_force_unload.py tests/test_chat_via_runtime_gateway.py tests/test_scheduled_tasks_hygiene.py -x -q --tb=line
	@echo "→ integration health"
	@$(PYTHON) -m ops.integration_health || echo '(integration_health reported issues — review above)'
	@echo "preflight complete"

integ-health:  ## Print swarm integration health (DB, scheduler, services, routes)
	@$(PYTHON) -m ops.integration_health

log-summary:  ## Summarize last hour of swarm-* journal errors
	@$(PYTHON) -m ops.service_log_summary

excellent: bullshit  ## Bullshit detector + per-batch tests = the standard
	@for f in tests/test_session28_batch*.py tests/test_tasker_dry_run.py tests/test_slash_commands.py ; do \
		[ -f "$$f" ] || continue ; \
		printf '%-50s ' "$$f" ; \
		timeout 30 $(PYTHON) -m pytest "$$f" -q 2>&1 | tail -1 ; \
	done
	@echo
	@echo "If every line above is green and the bullshit stamp is GREEN/AMBER, the build is up to standard."

restart:  ## Restart PROD service
	sudo systemctl restart swarm-terminal

restart-dev:  ## Restart DEV service
	sudo systemctl restart swarm-terminal-dev

sync:  ## Merge master into dev and uat worktrees
	cd /home/seven/swarm-dev && git merge master --no-edit
	cd /home/seven/swarm-uat && git merge master --no-edit

deploy: test sync restart restart-dev  ## Full deploy: test → sync → restart
	@echo "Deploy complete"

wake-dev:  ## Start DEV (port 5051) on demand — does NOT enable at boot
	sudo systemctl start swarm-terminal-dev
	@echo "DEV awake on :5051"

wake-uat:  ## Start UAT (port 5053) on demand — does NOT enable at boot
	sudo systemctl start swarm-terminal-uat
	@echo "UAT awake on :5053"

sleep-dev:  ## Stop DEV
	sudo systemctl stop swarm-terminal-dev

sleep-uat:  ## Stop UAT
	sudo systemctl stop swarm-terminal-uat

sleep-all:  ## Stop DEV + UAT (PROD stays running)
	sudo systemctl stop swarm-terminal-dev swarm-terminal-uat
	@echo "DEV + UAT asleep"

status:  ## Show all stage states
	@for s in swarm-terminal swarm-terminal-dev swarm-terminal-uat ; do \
	   printf '  %-22s enabled=%-9s active=%s\n' "$$s" "$$(systemctl is-enabled $$s 2>&1)" "$$(systemctl is-active $$s 2>&1)" ; \
	 done
