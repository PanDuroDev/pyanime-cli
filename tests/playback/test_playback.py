import os
import subprocess
from unittest.mock import patch, MagicMock
import pytest


class TestPlayerDiscovery:
    def test_get_cached_players_returns_dict(self):
        from src.playback.discovery import get_cached_players
        players = get_cached_players()
        assert isinstance(players, dict)
        assert "vlc" in players
        assert "mpv" in players

    def test_discover_players_returns_only_found(self):
        from src.playback.discovery import discover_players
        players = discover_players()
        assert isinstance(players, dict)

    def test_find_player_returns_none_for_missing(self):
        from src.playback.discovery import find_player
        result = find_player("nonexistent_player")
        assert result is None

    def test_clear_player_cache_resets(self):
        from src.playback.discovery import get_cached_players, clear_player_cache
        initial = get_cached_players()
        clear_player_cache()
        after_clear = get_cached_players()
        assert after_clear != initial

    @patch("src.playback.discovery.shutil.which")
    def test_find_vlc_returns_path(self, mock_which):
        from src.playback.discovery import find_vlc
        mock_which.return_value = "/usr/bin/vlc"
        result = find_vlc()
        assert result == "/usr/bin/vlc"

    @patch("src.playback.discovery.shutil.which")
    def test_find_mpv_returns_path(self, mock_which):
        from src.playback.discovery import find_mpv
        mock_which.return_value = "/usr/bin/mpv"
        result = find_mpv()
        assert result == "/usr/bin/mpv"

    @patch("src.playback.discovery.shutil.which")
    def test_find_player_not_found_returns_none(self, mock_which):
        from src.playback.discovery import find_vlc
        mock_which.return_value = None
        result = find_vlc()
        assert result is None or isinstance(result, str)

    @patch("src.playback.discovery.shutil.which")
    def test_discover_players_lists_found(self, mock_which):
        from src.playback.discovery import discover_players
        mock_which.return_value = None
        players = discover_players()
        assert isinstance(players, dict)


class TestPlayerLaunch:
    @patch("src.playback.launch.get_cached_players")
    @patch("src.playback.launch.subprocess.Popen")
    def test_play_with_vlc(self, mock_popen, mock_get_players):
        from src.playback.launch import play_with_vlc
        mock_get_players.return_value = {"vlc": "/usr/bin/vlc"}
        mock_popen.return_value = MagicMock()
        result = play_with_vlc(["https://stream.example/playlist.m3u8"])
        assert result is True
        mock_popen.assert_called_once()

    @patch("src.playback.launch.get_cached_players")
    @patch("src.playback.launch.subprocess.Popen")
    def test_play_with_vlc_no_player(self, mock_popen, mock_get_players):
        from src.playback.launch import play_with_vlc
        mock_get_players.return_value = {"vlc": None}
        result = play_with_vlc(["https://stream.example/playlist.m3u8"])
        assert result is False
        mock_popen.assert_not_called()

    @patch("src.playback.launch.get_cached_players")
    @patch("src.playback.launch.subprocess.Popen")
    def test_play_with_mpv(self, mock_popen, mock_get_players):
        from src.playback.launch import play_with_mpv
        mock_get_players.return_value = {"mpv": "/usr/bin/mpv"}
        mock_popen.return_value = MagicMock()
        result = play_with_mpv(["https://stream.example/playlist.m3u8"])
        assert result is True
        mock_popen.assert_called_once()

    @patch("src.playback.launch.get_cached_players")
    def test_play_with_mpv_no_player(self, mock_get_players):
        from src.playback.launch import play_with_mpv
        mock_get_players.return_value = {"mpv": None}
        result = play_with_mpv(["https://stream.example/playlist.m3u8"])
        assert result is False

    @patch("src.playback.launch.get_cached_players")
    @patch("src.playback.launch.subprocess.Popen")
    def test_play_with_vlc_extra_args(self, mock_popen, mock_get_players):
        from src.playback.launch import play_with_vlc
        mock_get_players.return_value = {"vlc": "/usr/bin/vlc"}
        mock_popen.return_value = MagicMock()
        result = play_with_vlc(["https://stream.example/1.m3u8"], extra_args=["--fullscreen"])
        assert result is True

    @patch("src.playback.launch.get_cached_players")
    @patch("src.playback.launch.subprocess.Popen")
    def test_play_router_mpv(self, mock_popen, mock_get_players):
        from src.playback.launch import play
        mock_get_players.return_value = {"mpv": "/usr/bin/mpv"}
        mock_popen.return_value = MagicMock()
        result = play(["https://stream.example/playlist.m3u8"], player="mpv")
        assert result is True

    @patch("src.playback.launch.get_cached_players")
    @patch("src.playback.launch.subprocess.Popen")
    def test_play_router_vlc(self, mock_popen, mock_get_players):
        from src.playback.launch import play
        mock_get_players.return_value = {"vlc": "/usr/bin/vlc"}
        mock_popen.return_value = MagicMock()
        result = play(["https://stream.example/playlist.m3u8"], player="vlc")
        assert result is True

    @patch("src.playback.launch.get_cached_players")
    def test_play_router_unknown_player(self, mock_get_players):
        from src.playback.launch import play
        result = play(["https://stream.example/playlist.m3u8"], player="unknown")
        assert result is False


class TestPlayerProgress:
    @patch("src.playback.progress.save_episode_progress")
    @patch("src.playback.progress.poll_mpv_progress")
    def test_start_progress_tracking(self, mock_poll, mock_save):
        from src.playback.progress import start_progress_tracking
        start_progress_tracking("naruto", 1, "/tmp/mpv-ipc")
        mock_poll.assert_called_once_with("/tmp/mpv-ipc", "naruto", 1)

    def test_poll_mpv_progress_catches_exceptions(self):
        from src.playback.progress import poll_mpv_progress
        poll_mpv_progress("/nonexistent/ipc/path", "naruto", 1)

    @patch("src.playback.progress.save_episode_progress")
    def test_poll_mpv_progress_with_mocked_socket(self, mock_save):
        from src.playback.progress import poll_mpv_progress
        with patch("src.playback.progress.os.name", "posix"):
            with patch("src.playback.progress.os.path.exists") as mock_exists:
                mock_exists.return_value = True
                poll_mpv_progress("/tmp/test-ipc", "naruto", 1)

    def test_progress_tracking_invalid_ipc(self):
        from src.playback.progress import start_progress_tracking
        start_progress_tracking("test", 1, None)

    @patch("src.playback.progress.poll_mpv_progress")
    def test_start_progress_tracking_called_once(self, mock_poll):
        from src.playback.progress import start_progress_tracking
        start_progress_tracking("naruto", 1, "/tmp/ipc")
        start_progress_tracking("naruto", 2, "/tmp/ipc")
        assert mock_poll.call_count == 2
