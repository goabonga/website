# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for asterisk/openai_realtime.py."""

import asyncio
import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import websockets
from asterisk.openai_realtime import OpenAIRealtimeClient


@pytest.fixture
def client():
    """Return a fresh OpenAIRealtimeClient."""
    return OpenAIRealtimeClient(
        api_key="sk-test",
        model="gpt-4o-test",
        voice="alloy",
        system_prompt="Test prompt",
        tools=[{"type": "function", "name": "test_tool"}],
    )


@pytest.fixture
def connected_client(client, mock_websocket):
    """Return a client with ws set and connected."""
    client.ws = mock_websocket
    client.is_connected = True
    return client


# --- Init ---


class TestOpenAIRealtimeClientInit:
    def test_stores_parameters(self, client):
        assert client.api_key == "sk-test"
        assert client.model == "gpt-4o-test"
        assert client.voice == "alloy"
        assert client.system_prompt == "Test prompt"
        assert len(client.tools) == 1

    def test_default_tools_is_empty_list(self):
        c = OpenAIRealtimeClient(api_key="sk-test")
        assert c.tools == []

    def test_initial_state(self, client):
        assert client.is_connected is False
        assert client.is_responding is False
        assert client.ws is None
        assert client._receive_task is None


# --- Callback Setters ---


class TestCallbackSetters:
    def test_set_audio_callback(self, client):
        cb = MagicMock()
        client.set_audio_callback(cb)
        assert client._audio_callback is cb

    def test_set_transcript_callback(self, client):
        cb = MagicMock()
        client.set_transcript_callback(cb)
        assert client._transcript_callback is cb

    def test_set_interrupt_callback(self, client):
        cb = MagicMock()
        client.set_interrupt_callback(cb)
        assert client._interrupt_callback is cb

    def test_set_response_done_callback(self, client):
        cb = MagicMock()
        client.set_response_done_callback(cb)
        assert client._response_done_callback is cb

    def test_set_tool_call_callback(self, client):
        cb = MagicMock()
        client.set_tool_call_callback(cb)
        assert client._tool_call_callback is cb


# --- Connect ---


class TestConnect:
    @patch("asterisk.openai_realtime.websockets.connect", new_callable=AsyncMock)
    async def test_connect_calls_websockets_with_url(self, mock_connect, client, mock_websocket):
        mock_connect.return_value = mock_websocket
        # Make _receive_loop a no-op
        mock_websocket.__aiter__ = MagicMock(return_value=iter([]))

        await client.connect()
        call_args = mock_connect.call_args
        assert "gpt-4o-test" in call_args[0][0]

    @patch("asterisk.openai_realtime.websockets.connect", new_callable=AsyncMock)
    async def test_connect_passes_auth_header(self, mock_connect, client, mock_websocket):
        mock_connect.return_value = mock_websocket
        mock_websocket.__aiter__ = MagicMock(return_value=iter([]))

        await client.connect()
        headers = mock_connect.call_args[1]["additional_headers"]
        assert headers["Authorization"] == "Bearer sk-test"
        assert headers["OpenAI-Beta"] == "realtime=v1"

    @patch("asterisk.openai_realtime.websockets.connect", new_callable=AsyncMock)
    async def test_connect_sets_is_connected(self, mock_connect, client, mock_websocket):
        mock_connect.return_value = mock_websocket
        mock_websocket.__aiter__ = MagicMock(return_value=iter([]))

        await client.connect()
        assert client.is_connected is True

    @patch("asterisk.openai_realtime.websockets.connect", new_callable=AsyncMock)
    async def test_connect_starts_receive_task(self, mock_connect, client, mock_websocket):
        mock_connect.return_value = mock_websocket
        mock_websocket.__aiter__ = MagicMock(return_value=iter([]))

        await client.connect()
        assert client._receive_task is not None
        # Clean up
        client._receive_task.cancel()
        try:
            await client._receive_task
        except asyncio.CancelledError:
            pass

    @patch("asterisk.openai_realtime.websockets.connect", new_callable=AsyncMock)
    async def test_connect_sends_session_config(self, mock_connect, client, mock_websocket):
        mock_connect.return_value = mock_websocket
        mock_websocket.__aiter__ = MagicMock(return_value=iter([]))

        await client.connect()
        # First ws.send call should be session.update
        first_msg = json.loads(mock_websocket.send.call_args_list[0][0][0])
        assert first_msg["type"] == "session.update"
        # Clean up
        client._receive_task.cancel()
        try:
            await client._receive_task
        except asyncio.CancelledError:
            pass

    @patch("asterisk.openai_realtime.websockets.connect", new_callable=AsyncMock)
    async def test_connect_failure_raises(self, mock_connect, client):
        mock_connect.side_effect = ConnectionRefusedError("refused")
        with pytest.raises(ConnectionRefusedError):
            await client.connect()
        assert client.is_connected is False


# --- Configure Session ---


class TestConfigureSession:
    async def test_sends_session_update(self, connected_client):
        await connected_client._configure_session()
        sent = json.loads(connected_client.ws.send.call_args[0][0])
        assert sent["type"] == "session.update"

    async def test_includes_vad_config(self, connected_client):
        await connected_client._configure_session()
        sent = json.loads(connected_client.ws.send.call_args[0][0])
        td = sent["session"]["turn_detection"]
        assert td["type"] == "server_vad"

    async def test_includes_hangup_tool(self, connected_client):
        await connected_client._configure_session()
        sent = json.loads(connected_client.ws.send.call_args[0][0])
        tool_names = [t["name"] for t in sent["session"]["tools"]]
        assert "hangup" in tool_names

    async def test_includes_custom_tools(self, connected_client):
        await connected_client._configure_session()
        sent = json.loads(connected_client.ws.send.call_args[0][0])
        tool_names = [t["name"] for t in sent["session"]["tools"]]
        assert "test_tool" in tool_names

    async def test_includes_system_prompt(self, connected_client):
        await connected_client._configure_session()
        sent = json.loads(connected_client.ws.send.call_args[0][0])
        assert sent["session"]["instructions"] == "Test prompt"

    async def test_audio_format_is_pcm16(self, connected_client):
        await connected_client._configure_session()
        sent = json.loads(connected_client.ws.send.call_args[0][0])
        assert sent["session"]["input_audio_format"] == "pcm16"
        assert sent["session"]["output_audio_format"] == "pcm16"


# --- Send Audio ---


class TestSendAudio:
    async def test_base64_encodes_data(self, connected_client):
        data = b"\x01\x02\x03\x04"
        await connected_client.send_audio(data)
        sent = json.loads(connected_client.ws.send.call_args[0][0])
        assert sent["audio"] == base64.b64encode(data).decode("utf-8")

    async def test_message_type(self, connected_client):
        await connected_client.send_audio(b"\x00" * 10)
        sent = json.loads(connected_client.ws.send.call_args[0][0])
        assert sent["type"] == "input_audio_buffer.append"

    async def test_not_connected_does_nothing(self, client):
        client.is_connected = False
        client.ws = MagicMock()
        await client.send_audio(b"\x00")
        client.ws.send.assert_not_called()

    async def test_no_ws_does_nothing(self, client):
        client.is_connected = True
        client.ws = None
        await client.send_audio(b"\x00")  # Should not raise

    async def test_handles_send_error(self, connected_client):
        connected_client.ws.send = AsyncMock(side_effect=OSError("broken"))
        await connected_client.send_audio(b"\x00")  # Should not raise


# --- Commit Audio ---


class TestCommitAudio:
    async def test_sends_correct_message(self, connected_client):
        await connected_client.commit_audio()
        sent = json.loads(connected_client.ws.send.call_args[0][0])
        assert sent["type"] == "input_audio_buffer.commit"

    async def test_not_connected_does_nothing(self, client):
        await client.commit_audio()  # Should not raise


# --- Send Text ---


class TestSendText:
    async def test_creates_conversation_item(self, connected_client):
        await connected_client.send_text("hello")
        first = json.loads(connected_client.ws.send.call_args_list[0][0][0])
        assert first["type"] == "conversation.item.create"
        assert first["item"]["content"][0]["text"] == "hello"

    async def test_requests_response(self, connected_client):
        await connected_client.send_text("hello")
        second = json.loads(connected_client.ws.send.call_args_list[1][0][0])
        assert second["type"] == "response.create"

    async def test_not_connected_does_nothing(self, client):
        await client.send_text("hello")  # Should not raise


# --- Cancel Response ---


class TestCancelResponse:
    async def test_sends_cancel(self, connected_client):
        await connected_client.cancel_response()
        sent = json.loads(connected_client.ws.send.call_args[0][0])
        assert sent["type"] == "response.cancel"

    async def test_not_connected_does_nothing(self, client):
        await client.cancel_response()  # Should not raise


# --- Handle Message ---


class TestHandleMessage:
    async def test_session_created(self, connected_client):
        await connected_client._handle_message({"type": "session.created"})

    async def test_session_updated(self, connected_client):
        await connected_client._handle_message({"type": "session.updated"})

    async def test_response_created_sets_responding(self, connected_client):
        await connected_client._handle_message({"type": "response.created"})
        assert connected_client.is_responding is True

    async def test_audio_delta_calls_callback(self, connected_client):
        cb = MagicMock()
        connected_client.set_audio_callback(cb)
        audio = base64.b64encode(b"\x01\x02\x03").decode()
        await connected_client._handle_message({"type": "response.audio.delta", "delta": audio})
        cb.assert_called_once_with(b"\x01\x02\x03")

    async def test_audio_delta_no_callback(self, connected_client):
        await connected_client._handle_message({"type": "response.audio.delta", "delta": "AQID"})

    async def test_audio_delta_empty(self, connected_client):
        cb = MagicMock()
        connected_client.set_audio_callback(cb)
        await connected_client._handle_message({"type": "response.audio.delta", "delta": ""})
        cb.assert_not_called()

    async def test_transcript_completed_calls_callback(self, connected_client):
        cb = MagicMock()
        connected_client.set_transcript_callback(cb)
        await connected_client._handle_message(
            {
                "type": "conversation.item.input_audio_transcription.completed",
                "transcript": "hello",
            }
        )
        cb.assert_called_once_with("hello")

    async def test_transcript_completed_no_callback(self, connected_client):
        await connected_client._handle_message(
            {
                "type": "conversation.item.input_audio_transcription.completed",
                "transcript": "hello",
            }
        )

    async def test_speech_started_no_interrupt_when_not_responding(self, connected_client):
        connected_client.is_responding = False
        connected_client.ws.send.reset_mock()
        await connected_client._handle_message({"type": "input_audio_buffer.speech_started"})
        # cancel_response should not be called (no response.cancel sent)
        connected_client.ws.send.assert_not_called()

    async def test_speech_started_interrupts_when_responding(self, connected_client):
        connected_client.is_responding = True
        cb = MagicMock()
        connected_client.set_interrupt_callback(cb)

        await connected_client._handle_message({"type": "input_audio_buffer.speech_started"})
        # Should have sent response.cancel
        sent = json.loads(connected_client.ws.send.call_args[0][0])
        assert sent["type"] == "response.cancel"
        cb.assert_called_once()

    async def test_speech_stopped(self, connected_client):
        await connected_client._handle_message({"type": "input_audio_buffer.speech_stopped"})

    async def test_response_done_clears_responding(self, connected_client):
        connected_client.is_responding = True
        await connected_client._handle_message({"type": "response.done"})
        assert connected_client.is_responding is False

    async def test_response_done_calls_callback(self, connected_client):
        cb = MagicMock()
        connected_client.set_response_done_callback(cb)
        await connected_client._handle_message({"type": "response.done"})
        cb.assert_called_once()

    async def test_response_cancelled_clears_responding(self, connected_client):
        connected_client.is_responding = True
        await connected_client._handle_message({"type": "response.cancelled"})
        assert connected_client.is_responding is False

    async def test_function_call_calls_tool_callback(self, connected_client):
        cb = MagicMock(return_value={"result": "ok"})
        connected_client.set_tool_call_callback(cb)

        await connected_client._handle_message(
            {
                "type": "response.function_call_arguments.done",
                "call_id": "call_123",
                "name": "test_tool",
                "arguments": '{"query": "test"}',
            }
        )
        cb.assert_called_once_with("test_tool", {"query": "test"})

    async def test_function_call_handles_invalid_json_arguments(self, connected_client):
        cb = MagicMock(return_value=None)
        connected_client.set_tool_call_callback(cb)

        await connected_client._handle_message(
            {
                "type": "response.function_call_arguments.done",
                "call_id": "call_123",
                "name": "test_tool",
                "arguments": "not valid json",
            }
        )
        cb.assert_called_once_with("test_tool", {})

    async def test_function_call_awaits_coroutine(self, connected_client):
        async def async_tool(name, args):
            return {"async": True}

        connected_client.set_tool_call_callback(async_tool)

        await connected_client._handle_message(
            {
                "type": "response.function_call_arguments.done",
                "call_id": "call_123",
                "name": "test_tool",
                "arguments": "{}",
            }
        )
        # Should have sent function output
        calls = connected_client.ws.send.call_args_list
        output_msg = json.loads(calls[0][0][0])
        assert output_msg["type"] == "conversation.item.create"
        assert output_msg["item"]["type"] == "function_call_output"

    async def test_function_call_hangup_no_response_requested(self, connected_client):
        cb = MagicMock(return_value=None)
        connected_client.set_tool_call_callback(cb)

        await connected_client._handle_message(
            {
                "type": "response.function_call_arguments.done",
                "call_id": "call_123",
                "name": "hangup",
                "arguments": '{"reason": "goodbye"}',
            }
        )
        # Should only send function output, NOT response.create
        calls = connected_client.ws.send.call_args_list
        types = [json.loads(c[0][0])["type"] for c in calls]
        assert "conversation.item.create" in types
        assert "response.create" not in types

    async def test_function_call_non_hangup_requests_response(self, connected_client):
        cb = MagicMock(return_value={"data": "value"})
        connected_client.set_tool_call_callback(cb)

        await connected_client._handle_message(
            {
                "type": "response.function_call_arguments.done",
                "call_id": "call_123",
                "name": "search",
                "arguments": "{}",
            }
        )
        calls = connected_client.ws.send.call_args_list
        types = [json.loads(c[0][0])["type"] for c in calls]
        assert "response.create" in types

    async def test_function_call_none_result_sends_success(self, connected_client):
        cb = MagicMock(return_value=None)
        connected_client.set_tool_call_callback(cb)

        await connected_client._handle_message(
            {
                "type": "response.function_call_arguments.done",
                "call_id": "call_123",
                "name": "test",
                "arguments": "{}",
            }
        )
        output_msg = json.loads(connected_client.ws.send.call_args_list[0][0][0])
        output = json.loads(output_msg["item"]["output"])
        assert output == {"success": True}

    async def test_function_call_async_error(self, connected_client):
        async def failing_tool(name, args):
            raise ValueError("tool failed")

        connected_client.set_tool_call_callback(failing_tool)

        await connected_client._handle_message(
            {
                "type": "response.function_call_arguments.done",
                "call_id": "call_123",
                "name": "test",
                "arguments": "{}",
            }
        )
        output_msg = json.loads(connected_client.ws.send.call_args_list[0][0][0])
        output = json.loads(output_msg["item"]["output"])
        assert "error" in output

    async def test_error_message(self, connected_client):
        await connected_client._handle_message(
            {
                "type": "error",
                "error": {"message": "rate limit exceeded"},
            }
        )

    async def test_error_message_empty_error(self, connected_client):
        """Branch 340->exit: error type with empty error dict."""
        await connected_client._handle_message(
            {
                "type": "error",
                "error": {},
            }
        )

    async def test_audio_transcript_delta_with_content(self, connected_client):
        """Lines 274-276: audio_transcript.delta with non-empty transcript."""
        await connected_client._handle_message(
            {
                "type": "response.audio_transcript.delta",
                "delta": "Hello world",
            }
        )

    async def test_audio_transcript_delta_empty(self, connected_client):
        """Branch: audio_transcript.delta with empty transcript."""
        await connected_client._handle_message(
            {
                "type": "response.audio_transcript.delta",
                "delta": "",
            }
        )

    async def test_speech_started_responding_no_interrupt_callback(self, connected_client):
        """Branch 291->exit: speech_started while responding, but no interrupt callback."""
        connected_client.is_responding = True
        connected_client._interrupt_callback = None

        await connected_client._handle_message({"type": "input_audio_buffer.speech_started"})
        # Should cancel response but not call non-existent callback
        sent = json.loads(connected_client.ws.send.call_args[0][0])
        assert sent["type"] == "response.cancel"

    async def test_function_call_no_tool_callback(self, connected_client):
        """Branch 322->326: function_call_arguments.done without tool_call_callback."""
        connected_client._tool_call_callback = None

        await connected_client._handle_message(
            {
                "type": "response.function_call_arguments.done",
                "call_id": "call_123",
                "name": "test_tool",
                "arguments": "{}",
            }
        )
        # Should send function output with {"success": True} since result is None
        output_msg = json.loads(connected_client.ws.send.call_args_list[0][0][0])
        assert output_msg["item"]["type"] == "function_call_output"

    async def test_transcript_completed_empty_no_callback(self, connected_client):
        """Branch: empty transcript doesn't call callback."""
        cb = MagicMock()
        connected_client.set_transcript_callback(cb)
        await connected_client._handle_message(
            {
                "type": "conversation.item.input_audio_transcription.completed",
                "transcript": "",
            }
        )
        cb.assert_not_called()

    async def test_function_call_empty_arguments(self, connected_client):
        """Branch: empty arguments string."""
        cb = MagicMock(return_value=None)
        connected_client.set_tool_call_callback(cb)

        await connected_client._handle_message(
            {
                "type": "response.function_call_arguments.done",
                "call_id": "call_123",
                "name": "test_tool",
                "arguments": "",
            }
        )
        cb.assert_called_once_with("test_tool", {})

    async def test_response_done_no_callback(self, connected_client):
        """Branch: response.done without response_done_callback."""
        connected_client.is_responding = True
        connected_client._response_done_callback = None
        await connected_client._handle_message({"type": "response.done"})
        assert connected_client.is_responding is False

    async def test_unknown_message_type(self, connected_client):
        """Default branch: unknown message type is ignored."""
        await connected_client._handle_message({"type": "some.unknown.type"})


# --- Send Function Output ---


class TestSendFunctionOutput:
    async def test_sends_output_item(self, connected_client):
        await connected_client._send_function_output("call_123", {"ok": True})
        first = json.loads(connected_client.ws.send.call_args_list[0][0][0])
        assert first["item"]["type"] == "function_call_output"
        assert first["item"]["call_id"] == "call_123"

    async def test_sends_response_create_when_requested(self, connected_client):
        await connected_client._send_function_output(
            "call_123", {"ok": True}, request_response=True
        )
        assert connected_client.ws.send.call_count == 2
        second = json.loads(connected_client.ws.send.call_args_list[1][0][0])
        assert second["type"] == "response.create"

    async def test_no_response_create_when_not_requested(self, connected_client):
        await connected_client._send_function_output(
            "call_123", {"ok": True}, request_response=False
        )
        assert connected_client.ws.send.call_count == 1

    async def test_not_connected_does_nothing(self, client):
        await client._send_function_output("call_123", {"ok": True})


# --- Disconnect ---


class TestDisconnect:
    async def test_sets_not_connected(self, connected_client):
        await connected_client.disconnect()
        assert connected_client.is_connected is False

    async def test_cancels_receive_task(self, connected_client):
        # Create a real asyncio task that we can cancel
        async def noop():
            await asyncio.sleep(10)

        task = asyncio.create_task(noop())
        connected_client._receive_task = task
        await connected_client.disconnect()
        assert task.cancelled()

    async def test_closes_websocket(self, connected_client):
        ws = connected_client.ws
        await connected_client.disconnect()
        ws.close.assert_called_once()
        assert connected_client.ws is None

    async def test_no_ws_no_error(self, client):
        client.ws = None
        await client.disconnect()

    async def test_no_task_no_error(self, client):
        client._receive_task = None
        await client.disconnect()


# --- Receive Loop ---


class TestReceiveLoop:
    async def test_processes_messages(self, connected_client):
        """Lines 241-242, 241->248: process message then exit normally into finally."""
        msg = json.dumps({"type": "session.created"})

        # Create a proper async iterator for the websocket
        async def async_iter():
            yield msg

        connected_client.ws.__aiter__ = lambda self: async_iter()

        await connected_client._receive_loop()
        assert connected_client.is_connected is False

    async def test_handles_connection_closed(self, connected_client):
        """Line 243: ConnectionClosed exception."""

        async def raise_connection_closed():
            raise websockets.ConnectionClosed(None, None)
            yield  # Make it an async generator  # noqa: RUF027

        connected_client.ws.__aiter__ = lambda self: raise_connection_closed()

        await connected_client._receive_loop()
        assert connected_client.is_connected is False

    async def test_handles_generic_exception(self, connected_client):
        async def raise_error():
            raise RuntimeError("unexpected")
            yield  # noqa: RUF027

        connected_client.ws.__aiter__ = lambda self: raise_error()

        await connected_client._receive_loop()
        assert connected_client.is_connected is False
