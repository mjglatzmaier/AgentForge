"""Operator CLI scaffolding for side-car services."""

from agentforge.sidecar.agentctl.approvals_cli import approve, approvals_list, deny
from agentforge.sidecar.agentctl.gmail_cli import auth_gmail
from agentforge.sidecar.agentctl.lifecycle import down, load_runtime_config, up

__all__ = ["approve", "approvals_list", "auth_gmail", "deny", "down", "load_runtime_config", "up"]
