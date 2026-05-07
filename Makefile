# Makefile is deprecated — the canonical workflow runner is `task` (Taskfile.yml).
# This shim forwards a few common targets to the equivalent task. Run `task --list`
# for the full menu.

.DEFAULT_GOAL := help

help:
	@echo "This project has migrated to the task CLI. Run:"
	@echo "  task --list         # see all targets"
	@echo "  task web            # run the web app"
	@echo "  task audit:quick    # JSON snapshot"
	@echo ""
	@echo "Direct equivalents:"
	@echo "  make web            -> task web"
	@echo "  make audit          -> task audit:quick"
	@echo "  make auto-archive   -> task auto-archive:apply"

web:
	@task web

web-api:
	@task web:api

web-frontend:
	@task web:frontend

web-install:
	@task web:install

audit-email-quick:
	@task audit:quick

auto-archive-dry-run:
	@task auto-archive:dry-run

auto-archive:
	@task auto-archive:apply

.PHONY: help web web-api web-frontend web-install audit-email-quick auto-archive auto-archive-dry-run
