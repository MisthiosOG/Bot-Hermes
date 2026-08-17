# -*- coding: utf-8 -*-
"""Entry point for Gunicorn. Import Flask app without bot."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from app import app as application

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    application.run(host="0.0.0.0", port=port)