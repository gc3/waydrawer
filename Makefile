PYZ     := dist/waydrawer
STAGING := build/staging
PREFIX  ?= $(HOME)/.local
SOURCES := $(shell find src/waydrawer -name '*.py')

build: $(PYZ)

$(PYZ): $(SOURCES)
	rm -rf $(STAGING)
	mkdir -p $(STAGING) dist
	cp -r src/waydrawer $(STAGING)/
	pip install --target $(STAGING) --no-compile tomlkit
	python3 -m zipapp $(STAGING) -o $(PYZ) -m "waydrawer.__main__:main" -p '/usr/bin/env python3'

tags:
	ctags -R --languages=Python --fields=+l --extras=+q --python-kinds=-i src/

install: build
	install -Dm755 $(PYZ) $(PREFIX)/bin/waydrawer

lint:
	mkdir -p build
	pylint --output build/lint.log src/waydrawer

clean:
	rm -rf dist build __pycache__ src/waydrawer/__pycache__ tags

.PHONY: build install clean lint
