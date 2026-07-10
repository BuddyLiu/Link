#!/usr/bin/env python3
import sys, os, subprocess
os.chdir(os.path.dirname(os.path.abspath(__file__)))
r = subprocess.run([sys.executable, "_execute_test.py"], timeout=120, capture_output=True, text=True)
print(r.stdout)
if r.stderr: print("STDERR:", r.stderr[:800])
print(f"\nExit code: {r.returncode}")
