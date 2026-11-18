import hashlib
import shutil
import sys
import urllib.request
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import DBLP_DTD, DBLP_DTD_RELEASE, DBLP_RELEASE, DBLP_XML

BASE = "https://drops.dagstuhl.de/storage/artifacts/dblp/xml"
XML_URL = f"{BASE}/{DBLP_RELEASE[:4]}/dblp-{DBLP_RELEASE}.xml.gz"
DTD_URL = f"{BASE}/{DBLP_DTD_RELEASE[:4]}/dblp-{DBLP_DTD_RELEASE}.dtd"


def md5sum(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def expected_md5(url: str) -> str:
    with urllib.request.urlopen(url + ".md5") as r:
        return r.read().decode().split()[0]


def fetch(url: str, dest: Path) -> None:
    expected = expected_md5(url)
    if dest.exists() and md5sum(dest) == expected:
        print(f"OK (sudah ada) {dest.name} md5={expected}")
        return
    tmp = dest.with_suffix(dest.suffix + ".part")
    print(f"Mengunduh {url}")
    with urllib.request.urlopen(url) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f, 1 << 20)
    actual = md5sum(tmp)
    if actual != expected:
        tmp.unlink()
        raise RuntimeError(f"MD5 tidak cocok untuk {dest.name}: {actual} != {expected}")
    tmp.replace(dest)
    print(f"OK {dest.name} md5={actual} size={dest.stat().st_size}")


def download():
    fetch(DTD_URL, DBLP_DTD)
    fetch(XML_URL, DBLP_XML)


if __name__ == "__main__":
    download()
