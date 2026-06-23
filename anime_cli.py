#!/usr/bin/env python3
"""
Anime CLI Player — Stream & Play
Thin orchestrator — delegates to src/ layer packages.
"""

# ── Check and Install Missing Python Dependencies ──
def check_and_install_dependencies():
    required_packages = {
        "bs4": "beautifulsoup4",
        "rich": "rich",
        "playwright": "playwright",
        "httpx": "httpx",
        "lxml": "lxml",
    }

    crypto_installed = False
    try:
        from Cryptodome.Cipher import AES
        crypto_installed = True
    except ImportError:
        try:
            from Crypto.Cipher import AES
        except ImportError:
            pass
        except ImportError:
            pass
            pass

    missing_packages = []
    for imp_name, pip_name in required_packages.items():
        try:
            __import__(imp_name)
        except ImportError:
            missing_packages.append(pip_name)

    if not crypto_installed:
        missing_packages.append("pycryptodome")

    if missing_packages:
        print("Missing required libraries: " + ", ".join(missing_packages))
        print("Attempting to install them automatically...")
        import sys
        import subprocess

        pip_cmd = [sys.executable, "-m", "pip", "install"] + missing_packages
        installed_ok = False
        try:
            subprocess.run(pip_cmd, check=True)
            installed_ok = True
        except Exception:
            try:
                print("Retrying with bypass flags (--user --break-system-packages)...")
                fallback_cmd = [sys.executable, "-m", "pip", "install", "--user", "--break-system-packages"] + missing_packages
                subprocess.run(fallback_cmd, check=True)
                installed_ok = True
            except Exception as e:
                print(f"Error installing dependencies: {e}")
                print("Please install them manually using: pip install " + " ".join(missing_packages))
                sys.exit(1)

        if installed_ok:
            print("Successfully installed missing libraries!")
            if "playwright" in missing_packages:
                print("Installing Playwright Chromium browser binaries...")
                try:
                    playwright_install_cmd = [sys.executable, "-m", "playwright", "install", "chromium"]
                    subprocess.run(playwright_install_cmd, check=True)
                    print("Playwright Chromium browser installed successfully!")
                except Exception as e:
                    print(f"Warning: Playwright browser installation failed: {e}")
                    print("You may need to run 'playwright install' manually later.")

check_and_install_dependencies()

from src.ui.cli import main

if __name__ == "__main__":
    main()
