#!/bin/sh
set -eu

case "${1:-run}" in
  run|status|render-seo|probe-plans)
    exec python3 -m scripts.pipeline_v3.cli "$@"
    ;;
  *)
    exec "$@"
    ;;
esac
