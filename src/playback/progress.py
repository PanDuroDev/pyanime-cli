import json
import os
import socket
import sys
import time
import threading

from db import save_episode_progress


def start_progress_tracking(slug, episode, player_ipc_path):
    threading.Thread(target=poll_mpv_progress, args=(player_ipc_path, slug, episode), daemon=True).start()


def poll_mpv_progress(ipc_path, slug, ep):
    client = None
    for _ in range(20):
        if os.name == 'nt':
            try:
                client = open(ipc_path, "r+b", buffering=0)
                break
            except Exception:
                time.sleep(0.5)
        else:
            if os.path.exists(ipc_path):
                try:
                    import socket
                    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    client.connect(ipc_path)
                    break
                except Exception:
                    time.sleep(0.5)
            else:
                time.sleep(0.5)

    if not client:
        return

    try:
        while True:
            time_cmd = json.dumps({"command": ["get_property", "time-pos"]}) + "\n"
            duration_cmd = json.dumps({"command": ["get_property", "duration"]}) + "\n"

            time_pos = None
            duration = None

            if os.name == 'nt':
                try:
                    client.write(time_cmd.encode("utf-8"))
                    line = b""
                    while True:
                        c = client.read(1)
                        if not c:
                            break
                        line += c
                        if c == b"\n":
                            break
                    if line:
                        resp = json.loads(line.decode("utf-8", errors="ignore"))
                        if resp.get("error") == "success":
                            time_pos = resp.get("data")
                except Exception:
                    break

                try:
                    client.write(duration_cmd.encode("utf-8"))
                    line = b""
                    while True:
                        c = client.read(1)
                        if not c:
                            break
                        line += c
                        if c == b"\n":
                            break
                    if line:
                        resp = json.loads(line.decode("utf-8", errors="ignore"))
                        if resp.get("error") == "success":
                            duration = resp.get("data")
                except Exception:
                    break
            else:
                try:
                    client.sendall(time_cmd.encode("utf-8"))
                    buffer = b""
                    while b"\n" not in buffer:
                        chunk = client.recv(4096)
                        if not chunk:
                            break
                        buffer += chunk
                    if b"\n" in buffer:
                        line = buffer.split(b"\n")[0]
                        resp = json.loads(line.decode("utf-8", errors="ignore"))
                        if resp.get("error") == "success":
                            time_pos = resp.get("data")
                except Exception:
                    break

                try:
                    client.sendall(duration_cmd.encode("utf-8"))
                    buffer = b""
                    while b"\n" not in buffer:
                        chunk = client.recv(4096)
                        if not chunk:
                            break
                        buffer += chunk
                    if b"\n" in buffer:
                        line = buffer.split(b"\n")[0]
                        resp = json.loads(line.decode("utf-8", errors="ignore"))
                        if resp.get("error") == "success":
                            duration = resp.get("data")
                except Exception:
                    break

            if time_pos is not None:
                if duration and (time_pos / duration > 0.95):
                    save_episode_progress(slug, ep, 0, duration)
                else:
                    save_episode_progress(slug, ep, time_pos, duration or 0)

            time.sleep(2.0)
    except Exception as e:
        sys.stderr.write(f"[pyanime] poll_mpv_progress error: {e}\n")
    finally:
        try:
            client.close()
        except Exception:
            pass
        if os.name != 'nt':
            try:
                if os.path.exists(ipc_path):
                    os.remove(ipc_path)
            except Exception:
                pass
