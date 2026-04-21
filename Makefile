.PHONY: test lint fmt audit restart sync help wake-dev wake-uat sleep-dev sleep-uat sleep-all status

PYTHON ?= python3

help:  ## Show this help
	@grep -E '^[a-z][a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*##' '{printf "  %-14s %s\n", $$1, $$2}'

test:  ## Run pytest
	$(PYTHON) -m pytest tests/ -x -q --tb=short

lint:  ## Syntax-check all Python files
	@find frontend/blueprints utils core fridays -name '*.py' -print0 | xargs -0 -n1 $(PYTHON) -m py_compile

fmt:  ## Format with black
	$(PYTHON) -m black --line-length 120 frontend/blueprints/ utils/ core/ fridays/

audit:  ## Run full auto-audit (pytest + lint) and store result
	$(PYTHON) -c "import sys; sys.path.insert(0,'.'); from frontend.blueprints.auto_audit import run_audit; r=run_audit(); print(r['summary'])"

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
