"""AI integration for semantic parameter analysis — supports Anthropic native + OpenAI-compatible endpoints."""

import asyncio
import ipaddress
import json
import logging
import os
import re
from urllib.parse import urlparse

import anthropic
import httpx

try:
    from .parser import COMMON_PARAMS
except ImportError:
    from parser import COMMON_PARAMS

logger = logging.getLogger("code-param-tuner.ai")

ANTHROPIC_NATIVE_MODELS = (
    "claude-opus", "claude-sonnet", "claude-haiku",
    "claude-3", "claude-4",
)

# L6: Default model configurable via env
DEFAULT_MODEL = os.getenv("CPT_DEFAULT_MODEL", "claude-sonnet-4-20250514")
AI_REQUEST_TIMEOUT_SECONDS = float(os.getenv("CPT_AI_TIMEOUT_SECONDS", "180"))
AI_REVIEW_TIMEOUT_SECONDS = float(os.getenv("CPT_AI_REVIEW_TIMEOUT_SECONDS", "210"))
AI_MAX_OUTPUT_TOKENS = int(os.getenv("CPT_AI_MAX_OUTPUT_TOKENS", "8192"))
MAX_CODE_CHARS_FOR_AI_EXPLANATION = int(os.getenv("CPT_AI_MAX_CODE_CHARS", "60000"))


def _build_review_prompt(code: str, params: list[dict]) -> str:
    param_summary = []
    for p in params:
        entry = {
            "name": p["name"],
            "value": p["value"],
            "type": p["type"],
            "source": p.get("source", "unknown"),
            "scope": p.get("scope", "unknown"),
            "line": p.get("line"),
        }
        if p.get("presetDesc"):
            entry["preset_desc"] = p["presetDesc"]
        if p.get("helpText"):
            entry["help_text"] = p["helpText"]
        param_summary.append(entry)

    code_for_ai = code
    if len(code_for_ai) > MAX_CODE_CHARS_FOR_AI_EXPLANATION:
        code_for_ai = code_for_ai[:MAX_CODE_CHARS_FOR_AI_EXPLANATION]

    return f"""你是一个面向编程新手的 Python/机器学习脚本讲解助手。
你需要先整体浏览脚本，理解这个脚本从导入依赖、配置参数、定义模型/函数、加载数据、训练/评估/保存等步骤分别在做什么。

任务：
1. 审查基础 AST 参数提取结果是否有明显误报。
2. 按脚本的自然结构划分代码段，并解释每段代码的作用。

输出要求：
只返回 JSON 对象，格式严格如下：
{{
  "exclude":["name1"],
  "notes":[],
  "sections":[
    {{"title":"依赖导入","start_line":1,"end_line":5,"explanation":"这一段加载脚本后续会用到的库。它决定了模型、数据读取、训练循环等能力从哪里来。"}}
  ]
}}

参数审查规则：
- exclude 只放明显不是用户调参项的候选名，例如训练循环里的临时变量、累计 loss、循环计数器、中间张量。
- 对常见 ML 超参数、配置字典、路径、随机种子、模型结构参数不要排除。
- 不确定就不要排除。
- notes 保持空数组，除非发现基础解析明显漏掉某个重要参数名；每条 note 不超过 30 字。

代码段解释规则：
- sections 必须覆盖脚本主要结构，按行号递增，不要逐行解释。
- 每段建议覆盖 3 到 30 行；短脚本可更少，长脚本要合并成 6 到 14 个自然段。
- title 用 4 到 12 个中文字，概括这段在做什么。
- explanation 面向新手，必须自然、具体、可读，说明这段在整个脚本流程中的作用，不要只写“定义函数”“循环执行”这种短标签。
- 如果某段包含可调参数，解释里说明这些参数会影响什么，但不要逐个写长篇参数说明。
- start_line/end_line 必须是源码中的实际 1-based 行号。

参数列表:
{json.dumps(param_summary, ensure_ascii=False, separators=(",", ":"))}

脚本源码:
```python
{code_for_ai}
```"""


def _is_anthropic_native(model: str) -> bool:
    return any(model.startswith(prefix) for prefix in ANTHROPIC_NATIVE_MODELS)


def _is_anthropic_base_url(base_url: str | None) -> bool:
    if not base_url:
        return True
    hostname = urlparse(base_url).hostname or ""
    return hostname == "api.anthropic.com" or hostname.endswith(".anthropic.com")


def _openai_chat_completions_url(base_url: str) -> str:
    """Build a chat completions URL without duplicating a trailing /v1."""
    clean_url = base_url.rstrip("/")
    if clean_url.endswith("/v1"):
        return clean_url + "/chat/completions"
    return clean_url + "/v1/chat/completions"


def _require_text_response(text: object) -> str:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("AI 返回了空响应")
    return text


def _extract_text_from_content_parts(content: object) -> str:
    """Extract text from OpenAI/Anthropic-style content blocks."""
    if isinstance(content, str):
        return _require_text_response(content)

    if content is None:
        raise ValueError("AI 返回了空响应")

    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
            else:
                text = getattr(item, "text", None)
                if isinstance(text, str):
                    parts.append(text)
        return _require_text_response("".join(parts))

    text = getattr(content, "text", None)
    return _require_text_response(text)


# H: SSRF protection — validate base_url before making requests
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _validate_base_url(url: str) -> None:
    """Raise ValueError if base_url targets a private/loopback address."""
    parsed = urlparse(url)
    if parsed.scheme not in ("https", "http"):
        raise ValueError(f"不支持的协议 '{parsed.scheme}'，仅允许 http/https")
    if parsed.scheme == "http":
        logger.warning("base_url 使用 HTTP 而非 HTTPS，API key 将以明文传输")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Base URL 缺少主机名")
    if hostname in ("localhost", "0.0.0.0"):
        raise ValueError("出于安全考虑，不允许请求 localhost 地址")
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        return  # domain name, not an IP — allow
    for net in _BLOCKED_NETWORKS:
        if ip in net:
            raise ValueError(f"出于安全考虑，不允许请求内网/环回地址 ({hostname})")


# M9: Async Anthropic call
async def _call_anthropic_native(prompt: str, api_key: str, base_url: str | None, model: str) -> str:
    """Call Anthropic native Messages API (async)."""
    import httpx as _httpx
    client = anthropic.AsyncAnthropic(
        api_key=api_key,
        base_url=base_url or None,
        timeout=_httpx.Timeout(AI_REQUEST_TIMEOUT_SECONDS),
        max_retries=0,
    )
    message = await client.messages.create(
        model=model,
        max_tokens=AI_MAX_OUTPUT_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    # Check for empty response
    if not message.content:
        raise ValueError("AI 返回了空响应")
    if getattr(message, "stop_reason", None) == "max_tokens":
        logger.warning("AI response hit max_tokens; attempting to parse returned content")
    return _extract_text_from_content_parts(message.content)


async def _call_openai_compatible(prompt: str, api_key: str, base_url: str, model: str | None) -> str:
    """Call any OpenAI-compatible /v1/chat/completions endpoint."""
    url = _openai_chat_completions_url(base_url)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "max_tokens": AI_MAX_OUTPUT_TOKENS,
        "messages": [
            {"role": "system", "content": "你是一个代码参数分析助手。请严格返回 JSON，不要包含其他文字。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
    }
    if model:
        payload["model"] = model
    async with httpx.AsyncClient(timeout=AI_REQUEST_TIMEOUT_SECONDS) as client:
        resp = await client.post(url, json=payload, headers=headers)
        # H6: Catch HTTP errors specifically, don't leak response body
        if resp.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {resp.status_code}",
                request=resp.request,
                response=resp,
            )
        try:
            data = resp.json()
        except ValueError as e:
            raise ValueError("AI 服务返回非 JSON 响应") from e

    choices = data.get("choices") if isinstance(data, dict) else None
    if not isinstance(choices, list) or not choices:
        raise ValueError("AI 响应缺少 choices")

    choice = choices[0]
    if not isinstance(choice, dict):
        raise ValueError("AI 响应 choices 格式异常")

    if choice.get("finish_reason") == "length":
        logger.warning("AI response hit max_tokens; attempting to parse returned content")

    message = choice.get("message")
    if isinstance(message, dict):
        return _extract_text_from_content_parts(message.get("content"))

    return _extract_text_from_content_parts(choice.get("text"))


async def _call_ai(
    prompt: str,
    api_key: str,
    base_url: str | None,
    model: str | None,
    api_format: str | None,
) -> str:
    """Call AI via Anthropic native or OpenAI-compatible chat completions."""
    if base_url:
        _validate_base_url(base_url)
        if _should_use_openai_compatible(base_url, api_format):
            return await _call_openai_compatible(prompt, api_key, base_url, model)
    return await _call_anthropic_native(prompt, api_key, base_url, model or DEFAULT_MODEL)


def _apply_preset_fallback(param: dict) -> dict:
    name = param["name"]
    preset = COMMON_PARAMS.get(name)
    if preset and "alias" in preset:
        target = preset["alias"]
        preset = COMMON_PARAMS.get(target) if target in COMMON_PARAMS and "alias" not in COMMON_PARAMS.get(target, {}) else None

    if preset and "alias" not in preset:
        # Preserve options from param (e.g. argparse choices) over preset defaults
        existing_opts = param.get("options") if isinstance(param.get("options"), list) else None
        opts = existing_opts or preset.get("options")
        return {
            "name": name,
            "is_tunable": True,
            "description": preset.get("desc", name),
            "impact": "",
            "edit_type": "slider" if preset.get("range") else ("select" if opts else "number"),
            "range": preset.get("range"),
            "options": opts,
            "group": preset.get("group", "其他"),
            "depends_on": None,
            "confidence": 0.7,
        }
    return {
        "name": name,
        "is_tunable": True,
        "description": name.replace("_", " "),
        "impact": "",
        "edit_type": _guess_edit_type(param),
        "range": None,
        "options": None,
        "group": "其他",
        "depends_on": None,
        "confidence": 0.3,
    }


def _guess_edit_type(param: dict) -> str:
    t = param.get("type", "string")
    if t == "bool":
        return "toggle"
    if t in ("int", "float"):
        return "number"
    if t == "path":
        return "path"
    if t == "list":
        return "text"
    return "text"


def _short_text(value: object, max_chars: int) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return text[:max_chars]


def _extract_json_object(text: str) -> dict:
    """Extract the first JSON object from text, handling surrounding non-JSON content."""
    # Try direct parse first
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    object_start = text.find("{")
    if object_start == -1:
        raise json.JSONDecodeError("No JSON object found", text, 0)

    decoder = json.JSONDecoder()
    try:
        result, _ = decoder.raw_decode(text, object_start)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    raise json.JSONDecodeError("Failed to extract JSON object", text, object_start)


def _normalize_api_format(api_format: str | None) -> str:
    value = (api_format or "auto").strip().lower()
    if value in ("anthropic", "anthropic_native", "anthropic-messages"):
        return "anthropic"
    if value in ("openai", "openai_compatible", "openai-compatible"):
        return "openai"
    return "auto"


def _should_use_openai_compatible(base_url: str | None, api_format: str | None) -> bool:
    normalized = _normalize_api_format(api_format)
    if normalized == "openai":
        return True
    if normalized == "anthropic":
        return False
    return bool(base_url and not _is_anthropic_base_url(base_url))


async def _review_params_with_ai(
    code: str,
    params: list[dict],
    api_key: str,
    base_url: str | None,
    model_name: str,
    api_format: str | None,
) -> dict:
    prompt = _build_review_prompt(code, params)
    response_text = await asyncio.wait_for(
        _call_ai(prompt, api_key, base_url, model_name, api_format),
        timeout=AI_REVIEW_TIMEOUT_SECONDS,
    )
    response_text = _require_text_response(response_text)
    logger.info("AI review response received (%d chars)", len(response_text))

    try:
        cleaned = re.sub(r"```(?:json|JSON)?[\s\n]*", "", response_text)
        cleaned = re.sub(r"```\s*$", "", cleaned.strip())
        first_brace = cleaned.find("{")
        last_brace = cleaned.rfind("}")
        if first_brace != -1 and last_brace > first_brace:
            cleaned = cleaned[first_brace:last_brace + 1]
        result = _extract_json_object(cleaned)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse AI review response as JSON: %s", e)
        logger.error("Raw response (first 500 chars): %s", response_text[:500])
        raise ValueError("AI 审查返回格式异常，已使用基础模式。") from e

    exclude = result.get("exclude", [])
    notes = result.get("notes", [])
    sections = result.get("sections", [])
    if not isinstance(exclude, list):
        exclude = []
    if not isinstance(notes, list):
        notes = []
    if not isinstance(sections, list):
        sections = []
    return {
        "exclude": [str(name) for name in exclude],
        "notes": [_short_text(note, 30) for note in notes],
        "sections": _normalize_sections(sections, len(code.splitlines()) or 1),
    }


# M9: Made async
async def analyze_params(
    code: str,
    params: list[dict],
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    api_format: str | None = None,
) -> dict:
    base_result = _build_fallback_result(code, params, "未配置 API Key")
    base_params = base_result["params"]

    if not api_key:
        return base_result

    try:
        review = await _review_params_with_ai(code, params, api_key, base_url, model, api_format)
    except ValueError as e:
        logger.warning("AI validation error: %s", e)
        return {**base_result, "error": str(e)}
    except anthropic.AuthenticationError as e:
        logger.error("AI auth error (401): %s", e.message)
        return {**base_result, "error": "API Key 无效（401），请检查 API Key 是否正确。"}
    except anthropic.NotFoundError as e:
        logger.error("AI 404: %s %s", e.message, getattr(e, 'response', None) and e.response.url)
        return {**base_result, "error": "API 地址不存在（404），请检查 Base URL 和 Model 是否正确。"}
    except anthropic.APIStatusError as e:
        logger.error("AI API error %s: %s", e.status_code, e.message)
        return {**base_result, "error": f"AI 服务返回错误 HTTP {e.status_code}：{e.message}"}
    except anthropic.APITimeoutError:
        logger.error("AI API request exceeded %.1fs", AI_REQUEST_TIMEOUT_SECONDS)
        return {**base_result, "error": f"AI 请求超时（上游超过 {int(AI_REQUEST_TIMEOUT_SECONDS)} 秒未返回），已使用基础模式。"}
    except httpx.HTTPStatusError as e:
        logger.error("AI HTTP error: %s %s", e.response.status_code, e.response.url)
        return {**base_result, "error": f"AI 服务返回错误 HTTP {e.response.status_code}，请检查 API Key 和设置。"}
    except httpx.TimeoutException:
        logger.error("AI request timed out")
        return {**base_result, "error": "AI 审查超时，已使用基础模式。"}
    except asyncio.TimeoutError:
        logger.error("AI review exceeded %.1fs", AI_REVIEW_TIMEOUT_SECONDS)
        return {**base_result, "error": "AI 审查超时，已使用基础模式。"}
    except Exception as e:
        logger.error("AI call failed: %s: %s", type(e).__name__, e, exc_info=True)
        return {**base_result, "error": f"AI 服务调用失败：{type(e).__name__}: {str(e)[:200]}"}

    exclude_names = set(review["exclude"])
    reviewed_params = [
        {**param, "aiReviewed": True}
        for param in base_params
        if param["name"] not in exclude_names
    ]
    return {
        "params": reviewed_params,
        "fallback": False,
        "error": None,
        "warnings": review["notes"],
        "sections": review["sections"] or base_result["sections"],
    }


def _normalize_sections(raw_sections: list, fallback_line_count: int) -> list[dict]:
    sections = []
    max_line = max(1, fallback_line_count)
    for item in raw_sections:
        if not isinstance(item, dict):
            continue
        try:
            start_line = int(item.get("start_line"))
            end_line = int(item.get("end_line"))
        except (TypeError, ValueError):
            continue
        if start_line < 1 or end_line < start_line:
            continue
        sections.append({
            "title": _short_text(item.get("title") or "代码片段", 24),
            "start_line": start_line,
            "end_line": end_line,
            "explanation": _short_text(item.get("explanation") or "", 500),
        })
    sections.sort(key=lambda s: (s["start_line"], s["end_line"]))
    return sections or [{
        "title": "脚本代码",
        "start_line": 1,
        "end_line": max_line,
        "explanation": "这部分是脚本的主体代码。当前 AI 没有返回可用的分段解释，因此先保留完整代码和可调参数位置。",
    }]


def _build_fallback_sections(code: str) -> list[dict]:
    lines = code.splitlines() or [""]
    sections = []
    current = None

    def kind_for(line: str) -> tuple[str, str]:
        stripped = line.strip()
        if not stripped:
            return ("blank", "空白分隔")
        if stripped.startswith("#"):
            return ("comment", "注释说明")
        if stripped.startswith(("import ", "from ")):
            return ("import", "依赖导入")
        if stripped.startswith("class "):
            return ("class", "类与模型定义")
        if stripped.startswith(("def ", "async def ")):
            return ("function", "函数流程定义")
        if re.match(r"^[A-Za-z_][\w.]*\s*=", stripped):
            return ("config", "参数与变量配置")
        return ("logic", "执行逻辑")

    for idx, line in enumerate(lines, start=1):
        kind, title = kind_for(line)
        if kind == "blank":
            continue
        if current and current["kind"] == kind and idx - current["end_line"] <= 2:
            current["end_line"] = idx
            continue
        if current:
            sections.append(current)
        current = {"kind": kind, "title": title, "start_line": idx, "end_line": idx}
    if current:
        sections.append(current)

    explanations = {
        "import": "这一段导入脚本后续依赖的库或模块。新手可以先看这里，了解代码后面使用的训练框架、数据工具或辅助函数来自哪里。",
        "comment": "这一段是作者写给读者的说明，用来提示下面代码的用途或分组。它不直接执行，但能帮助理解脚本结构。",
        "config": "这一段集中设置参数或中间变量。可调参数会以高亮输入块显示，修改这些值会影响训练配置、模型规模、路径或运行方式。",
        "class": "这一段定义类，通常用于描述模型结构、数据对象或可复用组件。类本身像模板，后续代码会创建实例并使用它。",
        "function": "这一段定义函数，把一组步骤封装成可重复调用的流程。训练、评估、数据处理等核心逻辑通常会放在函数里。",
        "logic": "这一段执行脚本的实际逻辑，例如创建对象、调用函数、循环训练、计算结果或保存输出。它把前面定义的参数和函数串起来。",
    }
    return [
        {
            "title": s["title"],
            "start_line": s["start_line"],
            "end_line": s["end_line"],
            "explanation": explanations.get(s["kind"], explanations["logic"]),
        }
        for s in sections
    ] or [{
        "title": "脚本代码",
        "start_line": 1,
        "end_line": len(lines),
        "explanation": "这里是完整脚本内容。当前没有可进一步划分的明显结构，因此先作为一个整体展示。",
    }]


def _build_fallback_result(code: str, params: list[dict], error: str) -> dict:
    merged = []
    for param in params:
        fb = _apply_preset_fallback(param)
        merged.append({**param, **{k: v for k, v in fb.items() if k != "name"}})
    return {"params": merged, "fallback": True, "error": error, "sections": _build_fallback_sections(code)}
