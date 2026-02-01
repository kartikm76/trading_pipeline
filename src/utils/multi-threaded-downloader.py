import subprocess
import time
import zipfile
import urllib.request
import io
import os
import signal
import sys
import platform
from concurrent.futures import ThreadPoolExecutor

# --- CONFIGURATION ---
REMOTE_NAME = "gdrive"
REMOTE_FOLDER_ID = "1jJM1OKS6QmI1-odSL8Xtg96-ShMpUbw-"
ZIP_FILENAME = "OPRA-20260129-39UX5P5C9X.zip"
PORT = "8080"
URL = f"http://127.0.0.1:{PORT}/{ZIP_FILENAME}"
MAX_WORKERS = 3  # Adjusted for Google Drive stability (3-4 is safest)

OUT_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "OPRA_EXTRACTED")

def setup_environment():
    try:
        subprocess.run(["rclone", "version"], check=True, capture_output=True)
    except:
        if platform.system() == "Darwin":
            os.system("curl https://rclone.org/install.sh | sudo bash")
        else:
            print("Please install rclone manually on Windows.")
            sys.exit(1)

    try:
        import tqdm
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "tqdm"])

setup_environment()
from tqdm import tqdm

class RemoteFile(io.RawIOBase):
    def __init__(self, url):
        self.url, self.pos = url, 0
        with urllib.request.urlopen(url) as f:
            self.size = int(f.getheader('Content-Length'))
    def seekable(self): return True
    def seek(self, offset, whence=io.SEEK_SET):
        if whence == io.SEEK_SET: self.pos = offset
        elif whence == io.SEEK_CUR: self.pos += offset
        elif whence == io.SEEK_END: self.pos = self.size + offset
        return self.pos
    def tell(self): return self.pos
    def readinto(self, b):
        end = min(self.pos + len(b) - 1, self.size - 1)
        req = urllib.request.Request(self.url, headers={'Range': f'bytes={self.pos}-{end}'})
        with urllib.request.urlopen(req) as f:
            data = f.read(); b[:len(data)] = data
            self.pos += len(data); return len(data)

def download_file(file_info, zip_url):
    file_name = file_info.filename
    expected_size = file_info.file_size
    target_path = os.path.join(OUT_DIR, file_name)

    # Resume Logic
    if os.path.exists(target_path) and os.path.getsize(target_path) == expected_size:
        return f"⏩ Skipped {file_name}"

    # Use a fresh RemoteFile instance per thread to avoid position conflicts
    rf = RemoteFile(zip_url)
    with zipfile.ZipFile(rf) as z:
        with z.open(file_name) as source, open(target_path, 'wb') as target:
            # Note: Multiple progress bars can get messy;
            # we use a simple print for start/end in multi-thread mode
            print(f"⬇️ Starting: {file_name}")
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk: break
                target.write(chunk)
    return f"✅ Finished: {file_name}"

# --- EXECUTION ---
print(f"🚀 Launching Rclone Bridge and starting {MAX_WORKERS} threads...")
rclone_proc = subprocess.Popen([
    "rclone", "serve", "http", f"{REMOTE_NAME}:",
    "--drive-root-folder-id", REMOTE_FOLDER_ID,
    "--addr", f"127.0.0.1:{PORT}"
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

time.sleep(5)

try:
    os.makedirs(OUT_DIR, exist_ok=True)
    master_rf = RemoteFile(URL)
    with zipfile.ZipFile(master_rf) as z:
        all_csvs = [z.getinfo(f) for f in z.namelist() if f.endswith('.csv')]

        print(f"📊 Found {len(all_csvs)} files. Parallel download active.")

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # Map the download function to our list of files
            results = list(executor.map(lambda f: download_file(f, URL), all_csvs))

    for res in results:
        print(res)

finally:
    rclone_proc.terminate()
    rclone_proc.wait()