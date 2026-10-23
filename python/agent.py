import json
import os
import subprocess
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

history: list[ResponseInputItemParam]=[{"role": "system", "content": "你是nano_code，你一个编码助手。"}]

#--- 工具定义 ---
def bash(command: str) -> str:
    proc = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=120)
    output = (proc.stdout + proc.stderr).strip() or "(命令没有输出)"
    return output[:10000] + ("\n...(输出过长已截断)" if len(output) > 10000 else "")

def read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        content = f.read()
    f.close()
    if len(content)==0:
        return "空文件"
    return content[:10000] + (("\n...(内容过长已截断)" if len(content) > 10000 else ""))

def write(path: str, content: str) -> str:
    with open(path, "w", encoding="utf-8") as f:
        num = f.write(content)
    f.close()
    return f"已写入{path}共{num}字符"



TOOL_FUNCS: dict[str, Callable[..., str]] = {"bash": bash, "read": read, "write": write}
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
    }
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