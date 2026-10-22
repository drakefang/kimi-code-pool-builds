"""将已验收客户端打包为固定 GitHub Release 资产。"""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

MEMBERS = ("kimi.exe", "build_info.json", "verification.json", "LICENSE")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def package(artifact, output, repository, tag):
    info = json.loads((artifact / "build_info.json").read_text(encoding="utf-8"))
    verification = json.loads((artifact / "verification.json").read_text(encoding="utf-8"))
    if verification.get("passed") is not True or info["exe_sha256"] != digest(artifact / "kimi.exe"):
        raise ValueError("产物未通过验收或 executable 不匹配")
    output.mkdir(parents=True, exist_ok=True)
    name = f"kimi-{info['version']}-pool-win32-x64.zip"
    archive = output / name
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as target:
        for member in MEMBERS:
            target.write(artifact / member, member)
    lock = {"schema": "nxclient-kimi-release/v1", "repository": repository, "tag": tag,
            "asset": name, "sha256": digest(archive), "exe_sha256": info["exe_sha256"],
            "version": info["version"], "platform": info["platform"]}
    (output / "release-lock.json").write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    return archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()
    print(package(args.artifact, args.output, args.repository, args.tag).name)


if __name__ == "__main__":
    main()
