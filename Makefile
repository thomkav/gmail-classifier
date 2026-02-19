SCRIPTS := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))scripts

audit-email:
	@source ~/.zsh_secrets 2>/dev/null; python3 $(SCRIPTS)/inbox_audit.py

audit-email-quick:
	@source ~/.zsh_secrets 2>/dev/null; python3 $(SCRIPTS)/sender_audit.py

.PHONY: audit-email audit-email-quick
