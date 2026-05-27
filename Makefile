PYZ := dist/waydrawer
PREFIX ?= $(HOME)/.local

build: $(PYZ)

$(PYZ): src/waydrawer/*.py config/style.css
	mkdir -p dist
	python -m zipapp src/waydrawer -o $@ -p "/usr/bin/env python3" -c

install: build
	install -Dm755 $(PYZ) $(PREFIX)/bin/waydrawer

clean:
	rm -rf dist __pycache__ src/waydrawer/__pycache__

.PHONY: build install clean
