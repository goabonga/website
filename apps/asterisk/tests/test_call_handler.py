# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for asterisk/call_handler.py."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from asterisk.call_handler import (
    FRAME_SIZE,
    _send_audio_loop,
    handle_call,
)

# --- Handle Call ---


@pytest.fixture
def mock_openai_client_class():
    """Patch OpenAIRealtimeClient and return mock instance."""
    with patch("asterisk.call_handler.OpenAIRealtimeClient") as MockClass:
        mock_instance = MagicMock()
        mock_instance.connect = AsyncMock()
        mock_instance.disconnect = AsyncMock()
        mock_instance.send_audio = AsyncMock()
        mock_instance.send_text = AsyncMock()
        mock_instance.cancel_response = AsyncMock()
        mock_instance.is_connected = True
        mock_instance.is_responding = False
        mock_instance.set_audio_callback = MagicMock()
        mock_instance.set_transcript_callback = MagicMock()
        mock_instance.set_interrupt_callback = MagicMock()
        mock_instance.set_response_done_callback = MagicMock()
        mock_instance.set_tool_call_callback = MagicMock()
        MockClass.return_value = mock_instance
        yield MockClass, mock_instance


@pytest.fixture
def mock_session():
    """Return a mock AudioSocketSession."""
    session = AsyncMock()
    session.is_active = True
    session.receive_loop = AsyncMock()
    session.send_hangup = AsyncMock()
    session.send_audio_frame = AsyncMock()
    session.set_audio_callback = MagicMock()
    return session


@pytest.fixture
def mock_config():
    """Patch config with the OpenAI settings."""
    with patch("asterisk.call_handler.config") as mock_config:
        mock_config.OPENAI_API_KEY = "sk-test"
        mock_config.OPENAI_MODEL = "test-model"
        mock_config.OPENAI_VOICE = "alloy"
        mock_config.OPENAI_SYSTEM_PROMPT = "Test prompt"
        yield mock_config


class TestHandleCall:
    async def test_creates_openai_client(self, mock_session, mock_openai_client_class, mock_config):
        MockClass, mock_instance = mock_openai_client_class
        # Make session go inactive after first check
        mock_session.is_active = False

        await handle_call(mock_session)
        MockClass.assert_called_once()
        kwargs = MockClass.call_args[1]
        assert kwargs["api_key"] == "sk-test"
        assert kwargs["model"] == "test-model"
        assert kwargs["voice"] == "alloy"
        assert kwargs["system_prompt"] == "Test prompt"

    async def test_connects_to_openai(self, mock_session, mock_openai_client_class, mock_config):
        _, mock_instance = mock_openai_client_class
        mock_session.is_active = False

        await handle_call(mock_session)
        mock_instance.connect.assert_called_once()

    @patch("asterisk.call_handler.asyncio.sleep", new_callable=AsyncMock)
    async def test_sends_greeting(
        self, mock_sleep, mock_session, mock_openai_client_class, mock_config
    ):
        _, mock_instance = mock_openai_client_class
        # Let one iteration happen then stop
        call_count = 0

        async def stop_after_greeting(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                mock_session.is_active = False

        mock_sleep.side_effect = stop_after_greeting
        await handle_call(mock_session)
        mock_instance.send_text.assert_called_once()

    async def test_sets_callbacks(self, mock_session, mock_openai_client_class, mock_config):
        _, mock_instance = mock_openai_client_class
        mock_session.is_active = False

        await handle_call(mock_session)
        mock_session.set_audio_callback.assert_called_once()
        mock_instance.set_audio_callback.assert_called_once()
        mock_instance.set_transcript_callback.assert_called_once()
        mock_instance.set_interrupt_callback.assert_called_once()
        mock_instance.set_tool_call_callback.assert_called_once()

    async def test_disconnects_on_exit(self, mock_session, mock_openai_client_class, mock_config):
        _, mock_instance = mock_openai_client_class
        mock_session.is_active = False

        await handle_call(mock_session)
        mock_instance.disconnect.assert_called_once()

    async def test_disconnects_even_on_error(
        self, mock_session, mock_openai_client_class, mock_config
    ):
        _, mock_instance = mock_openai_client_class
        mock_instance.connect = AsyncMock(side_effect=RuntimeError("fail"))

        await handle_call(mock_session)
        mock_instance.disconnect.assert_called_once()

    @patch("asterisk.call_handler.asyncio.sleep", new_callable=AsyncMock)
    async def test_hangup_flow(
        self, mock_sleep, mock_session, mock_openai_client_class, mock_config
    ):
        """Lines 272-292: hangup request processing."""
        _, mock_instance = mock_openai_client_class
        mock_instance.is_responding = False

        call_count = 0

        async def controlled_sleep(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # After greeting sleep (call 1) and first loop iteration (call 2),
            # trigger hangup on next check
            if call_count == 2:
                # Extract on_tool_call and trigger hangup
                on_tool_call = mock_instance.set_tool_call_callback.call_args[0][0]
                on_tool_call("hangup", {"reason": "goodbye"})
            # After a few more sleeps, stop the session
            if call_count >= 6:
                mock_session.is_active = False

        mock_sleep.side_effect = controlled_sleep
        await handle_call(mock_session)
        mock_session.send_hangup.assert_called_once()

    @patch("asterisk.call_handler.asyncio.sleep", new_callable=AsyncMock)
    async def test_hangup_waits_for_responding(
        self, mock_sleep, mock_session, mock_openai_client_class, mock_config
    ):
        """Lines 276-278: wait for is_responding to finish."""
        _, mock_instance = mock_openai_client_class

        responding_count = [0]

        # Start responding, stop after a few waits
        def is_responding_getter():
            responding_count[0] += 1
            return responding_count[0] < 3

        type(mock_instance).is_responding = property(lambda self: is_responding_getter())

        call_count = 0

        async def controlled_sleep(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                on_tool_call = mock_instance.set_tool_call_callback.call_args[0][0]
                on_tool_call("hangup", {"reason": "bye"})
            if call_count >= 15:
                mock_session.is_active = False

        mock_sleep.side_effect = controlled_sleep
        await handle_call(mock_session)
        mock_session.send_hangup.assert_called_once()

    @patch("asterisk.call_handler.asyncio.sleep", new_callable=AsyncMock)
    async def test_hangup_drains_audio_queue(
        self, mock_sleep, mock_session, mock_openai_client_class, mock_config
    ):
        """Lines 282-284: wait for audio queue to drain."""
        _, mock_instance = mock_openai_client_class
        mock_instance.is_responding = False

        call_count = 0
        queue_filled = False

        async def controlled_sleep(*args, **kwargs):
            nonlocal call_count, queue_filled
            call_count += 1
            if call_count == 2:
                # Fill the audio queue with data before triggering hangup
                on_openai_audio = mock_instance.set_audio_callback.call_args[0][0]
                # Feed enough audio to queue multiple chunks
                large_audio = b"\x01\x00" * 4800
                on_openai_audio(large_audio)
                queue_filled = True
                # Now trigger hangup
                on_tool_call = mock_instance.set_tool_call_callback.call_args[0][0]
                on_tool_call("hangup", {"reason": "bye"})
            if call_count >= 15:
                mock_session.is_active = False

        mock_sleep.side_effect = controlled_sleep
        await handle_call(mock_session)
        mock_session.send_hangup.assert_called_once()


# --- Callback Tests ---


class TestOnToolCall:
    """Test the on_tool_call callback by extracting it from the mock."""

    async def test_hangup_returns_none(self, mock_session, mock_openai_client_class, mock_config):
        _, mock_instance = mock_openai_client_class
        mock_session.is_active = False

        await handle_call(mock_session)

        # Extract on_tool_call callback
        on_tool_call = mock_instance.set_tool_call_callback.call_args[0][0]
        result = on_tool_call("hangup", {"reason": "goodbye"})
        assert result is None

    async def test_unknown_tool_returns_none(
        self, mock_session, mock_openai_client_class, mock_config
    ):
        _, mock_instance = mock_openai_client_class
        mock_session.is_active = False

        await handle_call(mock_session)

        on_tool_call = mock_instance.set_tool_call_callback.call_args[0][0]
        result = on_tool_call("unknown_tool", {})
        assert result is None


class TestOnTranscript:
    """Test the on_transcript callback."""

    async def test_logs_transcript(self, mock_session, mock_openai_client_class, mock_config):
        """Line 185: on_transcript callback."""
        _, mock_instance = mock_openai_client_class
        mock_session.is_active = False

        await handle_call(mock_session)

        on_transcript = mock_instance.set_transcript_callback.call_args[0][0]
        # Should not raise
        on_transcript("hello world")


class TestOnInterrupt:
    """Test the on_interrupt callback."""

    async def test_clears_queue(self, mock_session, mock_openai_client_class, mock_config):
        _, mock_instance = mock_openai_client_class
        mock_session.is_active = False

        await handle_call(mock_session)

        # Extract on_interrupt callback
        on_interrupt = mock_instance.set_interrupt_callback.call_args[0][0]
        # Should not raise
        on_interrupt()

    async def test_drains_items_from_queue(
        self, mock_session, mock_openai_client_class, mock_config, tone_24k_samples
    ):
        """Lines 240-243: on_interrupt drains items from audio queue."""
        _, mock_instance = mock_openai_client_class
        mock_session.is_active = False

        await handle_call(mock_session)

        # Feed audio to fill the queue first
        on_openai_audio = mock_instance.set_audio_callback.call_args[0][0]
        # Feed enough audio to generate queue items
        large_audio = b"\x01\x00" * 4800  # 9600 bytes of 24kHz audio
        on_openai_audio(large_audio)

        # Now interrupt should drain the queue
        on_interrupt = mock_instance.set_interrupt_callback.call_args[0][0]
        on_interrupt()

    async def test_interrupt_handles_queue_empty_race(
        self, mock_session, mock_openai_client_class, mock_config
    ):
        """Lines 242-243: QueueEmpty exception during drain (race condition)."""
        _, mock_instance = mock_openai_client_class
        mock_session.is_active = False

        # Create a custom Queue subclass that simulates the race condition
        class RacyQueue(asyncio.Queue):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self._empty_call_count = 0

            def empty(self):
                # First call returns False (there's an item), but get_nowait will fail
                self._empty_call_count += 1
                if self._empty_call_count == 1:
                    return False  # Lie: say not empty
                return True

            def get_nowait(self):
                raise asyncio.QueueEmpty()

        with patch("asterisk.call_handler.asyncio.Queue", RacyQueue):
            await handle_call(mock_session)

            on_interrupt = mock_instance.set_interrupt_callback.call_args[0][0]
            on_interrupt()  # Should hit QueueEmpty and break


class TestOnAsteriskAudio:
    """Test the on_asterisk_audio callback (VAD logic)."""

    async def test_vad_not_responding_resets_count(
        self, mock_session, mock_openai_client_class, mock_config
    ):
        """Lines 170-171: when not responding, reset speech_frame_count."""
        _, mock_instance = mock_openai_client_class
        mock_instance.is_responding = False
        mock_session.is_active = False

        await handle_call(mock_session)

        on_asterisk_audio = mock_session.set_audio_callback.call_args[0][0]
        # Send some audio - should not trigger VAD since not responding
        audio = b"\x00" * 320
        on_asterisk_audio(audio)

    async def test_vad_responding_low_rms_resets(
        self, mock_session, mock_openai_client_class, mock_config
    ):
        """Lines 155-156: RMS below threshold resets count."""
        _, mock_instance = mock_openai_client_class
        mock_instance.is_responding = True
        mock_session.is_active = False

        await handle_call(mock_session)

        on_asterisk_audio = mock_session.set_audio_callback.call_args[0][0]
        # Send silence (low RMS) while responding
        silence = b"\x00" * 320
        on_asterisk_audio(silence)

    async def test_vad_responding_high_rms_increments(
        self, mock_session, mock_openai_client_class, mock_config
    ):
        """Lines 153-154: RMS above threshold increments count."""
        _, mock_instance = mock_openai_client_class
        mock_instance.is_responding = True
        mock_session.is_active = False

        await handle_call(mock_session)

        on_asterisk_audio = mock_session.set_audio_callback.call_args[0][0]
        # Create loud audio (high RMS)
        samples = np.full(160, 5000, dtype="<i2")
        loud_audio = samples.tobytes()
        on_asterisk_audio(loud_audio)

    @patch("asterisk.call_handler.time")
    async def test_vad_triggers_interrupt_after_3_frames(
        self, mock_time, mock_session, mock_openai_client_class, mock_config
    ):
        """Lines 161-169: 3 consecutive loud frames trigger interrupt."""
        _, mock_instance = mock_openai_client_class
        mock_instance.is_responding = True
        mock_session.is_active = False

        # Ensure debounce passes
        mock_time.time.return_value = 1000.0

        await handle_call(mock_session)

        on_asterisk_audio = mock_session.set_audio_callback.call_args[0][0]
        # Create loud audio (RMS > LOCAL_VAD_RMS_THRESHOLD)
        samples = np.full(160, 5000, dtype="<i2")
        loud_audio = samples.tobytes()

        # Send 3 consecutive loud frames to trigger interrupt
        on_asterisk_audio(loud_audio)
        on_asterisk_audio(loud_audio)
        on_asterisk_audio(loud_audio)

        # Allow the create_task to execute
        await asyncio.sleep(0)

    async def test_vad_buffers_and_resamples(
        self, mock_session, mock_openai_client_class, mock_config
    ):
        """Lines 173-178: buffer and resample audio for OpenAI."""
        _, mock_instance = mock_openai_client_class
        mock_instance.is_responding = False
        mock_session.is_active = False

        await handle_call(mock_session)

        on_asterisk_audio = mock_session.set_audio_callback.call_args[0][0]
        # Send enough audio to fill the input buffer (640 bytes)
        audio = b"\x01\x00" * 320  # 640 bytes
        on_asterisk_audio(audio)

    async def test_vad_short_audio_no_crash(
        self, mock_session, mock_openai_client_class, mock_config
    ):
        """Line 148: audio_8k < 2 bytes doesn't crash."""
        _, mock_instance = mock_openai_client_class
        mock_instance.is_responding = True
        mock_session.is_active = False

        await handle_call(mock_session)

        on_asterisk_audio = mock_session.set_audio_callback.call_args[0][0]
        # Send very short audio (< 2 bytes)
        on_asterisk_audio(b"\x00")


class TestOnOpenaiAudio:
    """Test the on_openai_audio callback."""

    async def test_processes_audio(self, mock_session, mock_openai_client_class, mock_config):
        _, mock_instance = mock_openai_client_class
        mock_session.is_active = False

        await handle_call(mock_session)

        # Extract callback
        on_openai_audio = mock_instance.set_audio_callback.call_args[0][0]
        # Should not crash with empty audio
        on_openai_audio(b"")

    async def test_resamples_and_queues(
        self, mock_session, mock_openai_client_class, mock_config, tone_24k_samples
    ):
        _, mock_instance = mock_openai_client_class
        mock_session.is_active = False

        await handle_call(mock_session)

        on_openai_audio = mock_instance.set_audio_callback.call_args[0][0]
        # Feed actual audio data - should resample and queue
        on_openai_audio(tone_24k_samples)

    @patch("asterisk.call_handler.resample_24k_to_8k", return_value=b"")
    async def test_resample_returns_empty(
        self, mock_resample, mock_session, mock_openai_client_class, mock_config
    ):
        """Line 128: resample returns empty bytes."""
        _, mock_instance = mock_openai_client_class
        mock_session.is_active = False

        await handle_call(mock_session)

        on_openai_audio = mock_instance.set_audio_callback.call_args[0][0]
        on_openai_audio(b"\x01\x00" * 100)  # Non-empty input, but resample returns empty

    async def test_audio_no_chunks_generated(
        self, mock_session, mock_openai_client_class, mock_config
    ):
        """Line 137->exit: small audio that doesn't generate full chunks."""
        _, mock_instance = mock_openai_client_class
        mock_session.is_active = False

        await handle_call(mock_session)

        on_openai_audio = mock_instance.set_audio_callback.call_args[0][0]
        # Very small audio - after resample won't fill a 320-byte chunk
        on_openai_audio(b"\x01\x00" * 6)  # 12 bytes, resamples to ~4 bytes


# --- Send Audio Loop ---


class TestSendAudioLoop:
    async def test_sends_frames_from_queue(self):
        session = AsyncMock()
        session.is_active = True
        queue: asyncio.Queue[bytes] = asyncio.Queue()

        frame = b"\x01" * FRAME_SIZE
        queue.put_nowait(frame)

        # Stop after one iteration
        call_count = 0

        async def send_then_stop(data):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                session.is_active = False

        session.send_audio_frame = send_then_stop
        await _send_audio_loop(session, queue)

    async def test_sends_silence_when_empty(self):
        session = AsyncMock()
        session.is_active = True
        queue: asyncio.Queue[bytes] = asyncio.Queue()

        call_count = 0
        received_frames = []

        async def capture_frame(data):
            nonlocal call_count
            received_frames.append(data)
            call_count += 1
            if call_count >= 1:
                session.is_active = False

        session.send_audio_frame = capture_frame
        await _send_audio_loop(session, queue)

        assert len(received_frames) == 1
        assert received_frames[0] == b"\x00" * FRAME_SIZE

    async def test_stops_when_inactive(self):
        session = AsyncMock()
        session.is_active = False
        queue: asyncio.Queue[bytes] = asyncio.Queue()

        await _send_audio_loop(session, queue)
        session.send_audio_frame.assert_not_called()

    async def test_handles_cancellation(self):
        session = AsyncMock()
        session.is_active = True
        queue: asyncio.Queue[bytes] = asyncio.Queue()

        # Make send_audio_frame raise CancelledError
        session.send_audio_frame = AsyncMock(side_effect=asyncio.CancelledError)

        # CancelledError is caught internally
        await _send_audio_loop(session, queue)

    async def test_skips_sleep_when_elapsed_exceeds_frame_duration(self):
        """Line 337->322: sleep_time <= 0 when send takes longer than FRAME_DURATION."""
        session = AsyncMock()
        session.is_active = True
        queue: asyncio.Queue[bytes] = asyncio.Queue()

        frame = b"\x01" * FRAME_SIZE
        queue.put_nowait(frame)

        call_count = 0

        async def slow_send(data):
            """Simulate a send that takes longer than FRAME_DURATION."""
            nonlocal call_count
            call_count += 1
            # Sleep longer than FRAME_DURATION to make elapsed > FRAME_DURATION
            await asyncio.sleep(0.03)
            if call_count >= 1:
                session.is_active = False

        session.send_audio_frame = slow_send
        await _send_audio_loop(session, queue)
