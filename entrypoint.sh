#!/bin/sh
set -eu

case "${1:-run}" in
  run|status)
    exec python3 -m scripts.pipeline.cli "$1"
    ;;
  *)
    exec "$@"
    ;;
esac
