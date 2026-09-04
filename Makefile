# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

# citra-decks — local quickstart. Run `make help` for the list.
.DEFAULT_GOAL := help
.PHONY: help wizard setup start install ps logs down build

COMPOSE := docker compose -f docker-compose.yml

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

wizard: ## Guided setup: configure your AI key, then install (easiest first run)
	./scripts/quickstart/wizard.sh $(ARGS)

setup: ## Phase 1: generate .env, start data stores, create the MinIO bucket
	./scripts/quickstart/setup.sh

start: ## Phase 2: start backend + collaboration server + web shell
	./scripts/quickstart/start.sh

install: ## Phase 1 + Phase 2 (full bring-up from scratch)
	./scripts/quickstart/setup.sh && ./scripts/quickstart/start.sh

build: ## Rebuild the backend/collaboration/web images without restarting data stores
	$(COMPOSE) build backend collaboration-server web

ps: ## Show running services
	$(COMPOSE) ps

logs: ## Tail the backend + collaboration + web logs
	$(COMPOSE) logs -f backend collaboration-server web

down: ## Stop everything (keeps data). `make down ARGS=-v` also wipes volumes.
	$(COMPOSE) down $(ARGS)
