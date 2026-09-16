#!/usr/bin/env python3
"""Drop vault bootstrap credentials before starting an agent workload."""
import os, sys
if len(sys.argv)<2:raise SystemExit('Missing workload')
for key in list(os.environ):
    if key.startswith('OP_'):os.environ.pop(key)
os.execvp(sys.argv[1],sys.argv[1:])
