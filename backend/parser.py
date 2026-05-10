# Python 3.10+ required (uses ast.Constant for True/False/None)
"""AST-based Python parameter extractor for ML scripts."""

import ast
import re
from typing import Any

# Common ML parameters with built-in presets
COMMON_PARAMS: dict[str, dict] = {
    "lr": {"range": [1e-6, 1.0], "default": 0.001, "desc": "学习率", "group": "训练参数"},
    "learning_rate": {"alias": "lr"},
    "epochs": {"range": [1, 1000], "default": 100, "desc": "训练轮数", "group": "训练参数"},
    "num_epochs": {"alias": "epochs"},
    "n_epochs": {"alias": "epochs"},
    "batch_size": {"range": [1, 1024], "default": 32, "options": [8, 16, 32, 64, 128, 256], "desc": "批大小", "group": "训练参数"},
    "dropout": {"range": [0.0, 0.9], "default": 0.5, "desc": "Dropout 比率", "group": "模型结构"},
    "weight_decay": {"range": [0.0, 0.1], "default": 0.01, "desc": "权重衰减", "group": "训练参数"},
    "hidden_size": {"range": [16, 4096], "default": 256, "desc": "隐藏层大小", "group": "模型结构"},
    "hidden_dim": {"alias": "hidden_size"},
    "num_layers": {"range": [1, 100], "default": 3, "desc": "层数", "group": "模型结构"},
    "n_layers": {"alias": "num_layers"},
    "max_seq_len": {"range": [16, 8192], "default": 512, "desc": "最大序列长度", "group": "数据设置"},
    "max_length": {"alias": "max_seq_len"},
    "seq_len": {"alias": "max_seq_len"},
    "seed": {"range": [0, 2**31], "default": 42, "desc": "随机种子", "group": "其他"},
    "random_seed": {"alias": "seed"},
    "test_size": {"range": [0.01, 0.5], "default": 0.2, "desc": "测试集比例", "group": "数据设置"},
    "val_size": {"range": [0.01, 0.5], "default": 0.1, "desc": "验证集比例", "group": "数据设置"},
    "n_estimators": {"range": [1, 10000], "default": 100, "desc": "树的数量（随机森林等）", "group": "模型结构"},
    "max_depth": {"range": [1, 100], "default": None, "desc": "最大深度", "group": "模型结构"},
    "optimizer": {"options": ["adam", "sgd", "adamw", "rmsprop"], "desc": "优化器", "group": "训练参数"},
    "scheduler": {"options": ["step", "cosine", "plateau", "none"], "desc": "学习率调度器", "group": "训练参数"},
    "activation": {"options": ["relu", "gelu", "tanh", "sigmoid"], "desc": "激活函数", "group": "模型结构"},
    "loss": {"options": ["cross_entropy", "mse", "mae", "bce"], "desc": "损失函数", "group": "训练参数"},
    "loss_fn": {"alias": "loss"},
    "criterion": {"alias": "loss"},
    "num_workers": {"range": [0, 32], "default": 4, "desc": "数据加载线程数", "group": "数据设置"},
    "n_workers": {"alias": "num_workers"},
    "patience": {"range": [1, 100], "default": 10, "desc": "早停耐心值", "group": "训练参数"},
    "early_stopping_patience": {"alias": "patience"},
    "max_grad_norm": {"range": [0.1, 10.0], "default": 1.0, "desc": "梯度裁剪阈值", "group": "训练参数"},
    "clip_grad": {"alias": "max_grad_norm"},
    "temperature": {"range": [0.01, 10.0], "default": 1.0, "desc": "温度参数", "group": "模型结构"},
    "top_k": {"range": [1, 1000], "default": 50, "desc": "Top-K 采样", "group": "模型结构"},
    "top_p": {"range": [0.0, 1.0], "default": 0.9, "desc": "Top-P 采样", "group": "模型结构"},
    "embedding_dim": {"range": [16, 4096], "default": 128, "desc": "嵌入维度", "group": "模型结构"},
    "embed_dim": {"alias": "embedding_dim"},
    "vocab_size": {"range": [100, 500000], "default": 30000, "desc": "词表大小", "group": "模型结构"},
    "num_heads": {"range": [1, 64], "default": 8, "desc": "注意力头数", "group": "模型结构"},
    "n_heads": {"alias": "num_heads"},
    "dim_feedforward": {"range": [64, 16384], "default": 2048, "desc": "前馈网络维度", "group": "模型结构"},
    "ffn_dim": {"alias": "dim_feedforward"},
    "learning_rate_step": {"range": [1, 1000], "default": 30, "desc": "学习率衰减步数", "group": "训练参数"},
    "step_size": {"range": [1, 1000], "default": 30, "desc": "学习率调度步长", "group": "训练参数"},
    "gamma": {"range": [0.01, 1.0], "default": 0.1, "desc": "学习率衰减因子", "group": "训练参数"},
    "momentum": {"range": [0.0, 1.0], "default": 0.9, "desc": "动量", "group": "训练参数"},
    "alpha": {"range": [0.0, 10.0], "default": 0.99, "desc": "Alpha 参数", "group": "其他"},
    "eps": {"range": [1e-10, 1e-2], "default": 1e-8, "desc": "Epsilon 参数", "group": "其他"},
}


# M2/M5: Build resolved alias map without mutating COMMON_PARAMS
def _build_resolved_params() -> dict[str, dict]:
    resolved = {}
    for name, cfg in COMMON_PARAMS.items():
        if "alias" in cfg:
            target = cfg["alias"]
            if target in COMMON_PARAMS and "alias" not in COMMON_PARAMS[target]:
                resolved[name] = {**COMMON_PARAMS[target], "alias_of": target}
            else:
                resolved[name] = cfg
        else:
            resolved[name] = cfg
    return resolved


_RESOLVED_PARAMS = _build_resolved_params()


def _get_preset(name: str) -> dict | None:
    """Get preset for a param name, resolving aliases."""
    p = _RESOLVED_PARAMS.get(name)
    if p and "alias" not in p:
        return p
    return None


# M1: Extracted helper to apply preset data to a param dict
def _apply_preset(param: dict, name: str) -> None:
    """Mutate param dict in-place with preset data if available."""
    preset = _get_preset(name)
    if preset:
        param["range"] = preset.get("range")
        param["group"] = preset.get("group", "其他")
        param["presetDesc"] = preset.get("desc")
        if "options" in preset and "options" not in param:
            param["options"] = preset["options"]


# M3: Stricter path detection — require path-like structure
_PATH_PATTERN = re.compile(
    r"""(?:^\.?\.?/)|(?:^~)|(?:^[A-Za-z]:\\)|(?:\.(?:csv|json|yaml|yml|txt|pkl|pt|pth|h5|npy|npz|parquet|tsv|pem|key|cfg|ini|conf)$)"""
)


def _is_path_string(value: str) -> bool:
    return bool(_PATH_PATTERN.search(value))


def _is_constant_name(name: str) -> bool:
    return name.isupper() and len(name) > 1


def _extract_value(node: ast.expr) -> Any:
    """Extract a Python literal value from an AST node."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        val = _extract_value(node.operand)
        return -val if val is not None else None
    if isinstance(node, ast.List):
        return [_extract_value(elt) for elt in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_extract_value(elt) for elt in node.elts)
    if isinstance(node, ast.Dict):
        return {
            _extract_value(k): _extract_value(v)
            for k, v in zip(node.keys, node.values)
            if k is not None
        }
    return None


def _get_type_hint(value: Any, name: str) -> str:
    """Infer parameter type from value and name."""
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        if _is_path_string(value) or any(
            kw in name.lower() for kw in ("path", "dir", "file", "folder", "root")
        ):
            return "path"
        return "string"
    if isinstance(value, (list, tuple)):
        return "list"
    return "string"


def _line_col_from_node(node: ast.expr, source_lines: list[str]) -> tuple[int, int, int, int]:
    """Get start/end line/col for a value node (1-indexed)."""
    start_line = node.lineno
    start_col = node.col_offset
    end_line = getattr(node, "end_lineno", node.lineno)
    end_col = getattr(node, "end_col_offset", node.col_offset + 1)
    return start_line, start_col, end_line, end_col


def _extract_argparse_params(node: ast.Call, source_lines: list[str]) -> list[dict]:
    """Extract parameters from parser.add_argument() calls."""
    params = []
    if not isinstance(node.func, ast.Attribute) or node.func.attr != "add_argument":
        return params

    # Get the flag name from first positional arg
    flag_name = None
    if node.args and isinstance(node.args[0], ast.Constant):
        flag_name = node.args[0].value
    if not flag_name:
        return params

    # Clean flag name: --learning-rate -> learning_rate
    clean_name = flag_name.lstrip("-").replace("-", "_")

    kwargs = {}
    for kw in node.keywords:
        kwargs[kw.arg] = _extract_value(kw.value)

    default = kwargs.get("default")
    choices = kwargs.get("choices")
    arg_type = kwargs.get("type")
    help_text = kwargs.get("help", "")
    action = kwargs.get("action")

    # H4: Handle store_true/store_false boolean flags
    if action in ("store_true", "store_false"):
        default_val = action == "store_false"
        param = {
            "name": clean_name,
            "value": default_val,
            "originalText": repr(default_val),
            "type": "bool",
            "line": node.lineno,
            "col": node.col_offset,
            "endLine": getattr(node, "end_lineno", node.lineno),
            "endCol": getattr(node, "end_col_offset", node.col_offset + 1),
            "source": "argparse",
            "flag": flag_name,
            "group": "其他",
        }
        _apply_preset(param, clean_name)
        if help_text:
            param["helpText"] = help_text
        params.append(param)
        return params

    # Infer type
    param_type = "string"
    if arg_type:
        if isinstance(arg_type, ast.Name):
            type_name = arg_type.id
            if type_name in ("int", "float", "bool", "str"):
                param_type = type_name
    elif default is not None:
        param_type = _get_type_hint(default, clean_name)

    # Build result
    param = {
        "name": clean_name,
        "value": default,
        "originalText": repr(default) if default is not None else "None",
        "type": param_type,
        "line": node.lineno,
        "col": node.col_offset,
        "endLine": getattr(node, "end_lineno", node.lineno),
        "endCol": getattr(node, "end_col_offset", node.col_offset + 1),
        "source": "argparse",
        "flag": flag_name,
        "group": "其他",
    }

    if choices:
        param["type"] = "select"
        param["options"] = choices if isinstance(choices, list) else None
    else:
        param["type"] = param_type

    # M1: Use shared preset helper
    _apply_preset(param, clean_name)

    if help_text:
        param["helpText"] = help_text

    params.append(param)
    return params


def _extract_dict_params(
    node: ast.Dict, prefix: str, source_lines: list[str]
) -> list[dict]:
    """Recursively extract parameters from a dict literal."""
    params = []
    for key, value in zip(node.keys, node.values):
        if not isinstance(key, ast.Constant):
            continue
        key_name = str(key.value)
        full_name = f"{prefix}.{key_name}" if prefix else key_name
        val = _extract_value(value)

        if isinstance(value, ast.Dict):
            params.extend(_extract_dict_params(value, full_name, source_lines))
        elif val is not None:
            param_type = _get_type_hint(val, key_name)
            start_line, start_col, end_line, end_col = _line_col_from_node(value, source_lines)
            param = {
                "name": full_name,
                "value": val,
                "originalText": ast.get_source_segment(
                    "\n".join(source_lines), value
                )
                or repr(val),
                "type": param_type,
                "line": start_line,
                "col": start_col,
                "endLine": end_line,
                "endCol": end_col,
                "source": "dict",
                "group": "其他",
            }
            # M1: Use shared preset helper
            _apply_preset(param, key_name)
            params.append(param)
    return params


def parse_code(code: str) -> dict:
    """
    Parse Python code and extract potential tunable parameters.
    Returns { params: [...], errors: [...], source_lines: [...] }
    """
    source_lines = code.splitlines()
    params = []
    errors = []

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        errors.append(f"Syntax error: {e}")
        return {"params": [], "errors": errors, "source_lines": source_lines}

    param_id = 0

    for node in ast.walk(tree):
        # --- Direct assignment: x = value ---
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    name = target.id
                    val = _extract_value(node.value)

                    if val is None:
                        if isinstance(node.value, ast.Call):
                            pass  # handled below
                        continue

                    # M10: Lower confidence for UPPER_CASE constants
                    is_const = _is_constant_name(name)

                    param_type = _get_type_hint(val, name)
                    start_line, start_col, end_line, end_col = _line_col_from_node(
                        node.value, source_lines
                    )
                    original_text = (
                        ast.get_source_segment(code, node.value) or repr(val)
                    )

                    is_local = node.col_offset > 0
                    param = {
                        "name": name,
                        "value": val,
                        "originalText": original_text,
                        "type": param_type,
                        "line": start_line,
                        "col": start_col,
                        "endLine": end_line,
                        "endCol": end_col,
                        "source": "assign",
                        "scope": "module" if not is_local else "local",
                        "group": "其他",
                    }

                    if is_const:
                        param["confidence"] = 0.4  # M10: lower confidence for constants
                    elif is_local:
                        param["confidence"] = 0.3  # lower confidence for local scope variables

                    # Check if it's a dict literal → recurse
                    if isinstance(node.value, ast.Dict):
                        dict_params = _extract_dict_params(
                            node.value, name, source_lines
                        )
                        for dp in dict_params:
                            param_id += 1
                            dp["id"] = f"param_{param_id}"
                            params.append(dp)
                        continue

                    # M1: Use shared preset helper
                    _apply_preset(param, name)

                    param_id += 1
                    param["id"] = f"param_{param_id}"
                    params.append(param)

                # Tuple unpacking: (a, b) = (1, 2)
                elif isinstance(target, ast.Tuple) and isinstance(node.value, ast.Tuple):
                    for i, (t, v) in enumerate(zip(target.elts, node.value.elts)):
                        if isinstance(t, ast.Name):
                            val = _extract_value(v)
                            if val is None:
                                continue
                            start_line, start_col, end_line, end_col = _line_col_from_node(v, source_lines)
                            original_text = ast.get_source_segment(code, v) or repr(val)
                            param_id += 1
                            params.append({
                                "id": f"param_{param_id}",
                                "name": t.id,
                                "value": val,
                                "originalText": original_text,
                                "type": _get_type_hint(val, t.id),
                                "line": start_line,
                                "col": start_col,
                                "endLine": end_line,
                                "endCol": end_col,
                                "source": "assign",
                                "scope": "module" if node.col_offset == 0 else "local",
                                "group": "其他",
                            })

        # --- Annotated assignment: x: float = 0.01 ---
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.value is None:
                continue
            name = node.target.id
            val = _extract_value(node.value)
            if val is None:
                continue

            start_line, start_col, end_line, end_col = _line_col_from_node(
                node.value, source_lines
            )
            original_text = ast.get_source_segment(code, node.value) or repr(val)
            param_type = _get_type_hint(val, name)

            # Try to get type from annotation
            if isinstance(node.annotation, ast.Name):
                ann = node.annotation.id
                if ann in ("int", "float", "bool", "str"):
                    param_type = ann

            param_id += 1
            param = {
                "id": f"param_{param_id}",
                "name": name,
                "value": val,
                "originalText": original_text,
                "type": param_type,
                "line": start_line,
                "col": start_col,
                "endLine": end_line,
                "endCol": end_col,
                "source": "annotated_assign",
                "scope": "module" if node.col_offset == 0 else "local",
                "group": "其他",
            }
            # M1: Use shared preset helper
            _apply_preset(param, name)
            params.append(param)

        # --- Function default args ---
        elif isinstance(node, ast.FunctionDef):
            defaults = node.args.defaults
            args_with_defaults = node.args.args[-len(defaults):] if defaults else []
            for arg, default in zip(args_with_defaults, defaults):
                val = _extract_value(default)
                if val is None:
                    continue
                start_line, start_col, end_line, end_col = _line_col_from_node(default, source_lines)
                original_text = ast.get_source_segment(code, default) or repr(val)
                param_id += 1
                param = {
                    "id": f"param_{param_id}",
                    "name": arg.arg,
                    "value": val,
                    "originalText": original_text,
                    "type": _get_type_hint(val, arg.arg),
                    "line": start_line,
                    "col": start_col,
                    "endLine": end_line,
                    "endCol": end_col,
                    "source": "function_default",
                    "scope": "local",
                    "group": "其他",
                }
                # M1: Use shared preset helper
                _apply_preset(param, arg.arg)
                params.append(param)

        # --- argparse add_argument ---
        elif isinstance(node, ast.Call):
            arg_params = _extract_argparse_params(node, source_lines)
            for p in arg_params:
                param_id += 1
                p["id"] = f"param_{param_id}"
                params.append(p)

    # Deduplicate by (name, source, line, col, endLine, endCol)
    seen = set()
    unique_params = []
    for p in params:
        key = (p["name"], p.get("source", ""), p["line"], p["col"], p["endLine"], p["endCol"])
        if key not in seen:
            seen.add(key)
            unique_params.append(p)

    return {"params": unique_params, "errors": errors, "source_lines": source_lines}
