import zipfile, urllib.request, io, os

# Settings
URL = 'http://127.0.0.1:8080/OPRA-20260129-39UX5P5C9X.zip'
OUT_DIR = os.path.expanduser('~/Desktop/OPRA_EXTRACTED')

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

os.makedirs(OUT_DIR, exist_ok=True)
rf = RemoteFile(URL)
with zipfile.ZipFile(rf) as z:
    # Filter for the files you want (e.g., all CSVs)
    csv_files = [f for f in z.namelist() if f.endswith('.csv')]
    print(f"Found {len(csv_files)} CSV files. Starting extraction...")

    for file_name in csv_files:
        print(f"Extracting: {file_name}")
        with z.open(file_name) as source, open(os.path.join(OUT_DIR, file_name), 'wb') as target:
            target.write(source.read())

print(f"\nSuccess! Your files are in the '{OUT_DIR}' folder on your Desktop.")