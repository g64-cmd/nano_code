import os
from typing import cast, get_args

from dotenv import load_dotenv
from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam
from openai.types.shared.reasoning_effort import ReasoningEffort

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
EFFORT = cast(ReasoningEffort, effort)  # 已运行时校验，cast 只是告诉类型检查器

client = OpenAI(
    api_key=API_KEY,
    base_url=BASE_URL,
)

history: list[ChatCompletionMessageParam]=[{"role": "system", "content": "你是nano_code，你一个编码助手。"}]

while True:
    query = input()
    history.append({"role": "user", "content": query})

    response = client.chat.completions.create(
        model=MODEL,
        messages=history,
        stream=False,
        reasoning_effort=EFFORT,
        extra_body={"thinking": {"type": "enabled"}},
    )

    reply = response.choices[0].message.content
    history.append({"role": "assistant", "content": reply})
    print(reply)