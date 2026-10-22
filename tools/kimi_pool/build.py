"""从固定官方源码构建独立子代理池 Windows 客户端；不安装到日用环境。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parent


def run(args, **kwargs):
    return subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def recipe():
    return tomllib.loads((ROOT / "manifest.toml").read_text(encoding="utf-8"))


def prepare(source):
    config = recipe()
    if source.exists():
        raise ValueError("源码目标必须是不存在的新目录")
    upstream = config["upstream"]
    run(["git", "-c", "core.autocrlf=false", "clone", "--depth", "1", "--branch",
         "@moonshot-ai/kimi-code@" + upstream["version"], upstream["repository"], source])
    revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if revision != upstream["revision"]:
        raise ValueError("官方源码 revision 不匹配")
    patch = ROOT / config["build"]["patch"]
    run(["git", "-C", source, "apply", "--check", patch])
    run(["git", "-C", source, "apply", patch])


def build(source, output, node, pnpm_script):
    config = recipe()
    if os.name != "nt" or output.exists():
        raise ValueError("仅支持 Windows，产物目标必须不存在")
    node = Path(shutil.which(str(node)) or node).resolve()
    pnpm_script = pnpm_script.resolve()
    for command, expected in (([node, "--version"], "v" + config["build"]["node"]),
                              ([node, pnpm_script, "--version"], config["build"]["pnpm"])):
        if subprocess.check_output([str(a) for a in command], text=True).strip() != expected:
            raise ValueError("Node 或 pnpm 版本不匹配")
    environment = os.environ | {"HUSKY": "0", "KIMI_CODE_BUILD_TARGET": "win32-x64"}
    with tempfile.TemporaryDirectory(prefix="nxc-kimi-build-") as temporary:
        shim = Path(temporary) / "pnpm.cmd"
        if any(c in str(node) + str(pnpm_script) for c in ('"', '%', '\r', '\n')):
            raise ValueError("工具路径含不支持的 shell 字符")
        shim.write_text(f'@"{node}" "{pnpm_script}" %*\r\n', encoding="utf-8")
        environment["PATH"] = str(shim.parent) + os.pathsep + str(node.parent) + os.pathsep + environment.get("PATH", "")
        pnpm = [node, pnpm_script]
        run(pnpm + ["install", "--frozen-lockfile"], cwd=source, env=environment)
        filters = []
        for package in sorted((source / "packages").glob("*/package.json")):
            filters += ["--filter", json.loads(package.read_text(encoding="utf-8"))["name"]]
        run(pnpm + ["-r", "--workspace-concurrency=2"] + filters + ["run", "build"], cwd=source, env=environment)
        run(pnpm + ["run", "build:native:sea"], cwd=source / "apps/kimi-code", env=environment)
    output.mkdir(parents=True)
    executable = source / "apps/kimi-code/dist-native/bin/win32-x64/kimi.exe"
    shutil.copyfile(executable, output / "kimi.exe")
    shutil.copyfile(source / "LICENSE", output / "LICENSE")
    info = {"schema": "nxclient-kimi-build/v1", "version": config["upstream"]["version"],
            "source_revision": config["upstream"]["revision"], "platform": "win32-x64",
            "node": config["build"]["node"], "pnpm": config["build"]["pnpm"],
            "exe_sha256": hashlib.file_digest(executable.open("rb"), "sha256").hexdigest()}
    (output / "build_info.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    prep = commands.add_parser("prepare")
    prep.add_argument("--source", type=Path, required=True)
    compile_command = commands.add_parser("build")
    compile_command.add_argument("--source", type=Path, required=True)
    compile_command.add_argument("--output", type=Path, required=True)
    compile_command.add_argument("--node", type=Path, default=Path("node"))
    compile_command.add_argument("--pnpm-script", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args.source.resolve())
    else:
        build(args.source.resolve(), args.output.resolve(), args.node, args.pnpm_script)


if __name__ == "__main__":
    main()
