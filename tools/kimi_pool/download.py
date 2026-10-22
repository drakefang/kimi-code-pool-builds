"""下载固定版本客户端并校验发布完整性；不安装或修改 nxc 配置。"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import zipfile

MEMBERS = ("kimi.exe", "build_info.json", "verification.json", "LICENSE")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def download(lock_path, output):
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock.get("schema") != "nxclient-kimi-release/v1":
        raise ValueError("下载锁格式不支持")
    if output.exists():
        if (output / "kimi.exe").is_file() and digest(output / "kimi.exe") == lock["exe_sha256"]:
            return output / "kimi.exe"
        raise ValueError("目标已存在且不是匹配客户端，请选择新目录")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="nxc-kimi-download-", dir=output.parent) as temporary:
        stage = Path(temporary)
        subprocess.run(["gh", "release", "download", lock["tag"], "--repo", lock["repository"],
                        "--pattern", lock["asset"], "--dir", str(stage)], check=True)
        archive = stage / lock["asset"]
        if digest(archive) != lock["sha256"]:
            raise ValueError("下载资产完整性不匹配")
        extracted = stage / "client"
        extracted.mkdir()
        with zipfile.ZipFile(archive) as source:
            for name in MEMBERS:
                (extracted / name).write_bytes(source.read(name))
        if digest(extracted / "kimi.exe") != lock["exe_sha256"]:
            raise ValueError("executable 完整性不匹配")
        extracted.rename(output)
    return output / "kimi.exe"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-lock", type=Path, default=Path(__file__).with_name("release-lock.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(download(args.release_lock, args.output.resolve()))


if __name__ == "__main__":
    main()
