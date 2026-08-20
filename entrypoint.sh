#!/bin/sh
set -eu

case "${1:-run}" in
  run|status|probe-plans)
    exec python3 -m scripts.pipeline_v3.cli "$@"
    ;;
  *)
    exec "$@"
    ;;
esac
