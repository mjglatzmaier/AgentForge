"""Operator CLI scaffolding for side-car services."""

from agentforge.sidecar.agentctl.approvals_cli import approve, approvals_list, deny
from agentforge.sidecar.agentctl.gmail_cli import auth_gmail

__all__ = ["approve", "approvals_list", "auth_gmail", "deny"]
