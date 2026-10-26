# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for asterisk/audiosocket.py."""

import asyncio
import struct
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from asterisk.audiosocket import (
    PACKET_AUDIO,
    PACKET_ERROR,
    PACKET_HANGUP,
    PACKET_SILENCE,
    PACKET_UUID,
    AudioSocketServer,
    AudioSocketSession,
)

# --- Packet Constants ---


class TestPacketConstants:
    def test_packet_hangup_value(self):
        assert PACKET_HANGUP == 0x00

    def test_packet_uuid_value(self):
        assert PACKET_UUID == 0x01

    def test_packet_silence_value(self):
        assert PACKET_SILENCE == 0x02

    def test_packet_audio_value(self):
        assert PACKET_AUDIO == 0x10

    def test_packet_error_value(self):
        assert PACKET_ERROR == 0xFF


# --- AudioSocketSession ---


class TestAudioSocketSessionInit:
    def test_stores_reader_and_writer(
        self, audiosocket_session, mock_stream_reader, mock_stream_writer
    ):
        assert audiosocket_session.reader is mock_stream_reader
        assert audiosocket_session.writer is mock_stream_writer

    def test_channel_uuid_is_none(self, audiosocket_session):
        assert audiosocket_session.channel_uuid is None

    def test_is_active_is_true(self, audiosocket_session):
        assert audiosocket_session.is_active is True

    def test_audio_callback_is_none(self, audiosocket_session):
        assert audiosocket_session._audio_callback is None


class TestSetAudioCallback:
    def test_sets_callback(self, audiosocket_session):
        cb = MagicMock()
        audiosocket_session.set_audio_callback(cb)
        assert audiosocket_session._audio_callback is cb


class TestReadPacket:
    async def test_parses_header_and_payload(self, audiosocket_session, mock_stream_reader):
        payload = b"\x01" * 320
        header = struct.pack(">BH", PACKET_AUDIO, 320)
        mock_stream_reader.readexactly = AsyncMock(side_effect=[header, payload])

        ptype, data = await audiosocket_session.read_packet()
        assert ptype == PACKET_AUDIO
        assert data == payload

    async def test_zero_length_payload(self, audiosocket_session, mock_stream_reader):
        header = struct.pack(">BH", PACKET_SILENCE, 0)
        mock_stream_reader.readexactly = AsyncMock(return_value=header)

        ptype, data = await audiosocket_session.read_packet()
        assert ptype == PACKET_SILENCE
        assert data == b""

    async def test_uuid_16_bytes(self, audiosocket_session, mock_stream_reader):
        test_uuid = uuid.uuid4()
        header = struct.pack(">BH", PACKET_UUID, 16)
        mock_stream_reader.readexactly = AsyncMock(side_effect=[header, test_uuid.bytes])

        ptype, data = await audiosocket_session.read_packet()
        assert ptype == PACKET_UUID
        assert len(data) == 16


class TestSendAudioFrame:
    async def test_sends_exact_320_bytes(
        self, audiosocket_session, mock_stream_writer, silence_320
    ):
        await audiosocket_session.send_audio_frame(silence_320)
        written = mock_stream_writer.write.call_args[0][0]
        # 3 header bytes + 320 payload
        assert len(written) == 323
        assert written[0] == PACKET_AUDIO

    async def test_pads_short_frame(self, audiosocket_session, mock_stream_writer):
        await audiosocket_session.send_audio_frame(b"\x01" * 100)
        written = mock_stream_writer.write.call_args[0][0]
        assert len(written) == 323  # 3 + 320

    async def test_truncates_long_frame(self, audiosocket_session, mock_stream_writer):
        await audiosocket_session.send_audio_frame(b"\x01" * 500)
        written = mock_stream_writer.write.call_args[0][0]
        assert len(written) == 323  # 3 + 320

    async def test_does_nothing_when_inactive(self, audiosocket_session, mock_stream_writer):
        audiosocket_session.is_active = False
        await audiosocket_session.send_audio_frame(b"\x00" * 320)
        mock_stream_writer.write.assert_not_called()

    async def test_handles_write_error(self, audiosocket_session, mock_stream_writer):
        mock_stream_writer.drain = AsyncMock(side_effect=OSError("broken pipe"))
        await audiosocket_session.send_audio_frame(b"\x00" * 320)
        # Should not raise


class TestSendAudio:
    async def test_splits_into_320_byte_chunks(self, audiosocket_session, mock_stream_writer):
        await audiosocket_session.send_audio(b"\x01" * 640)
        assert mock_stream_writer.write.call_count == 2

    async def test_pads_last_chunk(self, audiosocket_session, mock_stream_writer):
        await audiosocket_session.send_audio(b"\x01" * 400)
        assert mock_stream_writer.write.call_count == 2
        # Second chunk should be padded to 320
        second_write = mock_stream_writer.write.call_args_list[1][0][0]
        assert len(second_write) == 323  # 3 + 320

    async def test_empty_data_does_nothing(self, audiosocket_session, mock_stream_writer):
        await audiosocket_session.send_audio(b"")
        mock_stream_writer.write.assert_not_called()

    async def test_inactive_session_does_nothing(self, audiosocket_session, mock_stream_writer):
        audiosocket_session.is_active = False
        await audiosocket_session.send_audio(b"\x01" * 320)
        mock_stream_writer.write.assert_not_called()

    async def test_handles_write_error(self, audiosocket_session, mock_stream_writer):
        mock_stream_writer.drain = AsyncMock(side_effect=OSError("broken"))
        await audiosocket_session.send_audio(b"\x01" * 320)
        # Should not raise


class TestSendHangup:
    async def test_sends_correct_packet(self, audiosocket_session, mock_stream_writer):
        await audiosocket_session.send_hangup()
        written = mock_stream_writer.write.call_args[0][0]
        assert len(written) == 3
        assert written[0] == PACKET_HANGUP

    async def test_sets_inactive(self, audiosocket_session):
        await audiosocket_session.send_hangup()
        assert audiosocket_session.is_active is False


class TestReceiveLoop:
    def _make_packet(self, ptype, payload=b""):
        header = struct.pack(">BH", ptype, len(payload))
        return header, payload

    async def test_processes_uuid_packet(self, audiosocket_session, mock_stream_reader):
        test_uuid = uuid.uuid4()
        header, payload = self._make_packet(PACKET_UUID, test_uuid.bytes)
        hangup_header, _ = self._make_packet(PACKET_HANGUP)

        mock_stream_reader.readexactly = AsyncMock(side_effect=[header, payload, hangup_header])
        await audiosocket_session.receive_loop()
        assert audiosocket_session.channel_uuid == str(test_uuid)

    async def test_processes_audio_with_callback(self, audiosocket_session, mock_stream_reader):
        callback = MagicMock()
        audiosocket_session.set_audio_callback(callback)

        audio_data = b"\x01" * 320
        header, payload = self._make_packet(PACKET_AUDIO, audio_data)
        hangup_header, _ = self._make_packet(PACKET_HANGUP)

        mock_stream_reader.readexactly = AsyncMock(side_effect=[header, payload, hangup_header])
        await audiosocket_session.receive_loop()
        callback.assert_called_once_with(audio_data)

    async def test_ignores_audio_without_callback(self, audiosocket_session, mock_stream_reader):
        audio_data = b"\x01" * 320
        header, payload = self._make_packet(PACKET_AUDIO, audio_data)
        hangup_header, _ = self._make_packet(PACKET_HANGUP)

        mock_stream_reader.readexactly = AsyncMock(side_effect=[header, payload, hangup_header])
        await audiosocket_session.receive_loop()
        # Should not crash

    async def test_processes_silence_packet(self, audiosocket_session, mock_stream_reader):
        header, _ = self._make_packet(PACKET_SILENCE)
        hangup_header, _ = self._make_packet(PACKET_HANGUP)

        mock_stream_reader.readexactly = AsyncMock(side_effect=[header, hangup_header])
        await audiosocket_session.receive_loop()

    async def test_handles_hangup(self, audiosocket_session, mock_stream_reader):
        header, _ = self._make_packet(PACKET_HANGUP)
        mock_stream_reader.readexactly = AsyncMock(return_value=header)

        await audiosocket_session.receive_loop()
        assert audiosocket_session.is_active is False

    async def test_handles_error_packet(self, audiosocket_session, mock_stream_reader):
        error_msg = b"something went wrong"
        header, payload = self._make_packet(PACKET_ERROR, error_msg)

        mock_stream_reader.readexactly = AsyncMock(side_effect=[header, payload])
        await audiosocket_session.receive_loop()
        assert audiosocket_session.is_active is False

    async def test_handles_unknown_packet_type(self, audiosocket_session, mock_stream_reader):
        header, _ = self._make_packet(0xAB)
        hangup_header, _ = self._make_packet(PACKET_HANGUP)

        mock_stream_reader.readexactly = AsyncMock(side_effect=[header, hangup_header])
        await audiosocket_session.receive_loop()

    async def test_handles_incomplete_read(self, audiosocket_session, mock_stream_reader):
        mock_stream_reader.readexactly = AsyncMock(side_effect=asyncio.IncompleteReadError(b"", 3))
        await audiosocket_session.receive_loop()
        assert audiosocket_session.is_active is False

    async def test_handles_generic_exception(self, audiosocket_session, mock_stream_reader):
        mock_stream_reader.readexactly = AsyncMock(side_effect=RuntimeError("network error"))
        await audiosocket_session.receive_loop()
        assert audiosocket_session.is_active is False


class TestClose:
    def test_sets_inactive_and_closes_writer(self, audiosocket_session, mock_stream_writer):
        audiosocket_session.close()
        assert audiosocket_session.is_active is False
        mock_stream_writer.close.assert_called_once()

    def test_close_without_writer(self, mock_stream_reader):
        """Branch 169->exit: close when writer is falsy."""
        from asterisk.audiosocket import AudioSocketSession

        session = AudioSocketSession(mock_stream_reader, None)
        session.close()
        assert session.is_active is False


class TestReceiveLoopExitBranch:
    """Branch 128->exit: receive_loop exits when is_active is set False externally."""

    def _make_packet(self, ptype, payload=b""):
        header = struct.pack(">BH", ptype, len(payload))
        return header, payload

    async def test_exits_when_is_active_set_false(self, audiosocket_session, mock_stream_reader):
        """The while loop condition becomes False after processing a packet."""
        audio_data = b"\x01" * 320
        header, payload = self._make_packet(PACKET_AUDIO, audio_data)

        call_count = 0

        async def read_and_deactivate(n):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return header
            elif call_count == 2:
                # After returning payload, set inactive so loop condition fails
                audiosocket_session.is_active = False
                return payload
            # Should not reach here
            raise asyncio.IncompleteReadError(b"", n)

        mock_stream_reader.readexactly = read_and_deactivate
        await audiosocket_session.receive_loop()
        assert audiosocket_session.is_active is False


# --- AudioSocketServer ---


class TestAudioSocketServer:
    def test_init_default_host_port(self):
        server = AudioSocketServer()
        assert server.host == "127.0.0.1"
        assert server.port == 9092

    def test_init_custom_host_port(self):
        server = AudioSocketServer(host="0.0.0.0", port=8080)
        assert server.host == "0.0.0.0"
        assert server.port == 8080

    def test_set_handler(self):
        server = AudioSocketServer()
        handler = AsyncMock()
        server.set_handler(handler)
        assert server.handler is handler

    async def test_handle_connection_calls_handler(self, mock_stream_reader, mock_stream_writer):
        server = AudioSocketServer()
        handler = AsyncMock()
        server.set_handler(handler)

        await server.handle_connection(mock_stream_reader, mock_stream_writer)
        handler.assert_called_once()
        # First arg should be an AudioSocketSession
        session = handler.call_args[0][0]
        assert isinstance(session, AudioSocketSession)

    async def test_handle_connection_no_handler(self, mock_stream_reader, mock_stream_writer):
        server = AudioSocketServer()
        await server.handle_connection(mock_stream_reader, mock_stream_writer)
        # Should not crash, writer should be closed
        mock_stream_writer.wait_closed.assert_called_once()

    async def test_handle_connection_handler_exception(
        self, mock_stream_reader, mock_stream_writer
    ):
        server = AudioSocketServer()
        server.set_handler(AsyncMock(side_effect=RuntimeError("boom")))

        await server.handle_connection(mock_stream_reader, mock_stream_writer)
        # Should not crash, writer should be closed
        mock_stream_writer.wait_closed.assert_called_once()

    async def test_stop_closes_server(self):
        server = AudioSocketServer()
        mock_server = MagicMock()
        mock_server.close = MagicMock()
        mock_server.wait_closed = AsyncMock()
        server.server = mock_server

        await server.stop()
        mock_server.close.assert_called_once()
        mock_server.wait_closed.assert_called_once()

    async def test_stop_no_server(self):
        server = AudioSocketServer()
        await server.stop()
        # Should not crash

    @patch("asterisk.audiosocket.asyncio.start_server", new_callable=AsyncMock)
    async def test_start_creates_and_serves(self, mock_start_server):
        """Lines 211-215: start() creates server and calls serve_forever."""
        server = AudioSocketServer(host="127.0.0.1", port=9092)

        # Create a mock server that supports async with
        mock_async_server = MagicMock()
        mock_async_server.serve_forever = AsyncMock()
        mock_async_server.__aenter__ = AsyncMock(return_value=mock_async_server)
        mock_async_server.__aexit__ = AsyncMock(return_value=False)
        mock_start_server.return_value = mock_async_server

        await server.start()
        mock_start_server.assert_called_once_with(server.handle_connection, "127.0.0.1", 9092)
        mock_async_server.serve_forever.assert_called_once()
