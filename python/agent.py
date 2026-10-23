import json
import os
import subprocess
import glob
import re
from typing import Callable, cast, get_args

from dotenv import load_dotenv
from openai import OpenAI
from openai.types.shared.reasoning_effort import ReasoningEffort
from openai.types.responses import FunctionToolParam, ResponseInputItemParam

#--- 初始化 ---
load_dotenv()

def load_param(param: str) -> str:
    result = os.environ.get(param)
    if result is None:
        raise RuntimeError(f"缺少{param}，请到.env中配置\n")
    return result


BASE_URL = load_param("BASE_URL")
API_KEY = load_param("API_KEY")
MODEL = load_param("MODEL_ID")
# ReasoningEffort 是 Literal[...] | None，unwrap 两层拿到全部合法字面量
VALID_EFFORTS = frozenset(get_args(get_args(ReasoningEffort)[0]))

effort = load_param("THINKING_EFFORT")
if effort not in VALID_EFFORTS:
    raise RuntimeError(
        f"THINKING_EFFORT={effort!r} 不合法，必须是 {'/'.join(sorted(VALID_EFFORTS))} 之一，请到.env中配置\n"
    )
EFFORT = cast(ReasoningEffort, effort)

client = OpenAI(
    api_key=API_KEY,
    base_url=BASE_URL,
)

history: list[ResponseInputItemParam]=[{"role": "system", "content": "你是nano_code，一个编码助手。"}]

#--- 工具定义 ---
def run_bash(command: str) -> str:
    proc = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=120)
    output = (proc.stdout + proc.stderr).strip() or "(命令没有输出)"
    return output[:10000] + ("输出已截断前10000字符\n" if len(output) > 10000 else "")

def run_read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        content = f.read()
    if len(content)==0:
        return "空文件"
    return content[:10000] + (("输出已截断前10000字符\n" if len(content) > 10000 else ""))

def run_write(path: str, content: str) -> str:
    with open(path, "w", encoding="utf-8") as f:
        num = f.write(content)
    return f"已写入{path}共{num}字符"

def run_glob(pattern: str) -> str:
    result: list[str] = sorted(glob.glob(pattern, recursive=True))
    if not result:
        return "(没有匹配的文件)"
    return '\n'.join(result[:10000]) + ("输出已截断前10000条\n" if(len(result))>10000 else "")

def run_grep(pattern: str) -> str:
    top_dir = '.'
    result: list[str] = []
    pat = re.compile(pattern, flags=0)
    SKIP_DIRS = {"__pycache__", "node_modules", "venv"}
    for dirpath, dirnames, filenames in os.walk(top_dir):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in SKIP_DIRS]
        for name in filenames:
            full = os.path.join(dirpath, name)
            try:
                with open(full, encoding="utf-8") as f:
                    for line_no, text in enumerate(f,1):
                        match_obj = pat.search(text)
                        if(match_obj):
                            result.append(f"{full}:{line_no}:{text.rstrip('\n')}")
            except (UnicodeDecodeError, OSError):
                continue
    if not result:
        return "未发现匹配的代码行"
    return '\n'.join(result[:10000]) + ("已截断前10000条\n" if(len(result)>10000) else "")

def run_edit(path: str, old_string: str, new_string: str) -> str:
    if not old_string:
        return "被替换字符串不能为空！"
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
        count = content.count(old_string)
        if count == 0:
            return "没有找到目标字符串"
        elif count > 1:
            return "匹配字符串超过1处，请提供更多上下文缩小匹配范围"
        with open(path, "w", encoding="utf-8") as f:
            f.write(content.replace(old_string, new_string, 1))
    except (UnicodeDecodeError):
        return "文件编码不为utf-8"
    except (OSError):
        return "文件打开失败"
    return f"已替换{path}共1处"


TOOL_FUNCS: dict[str, Callable[..., str]] = {
    "bash": run_bash,
    "read": run_read, 
    "write": run_write,
    "glob": run_glob,
    "grep": run_grep,
    "edit": run_edit
    }
TOOLS: list[FunctionToolParam] = [
    {
        "type": "function",
        "name": "bash",
        "description": "在 linux bash shell 中执行命令",
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string", "description": "要执行的 bash 命令"}},
            "required": ["command"],
        },
        "strict": False,
    },
    {
        "type": "function",
        "name": "read",
        "description": "完整读取指定路径的文件",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "要读取文件的路径"}},
            "required": ["path"],
        },
        "strict": False,
    },
    {
        "type": "function",
        "name": "write",
        "description": "向指定路径的文件进行完整的写入，调用 write 工具前必须先对目标文件调用 read 工具",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "要写入文件的路径"},
                "content": {"type": "string", "description": "要写入文件的完整内容"}
            },
            "required": ["path", "content"],
        },
        "strict": False,
    },
    {
        "type": "function",
        "name": "glob",
        "description": "从工作目录的根目录开始，向下递归匹配目标文件。用于查看文件集合",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern":{"type": "string", "description": "glob 通配符模式：* 匹配单层任意字符，** 跨目录匹配，如 **/*.py、src/*.ts"}
            },
            "required": ["pattern"],
        },
        "strict": False,
    },
    {
        "type": "function",
        "name": "grep",
        "description": "从整个仓库中匹配符合目标代码的代码行",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern":{"type": "string", "description": "要匹配的代码，正则表达式"}
            },
            "required": ["pattern"],
        },
        "strict": False,
    },
    {
        "type": "function",
        "name": "edit",
        "description": "对目标文件替换修改部分字符串，在调用 edit 工具之前要先调用 read 工具",
        "parameters": {
            "type": "object",
            "properties": {
                "path":{"type": "string", "description": "目标文件所在位置，如 src/main.py"},
                "old_string":{"type": "string", "description": "被替换的字符串"},
                "new_string":{"type": "string", "description": "替换后的字符串"}
            },
            "required": ["path", "old_string", "new_string"],
        },
        "strict": False,
    },
]

#--- agent循环 ---
while True:
    query = input()
    history.append({"role": "user", "content": query})

    while True:
        response = client.responses.create(
            model=MODEL,
            input=history,
            reasoning={"effort": EFFORT},
            tools=TOOLS,
        )

        history.extend(cast("list[ResponseInputItemParam]", [item.model_dump(exclude_none=True) for item in response.output]))

        calls = [item for item in response.output if item.type == "function_call"]
        if not calls:
            break

        for call in calls:
            print(f"[{call.name}] {call.arguments}")
            try:
                result = TOOL_FUNCS[call.name](**json.loads(call.arguments))
            except Exception as e:
                result = f"工具执行失败: {e}"
            history.append({
                "type": "function_call_output",
                "call_id": call.call_id,
                "output": result,
            })

    print(response.output_text)