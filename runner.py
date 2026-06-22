import requests
import json
import os
from pathlib import Path
from datetime import datetime

# Optional: for setting Windows creation time
try:
    import pywintypes
    import win32file
    import win32con
    WINDOWS = True
except ImportError:
    WINDOWS = False


# ------------------------------------------------------------
# Detect file type from magic numbers
# ------------------------------------------------------------
def detect_file_type(data: bytes) -> str:
    sig = data[:8]

    if sig.startswith(b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1"):
        return "xls"
    if sig.startswith(b"\x50\x4B\x03\x04"):
        return "xlsx"
    if sig.startswith(b"\x25\x50\x44\x46"):
        return "pdf"
    if sig.startswith(b"\xEF\xBB\xBF"):
        return "csv"

    return "dat"


# ------------------------------------------------------------
# Detect HTML error page
# ------------------------------------------------------------
def is_html_error(data: bytes) -> bool:
    head = data[:4096].decode("utf-8", errors="ignore").lower()
    return "<html" in head or "<!doctype" in head


# ------------------------------------------------------------
# Set Windows timestamps (creation + modified + accessed)
# ------------------------------------------------------------
def set_windows_timestamp(path: Path, timestamp: datetime):
    if not WINDOWS:
        return

    wintime = pywintypes.Time(timestamp)
    handle = win32file.CreateFile(
        str(path),
        win32con.GENERIC_WRITE,
        win32con.FILE_SHARE_READ,
        None,
        win32con.OPEN_EXISTING,
        win32con.FILE_ATTRIBUTE_NORMAL,
        None
    )
    win32file.SetFileTime(handle, wintime, wintime, wintime)
    handle.close()


# ------------------------------------------------------------
# Main download function
# ------------------------------------------------------------
def download_report(task_id, info, session: requests.Session, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)

    # Clean old temp files
    for f in output_dir.glob(f"temp_{task_id}*.bin"):
        f.unlink()

    temp_file = output_dir / f"temp_{task_id}.bin"

    # Build URL
    report_url = info["Url"]

    # Download
    r = session.get(report_url)
    r.raise_for_status()

    # Save temp file
    temp_file.write_bytes(r.content)

    # Detect HTML error
    if is_html_error(r.content):
        error_file = output_dir / f"Error_{task_id}.html"
        error_file.write_bytes(r.content)
        print(f"HTML error for task {task_id}")
        return

    # Detect actual file type
    ext = detect_file_type(r.content)

    # Final file name
    final_file = output_dir / f"Report_{task_id}.{ext}"

    # Overwrite if exists
    if final_file.exists():
        final_file.unlink()

    temp_file.rename(final_file)

    # Parse timestamp from metadata
    raw = info["ReportDate"]  # e.g. "20240619:153012"
    timestamp = datetime.strptime(raw, "%Y%m%d:%H%M%S")

    # Apply timestamps
    os.utime(final_file, (timestamp.timestamp(), timestamp.timestamp()))
    set_windows_timestamp(final_file, timestamp)

    # Write metadata JSON
    json_file = final_file.with_suffix(".json")
    with open(json_file, "w", encoding="utf-8") as jf:
        json.dump(info, jf, indent=4)

    # Apply timestamp to JSON too
    os.utime(json_file, (timestamp.timestamp(), timestamp.timestamp()))
    set_windows_timestamp(json_file, timestamp)

    print(f"Downloaded {final_file.name}")


# ------------------------------------------------------------
# Example usage
# ------------------------------------------------------------
if __name__ == "__main__":
    # Load your driving metadata JSON
    with open("metadata.json", "r") as f:
        meta = json.load(f)

    output_dir = Path("reports")

    # Create session (cookies, login, etc.)
    session = requests.Session()

    # Loop through all tasks
    for task_id, info in meta.items():
        download_report(task_id, info, session, output_dir)
      
