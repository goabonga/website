# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Audio utilities for format conversion between Asterisk and OpenAI.

Asterisk AudioSocket: PCM 8kHz 16-bit mono (signed little-endian)
OpenAI Realtime: PCM 24kHz 16-bit mono (signed little-endian)

We need to resample between these formats using proper interpolation.
"""

import numpy as np


def resample_8k_to_24k(audio_8k: bytes) -> bytes:
    """Resample audio from 8kHz to 24kHz using linear interpolation.

    Args:
        audio_8k: PCM audio at 8kHz (16-bit signed little-endian)

    Returns:
        PCM audio at 24kHz (16-bit signed little-endian)
    """
    if not audio_8k or len(audio_8k) < 2:
        return b""

    # Convert bytes to numpy array (little-endian int16)
    samples_8k = np.frombuffer(audio_8k, dtype="<i2")

    if len(samples_8k) == 0:
        return b""

    # Upsample by factor of 3 (8kHz -> 24kHz) using linear interpolation
    # Create indices for interpolation
    old_indices = np.arange(len(samples_8k))
    new_indices = np.linspace(0, len(samples_8k) - 1, len(samples_8k) * 3)

    # Linear interpolation
    samples_24k = np.interp(new_indices, old_indices, samples_8k.astype(np.float64))

    # Convert back to int16 (little-endian)
    samples_24k = np.clip(samples_24k, -32768, 32767).astype("<i2")

    return samples_24k.tobytes()


def resample_24k_to_8k(audio_24k: bytes) -> bytes:
    """Resample audio from 24kHz to 8kHz using decimation with anti-aliasing.

    Args:
        audio_24k: PCM audio at 24kHz (16-bit signed little-endian)

    Returns:
        PCM audio at 8kHz (16-bit signed little-endian)
    """
    if not audio_24k or len(audio_24k) < 2:
        return b""

    # Convert bytes to numpy array (little-endian int16)
    samples_24k = np.frombuffer(audio_24k, dtype="<i2")  # '<i2' = little-endian int16

    if len(samples_24k) < 3:
        return b""

    # Log audio levels for debugging
    max_val = np.max(np.abs(samples_24k))
    import logging

    logger = logging.getLogger(__name__)
    logger.debug(
        f"24kHz audio: {len(samples_24k)} samples, max amplitude: {max_val}, "
        f"range: [{samples_24k.min()}, {samples_24k.max()}]"
    )

    # Convert to float for processing
    samples_float = samples_24k.astype(np.float64)

    # Apply simple low-pass filter (3-sample moving average) before decimation
    # This prevents aliasing artifacts
    kernel = np.array([1.0, 1.0, 1.0]) / 3.0
    filtered = np.convolve(samples_float, kernel, mode="valid")

    # Downsample by factor of 3 (24kHz -> 8kHz)
    samples_8k = filtered[::3]

    # Log output amplitude
    if len(samples_8k) > 0:
        out_max = np.max(np.abs(samples_8k))
        logger.debug(f"8kHz output: {len(samples_8k)} samples, max amplitude: {out_max:.0f}")

    # Clip and convert back to int16 little-endian
    samples_8k = np.clip(samples_8k, -32768, 32767).astype("<i2")

    return samples_8k.tobytes()


class AudioBuffer:
    """Buffer for accumulating audio data before sending.

    Helps batch small audio chunks into larger ones for more
    efficient network transmission.
    """

    def __init__(self, chunk_size: int = 4800):
        """Initialize the buffer.

        Args:
            chunk_size: Minimum bytes to accumulate before flushing
        """
        self.chunk_size = chunk_size
        self._buffer = bytearray()

    def add(self, data: bytes) -> bytes:
        """Add data to buffer and return data if buffer is full.

        Args:
            data: Audio data to add

        Returns:
            Buffered data if size threshold reached, else empty bytes
        """
        self._buffer.extend(data)

        if len(self._buffer) >= self.chunk_size:
            result = bytes(self._buffer)
            self._buffer.clear()
            return result

        return b""

    def add_and_get_chunks(self, data: bytes) -> list[bytes]:
        """Add data and return list of fixed-size chunks.

        Args:
            data: Audio data to add

        Returns:
            List of chunk_size byte chunks (may be empty)
        """
        self._buffer.extend(data)

        chunks = []
        while len(self._buffer) >= self.chunk_size:
            chunks.append(bytes(self._buffer[: self.chunk_size]))
            del self._buffer[: self.chunk_size]

        return chunks

    def flush(self) -> bytes:
        """Flush and return all buffered data."""
        result = bytes(self._buffer)
        self._buffer.clear()
        return result

    def clear(self):
        """Clear the buffer without returning data."""
        self._buffer.clear()
