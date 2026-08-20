#!/bin/sh
set -eu

case "${1:-run}" in
  run|status|review|release|alerts|maintenance)
    exec python3 -m scripts.pipeline_v2.cli "$@"
    ;;
  pipeline-v2)
    shift
    exec python3 -m scripts.pipeline_v2.cli "$@"
    ;;
  *)
    exec "$@"
    ;;
esac
