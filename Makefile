.PHONY: up down migrate seed test shell preview

up:
	docker compose up --build

down:
	docker compose down -v

migrate:
	docker compose exec api alembic upgrade head

seed:
	docker compose exec api python scripts/seed_mvp.py

test:
	docker compose exec api pytest tests/ -v

shell:
	docker compose exec api bash

preview:
	cd frontend/admin && pnpm install && pnpm build
	docker compose --profile deploy up --build -d
	docker compose exec api alembic upgrade head
