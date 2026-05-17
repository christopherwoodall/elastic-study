#!/usr/bin/make -f
# -*- makefile -*-

SHELL         := /bin/bash
.SHELLFLAGS   := -eu -o pipefail -c
.DEFAULT_GOAL := help
.LOGGING      := 0

.ONESHELL:             ;	# Recipes execute in same shell
.NOTPARALLEL:          ;	# Wait for this target to finish
.SILENT:               ;	# No need for @
.EXPORT_ALL_VARIABLES: ;	# Export variables to child processes.
.DELETE_ON_ERROR:      ;	# Delete target if recipe fails.

# Modify the block character to be `-\t` instead of `\t`
ifeq ($(origin .RECIPEPREFIX), undefined)
	$(error This version of Make does not support .RECIPEPREFIX.)
endif
.RECIPEPREFIX = -


PROJECT_DIR := $(shell git rev-parse --show-toplevel)
SRC_DIR     := $(PROJECT_DIR)/src
BUILD_DIR   := $(PROJECT_DIR)/dist
RUN_DIR     := $(PROJECT_DIR)/runs

default: $(.DEFAULT_GOAL)
all: help

# -----------------------------------------------------------------------------
# Commands
# -----------------------------------------------------------------------------
# Each command should be defined as a separate target with a description.
# Example:
# .PHONY: my-command
# my-command: ## Description of what my-command does
# -	@echo "Running my-command..."

.PHONY: help
help: ## List commands <default>
-	echo -e "USAGE: make \033[36m[COMMAND]\033[0m\n"
-	echo "Available commands:"
-	awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "\t\033[36m%-20s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)


.PHONY: build
build: ## Build the application
-	uv pip install --editable .
-	hatch build --clean --target wheel


.PHONY: clean
clean: ## Clean artifacts
-	rm -rf $(BUILD_DIR) dist *.egg-info
-	rm -rf $(RUN_DIR) dist *.egg-info


.PHONY: lint
lint: ## Lint the code
-	ruff check $(SRC_DIR) --fix
-	ruff format $(SRC_DIR)


.PHONY: tree
tree: ## Display project structure
-	tree -I 'dist|build|*.egg-info|__pycache__' $(SRC_DIR)


.PHONY: lines
lines: ## Count lines of code
-	find $(SRC_DIR) -name '*.py' -print0 | xargs -0 wc -l
