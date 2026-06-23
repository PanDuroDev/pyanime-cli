import os
import subprocess
import threading

from config import load_config
from db import get_episode_progress

from .discovery import get_cached_players, _get_player_cfg
from .progress import poll_mpv_progress


def play(stream_urls, player="mpv", fullscreen=True, slug=None, episode=None, extra_args=None):
    if player == "mpv":
        return play_with_mpv(stream_urls, slug=slug, ep=episode, extra_args=extra_args)
    elif player == "vlc":
        return play_with_vlc(stream_urls, extra_args=extra_args)
    elif player == "iina":
        return play_with_iina(stream_urls)
    elif player == "celluloid":
        return play_with_celluloid(stream_urls)
    elif player == "haruna":
        return play_with_haruna(stream_urls)
    return False


def play_with_vlc(stream_urls, extra_args=None):
    vlc_path = get_cached_players().get("vlc")
    if not vlc_path:
        return False

    pcfg = _get_player_cfg()
    user_args = list(pcfg["custom_args"])
    if extra_args:
        user_args = extra_args + user_args

    fs_arg = ["--fullscreen"] if pcfg["fullscreen"] else []
    cmd = [vlc_path] + fs_arg + user_args + stream_urls
    try:
        if os.name == 'nt':
            subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS)
        else:
            subprocess.Popen(cmd, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def play_with_mpv(stream_urls, slug=None, ep=None, extra_args=None):
    mpv_path = get_cached_players().get("mpv")
    if not mpv_path:
        return False

    is_mpvnet = "mpvnet" in os.path.basename(mpv_path).lower()

    pcfg = _get_player_cfg()
    user_args = list(pcfg["custom_args"])
    if extra_args:
        user_args = extra_args + user_args

    fs_arg = ["--fullscreen"] if pcfg["fullscreen"] else []

    ipc_path = None
    if slug and ep is not None:
        if os.name == 'nt':
            ipc_path = rf"\\.\pipe\pyanime-ipc-{slug}-{ep}"
        else:
            ipc_path = f"/tmp/pyanime-ipc-{slug}-{ep}.sock"
        fs_arg.append(f"--input-ipc-server={ipc_path}")

        prog = get_episode_progress(slug, ep)
        if prog and prog.get("time_pos", 0) > 5:
            fs_arg.append(f"--start={int(prog['time_pos'])}")

    if is_mpvnet:
        cmd = [mpv_path] + fs_arg + user_args + stream_urls
    else:
        cmd = [mpv_path, "--force-window", "--keep-open=yes"] + fs_arg + user_args + stream_urls

    try:
        if os.name == 'nt':
            subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS)
        else:
            subprocess.Popen(cmd, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if ipc_path:
            threading.Thread(target=poll_mpv_progress, args=(ipc_path, slug, ep), daemon=True).start()

        return True
    except Exception:
        return False


def play_with_iina(stream_urls):
    iina_path = get_cached_players().get("iina")
    if not iina_path:
        return False
    pcfg = _get_player_cfg()
    user_args = list(pcfg["custom_args"])
    fs_arg = ["--mpv-fs"] if pcfg["fullscreen"] else []
    cmd = [iina_path] + fs_arg + user_args + stream_urls
    try:
        subprocess.Popen(cmd, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def play_with_celluloid(stream_urls):
    celluloid_path = get_cached_players().get("celluloid")
    if not celluloid_path:
        return False
    pcfg = _get_player_cfg()
    user_args = list(pcfg["custom_args"])
    fs_arg = ["--fullscreen"] if pcfg["fullscreen"] else []
    cmd = [celluloid_path] + fs_arg + user_args + stream_urls
    try:
        subprocess.Popen(cmd, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def play_with_haruna(stream_urls):
    haruna_path = get_cached_players().get("haruna")
    if not haruna_path:
        return False
    pcfg = _get_player_cfg()
    user_args = list(pcfg["custom_args"])
    fs_arg = ["--fullscreen"] if pcfg["fullscreen"] else []
    cmd = [haruna_path] + fs_arg + user_args + stream_urls
    try:
        subprocess.Popen(cmd, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False
