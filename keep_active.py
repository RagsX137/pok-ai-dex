#!/usr/bin/env python3
"""
keep_active.py — nudges the mouse every 60 s to prevent screen lock
and keep Teams status green.  Stop with Ctrl+C.
"""

import time
import sys

try:
    import pyautogui
except ImportError:
    sys.exit("Missing dependency: run  pip install pyautogui  then try again.")

INTERVAL = 60  # seconds between nudges

print("Running… (Ctrl+C to stop)")

try:
    while True:
        x, y = pyautogui.position()
        pyautogui.moveTo(x + 1, y)
        pyautogui.moveTo(x, y)
        time.sleep(INTERVAL)
except KeyboardInterrupt:
    print("\nStopped.")
