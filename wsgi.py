#!/usr/bin/env python3
"""Gunicorn entry point.

Exists so that MP_UNIVERSE_V1 could be added without editing app.py, which is
2,000-odd lines and is the file every other MinePortal change has to touch.
Registering the blueprint here keeps the universe work to new files only, so
reverting it is `ExecStart ... app:app` and a restart — no diff to unpick.
"""
from app import app
from universe import universe_bp

app.register_blueprint(universe_bp)
