.PHONY: test lint fmt audit restart sync help

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
