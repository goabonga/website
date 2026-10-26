# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for asterisk/audio_utils.py."""

from unittest.mock import patch

import numpy as np
from asterisk.audio_utils import AudioBuffer, resample_8k_to_24k, resample_24k_to_8k


class TestResample8kTo24k:
    def test_empty_input_returns_empty(self):
        assert resample_8k_to_24k(b"") == b""

    def test_single_byte_returns_empty(self):
        assert resample_8k_to_24k(b"\x00") == b""

    def test_output_length_is_triple_input(self):
        # 160 samples (320 bytes) at 8k -> 480 samples (960 bytes) at 24k
        input_data = b"\x00" * 320
        output = resample_8k_to_24k(input_data)
        assert len(output) == 960

    def test_silence_remains_silence(self):
        input_data = b"\x00" * 320
        output = resample_8k_to_24k(input_data)
        samples = np.frombuffer(output, dtype="<i2")
        assert np.all(samples == 0)

    def test_preserves_signal_shape(self, tone_8k_samples):
        output = resample_8k_to_24k(tone_8k_samples)
        assert len(output) > 0
        samples = np.frombuffer(output, dtype="<i2")
        # Output should have non-zero samples for a tone input
        assert np.max(np.abs(samples)) > 0

    def test_output_is_valid_int16(self, tone_8k_samples):
        output = resample_8k_to_24k(tone_8k_samples)
        samples = np.frombuffer(output, dtype="<i2")
        assert np.all(samples >= -32768)
        assert np.all(samples <= 32767)

    def test_clipping_at_int16_bounds(self):
        # Max amplitude samples
        samples = np.array([32767, 32767, 32767, 32767], dtype="<i2")
        output = resample_8k_to_24k(samples.tobytes())
        out_samples = np.frombuffer(output, dtype="<i2")
        assert np.all(out_samples <= 32767)

    @patch("asterisk.audio_utils.np.frombuffer", return_value=np.array([], dtype="<i2"))
    def test_frombuffer_returns_empty_array(self, mock_frombuffer):
        """Line 28: defensive guard when frombuffer returns empty."""
        result = resample_8k_to_24k(b"\x00\x00")
        assert result == b""


class TestResample24kTo8k:
    def test_empty_input_returns_empty(self):
        assert resample_24k_to_8k(b"") == b""

    def test_single_byte_returns_empty(self):
        assert resample_24k_to_8k(b"\x00") == b""

    def test_very_short_input_returns_empty(self):
        # Less than 3 samples (6 bytes)
        assert resample_24k_to_8k(b"\x00\x00\x00\x00") == b""

    def test_output_length_approximately_one_third(self, tone_24k_samples):
        output = resample_24k_to_8k(tone_24k_samples)
        # 480 samples -> convolve valid loses 2 -> 478 / 3 ~ 159 samples
        out_samples = np.frombuffer(output, dtype="<i2")
        assert 150 <= len(out_samples) <= 165

    def test_silence_remains_silence(self):
        input_data = b"\x00" * 960  # 480 samples of silence
        output = resample_24k_to_8k(input_data)
        samples = np.frombuffer(output, dtype="<i2")
        assert np.all(samples == 0)

    def test_preserves_signal_energy(self, tone_24k_samples):
        output = resample_24k_to_8k(tone_24k_samples)
        samples = np.frombuffer(output, dtype="<i2")
        # Output should have non-zero samples
        assert np.max(np.abs(samples)) > 0

    def test_output_is_valid_int16(self, tone_24k_samples):
        output = resample_24k_to_8k(tone_24k_samples)
        samples = np.frombuffer(output, dtype="<i2")
        assert np.all(samples >= -32768)
        assert np.all(samples <= 32767)

    @patch("asterisk.audio_utils.np.convolve", return_value=np.array([], dtype=np.float64))
    def test_empty_after_decimation(self, mock_convolve):
        """Branch 84->89: samples_8k is empty after decimation."""
        # 3 samples = 6 bytes (minimum to pass len check)
        input_data = b"\x01\x00" * 3
        result = resample_24k_to_8k(input_data)
        # Result should still be valid (empty or minimal)
        assert isinstance(result, bytes)


class TestAudioBuffer:
    def test_init_default_chunk_size(self):
        buf = AudioBuffer()
        assert buf.chunk_size == 4800

    def test_init_custom_chunk_size(self):
        buf = AudioBuffer(chunk_size=320)
        assert buf.chunk_size == 320

    def test_add_returns_empty_when_below_threshold(self):
        buf = AudioBuffer(chunk_size=320)
        result = buf.add(b"\x00" * 100)
        assert result == b""

    def test_add_returns_data_when_threshold_reached(self):
        buf = AudioBuffer(chunk_size=320)
        result = buf.add(b"\x01" * 320)
        assert len(result) == 320

    def test_add_returns_data_when_threshold_exceeded(self):
        buf = AudioBuffer(chunk_size=320)
        result = buf.add(b"\x01" * 400)
        assert len(result) == 400

    def test_add_accumulates_across_calls(self):
        buf = AudioBuffer(chunk_size=320)
        assert buf.add(b"\x01" * 160) == b""
        result = buf.add(b"\x02" * 160)
        assert len(result) == 320

    def test_add_clears_buffer_after_return(self):
        buf = AudioBuffer(chunk_size=320)
        buf.add(b"\x01" * 320)
        result = buf.add(b"\x01" * 100)
        assert result == b""

    def test_add_and_get_chunks_returns_empty_below_threshold(self):
        buf = AudioBuffer(chunk_size=320)
        result = buf.add_and_get_chunks(b"\x00" * 100)
        assert result == []

    def test_add_and_get_chunks_returns_one_chunk_at_threshold(self):
        buf = AudioBuffer(chunk_size=320)
        result = buf.add_and_get_chunks(b"\x01" * 320)
        assert len(result) == 1
        assert len(result[0]) == 320

    def test_add_and_get_chunks_returns_multiple_chunks(self):
        buf = AudioBuffer(chunk_size=320)
        result = buf.add_and_get_chunks(b"\x01" * 700)
        assert len(result) == 2
        assert all(len(chunk) == 320 for chunk in result)

    def test_add_and_get_chunks_keeps_remainder(self):
        buf = AudioBuffer(chunk_size=320)
        buf.add_and_get_chunks(b"\x01" * 700)
        # 700 - 640 = 60 bytes remaining
        remaining = buf.flush()
        assert len(remaining) == 60

    def test_flush_returns_buffered_data(self):
        buf = AudioBuffer(chunk_size=320)
        buf.add(b"\x01" * 100)
        result = buf.flush()
        assert len(result) == 100

    def test_flush_clears_buffer(self):
        buf = AudioBuffer(chunk_size=320)
        buf.add(b"\x01" * 100)
        buf.flush()
        assert buf.flush() == b""

    def test_flush_empty_buffer(self):
        buf = AudioBuffer(chunk_size=320)
        assert buf.flush() == b""

    def test_clear_discards_data(self):
        buf = AudioBuffer(chunk_size=320)
        buf.add(b"\x01" * 100)
        buf.clear()
        assert buf.flush() == b""
