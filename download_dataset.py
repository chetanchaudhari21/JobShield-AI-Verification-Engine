
from pathlib import Path
import kagglehub

dataset_id = "amruthjithrajvr/recruitment-scam"

download_path = kagglehub.dataset_download(dataset_id)

print("\nDownloaded dataset directory:", download_path)
print("\nFiles found:")

for file in sorted(Path(download_path).rglob("*")):
    if file.is_file():
        print(f"{file.name} — {file.stat().st_size:,} bytes")