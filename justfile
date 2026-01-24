[private]
default:
    just --list

check: fmt lint test

test:
    uv run pytest

fmt:
    uv run ruff format

lint:
    uv run ty check
    uv run mypy --strict cloudflare_dyndns tests

build:
    docker build -t ghcr.io/yaleman/cloudflare-dyndns:latest .

run:
    docker run --rm -it ghcr.io/yaleman/cloudflare-dyndns:latest