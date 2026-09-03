.PHONY: install dev build deploy rollback health

# One-command production install on a fresh Linux server (bundled Postgres,
# migrations, first superuser, health checks). See scripts/install.sh.
install:
	./scripts/install.sh

dev:
	docker compose up --build

build:
	docker compose -f docker-compose.prod.yml build

deploy:
	./scripts/deploy.sh

rollback:
	./scripts/rollback.sh

health:
	curl -fsS http://127.0.0.1:8080/healthz
