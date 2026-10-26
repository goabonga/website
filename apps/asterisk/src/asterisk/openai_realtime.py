# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""OpenAI Realtime API client for voice conversations.

This module handles the WebSocket connection to OpenAI's Realtime API,
providing bidirectional audio streaming with VAD (Voice Activity Detection).

Audio format requirements:
- Input to OpenAI: PCM 24kHz 16-bit mono (base64 encoded)
- Output from OpenAI: PCM 24kHz 16-bit mono (base64 encoded)
- Asterisk AudioSocket: PCM 8kHz 16-bit mono (raw bytes)

We need to resample between 8kHz (Asterisk) and 24kHz (OpenAI).
"""

import asyncio
import base64
import contextlib
import json
import logging
from collections.abc import Callable
from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection

logger = logging.getLogger(__name__)

OPENAI_REALTIME_URL = "wss://api.openai.com/v1/realtime"
OPENAI_REALTIME_MODEL = "gpt-4o-realtime-preview-2024-12-17"


class OpenAIRealtimeClient:
    """Client for OpenAI Realtime API with voice capabilities."""

    def __init__(
        self,
        api_key: str,
        model: str = OPENAI_REALTIME_MODEL,
        voice: str = "alloy",
        system_prompt: str = "You are a helpful phone assistant. Keep responses brief and conversational.",
        tools: list[dict] | None = None,
    ):
        self.api_key = api_key
        self.model = model
        self.voice = voice
        self.system_prompt = system_prompt
        self.tools = tools or []
        self.ws: ClientConnection | None = None
        self.is_connected = False
        self.is_responding = False  # Track if AI is currently speaking
        self._audio_callback: Callable[[bytes], None] | None = None
        self._transcript_callback: Callable[[str], None] | None = None
        self._interrupt_callback: Callable[[], None] | None = None
        self._response_done_callback: Callable[[], None] | None = None
        self._tool_call_callback: Callable[[str, dict[str, Any]], Any] | None = None
        self._pending_tool_calls: dict[str, asyncio.Future] = {}
        self._receive_task: asyncio.Task | None = None

    def set_audio_callback(self, callback: Callable[[bytes], None]):
        """Set callback for receiving audio from OpenAI (24kHz PCM)."""
        self._audio_callback = callback

    def set_transcript_callback(self, callback: Callable[[str], None]):
        """Set callback for receiving transcripts."""
        self._transcript_callback = callback

    def set_interrupt_callback(self, callback: Callable[[], None]):
        """Set callback for when user interrupts (barge-in)."""
        self._interrupt_callback = callback

    def set_response_done_callback(self, callback: Callable[[], None]):
        """Set callback for when AI response is complete."""
        self._response_done_callback = callback

    def set_tool_call_callback(self, callback: Callable[[str, dict[str, Any]], Any]):
        """Set callback for when AI calls a tool.

        Args:
            callback: Function(tool_name, arguments) called when tool is invoked
        """
        self._tool_call_callback = callback

    async def connect(self):
        """Connect to OpenAI Realtime API."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1",
        }

        url = f"{OPENAI_REALTIME_URL}?model={self.model}"

        try:
            self.ws = await websockets.connect(url, additional_headers=headers)
            self.is_connected = True
            logger.info("Connected to OpenAI Realtime API")

            # Configure the session
            await self._configure_session()

            # Start receiving messages
            self._receive_task = asyncio.create_task(self._receive_loop())

        except Exception as e:
            logger.error(f"Failed to connect to OpenAI Realtime API: {e}")
            raise

    async def _configure_session(self):
        """Configure the realtime session."""
        # Default hangup tool
        default_tools = [
            {
                "type": "function",
                "name": "hangup",
                "description": "End the phone call. Use this function when the user says goodbye, wants to hang up, or indicates they are done with the conversation.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reason": {
                            "type": "string",
                            "description": "Reason for ending the call (e.g., 'user_goodbye', 'user_request')",
                        }
                    },
                    "required": [],
                },
            }
        ]

        # Combine default tools with custom tools
        all_tools = default_tools + self.tools

        config = {
            "type": "session.update",
            "session": {
                "modalities": ["text", "audio"],
                "instructions": self.system_prompt,
                "voice": self.voice,
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "input_audio_transcription": {"model": "whisper-1"},
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.3,  # Lower = more sensitive to speech
                    "prefix_padding_ms": 200,  # Less padding before speech
                    "silence_duration_ms": 400,  # Shorter silence to end turn
                    "create_response": True,  # Auto-create response after user stops
                },
                "tools": all_tools,
                "tool_choice": "auto",
            },
        }
        assert self.ws is not None
        await self.ws.send(json.dumps(config))
        logger.info(f"Session configured with VAD and {len(all_tools)} tools")

    async def send_audio(self, audio_data: bytes):
        """Send audio data to OpenAI.

        Args:
            audio_data: Raw PCM audio (24kHz, 16-bit mono)
        """
        if not self.is_connected or not self.ws:
            return

        # Base64 encode the audio
        audio_b64 = base64.b64encode(audio_data).decode("utf-8")

        message = {
            "type": "input_audio_buffer.append",
            "audio": audio_b64,
        }

        try:
            await self.ws.send(json.dumps(message))
        except Exception as e:
            logger.error(f"Error sending audio: {e}")

    async def commit_audio(self):
        """Commit the audio buffer (manual turn detection)."""
        if not self.is_connected or not self.ws:
            return

        message = {"type": "input_audio_buffer.commit"}
        await self.ws.send(json.dumps(message))

    async def send_text(self, text: str):
        """Send a text message to the conversation."""
        if not self.is_connected or not self.ws:
            return

        message = {
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": text}],
            },
        }
        await self.ws.send(json.dumps(message))

        # Request a response
        await self.ws.send(json.dumps({"type": "response.create"}))

    async def cancel_response(self):
        """Cancel the current response (for interruptions)."""
        if not self.is_connected or not self.ws:
            return

        message = {"type": "response.cancel"}
        await self.ws.send(json.dumps(message))

    async def _send_function_output(
        self, call_id: str, output: dict, request_response: bool = True
    ):
        """Send function call output back to OpenAI.

        Args:
            call_id: The function call ID
            output: The function result
            request_response: Whether to request a new response after the output
        """
        if not self.is_connected or not self.ws:
            return

        message = {
            "type": "conversation.item.create",
            "item": {
                "type": "function_call_output",
                "call_id": call_id,
                "output": json.dumps(output),
            },
        }
        await self.ws.send(json.dumps(message))

        # Request a new response after function output (unless disabled)
        if request_response:
            await self.ws.send(json.dumps({"type": "response.create"}))

    async def _receive_loop(self):
        """Main loop to receive messages from OpenAI."""
        assert self.ws is not None
        try:
            async for message in self.ws:
                await self._handle_message(json.loads(message))
        except websockets.ConnectionClosed:
            logger.info("OpenAI WebSocket connection closed")
        except Exception as e:
            logger.error(f"Error in receive loop: {e}")
        finally:
            self.is_connected = False

    async def _handle_message(self, message: dict):
        """Handle a message from OpenAI."""
        msg_type = message.get("type", "")

        if msg_type == "session.created":
            logger.info("OpenAI session created")

        elif msg_type == "session.updated":
            logger.info("OpenAI session updated")

        elif msg_type == "response.created":
            # AI started generating a response
            self.is_responding = True
            logger.debug("Response started")

        elif msg_type == "response.audio.delta":
            # Incoming audio chunk (base64 encoded PCM 24kHz)
            audio_b64 = message.get("delta", "")
            if audio_b64 and self._audio_callback:
                audio_data = base64.b64decode(audio_b64)
                self._audio_callback(audio_data)

        elif msg_type == "response.audio_transcript.delta":
            # Assistant's speech transcript
            transcript = message.get("delta", "")
            if transcript:
                logger.debug(f"Assistant transcript: {transcript}")

        elif msg_type == "conversation.item.input_audio_transcription.completed":
            # User's speech transcript
            transcript = message.get("transcript", "")
            if transcript and self._transcript_callback:
                self._transcript_callback(transcript)
            logger.info(f"User said: {transcript}")

        elif msg_type == "input_audio_buffer.speech_started":
            logger.debug("VAD: Speech started")
            # User is speaking - if AI is responding, this is an interruption
            if self.is_responding:
                logger.info("User interrupted - canceling response")
                await self.cancel_response()
                if self._interrupt_callback:
                    self._interrupt_callback()

        elif msg_type == "input_audio_buffer.speech_stopped":
            logger.debug("VAD: Speech stopped")

        elif msg_type == "response.done":
            self.is_responding = False
            logger.debug("Response completed")
            if self._response_done_callback:
                self._response_done_callback()

        elif msg_type == "response.cancelled":
            self.is_responding = False
            logger.debug("Response cancelled")

        elif msg_type == "response.function_call_arguments.done":
            # Function call completed - extract tool name and arguments
            call_id = message.get("call_id", "")
            name = message.get("name", "")
            arguments_str = message.get("arguments", "{}")

            try:
                arguments = json.loads(arguments_str) if arguments_str else {}
            except json.JSONDecodeError:
                arguments = {}

            logger.info(f"Tool call: {name}({arguments})")

            # Call the tool callback and get result (may be a Future for async tools)
            result: Any = None
            if self._tool_call_callback:
                result = self._tool_call_callback(name, arguments)

            # If result is a coroutine or Future, await it
            if asyncio.isfuture(result) or asyncio.iscoroutine(result):
                try:
                    result = await result
                    logger.info(f"Tool {name} returned: {result}")
                except Exception as e:
                    logger.error(f"Error executing tool {name}: {e}")
                    result = {"error": str(e)}

            # Send function call output to OpenAI
            # For hangup, don't request a new response (avoids "call ended" message)
            request_response = name != "hangup"
            output = result if result is not None else {"success": True}
            await self._send_function_output(call_id, output, request_response=request_response)

        elif msg_type == "error":
            error = message.get("error", {})
            logger.error(f"OpenAI error: {error.get('message', 'Unknown error')}")

    async def disconnect(self):
        """Disconnect from OpenAI Realtime API."""
        self.is_connected = False

        if self._receive_task:
            self._receive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._receive_task

        if self.ws:
            await self.ws.close()
            self.ws = None

        logger.info("Disconnected from OpenAI Realtime API")
