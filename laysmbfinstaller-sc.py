#dont forget to use pyinstaller dumbi
import os
import sys
import json
import time
import shutil
import zipfile
import logging
import tempfile
import threading
import subprocess
import requests
import urwid
import ctypes

CONFIG_JSON_URL = "https://raw.githubusercontent.com/AltyFox/MBFLauncherAutoInstaller/refs/heads/main/config.json"
ADB_URL = "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"
OCULUS_QUEST_ADB_DRIVER_URL = "https://securecdn.oculus.com/binaries/download/?id=2987319634674616"

logger = logging.getLogger("ILogs")
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler(sys.stdout)
ch.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
logger.addHandler(ch)

class InstallerUI:
    def __init__(self):
        self.log_lines = []
        self.progress = 0
        self.progress_text = urwid.Text("Progress: 0%")
        self.log_widget = urwid.Text("", wrap="clip")
        self.info_widget = urwid.Text("lays cutie installer <3", align="left")
        self.main_widget = urwid.Frame(
            header=urwid.Pile([self.info_widget, self.progress_text]),
            body=urwid.Filler(self.log_widget, valign="top"),
        )
        self.loop = urwid.MainLoop(self.main_widget, unhandled_input=self.handle_input)
    
    def handle_input(self, key):
        if key in ('q', 'Q'):
            raise urwid.ExitMainLoop()

    def update_progress(self, progress):
        self.progress = progress
        self.progress_text.set_text(f"Progress: {progress:.2f}%")
        self.loop.draw_screen()

    def add_log(self, text):
        timestamp = time.strftime("%H:%M:%S")
        self.log_lines.append(f"[{timestamp}] {text}")
        self.log_widget.set_text("\n".join(self.log_lines[-20:]))
        self.loop.draw_screen()

    def run(self):
        self.loop.run()


def download_file(url, destination, ui: InstallerUI, desc="Downloading"):
    ui.add_log(f"{desc} from {url}")
    response = requests.get(url, stream=True)
    total = int(response.headers.get("content-length", 0))
    downloaded = 0
    chunk_size = 8192
    with open(destination, "wb") as f:
        for chunk in response.iter_content(chunk_size):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                percentage = (downloaded / total * 100) if total else 0
                ui.update_progress(percentage)
    ui.add_log(f"Finished downloading {os.path.basename(destination)}")
    return destination

def extract_zip(zip_path, extract_to, ui: InstallerUI):
    ui.add_log(f"Extracting {zip_path} to {extract_to}")
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        members = zip_ref.infolist()
        total_members = len(members)
        for idx, member in enumerate(members):
            zip_ref.extract(member, extract_to)
            progress = (idx + 1) / total_members * 100
            ui.update_progress(progress)
    ui.add_log("Extraction complete.")

def extract_nested_zip(zip_path, extract_to, ui: InstallerUI):
    extract_zip(zip_path, extract_to, ui)
    for root, dirs, files in os.walk(extract_to):
        for file in files:
            if file.lower().endswith(".zip"):
                nested_zip = os.path.join(root, file)
                ui.add_log(f"Found nested zip: {nested_zip}")
                nested_extract_to = os.path.join(root, "nested")
                os.makedirs(nested_extract_to, exist_ok=True)
                extract_zip(nested_zip, nested_extract_to, ui)

def run_adb_command(args, adb_path="adb"):
    try:
        result = subprocess.run([adb_path] + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, universal_newlines=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return e.stdout.strip() + e.stderr.strip()

def check_connected_device(adb_path="adb"):
    output = run_adb_command(["devices"], adb_path)
    devices = {}
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("List of devices"):
            continue
        if line:
            parts = line.split()
            if len(parts) >= 2:
                devices[parts[0]] = parts[1]
    return devices

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False

def run_elevated(args, ui: InstallerUI):
    ui.add_log("Launching elevated CMD for driver operation...")
    script_path = os.path.abspath(__file__)
    cmd = f'cmd /k "{sys.executable} {script_path} {" ".join(args)} & pause"'
    ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", "cmd.exe", f'/c {cmd}', None, 1)
    if ret <= 32:
        ui.add_log("Failed to launch elevated CMD.")
    else:
        ui.add_log("Elevated CMD launched.")

def install_oculus_driver(driver_inf_path, ui: InstallerUI):
    ui.add_log("Requesting admin privileges to install Oculus Quest driver...")
    if os.name == 'nt':
        if not is_admin():
            args = [f'--driver-action=install', f'--driver-inf="{driver_inf_path}"']
            run_elevated(args, ui)
            ui.add_log("Please complete the installation in the new window, then press Enter here.")
            input("Press Enter after driver installation is complete...")
        else:
            cmd = ["pnputil", "/add-driver", driver_inf_path, "/install"]
            ui.add_log(f"Installing driver with command: {' '.join(cmd)}")
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            ui.add_log(proc.stdout)
            ui.add_log(proc.stderr)
            if proc.returncode == 0:
                ui.add_log("Driver installed successfully.")
            else:
                ui.add_log("Driver installation failed.")
    else:
        ui.add_log("Driver installation is only supported on Windows.")

def uninstall_oculus_driver(driver_inf_path, ui: InstallerUI):
    ui.add_log("Requesting admin privileges to uninstall Oculus Quest driver...")
    if os.name == 'nt':
        if not is_admin():
            args = [f'--driver-action=uninstall', f'--driver-inf="{driver_inf_path}"']
            run_elevated(args, ui)
            ui.add_log("Please complete the uninstallation in the new window, then press Enter here.")
            input("Press Enter after driver uninstallation is complete...")
        else:
            cmd = ["pnputil", "/delete-driver", driver_inf_path, "/uninstall"]
            ui.add_log(f"Uninstalling driver with command: {' '.join(cmd)}")
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            ui.add_log(proc.stdout)
            ui.add_log(proc.stderr)
            if proc.returncode == 0:
                ui.add_log("Driver uninstalled successfully.")
            else:
                ui.add_log("Driver uninstallation failed.")
    else:
        ui.add_log("Driver uninstallation is only supported on Windows.")

class LayMBFInstaller:
    def __init__(self, ui: InstallerUI):
        self.ui = ui
        self.temp_dir = os.path.join(tempfile.gettempdir(), "lays_mbf_installer")
        os.makedirs(self.temp_dir, exist_ok=True)
        self.config_json_path = os.path.join(self.temp_dir, "config.json")
        self.launcher_zip_path = os.path.join(self.temp_dir, "launcher.zip")
        self.adb_zip_path = os.path.join(self.temp_dir, "adb.zip")
        self.oculus_driver_zip_path = os.path.join(self.temp_dir, "oculus_driver.zip")
        self.launcher_dir = os.path.join(self.temp_dir, "launcher")
        self.adb_dir = os.path.join(self.temp_dir, "adb")
        self.oculus_driver_dir = os.path.join(self.temp_dir, "oculus_driver")
        self.apk_path = None
        self.adb_executable = None
        self.driver_inf_path = None

    def cleanup(self):
        self.ui.add_log("Cleaning up temporary files and uninstalling driver...")
        # Uninstall the Oculus driver before cleanup:
        if self.driver_inf_path and os.name == 'nt':
            uninstall_oculus_driver(self.driver_inf_path, self.ui)
        try:
            shutil.rmtree(self.temp_dir)
            self.ui.add_log("Cleanup complete.")
        except Exception as e:
            self.ui.add_log(f"Error during cleanup: {str(e)}")

    def download_and_extract_launcher(self):
        self.ui.add_log("Downloading configuration JSON...")
        download_file(CONFIG_JSON_URL, self.config_json_path, self.ui, "Downloading config JSON")
        with open(self.config_json_path, "r") as f:
            config = json.load(f)
        launcher_url = config.get("launcher-download-url")
        if not launcher_url:
            self.ui.add_log("Launcher download URL not found in JSON.")
            return False
        
        self.ui.add_log("Downloading launcher zip file...")
        download_file(launcher_url, self.launcher_zip_path, self.ui, "Downloading launcher")
        os.makedirs(self.launcher_dir, exist_ok=True)
        extract_zip(self.launcher_zip_path, self.launcher_dir, self.ui)
        self.ui.add_log("Searching for .apk file in the launcher directory...")
        for root, _, files in os.walk(self.launcher_dir):
            for file in files:
                if file.lower().endswith(".apk"):
                    self.apk_path = os.path.join(root, file)
                    self.ui.add_log(f"Found APK: {self.apk_path}")
                    break
            if self.apk_path:
                break
        if not self.apk_path:
            self.ui.add_log("No APK found in the launcher zip.")
            return False
        return True

    def download_adb(self):
        self.ui.add_log("Downloading ADB (Platform Tools from Google)...")
        download_file(ADB_URL, self.adb_zip_path, self.ui, "Downloading ADB")
        os.makedirs(self.adb_dir, exist_ok=True)
        extract_zip(self.adb_zip_path, self.adb_dir, self.ui)
        potential_adb = os.path.join(self.adb_dir, "platform-tools", "adb.exe")
        if os.path.exists(potential_adb):
            self.adb_executable = potential_adb
            self.ui.add_log(f"ADB executable found at {self.adb_executable}")
        else:
            self.ui.add_log("ADB executable not found. Please check the downloaded files.")
            return False
        return True

    def download_and_extract_oculus_driver(self):
        self.ui.add_log("Downloading Oculus Quest ADB Driver...")
        download_file(OCULUS_QUEST_ADB_DRIVER_URL, self.oculus_driver_zip_path, self.ui, "Downloading Oculus Quest Driver")
        os.makedirs(self.oculus_driver_dir, exist_ok=True)
        extract_zip(self.oculus_driver_zip_path, self.oculus_driver_dir, self.ui)
        nested_zip_found = False
        for root, _, files in os.walk(self.oculus_driver_dir):
            for file in files:
                if file.lower().endswith(".zip"):
                    nested_zip_path = os.path.join(root, file)
                    self.ui.add_log(f"Found nested driver zip: {nested_zip_path}")
                    extract_zip(nested_zip_path, self.oculus_driver_dir, self.ui)
                    nested_zip_found = True
        if not nested_zip_found:
            self.ui.add_log("No nested zip found inside the Oculus driver package.")
        
        self.ui.add_log("Searching for driver .inf file (android_winusb.inf)...")
        for root, _, files in os.walk(self.oculus_driver_dir):
            for file in files:
                if file.lower() == "android_winusb.inf":
                    self.driver_inf_path = os.path.join(root, file)
                    self.ui.add_log(f"Found driver INF file at: {self.driver_inf_path}")
                    break
            if self.driver_inf_path:
                break
        if not self.driver_inf_path:
            self.ui.add_log("Oculus driver INF file not found.")
            return False
        return True

    def install_oculus_driver_phase(self):
        install_oculus_driver(self.driver_inf_path, self.ui)

    def wait_for_device(self):
        self.ui.add_log("Please connect your Oculus Quest via USB.")
        authorized = False
        while not authorized:
            devices = check_connected_device(adb_path=self.adb_executable)
            if devices:
                for device_id, state in devices.items():
                    self.ui.add_log(f"Device detected: {device_id} - {state}")
                    if state.lower() == "unauthorized":
                        self.ui.add_log("Device is not authorized. On your Quest, please accept the ADB debugging popup (choose Allow).")
                    elif state.lower() in ["device", "online"]:
                        authorized = True
                        self.ui.add_log("Device recognized and authorized.")
                        break
                    else:
                        self.ui.add_log("The connected device might be in a charging-only mode. Please use a cable that supports data transfer.")
            else:
                self.ui.add_log("No device detected yet.")
            if not authorized:
                self.ui.add_log("Waiting for device connection... (Press 'q' to quit)")
                time.sleep(3)
        return authorized

    def install_apk(self):
        self.ui.add_log("Installing APK on the connected device...")
        result = run_adb_command(["install", "-r", self.apk_path], adb_path=self.adb_executable)
        self.ui.add_log(f"ADB install output:\n{result}")
        if "Failure" in result or "error" in result.lower():
            self.ui.add_log("Standard ADB installation failed. Trying alternative installation method...")
            remote_tmp = "/data/local/tmp/installer.apk"
            result_push = run_adb_command(["push", self.apk_path, remote_tmp], adb_path=self.adb_executable)
            self.ui.add_log(f"ADB push output:\n{result_push}")
            result_install = run_adb_command(["shell", "pm", "install", "-r", remote_tmp], adb_path=self.adb_executable)
            self.ui.add_log(f"ADB shell install output:\n{result_install}")
            if "Success" in result_install:
                self.ui.add_log("Alternative installation succeeded.")
            else:
                self.ui.add_log("Alternative installation method failed.")
                return False
        else:
            self.ui.add_log("APK successfully installed using standard method.")
        return True

    def run(self):
        try:
            if not self.download_and_extract_launcher():
                self.ui.add_log("Failed to download or extract launcher. Exiting.")
                return
            if not self.download_adb():
                self.ui.add_log("Failed to download or extract ADB. Exiting.")
                return
            if not self.download_and_extract_oculus_driver():
                self.ui.add_log("Failed to download or extract Oculus Quest driver. Exiting.")
                return
            self.install_oculus_driver_phase()
            if not self.wait_for_device():
                self.ui.add_log("No authorized device connected. Exiting.")
                return
            if not self.install_apk():
                self.ui.add_log("APK installation failed. Exiting.")
                return
            self.ui.add_log("APK installation complete. Cleaning up temporary files.")
        except Exception as e:
            self.ui.add_log(f"An exception occurred: {str(e)}")
        finally:
            self.cleanup()
            self.ui.add_log("Everything worked smoothly, you can now disconnect your quest from your computer!")

def main():
    if len(sys.argv) > 1:
        action = None
        driver_inf = None
        for arg in sys.argv[1:]:
            if arg.startswith("--driver-action="):
                action = arg.split("=",1)[1].lower()
            if arg.startswith("--driver-inf="):
                driver_inf = arg.split("=",1)[1].strip('"')
        if action and driver_inf:
            if action == "install":
                cmd = ["pnputil", "/add-driver", driver_inf, "/install"]
            elif action == "uninstall":
                cmd = ["pnputil", "/delete-driver", driver_inf, "/uninstall"]
            else:
                sys.exit(1)
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            print(result.stdout)
            print(result.stderr)
            sys.exit(result.returncode)

    ui = InstallerUI()
    installer = LayMBFInstaller(ui)

    installer_thread = threading.Thread(target=installer.run, daemon=True)
    installer_thread.start()

    ui.run()

if __name__ == "__main__":
    main()