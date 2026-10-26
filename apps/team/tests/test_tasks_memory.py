# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for memory tasks."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from team.tasks.memory_tasks import _summarize, summarize_memory


def _make_team():
    team = MagicMock()
    team.id = uuid4()
    team.name = "Engineering"
    team.is_active = True
    return team


def _make_entry(content="Some fact", is_summary=False):
    entry = MagicMock()
    entry.id = uuid4()
    entry.content = content
    entry.extra = {"is_summary": True} if is_summary else {}
    return entry


class TestSummarize:
    async def test_skips_without_api_key(self):
        with patch("team.tasks.memory_tasks.settings") as mock_settings:
            mock_settings.openai_api_key = ""
            mock_settings.anthropic_api_key = ""

            result = await _summarize()

        assert result == 0

    async def test_summarizes_old_entries(self):
        team = _make_team()
        entry1 = _make_entry("Fact A")
        entry2 = _make_entry("Fact B")

        mock_session = AsyncMock()

        team_result = MagicMock()
        team_result.scalars.return_value.all.return_value = [team]

        entries_result = MagicMock()
        entries_result.scalars.return_value.all.return_value = [entry1, entry2]

        mock_session.execute = AsyncMock(side_effect=[team_result, entries_result])
        mock_session.add = MagicMock()
        mock_session.delete = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("team.tasks.memory_tasks.settings") as mock_settings,
            patch("team.tasks.memory_tasks.async_session_factory", return_value=mock_factory),
            patch("team.tasks.memory_tasks.get_completion", new_callable=AsyncMock) as mock_llm,
            patch(
                "team.tasks.memory_tasks.generate_embedding", new_callable=AsyncMock
            ) as mock_embed,
        ):
            mock_settings.openai_api_key = "sk-test"
            mock_settings.anthropic_api_key = ""
            mock_llm.return_value = "Summary of facts"
            mock_embed.return_value = [0.5] * 1536

            result = await _summarize()

        assert result == 2
        mock_llm.assert_awaited_once()
        mock_embed.assert_awaited_once_with("Summary of facts")
        mock_session.add.assert_called_once()
        assert mock_session.delete.await_count == 2

    async def test_skips_already_summarized(self):
        team = _make_team()
        entry1 = _make_entry("Summary", is_summary=True)
        entry2 = _make_entry("Another summary", is_summary=True)

        mock_session = AsyncMock()

        team_result = MagicMock()
        team_result.scalars.return_value.all.return_value = [team]

        entries_result = MagicMock()
        entries_result.scalars.return_value.all.return_value = [entry1, entry2]

        mock_session.execute = AsyncMock(side_effect=[team_result, entries_result])
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("team.tasks.memory_tasks.settings") as mock_settings,
            patch("team.tasks.memory_tasks.async_session_factory", return_value=mock_factory),
        ):
            mock_settings.openai_api_key = "sk-test"
            mock_settings.anthropic_api_key = ""

            result = await _summarize()

        assert result == 0

    async def test_skips_single_entry(self):
        team = _make_team()
        entry = _make_entry("Only one")

        mock_session = AsyncMock()

        team_result = MagicMock()
        team_result.scalars.return_value.all.return_value = [team]

        entries_result = MagicMock()
        entries_result.scalars.return_value.all.return_value = [entry]

        mock_session.execute = AsyncMock(side_effect=[team_result, entries_result])
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("team.tasks.memory_tasks.settings") as mock_settings,
            patch("team.tasks.memory_tasks.async_session_factory", return_value=mock_factory),
        ):
            mock_settings.openai_api_key = "sk-test"
            mock_settings.anthropic_api_key = ""

            result = await _summarize()

        assert result == 0

    async def test_handles_llm_error(self):
        team = _make_team()
        entry1 = _make_entry("Fact A")
        entry2 = _make_entry("Fact B")

        mock_session = AsyncMock()

        team_result = MagicMock()
        team_result.scalars.return_value.all.return_value = [team]

        entries_result = MagicMock()
        entries_result.scalars.return_value.all.return_value = [entry1, entry2]

        mock_session.execute = AsyncMock(side_effect=[team_result, entries_result])
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("team.tasks.memory_tasks.settings") as mock_settings,
            patch("team.tasks.memory_tasks.async_session_factory", return_value=mock_factory),
            patch("team.tasks.memory_tasks.get_completion", new_callable=AsyncMock) as mock_llm,
        ):
            mock_settings.openai_api_key = "sk-test"
            mock_settings.anthropic_api_key = ""
            mock_llm.side_effect = Exception("API error")

            result = await _summarize()

        assert result == 0

    async def test_uses_anthropic_when_no_openai(self):
        team = _make_team()
        entry1 = _make_entry("Fact A")
        entry2 = _make_entry("Fact B")

        mock_session = AsyncMock()

        team_result = MagicMock()
        team_result.scalars.return_value.all.return_value = [team]

        entries_result = MagicMock()
        entries_result.scalars.return_value.all.return_value = [entry1, entry2]

        mock_session.execute = AsyncMock(side_effect=[team_result, entries_result])
        mock_session.add = MagicMock()
        mock_session.delete = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("team.tasks.memory_tasks.settings") as mock_settings,
            patch("team.tasks.memory_tasks.async_session_factory", return_value=mock_factory),
            patch("team.tasks.memory_tasks.get_completion", new_callable=AsyncMock) as mock_llm,
            patch(
                "team.tasks.memory_tasks.generate_embedding", new_callable=AsyncMock
            ) as mock_embed,
        ):
            mock_settings.openai_api_key = ""
            mock_settings.anthropic_api_key = "sk-ant-test"
            mock_llm.return_value = "Summary"
            mock_embed.return_value = [0.3] * 1536

            result = await _summarize()

        assert result == 2
        call_args = mock_llm.call_args
        assert call_args.kwargs["provider"] == "anthropic"
        mock_embed.assert_awaited_once_with("Summary")


def _fake_run_async(coro, return_value=0):
    """Close the coroutine to avoid 'was never awaited' warnings."""
    coro.close()
    return return_value


class TestSummarizeMemory:
    def test_calls_summarize(self):
        with patch(
            "team.tasks.memory_tasks.run_async",
            side_effect=lambda coro: _fake_run_async(coro, 5),
        ):
            result = summarize_memory()

        assert result == {"summarized": 5}
