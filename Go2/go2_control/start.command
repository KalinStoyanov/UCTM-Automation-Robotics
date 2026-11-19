#!/bin/zsh
# Go2 Control launcher (double-click in Finder). Runs from this folder.
cd "${0:A:h}"
PY=.venv/bin/python
[[ -x $PY ]] || PY=python3
caffeinate -dims -w $$ &
(sleep 3; open http://localhost:8080) &
$PY -m controller.app "$@"
