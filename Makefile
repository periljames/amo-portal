.PHONY: dev build deploy rollback health

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
