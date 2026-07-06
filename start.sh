#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
export LIBGL_ALWAYS_SOFTWARE=1
python3 run.py
