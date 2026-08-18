"""Connectivity-state tracking and bounded exponential backoff with jitter."""

from edge.connectivity.backoff import compute_backoff
from edge.connectivity.manager import ConnectivityManager

__all__ = ["ConnectivityManager", "compute_backoff"]
