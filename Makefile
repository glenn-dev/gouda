SHELL := /bin/sh

override DEMO_COMPOSE := docker compose --project-directory "$(CURDIR)" --env-file "$(CURDIR)/.env" -f "$(CURDIR)/docker-compose.yml" -p gouda-demo
override DEMO_METADATA_COMPOSE := env DJANGO_SECRET_KEY=compose-metadata-only POSTGRES_PASSWORD=compose-metadata-only docker compose --project-directory "$(CURDIR)" --env-file /dev/null -f "$(CURDIR)/docker-compose.yml" -p gouda-demo

.PHONY: help demo demo-check down status logs demo-reset

help:
	@echo "Gouda local demo commands:"
	@echo "  make demo        Build, start, health-check, and seed the isolated demo"
	@echo "  make status      Show isolated demo service state"
	@echo "  make logs        Show the latest isolated demo logs"
	@echo "  make down        Remove demo containers/networks; preserve demo data"
	@echo "  make demo-reset  Remove demo containers/networks and ONLY the demo volume"

demo-check:
	@"$(CURDIR)/scripts/check-local-env.sh" "$(CURDIR)/.env"
	@$(DEMO_COMPOSE) config --quiet || { \
		echo "Error: demo Compose configuration is invalid." >&2; \
		exit 1; \
	}

demo: demo-check
	@$(DEMO_COMPOSE) up --build --detach --force-recreate --remove-orphans --wait --wait-timeout 180 || { \
		echo "Error: demo services did not start cleanly. Run 'make status' and 'make logs'." >&2; \
		exit 1; \
	}
	@$(DEMO_COMPOSE) exec -T backend python manage.py seed_demo || { \
		echo "Error: demo services are healthy, but synthetic seeding failed. Run 'make logs'." >&2; \
		exit 1; \
	}
	@echo "Gouda demo ready: http://127.0.0.1:5173/"

down:
	@$(DEMO_METADATA_COMPOSE) down --remove-orphans
	@echo "Isolated demo stopped. Volume gouda-demo_gouda-postgres-data was preserved."

status:
	@$(DEMO_METADATA_COMPOSE) ps --all

logs:
	@$(DEMO_METADATA_COMPOSE) logs --tail 200

demo-reset:
	@echo "Destructive reset: removing ONLY isolated project gouda-demo and volume gouda-demo_gouda-postgres-data."
	@$(DEMO_METADATA_COMPOSE) down --remove-orphans
	@if docker volume inspect gouda-demo_gouda-postgres-data >/dev/null 2>&1; then \
		docker volume rm gouda-demo_gouda-postgres-data >/dev/null || { \
			echo "Error: could not remove gouda-demo_gouda-postgres-data; check for containers still using it." >&2; \
			exit 1; \
		}; \
		echo "Removed isolated synthetic demo volume gouda-demo_gouda-postgres-data."; \
	else \
		echo "Isolated synthetic demo volume does not exist; nothing to remove."; \
	fi
