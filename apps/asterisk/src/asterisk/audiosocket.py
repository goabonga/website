# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""AudioSocket server for Asterisk bidirectional audio streaming.

AudioSocket protocol:
- Each packet has a 3-byte header: 1 byte type + 2 bytes length (big-endian)
- Type 0x00: UUID (16 bytes) - sent at connection start
- Type 0x01: Audio data (signed linear 16-bit, 8kHz mono)
- Type 0x02: Hangup signal
- Type 0x10: Error
"""

import asyncio
import contextlib
import logging
import struct
import uuid
from collections.abc import Callable

logger = logging.getLogger(__name__)

# AudioSocket packet types (from CyCoreSystems/audiosocket protocol)
# https://github.com/CyCoreSystems/audiosocket
PACKET_HANGUP = 0x00  # Terminate connection
PACKET_UUID = 0x01  # UUID message (16 bytes) - sent by Asterisk at start
PACKET_SILENCE = 0x02  # Silence indicator
PACKET_AUDIO = 0x10  # Audio data (signed linear 16-bit, 8kHz mono, little-endian)
PACKET_ERROR = 0xFF  # Error message


class AudioSocketSession:
    """Represents an AudioSocket session with Asterisk."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.reader = reader
        self.writer = writer
        self.channel_uuid: str | None = None
        self.is_active = True
        self._audio_callback: Callable[[bytes], None] | None = None

    def set_audio_callback(self, callback: Callable[[bytes], None]):
        """Set callback for incoming audio data."""
        self._audio_callback = callback

    async def read_packet(self) -> tuple[int, bytes]:
        """Read a single AudioSocket packet.

        Returns:
            Tuple of (packet_type, payload)
        """
        # Read 3-byte header
        header = await self.reader.readexactly(3)
        packet_type = header[0]
        length = struct.unpack(">H", header[1:3])[0]

        # Read payload
        payload = await self.reader.readexactly(length) if length > 0 else b""

        return packet_type, payload

    async def send_audio_frame(self, frame: bytes):
        """Send a single audio frame to Asterisk.

        This method sends exactly one 320-byte frame (20ms at 8kHz).
        Use this for timed audio output.

        Args:
            frame: Exactly 320 bytes of PCM audio (signed 16-bit LE, 8kHz mono)
        """
        if not self.is_active:
            return

        # Ensure frame is exactly 320 bytes
        if len(frame) < 320:
            frame = frame + b"\x00" * (320 - len(frame))
        elif len(frame) > 320:
            frame = frame[:320]

        # Build packet: type (1 byte) + length (2 bytes big-endian) + data
        header = struct.pack(">BH", PACKET_AUDIO, 320)

        try:
            self.writer.write(header + frame)
            await self.writer.drain()
        except Exception as e:
            logger.error(f"Error sending audio frame: {e}")

    async def send_audio(self, audio_data: bytes):
        """Send audio data to Asterisk (legacy method, splits into frames).

        Args:
            audio_data: Raw PCM audio (signed 16-bit little-endian, 8kHz mono)
        """
        if not self.is_active or not audio_data:
            return

        # AudioSocket expects audio in chunks
        # Send in 320-byte chunks (160 samples = 20ms at 8kHz)
        chunk_size = 320
        offset = 0

        try:
            while offset < len(audio_data):
                chunk = audio_data[offset : offset + chunk_size]
                # Pad last chunk if needed
                if len(chunk) < chunk_size:
                    chunk = chunk + b"\x00" * (chunk_size - len(chunk))

                # Build packet: type (1 byte) + length (2 bytes big-endian) + data
                header = struct.pack(">BH", PACKET_AUDIO, len(chunk))
                self.writer.write(header + chunk)
                offset += chunk_size

            # Drain once after all chunks are queued
            await self.writer.drain()

        except Exception as e:
            logger.error(f"Error sending audio: {e}")

    async def send_hangup(self):
        """Send hangup signal to Asterisk."""
        header = struct.pack(">BH", PACKET_HANGUP, 0)
        self.writer.write(header)
        await self.writer.drain()
        self.is_active = False

    async def receive_loop(self):
        """Main loop to receive packets from Asterisk."""
        try:
            while self.is_active:
                packet_type, payload = await self.read_packet()

                if packet_type == PACKET_UUID:
                    # Channel UUID (16 bytes)
                    self.channel_uuid = str(uuid.UUID(bytes=payload))
                    logger.info(f"Channel UUID: {self.channel_uuid}")

                elif packet_type == PACKET_AUDIO:
                    # Audio data from caller
                    if self._audio_callback:
                        self._audio_callback(payload)

                elif packet_type == PACKET_SILENCE:
                    # Silence indicator - can be ignored or logged
                    logger.debug("Received silence indicator")

                elif packet_type == PACKET_HANGUP:
                    logger.info("Received hangup from Asterisk")
                    self.is_active = False
                    break

                elif packet_type == PACKET_ERROR:
                    error_msg = payload.decode("utf-8", errors="ignore")
                    logger.error(f"AudioSocket error: {error_msg}")
                    self.is_active = False
                    break

                else:
                    logger.warning(f"Unknown packet type: 0x{packet_type:02x}")

        except asyncio.IncompleteReadError:
            logger.info("Connection closed by Asterisk")
            self.is_active = False
        except Exception as e:
            logger.error(f"Error in receive loop: {e}")
            self.is_active = False

    def close(self):
        """Close the session."""
        self.is_active = False
        if self.writer:
            self.writer.close()


class AudioSocketServer:
    """AudioSocket server for handling Asterisk audio connections."""

    def __init__(self, host: str = "127.0.0.1", port: int = 9092):
        self.host = host
        self.port = port
        self.handler: Callable | None = None
        self.server: asyncio.Server | None = None

    def set_handler(self, handler: Callable):
        """Set the handler function for new connections.

        Handler signature: async def handler(session: AudioSocketSession)
        """
        self.handler = handler

    async def handle_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle an incoming AudioSocket connection."""
        addr = writer.get_extra_info("peername")
        logger.info(f"New AudioSocket connection from {addr}")

        session = AudioSocketSession(reader, writer)

        try:
            if self.handler:
                await self.handler(session)
            else:
                logger.warning("No handler registered for AudioSocket")
        except Exception as e:
            logger.error(f"Error handling AudioSocket connection: {e}")
        finally:
            session.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
            logger.info(f"AudioSocket connection closed from {addr}")

    async def start(self):
        """Start the AudioSocket server."""
        self.server = await asyncio.start_server(self.handle_connection, self.host, self.port)
        logger.info(f"AudioSocket server listening on {self.host}:{self.port}")

        async with self.server:
            await self.server.serve_forever()

    async def stop(self):
        """Stop the AudioSocket server."""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
