# Kimi Code 独立子代理池 Windows 客户端

当前固定版本：`kimi-2.3.0-pool-v1`，官方 Kimi Code 2.3.0 基线，Windows x64。它是独立补丁构建，提供不污染主模型列表的对象子代理池，并保持子代理 model/effort 的原生持久绑定。

## 跨机器直接下载

需要 Git、Python 3.11+ 与 GitHub CLI `gh`，不需要 Node、pnpm 或本地编译。

```powershell
git clone --branch kimi-2.3.0-pool-v1 --depth 1 https://github.com/drakefang/kimi-code-pool-builds.git
Set-Location kimi-code-pool-builds
python tools/kimi_pool/download.py --output <新的客户端目录>
```

下载固定资产并校验 ZIP 与 exe 的发布完整性，输出 executable 位置。下载不会安装到 PATH，不修改日用 HOME、会话或 nxc 配置；后续安装时再显式指定 `[kimi].executable`。

ZIP 包含 `kimi.exe`、`build_info.json`、`verification.json`、`LICENSE`。构建配方、补丁和验收说明见 [tools/kimi_pool](tools/kimi_pool/README.md)。本构建经过原生 consumer/replay 和隔离真实请求验收；未调用真实付费上游。

历史 2.1.1 资产保持不变，使用时检出各自固定 tag，不混用不同版本的下载锁与工具。
