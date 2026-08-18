"""Telemetry acquisition — `TelemetrySource` protocol + adapters, envelope construction."""

from edge.acquisition.builder import EnvelopeBuilder
from edge.acquisition.source import (
    FutureRealDeviceTelemetrySource,
    RawObservation,
    SimulatorTelemetrySource,
    TelemetrySource,
)

__all__ = [
    "TelemetrySource",
    "RawObservation",
    "SimulatorTelemetrySource",
    "FutureRealDeviceTelemetrySource",
    "EnvelopeBuilder",
]
