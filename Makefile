.PHONY: build run
.DEFAULT: build

build:
	docker build -t ghcr.io/yaleman/cloudflare-dydns:latest .

run:
	docker run --rm -it ghcr.io/yaleman/cloudflare-dydns:latest