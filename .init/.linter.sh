#!/bin/bash
cd /home/kavia/workspace/code-generation/data-insight-assistant-40465-40470/fastapi_backend
source venv/bin/activate
flake8 .
LINT_EXIT_CODE=$?
if [ $LINT_EXIT_CODE -ne 0 ]; then
  exit 1
fi

