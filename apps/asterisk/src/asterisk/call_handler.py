# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Call handler that bridges AudioSocket and OpenAI Realtime."""

import asyncio
import contextlib
import logging
import os
import time

import numpy as np

from asterisk.audio_utils import AudioBuffer, resample_8k_to_24k, resample_24k_to_8k
from asterisk.audiosocket import AudioSocketSession
from asterisk.config import config
from asterisk.openai_realtime import OpenAIRealtimeClient

logger = logging.getLogger(__name__)

# Greeting message - can be customized via environment variable
GREETING_MESSAGE = os.getenv(
    "GREETING_MESSAGE",
    "Say hello to the caller, introduce yourself as Chris, and ask how you can help.",
)

# Audio timing constants
FRAME_SIZE = 320  # 160 samples * 2 bytes = 20ms at 8kHz
FRAME_DURATION = 0.02  # 20ms per frame

# Local VAD settings
LOCAL_VAD_RMS_THRESHOLD = 1000  # RMS threshold for speech detection
LOCAL_VAD_DEBOUNCE_MS = 300  # Minimum time between interrupts


def _build_rag_tools() -> list[dict]:
    """Build RAG-related tools if enabled."""
    if not config.RAG_ENABLED:
        return []

    return [
        {
            "type": "function",
            "name": "search_knowledge",
            "description": "Search for an answer in the knowledge base. ALWAYS use this function BEFORE answering a user's question to check if the answer exists in the knowledge base.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The user's question to search for"}
                },
                "required": ["query"],
            },
        }
    ]


def _build_rag_system_prompt() -> str:
    """Build system prompt with RAG instructions if enabled."""
    base_prompt = config.OPENAI_SYSTEM_PROMPT

    if not config.RAG_ENABLED:
        return base_prompt

    rag_instructions = """

IMPORTANT KNOWLEDGE BASE INSTRUCTIONS:
1. BEFORE answering any question, you MUST use the search_knowledge() function to search for the answer.
2. If search_knowledge() returns results, use them to formulate your response.
3. If search_knowledge() finds nothing (no results), you MUST say that you cannot answer this question and give examples of questions you can answer (provided by the function).
4. Never make up an answer. Use ONLY information from the knowledge base.
5. If the user asks an off-topic question (greetings, goodbye, etc.), you can respond normally without using search_knowledge().
"""
    return base_prompt + rag_instructions


async def handle_call(session: AudioSocketSession):
    """Handle an incoming call with OpenAI Realtime integration.

    This function bridges:
    - AudioSocket (8kHz PCM from Asterisk)
    - OpenAI Realtime API (24kHz PCM via WebSocket)

    Args:
        session: The AudioSocket session from Asterisk
    """
    logger.info("Starting call handler")

    # Import knowledge base only if RAG is enabled
    # Note: knowledge base is a global singleton shared across all calls
    knowledge_base = None
    if config.RAG_ENABLED:
        from asterisk.knowledge_base import get_knowledge_base

        knowledge_base = await get_knowledge_base()
        logger.info("RAG enabled - knowledge base connected")

    # Build tools and system prompt
    rag_tools = _build_rag_tools()
    system_prompt = _build_rag_system_prompt()

    # Create OpenAI Realtime client
    openai_client = OpenAIRealtimeClient(
        api_key=config.OPENAI_API_KEY,
        model=config.OPENAI_MODEL,
        voice=config.OPENAI_VOICE,
        system_prompt=system_prompt,
        tools=rag_tools,
    )

    # Buffer for input audio (from Asterisk to OpenAI)
    # 640 bytes = 320 samples = 40ms at 8kHz
    input_buffer = AudioBuffer(chunk_size=640)

    # Buffer for output audio (from OpenAI to Asterisk)
    # Must output exactly 320 bytes (20ms) per frame
    output_buffer = AudioBuffer(chunk_size=FRAME_SIZE)

    # Queue for sending audio to Asterisk (fixed 320-byte chunks)
    audio_to_asterisk: asyncio.Queue[bytes] = asyncio.Queue()

    def on_openai_audio(audio_24k: bytes):
        """Callback when OpenAI sends audio."""
        if not audio_24k:
            return

        # Log audio chunk size for debugging
        logger.debug(f"Received {len(audio_24k)} bytes from OpenAI")

        # Resample 24kHz to 8kHz
        audio_8k = resample_24k_to_8k(audio_24k)
        if not audio_8k:
            return

        logger.debug(f"Resampled to {len(audio_8k)} bytes for Asterisk")

        # Buffer into fixed 320-byte chunks and queue them
        chunks = output_buffer.add_and_get_chunks(audio_8k)
        for chunk in chunks:
            audio_to_asterisk.put_nowait(chunk)

        if chunks:
            logger.debug(f"Queued {len(chunks)} audio frames for Asterisk")

    # Local VAD state
    last_interrupt_time = [0.0]  # Use list to allow modification in nested function
    speech_frame_count = [0]

    def on_asterisk_audio(audio_8k: bytes):
        """Callback when Asterisk sends audio."""

        # Check audio level for local interrupt detection
        if openai_client.is_responding and len(audio_8k) >= 2:
            samples = np.frombuffer(audio_8k, dtype="<i2")
            rms = np.sqrt(np.mean(samples.astype(np.float64) ** 2))

            # Count consecutive frames with speech
            if rms > LOCAL_VAD_RMS_THRESHOLD:
                speech_frame_count[0] += 1
            else:
                speech_frame_count[0] = 0

            # Require 3 consecutive frames (~60ms) of speech to trigger interrupt
            # Also enforce debounce to avoid rapid interrupts
            current_time = time.time()
            if (
                speech_frame_count[0] >= 3
                and current_time - last_interrupt_time[0] > LOCAL_VAD_DEBOUNCE_MS / 1000
            ):
                logger.info(f"Local VAD: RMS={rms:.0f}, triggering interrupt")
                last_interrupt_time[0] = current_time
                speech_frame_count[0] = 0
                asyncio.create_task(openai_client.cancel_response())
                on_interrupt()
        else:
            speech_frame_count[0] = 0

        # Buffer and resample
        buffered = input_buffer.add(audio_8k)
        if buffered:
            audio_24k = resample_8k_to_24k(buffered)
            # Send to OpenAI (fire and forget)
            asyncio.create_task(openai_client.send_audio(audio_24k))

    # Flag to request hangup
    hangup_requested = False

    def on_transcript(text: str):
        """Callback when user speech is transcribed."""
        logger.info(f"Caller said: {text}")

    async def handle_search_knowledge(query: str) -> dict:
        """Handle search_knowledge tool call."""
        if not knowledge_base:
            return {"error": "Knowledge base not available"}

        results = await knowledge_base.search(query)

        if results:
            # Found matching entries
            answers = []
            for entry in results:
                answers.append(
                    {
                        "question": entry.question,
                        "answer": entry.answer,
                        "confidence": round(entry.similarity, 2),
                    }
                )
            return {"found": True, "results": answers}
        else:
            # No matches - get sample questions
            samples = await knowledge_base.get_sample_questions(limit=3)
            return {
                "found": False,
                "message": "No answer found in the knowledge base.",
                "sample_questions": samples,
            }

    def on_tool_call(tool_name: str, arguments: dict):
        """Callback when AI calls a tool."""
        nonlocal hangup_requested
        logger.info(f"Tool called: {tool_name} with args: {arguments}")

        if tool_name == "hangup":
            logger.info("Hangup tool called - will terminate after AI says goodbye")
            hangup_requested = True
            return None  # No result needed for hangup

        if tool_name == "search_knowledge":
            query = arguments.get("query", "")
            # Run async search in event loop
            future = asyncio.ensure_future(handle_search_knowledge(query))
            return future

        return None

    def on_interrupt():
        """Callback when user interrupts the AI response."""
        logger.info("Clearing audio queue due to interruption")
        # Clear the output buffer
        output_buffer.clear()
        # Clear the audio queue
        while not audio_to_asterisk.empty():
            try:
                audio_to_asterisk.get_nowait()
            except asyncio.QueueEmpty:
                break

    # Set up callbacks
    session.set_audio_callback(on_asterisk_audio)
    openai_client.set_audio_callback(on_openai_audio)
    openai_client.set_transcript_callback(on_transcript)
    openai_client.set_interrupt_callback(on_interrupt)
    openai_client.set_tool_call_callback(on_tool_call)

    try:
        # Connect to OpenAI
        await openai_client.connect()
        logger.info("OpenAI Realtime connected")

        # Start tasks
        receive_task = asyncio.create_task(session.receive_loop())
        send_task = asyncio.create_task(_send_audio_loop(session, audio_to_asterisk))

        # Wait a moment for the connection to stabilize
        await asyncio.sleep(0.3)

        # Send initial greeting request - the bot speaks first
        logger.info("Requesting greeting from OpenAI")
        await openai_client.send_text(GREETING_MESSAGE)

        # Main loop - check for hangup request
        while session.is_active:
            # Check if user requested hangup
            if hangup_requested:
                logger.info("Processing hangup request")

                # Wait for current response to finish (AI might already be saying goodbye)
                wait_timeout = 3.0
                while openai_client.is_responding and wait_timeout > 0:
                    await asyncio.sleep(0.1)
                    wait_timeout -= 0.1

                # Wait for audio queue to empty (let the goodbye play)
                drain_timeout = 5.0
                while not audio_to_asterisk.empty() and drain_timeout > 0:
                    await asyncio.sleep(0.1)
                    drain_timeout -= 0.1

                # Small delay to ensure audio is fully played
                await asyncio.sleep(0.5)

                # Hangup
                logger.info("Sending hangup to Asterisk")
                await session.send_hangup()
                break

            # Small sleep to prevent busy loop
            await asyncio.sleep(0.1)

        # Cancel tasks
        receive_task.cancel()
        send_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await receive_task
        with contextlib.suppress(asyncio.CancelledError):
            await send_task

    except Exception as e:
        logger.error(f"Error in call handler: {e}", exc_info=True)

    finally:
        # Disconnect from OpenAI
        await openai_client.disconnect()
        logger.info("Call handler finished")


async def _send_audio_loop(session: AudioSocketSession, queue: asyncio.Queue[bytes]):
    """Loop to send audio from queue to Asterisk with proper timing.

    Sends exactly one 320-byte frame every 20ms for proper audio playback.
    """
    silence_frame = b"\x00" * FRAME_SIZE

    try:
        while session.is_active:
            start_time = asyncio.get_event_loop().time()

            # Get audio frame or use silence
            try:
                audio = queue.get_nowait()
            except asyncio.QueueEmpty:
                audio = silence_frame

            # Send exactly one frame
            await session.send_audio_frame(audio)

            # Maintain 20ms timing
            elapsed = asyncio.get_event_loop().time() - start_time
            sleep_time = max(0, FRAME_DURATION - elapsed)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

    except asyncio.CancelledError:
        pass
