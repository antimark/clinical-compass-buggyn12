"""Clinical Compass synthetic prototype Flask application package.

Public import `from cc_api import create_app` remains backward-compatible.
"""
from .app import create_app

__all__ = ['create_app']
