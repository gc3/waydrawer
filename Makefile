PYZ     := dist/waydrawer
STAGING := build/staging
PREFIX  ?= $(HOME)/.local

build: $(PYZ)

$(PYZ): src/waydrawer/*.py
	rm -rf $(STAGING)
	mkdir -p $(STAGING) dist
	cp -r src/waydrawer $(STAGING)/waydrawer
	echo 'from waydrawer.__main__ import main; main()' > $(STAGING)/__main__.py
	python -m zipapp $(STAGING) -o $@ -p "/usr/bin/env python3" -c

install: build
	install -Dm755 $(PYZ) $(PREFIX)/bin/waydrawer

lint:
	mkdir -p build
	pylint --output build/lint.log src/waydrawer

clean:
	rm -rf dist build __pycache__ src/waydrawer/__pycache__

.PHONY: build install clean lint
