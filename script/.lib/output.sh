#!/usr/bin/env bash

log_header() {
  printf '\n==> %s\n' "$1"
}

log_info() {
  printf '  %s\n' "$1"
}

log_success() {
  printf '  OK: %s\n' "$1"
}

log_error() {
  printf '  ERROR: %s\n' "$1" >&2
}
