"""Observability data collection and dispatch pipeline.

Provides a unified pipeline for collecting observability events and
dispatching them to multiple sinks (RocketMQ, WebSocket, logs, etc.).
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol

from deerflow.observability.types import ObservabilityEvent

logger = logging.getLogger(__name__)


class ObservabilitySink(Protocol):
    """Protocol for observability data sinks."""

    async def send(self, data: dict[str, Any]) -> None:
        """Send observability data to this sink."""
        ...


@dataclass
class PipelineConfig:
    """Configuration for the observability pipeline."""

    buffer_size: int = 1000
    """Maximum number of events to buffer."""

    batch_size: int = 100
    """Number of events to batch before flushing."""

    flush_interval_sec: float = 5.0
    """Interval between automatic flushes."""

    sample_rate: float = 1.0
    """Event sampling rate (1.0 = all events)."""

    max_retries: int = 3
    """Maximum number of retries for failed sends."""

    retry_delay_sec: float = 1.0
    """Delay between retries."""


class ObservabilityPipeline:
    """Collects and dispatches observability events to multiple sinks."""

    def __init__(
        self,
        sinks: list[ObservabilitySink],
        config: PipelineConfig | None = None,
    ):
        self.sinks = sinks
        self.config = config or PipelineConfig()
        self._buffer: deque[ObservabilityEvent] = deque(maxlen=self.config.buffer_size)
        self._lock = asyncio.Lock()
        self._flush_task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        """Start the periodic flush task."""
        self._running = True
        self._flush_task = asyncio.create_task(self._periodic_flush())
        logger.info("ObservabilityPipeline started")

    async def stop(self) -> None:
        """Stop the pipeline and flush remaining events."""
        self._running = False
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        await self._flush()
        logger.info("ObservabilityPipeline stopped")

    def emit(self, event: ObservabilityEvent) -> None:
        """Emit an observability event.

        Events are sampled according to the configured sample rate.
        """
        if random.random() > self.config.sample_rate:
            return

        self._buffer.append(event)

        # Trigger immediate flush if batch size reached
        if len(self._buffer) >= self.config.batch_size:
            try:
                asyncio.create_task(self._flush())
            except RuntimeError:
                # No running event loop, will be flushed on next periodic flush
                pass

    async def _periodic_flush(self) -> None:
        """Periodically flush the buffer."""
        while self._running:
            try:
                await asyncio.sleep(self.config.flush_interval_sec)
                await self._flush()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Periodic flush failed")

    async def _flush(self) -> None:
        """Flush buffered events to all sinks."""
        async with self._lock:
            if not self._buffer:
                return

            # Extract batch
            batch: list[ObservabilityEvent] = []
            while len(batch) < self.config.batch_size and self._buffer:
                batch.append(self._buffer.popleft())

            if not batch:
                return

            # Prepare payload
            payload = {
                "events": [self._serialize_event(e) for e in batch],
                "metadata": {
                    "batch_size": len(batch),
                    "timestamp": time.time(),
                    "remaining": len(self._buffer),
                },
            }

        # Send to all sinks (outside lock)
        for sink in self.sinks:
            try:
                await self._send_with_retry(sink, payload)
            except Exception:
                logger.exception("Failed to send to sink %s", type(sink).__name__)

    async def _send_with_retry(self, sink: ObservabilitySink, payload: dict[str, Any]) -> None:
        """Send data to sink with retry logic."""
        for attempt in range(self.config.max_retries):
            try:
                await sink.send(payload)
                return
            except Exception:
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay_sec * (2**attempt))
                else:
                    raise

    def _serialize_event(self, event: ObservabilityEvent) -> dict[str, Any]:
        """Serialize an event to a dictionary."""
        return {
            "event_type": event.event_type,
            "timestamp": event.timestamp,
            "trace_id": event.trace_id,
            "span_id": event.span_id,
            "payload": event.payload,
        }


class LoggingSink(ObservabilitySink):
    """Sink that writes observability events to logs."""

    def __init__(self, logger_name: str = "deerflow.observability.events"):
        self.event_logger = logging.getLogger(logger_name)

    async def send(self, data: dict[str, Any]) -> None:
        """Log observability events."""
        events = data.get("events", [])
        for event in events:
            self.event_logger.info(
                "Observability event: %s",
                event.get("event_type"),
                extra={"event": event},
            )


class CallbackSink(ObservabilitySink):
    """Sink that invokes a callback function for each batch."""

    def __init__(self, callback: Callable[[dict[str, Any]], Awaitable[None]]):
        self.callback = callback

    async def send(self, data: dict[str, Any]) -> None:
        """Invoke callback with observability data."""
        await self.callback(data)


# Global pipeline instance (initialized on demand)
_global_pipeline: ObservabilityPipeline | None = None


def get_global_pipeline() -> ObservabilityPipeline | None:
    """Get the global observability pipeline instance."""
    return _global_pipeline


def set_global_pipeline(pipeline: ObservabilityPipeline) -> None:
    """Set the global observability pipeline instance."""
    global _global_pipeline
    _global_pipeline = pipeline


def emit_event(event: ObservabilityEvent) -> None:
    """Emit an event to the global pipeline if available."""
    pipeline = get_global_pipeline()
    if pipeline:
        pipeline.emit(event)
