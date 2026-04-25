"""
Unified agents module — re-exports the three agent functions for app.py.
"""

from requirement_extractor import extract_requirements
from sourcing_analyst import source_all_items
from procurement_coordinator import generate_all_drafts, send_all_emails
