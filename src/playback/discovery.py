import os
import shutil
import subprocess
import sys
import time

from config import load_config, THEME, console, get_icon


_cached_players = {}
_player_cfg = None


def _get_player_cfg():
    global _player_cfg
    if _player_cfg is None:
        cfg = load_config()
        custom_raw = cfg.get("custom_player_args", "").strip()
        _player_cfg = {
            "fullscreen": cfg.get("fullscreen", True),
            "custom_args": custom_raw.split() if custom_raw else [],
        }
    return _player_cfg


def _invalidate_player_cfg():
    global _player_cfg
    _player_cfg = None


def get_cached_players():
    global _cached_players
    if not _cached_players:
        _cached_players = {
            "vlc": find_vlc(),
            "mpv": find_mpv(),
            "iina": find_iina(),
            "celluloid": find_celluloid(),
            "haruna": find_haruna(),
        }
    return _cached_players


def clear_player_cache():
    global _cached_players
    _cached_players.clear()


def discover_players():
    return {k: v for k, v in get_cached_players().items() if v is not None}


def find_player(name):
    return get_cached_players().get(name)


def refresh_system_path():
    if os.name != 'nt':
        return
    try:
        import winreg
        parts = []
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment") as key:
                sys_path, _ = winreg.QueryValueEx(key, "Path")
                parts.append(sys_path)
        except Exception:
            pass
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
                usr_path, _ = winreg.QueryValueEx(key, "Path")
                parts.append(usr_path)
        except Exception:
            pass
        if parts:
            os.environ['PATH'] = ";".join(parts)
    except Exception:
        pass


def find_vlc():
    vlc_path = shutil.which("vlc")
    if vlc_path:
        return vlc_path

    if os.name == 'nt':
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\vlc.exe")
            vlc_path, _ = winreg.QueryValueEx(key, "")
            if vlc_path and os.path.exists(vlc_path):
                return vlc_path
        except Exception:
            pass

        common_paths = [
            r"C:\Program Files\VideoLAN\VLC\vlc.exe",
            r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\VideoLAN\VLC\vlc.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\VideoLAN\VLC\vlc.exe"),
            r"C:\ProgramData\chocolatey\bin\vlc.exe",
            os.path.expandvars(r"%USERPROFILE%\scoop\apps\vlc\current\vlc.exe"),
            os.path.expandvars(r"%USERPROFILE%\scoop\shims\vlc.exe"),
        ]
        for p in common_paths:
            if os.path.exists(p):
                return p
    return None


def find_mpv():
    for exe_name in ("mpv", "mpvnet"):
        found = shutil.which(exe_name)
        if found:
            return found

    if os.name == 'nt':
        for reg_exe in ("mpv.exe", "mpvnet.exe"):
            try:
                import winreg
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                    rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{reg_exe}")
                val, _ = winreg.QueryValueEx(key, "")
                if val and os.path.exists(val):
                    return val
            except Exception:
                pass

        home = os.path.expanduser("~")
        localappdata = os.environ.get("LOCALAPPDATA", "")
        appdata = os.environ.get("APPDATA", "")
        programfiles = os.environ.get("ProgramFiles", r"C:\Program Files")
        programfiles86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")

        common_paths = [
            os.path.join(programfiles, "mpv", "mpv.exe"),
            os.path.join(programfiles86, "mpv", "mpv.exe"),
            os.path.join(localappdata, "Programs", "mpv", "mpv.exe"),
            os.path.join(localappdata, "mpv", "mpv.exe"),
            os.path.join(programfiles, "mpv.net", "mpvnet.exe"),
            os.path.join(programfiles86, "mpv.net", "mpvnet.exe"),
            os.path.join(localappdata, "Programs", "mpv.net", "mpvnet.exe"),
            os.path.join(localappdata, "mpv.net", "mpvnet.exe"),
            os.path.join(appdata, "mpv.net", "mpvnet.exe"),
            r"C:\ProgramData\chocolatey\bin\mpv.exe",
            r"C:\ProgramData\chocolatey\lib\mpv\tools\mpv.exe",
            os.path.join(home, "scoop", "apps", "mpv", "current", "mpv.exe"),
            os.path.join(home, "scoop", "shims", "mpv.exe"),
            os.path.join(localappdata, "Microsoft", "WinGet", "Packages"),
        ]

        for p in common_paths:
            if os.path.isfile(p):
                return p

        winget_pkgs = os.path.join(localappdata, "Microsoft", "WinGet", "Packages")
        if os.path.isdir(winget_pkgs):
            try:
                for root, dirs, files in os.walk(winget_pkgs):
                    for fname in files:
                        if fname.lower() in ("mpv.exe", "mpvnet.exe"):
                            return os.path.join(root, fname)
            except Exception:
                pass

        for pf in (programfiles, programfiles86, localappdata):
            if not pf or not os.path.isdir(pf):
                continue
            try:
                for item in os.listdir(pf):
                    if "mpv" in item.lower():
                        candidate_dir = os.path.join(pf, item)
                        if os.path.isdir(candidate_dir):
                            for exe in ("mpv.exe", "mpvnet.exe"):
                                full = os.path.join(candidate_dir, exe)
                                if os.path.isfile(full):
                                    return full
            except Exception:
                pass

    else:
        for p in ("/usr/bin/mpv", "/usr/local/bin/mpv", "/snap/bin/mpv"):
            if os.path.isfile(p):
                return p

    return None


def find_iina():
    iina_path = shutil.which("iina")
    if iina_path:
        return iina_path
    if sys.platform == "darwin":
        common_paths = [
            "/Applications/IINA.app/Contents/MacOS/IINA",
            os.path.expanduser("~/Applications/IINA.app/Contents/MacOS/IINA")
        ]
        for p in common_paths:
            if os.path.exists(p):
                return p
    return None


def find_celluloid():
    return shutil.which("celluloid")


def find_haruna():
    return shutil.which("haruna")


def install_player(player_name):
    """Attempt to automatically install VLC, MPV, IINA, Celluloid, or Haruna."""
    console.print(f"\n[bold {THEME['primary']}]{get_icon('watch_history')}Attempting to install {player_name.upper()}...[/bold {THEME['primary']}]")

    installed = False

    if os.name == 'nt' and player_name in ["iina", "celluloid", "haruna"]:
        console.print(f"\n[bold {THEME['error']}]{get_icon('cross')}{player_name.upper()} is not natively supported on Windows.[/bold {THEME['error']}]")
        if player_name == "iina":
            console.print(f"[bold {THEME['warning']}]IINA is a macOS-only player.[/bold {THEME['warning']}]")
        else:
            console.print(f"[bold {THEME['warning']}]{player_name.upper()} is a Linux-oriented player. We recommend installing MPV or VLC on Windows.[/bold {THEME['warning']}]")
        time.sleep(4.0)
        return False

    if sys.platform == "darwin":
        if shutil.which("brew"):
            try:
                is_cask = player_name in ["iina", "vlc", "mpv", "celluloid", "haruna"]
                cmd = ["brew", "install"]
                if is_cask:
                    cmd.append("--cask")
                cmd.append(player_name)
                console.print(f"[{THEME['dim']}]  Trying brew install {player_name}...[/{THEME['dim']}]")
                result = subprocess.run(cmd, timeout=300)
                if result.returncode == 0:
                    console.print(f"[bold {THEME['success']}]{get_icon('check')}{player_name.upper()} installed successfully via Homebrew![/bold {THEME['success']}]")
                    time.sleep(2.0)
                    return True
            except Exception as e:
                print(f"[pyanime] Warning: player install failed: {e}")
                console.print(f"\n[bold {THEME['error']}]{get_icon('cross')}Could not auto-install {player_name.upper()} on macOS.[/bold {THEME['error']}]")
                console.print(f"[bold {THEME['warning']}]{get_icon('warning')}Please install it manually from the official website or using Homebrew.[/bold {THEME['warning']}]")
                time.sleep(3.0)
                return False

    if os.name == 'nt':
        try:
            choco_pkg = "mpv" if player_name == "mpv" else "vlc"
            cmd = ["choco", "install", choco_pkg, "-y"]
            console.print(f"[{THEME['dim']}]  Trying choco install {choco_pkg}...[/{THEME['dim']}]")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                console.print(f"[bold {THEME['success']}]{get_icon('check')}{player_name.upper()} installed successfully via Chocolatey![/bold {THEME['success']}]")
                installed = True
        except FileNotFoundError:
            console.print(f"[{THEME['dim']}]  choco not found, trying alternatives...[/{THEME['dim']}]")
        except subprocess.TimeoutExpired:
            console.print(f"[{THEME['dim']}]  choco timed out[/{THEME['dim']}]")

        if not installed:
            try:
                scoop_pkg = "mpv" if player_name == "mpv" else "vlc"
                cmd = ["scoop", "install", scoop_pkg]
                console.print(f"[{THEME['dim']}]  Trying scoop install {scoop_pkg}...[/{THEME['dim']}]")
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                if result.returncode == 0:
                    console.print(f"[bold {THEME['success']}]{get_icon('check')}{player_name.upper()} installed successfully via Scoop![/bold {THEME['success']}]")
                    installed = True
            except FileNotFoundError:
                console.print(f"[{THEME['dim']}]  scoop not found, trying alternatives...[/{THEME['dim']}]")
            except subprocess.TimeoutExpired:
                console.print(f"[{THEME['dim']}]  scoop timed out[/{THEME['dim']}]")

        if not installed:
            try:
                if player_name == "mpv":
                    winget_id = "mpv.net"
                else:
                    winget_id = "VideoLAN.VLC"

                cmd = [
                    "winget", "install", "--id", winget_id, "-e",
                    "--accept-source-agreements", "--accept-package-agreements",
                    "--silent"
                ]
                console.print(f"[{THEME['dim']}]  Trying winget install {winget_id}...[/{THEME['dim']}]")
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                if result.returncode == 0:
                    console.print(f"[bold {THEME['success']}]{get_icon('check')}{player_name.upper()} installed successfully via winget![/bold {THEME['success']}]")
                    installed = True
                else:
                    console.print(f"[{THEME['dim']}]  winget returned code {result.returncode}[/{THEME['dim']}]")
            except FileNotFoundError:
                console.print(f"[{THEME['dim']}]  winget not found[/{THEME['dim']}]")
            except subprocess.TimeoutExpired:
                console.print(f"[{THEME['dim']}]  winget timed out[/{THEME['dim']}]")

        if installed:
            console.print(f"[{THEME['dim']}]  Refreshing system PATH...[/{THEME['dim']}]")
            refresh_system_path()
            time.sleep(2.0)
            found = find_mpv() if player_name == "mpv" else find_vlc()
            if found:
                console.print(f"[bold {THEME['success']}]{get_icon('check')}{player_name.upper()} verified at: {found}[/bold {THEME['success']}]")
            else:
                console.print(f"[bold {THEME['warning']}]{get_icon('warning')}Installed but path not detected yet. Searching deeper...[/bold {THEME['warning']}]")
                time.sleep(1.0)
            return True

        console.print(f"\n[bold {THEME['error']}]{get_icon('cross')}Could not auto-install {player_name.upper()} on Windows.[/bold {THEME['error']}]")
        console.print(f"[bold {THEME['warning']}]{get_icon('warning')}Please install it manually:[/bold {THEME['warning']}]")
        if player_name == "mpv":
            console.print(f"[{THEME['dim']}]  Download: https://mpv.io/installation/[/{THEME['dim']}]")
            console.print(f"[{THEME['dim']}]  Or run: winget install mpv.net[/{THEME['dim']}]")
        else:
            console.print(f"[{THEME['dim']}]  Download: https://www.videolan.org/vlc/[/{THEME['dim']}]")
            console.print(f"[{THEME['dim']}]  Or run: winget install VideoLAN.VLC[/{THEME['dim']}]")
        time.sleep(3.0)
        return False

    else:
        pkg_managers = [
            ("apt", ["sudo", "apt", "install", "-y", player_name]),
            ("dnf", ["sudo", "dnf", "install", "-y", player_name]),
            ("pacman", ["sudo", "pacman", "-S", "--noconfirm", player_name]),
            ("zypper", ["sudo", "zypper", "install", "-y", player_name]),
            ("apk", ["sudo", "apk", "add", player_name]),
            ("emerge", ["sudo", "emerge", player_name]),
            ("xbps-install", ["sudo", "xbps-install", "-y", player_name]),
        ]

        for pm_name, cmd in pkg_managers:
            if shutil.which(pm_name):
                try:
                    console.print(f"[{THEME['dim']}]  Using {pm_name} to install {player_name}...[/{THEME['dim']}]")
                    result = subprocess.run(cmd, timeout=300)
                    if result.returncode == 0:
                        console.print(f"[bold {THEME['success']}]{get_icon('check')}{player_name.upper()} installed successfully via {pm_name}![/bold {THEME['success']}]")
                        time.sleep(2.0)
                        return True
                except FileNotFoundError:
                    continue
                except subprocess.TimeoutExpired:
                    continue

        if shutil.which("flatpak"):
            try:
                if player_name == "vlc":
                    flatpak_id = "org.videolan.VLC"
                elif player_name == "mpv":
                    flatpak_id = "io.mpv.Mpv"
                elif player_name == "celluloid":
                    flatpak_id = "io.github.celluloid_player.Celluloid"
                elif player_name == "haruna":
                    flatpak_id = "org.kde.haruna"
                else:
                    flatpak_id = None

                if flatpak_id:
                    cmd = ["flatpak", "install", "-y", flatpak_id]
                    console.print(f"[{THEME['dim']}]  Trying flatpak install {flatpak_id}...[/{THEME['dim']}]")
                    result = subprocess.run(cmd, timeout=300)
                    if result.returncode == 0:
                        console.print(f"[bold {THEME['success']}]{get_icon('check')}{player_name.upper()} installed successfully via Flatpak![/bold {THEME['success']}]")
                        time.sleep(2.0)
                        return True
            except Exception as e:
                print(f"[pyanime] Warning: player install subprocess failed: {e}")

        console.print(f"\n[bold {THEME['error']}]{get_icon('cross')}Could not auto-install {player_name.upper()} on this system.[/bold {THEME['error']}]")
        console.print(f"[bold {THEME['warning']}]{get_icon('warning')}Please install manually using your package manager.[/bold {THEME['warning']}]")
        time.sleep(3.0)
        return False
