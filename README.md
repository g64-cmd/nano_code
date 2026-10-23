# nano_code

一个极简的**编码代理（Coding Agent）**内核实现：用几十行 Python 代码，把大模型包装成一个能够**执行命令、读写文件**的命令行助手。

本 README 主要介绍 `python/agent.py`，由 nano_code 创建。

## 项目简介

`agent.py` 是一个最小可用的 Agent 循环（Agent Loop）：

1. 读取用户输入，追加到对话历史；
2. 把历史与**工具定义**一起发给大模型；
3. 若模型返回 `function_call`，本地执行对应工具（bash / read / write），把结果写回历史，继续下一次请求；
4. 直到模型不再调用工具，打印最终回答，等待下一轮输入。

它不依赖 LangChain、LlamaIndex 等任何 Agent 框架，只依赖 `openai` SDK（使用 OpenAI Responses API 协议），因此可以对接任何**兼容 OpenAI 协议**的服务（如 DeepSeek、vLLM、Ollama 等）。

## 功能特性

- **无框架**：核心逻辑不到 100 行，便于阅读和二次开发；
- **OpenAI Responses API**：使用 `client.responses.create()`，支持 `reasoning.effort` 思考强度控制；
- **三个内置工具**：
  | 工具 | 说明 |
  | --- | --- |
  | `bash` | 在 Linux shell 中执行命令，合并 stdout/stderr 返回，超时 120 秒，输出上限 10000 字符 |
  | `read` | 完整读取指定文件（UTF-8），空文件返回提示，内容超过 10000 字符时截断 |
  | `write` | 向指定路径完整写入文件，返回写入字符数 |
- **上下文保护**：工具输出做了长度截断，避免单次结果撑爆上下文；
- **错误兜底**：工具执行异常会被捕获，并以 `工具执行失败: ...` 的形式回传给模型，Agent 循环不会崩溃；
- **配置校验**：启动时检查 `.env` 中的必填项，并对 `THINKING_EFFORT` 做合法值校验。

## 目录结构

```
nano_code/
├── python/
│   ├── agent.py          # Agent 内核
│   ├── .env.example      # 配置模板
│   └── .env              # 本地配置（已被 .gitignore 忽略）
├── typescript/           # 预留（TypeScript 版本）
├── LICENSE
└── README.md
```

## 环境要求

- Python 3.10+（`python/agent.py` 使用 `list[...]`、`dict[...]` 等现代类型注解，py3.14 下已验证）
- 一个兼容 OpenAI Responses API 的模型服务

## 快速开始

### 1. 安装依赖

```bash
cd python
python -m venv .venv
source .venv/bin/activate
pip install openai python-dotenv
```

### 2. 配置环境变量

复制模板并填写：

```bash
cp .env.example .env
```

| 变量 | 说明 |
| --- | --- |
| `BASE_URL` | API 地址，例如 `https://api.deepseek.com` |
| `API_KEY` | API 密钥 |
| `MODEL_ID` | 模型名称，例如 `deepseek-flash` |
| `THINKING_EFFORT` | 思考强度，取值为 `ReasoningEffort` 的合法字面量（如 `low` / `medium` / `high` 等，具体以所用模型服务为准） |

### 3. 运行

```bash
python agent.py
```

在终端输入问题后回车即可。工具调用过程会打印在终端：

```
[read] {"path": "python/agent.py"}
[write] {"path": "README.md", "content": "..."}
```

最后输出模型的最终回答。按 `Ctrl+C` 退出。

## 工作原理

```
用户输入
   │
   ▼
history += user message
   │
   ▼
┌──────────────────────────────┐
│ responses.create(            │
│   model, input=history,      │
│   reasoning={effort},        │
│   tools=TOOLS)               │
└──────────────────────────────┘
   │
   ├── 有 function_call ?
   │      │ 是
   │      ▼
   │   history += 模型输出
   │   本地执行工具
   │   history += function_call_output
   │      └── 回到上一步（继续请求）
   │
   └── 否 → 打印 output_text，等待下一轮用户输入
```

关键点：

- `history` 是一个 `list[ResponseInputItemParam]`，保存完整的对话与工具调用链路；
- 模型的输出项通过 `model_dump(exclude_none=True)` 转成 dict 后并入历史，便于后续请求回放；
- 工具的真实执行函数与给模型看的 `TOOLS` 定义通过名字在 `TOOL_FUNCS` 字典中对应。

## 扩展方式

新增一个工具只需两步：

1. 实现函数并注册：

   ```python
   def grep(pattern: str, path: str) -> str:
       ...

   TOOL_FUNCS["grep"] = grep
   ```

2. 在 `TOOLS` 中补充对应的 JSON Schema 定义（`name` / `description` / `parameters`）。

## 已知限制

- 工具输出上限 10000 字符，长文件/长日志会被截断；
- 无对话历史持久化，进程退出后上下文丢失；
- 无命令执行的安全沙箱与人工确认机制，请在受信任环境中使用，**避免在重要目录下运行**；
- `bash` 工具使用 `shell=True`，模型生成的命令会被直接执行，请注意风险。

## License

MIT，详见 [LICENSE](LICENSE)。
