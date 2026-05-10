# Code Param Tuner

Code Param Tuner 是一个本地运行的 Python/机器学习脚本参数调优工具。它会先用 AST 做基础参数识别，再可选调用 AI 审查参数是否误报/遗漏，并把脚本按自然代码块解释给新手阅读。

默认服务地址：

```text
http://localhost:8000/
```

## 功能

- 识别 Python 脚本中的可调参数，例如学习率、训练轮数、batch size、模型结构参数和配置字典。
- 支持 `.py` 和 `.ipynb` 导入。
- 第二窗口保留完整代码，只把可调值渲染成可编辑高亮块。
- AI 只做审查和代码块解释，不逐个参数输出冗长中文说明。
- 支持 Anthropic 原生接口和 OpenAI 兼容接口；OpenAI 兼容接口留空 model 时尊重上游默认模型。
- 支持暗色/浅色模式、左右窗口收起、专注模式。

## 安装运行

需要 Python 3.10 或更高版本。

macOS / Linux:

```bash
./scripts/run.sh
```

Windows:

```bat
scripts\run.bat
```

手动安装方式：

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
python -m backend.main
```

然后打开 `http://localhost:8000/`。

## API 设置

打开页面右上角「API 设置」：

- API Key 输入后保存在本机后端配置文件，不写入浏览器 `localStorage`。
- Base URL 留空时使用 Anthropic 默认接口。
- API 格式可选自动判断、Anthropic Messages 或 OpenAI 兼容。
- OpenAI 兼容接口的 Model 可留空，由上游服务使用默认模型。

本机配置默认保存到：

- macOS / Linux: `~/.code-param-tuner/settings.json`
- Windows: `%USERPROFILE%\.code-param-tuner\settings.json`

也可以用环境变量覆盖：

```bash
CPT_CONFIG_DIR=/path/to/config
CPT_PORT=8000
CPT_HOST=127.0.0.1
CPT_ALLOWED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000
```

完整示例见 `.env.example`。

## 验证

```bash
./scripts/check.sh
```

Windows:

```bat
scripts\check.bat
```

## 安全说明

- 服务默认只绑定 `127.0.0.1`，不要在不可信网络中绑定 `0.0.0.0`。
- API Key 不会提交到 GitHub；`.env`、虚拟环境、缓存和浏览器测试产物已被 `.gitignore` 排除。
- 后端对 API Base URL 做了基础 SSRF 防护，会拒绝 localhost 和常见内网 IP。
- 前端页面加了 CSP 等基础安全响应头，限制脚本把数据发往非本站地址。

## 示例

示例脚本放在 `examples/`：

- `examples/test_ml_script.py`
- `examples/full_model_script.py`
- `examples/Model.ipynb`
