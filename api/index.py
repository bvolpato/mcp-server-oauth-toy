"""
Vercel serverless function entry point.
Exposes the Starlette ASGI app for Vercel's Python runtime.
"""

import os
import sys

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Set BASE_URL from Vercel environment
if os.environ.get('VERCEL_URL'):
    os.environ.setdefault('BASE_URL', f"https://{os.environ['VERCEL_URL']}")

from mcp_server_oauth_toy.server import create_app

# Vercel expects an 'app' variable for ASGI
app = create_app()
