# nano_code

一个极简的**编码代理（Coding Agent）**内核实现：用两百多行 Python 代码（`python/agent.py`，226 行），把大模型包装成一个能够**执行命令、读写文件、检索代码、局部改代码**的命令行助手。

它不依赖 LangChain、LlamaIndex 等任何 Agent 框架，只依赖 `openai` SDK（使用 OpenAI Responses API 协议），因此可以对接任何**兼容 OpenAI 协议**的服务（如 DeepSeek、vLLM、Ollama 等）。

## 项目简介

`agent.py` 是一个最小可用的 Agent 循环（Agent Loop）：

1. 读取用户输入，追加到对话历史；
2. 把历史与**工具定义**一起发给大模型；
3. 若模型返回 `function_call`，本地执行对应工具（bash / read / write / glob / grep / edit），把结果写回历史，继续下一次请求；
4. 直到模型不再调用工具，打印最终回答，等待下一轮输入。

## 功能特性

- **无框架**：核心逻辑两百余行，便于阅读和二次开发；
- **OpenAI Responses API**：使用 `client.responses.create()`，支持 `reasoning.effort` 思考强度控制；
- **六个内置工具**：

  | 工具 | 参数 | 说明 |
  | --- | --- | --- |
  | `bash` | `command` | 在 Linux shell 中执行命令（`shell=True`），合并 stdout/stderr 并 strip，超时 120 秒；无输出时返回 `(命令没有输出)`，超过 10000 字符时截断并附加提示 |
  | `read` | `path` | 以 UTF-8 完整读取指定文件；空文件返回 `空文件`，超过 10000 字符时截断并附加提示 |
  | `write` | `path`、`content` | 向指定路径**整文件覆盖写入**（UTF-8），返回 `已写入{path}共{n}字符`；父目录不存在时会失败 |
  | `glob` | `pattern` | 以 `glob.glob(pattern, recursive=True)` 从当前工作目录递归匹配文件，结果按字典序排序；无匹配返回 `(没有匹配的文件)`，最多返回 10000 条并附加截断提示 |
  | `grep` | `pattern` | 从当前工作目录递归搜索匹配正则的行，输出 `路径:行号:内容`；跳过隐藏目录与 `__pycache__` / `node_modules` / `venv`，非 UTF-8 或读取失败的文件静默跳过；无匹配返回 `未发现匹配的代码行`，最多返回 10000 条并附加截断提示 |
  | `edit` | `path`、`old_string`、`new_string` | 对文件做**整文件读入 → 唯一匹配替换 → 写回**，要求 `old_string` 在文件中恰好出现一次 |

- **上下文保护**：工具输出做了长度/条数截断，避免单次结果撑爆上下文；
- **错误兜底**：工具执行异常（含 `bash` 超时、路径不存在等）会被捕获，并以 `工具执行失败: ...` 的形式回传给模型，Agent 循环不会崩溃；
- **配置校验**：启动时检查 `.env` 中的必填项，并对 `THINKING_EFFORT` 做合法值校验（取值集合从 `ReasoningEffort` 类型中反射得到，无需硬编码）。

### `edit` 的各类返回

| 情况 | 返回 |
| --- | --- |
| 成功替换 1 处 | `已替换{path}共1处` |
| `old_string` 为空 | `被替换字符串不能为空！` |
| 文件中找不到 `old_string` | `没有找到目标字符串` |
| `old_string` 出现多次 | `匹配字符串超过1处，请提供更多上下文缩小匹配范围` |
| 文件不是 UTF-8 | `文件编码不为utf-8` |
| 文件打不开（不存在/无权限） | `文件打开失败` |

## 目录结构

```
nano_code/
├── python/
│   ├── agent.py          # Agent 内核（唯一源码）
│   ├── .env.example      # 配置模板
│   └── .env              # 本地配置（已被 .gitignore 忽略）
├── typescript/           # 预留（TypeScript 版本，暂无代码）
├── LICENSE
└── README.md
```

运行后产生的 `.venv/`、`__pycache__/`等均已列入 `.gitignore`（见文件内容），不会入库。

## 环境要求

- Python 3.10+（`python/agent.py` 使用 `list[...]`、`str | None` 等现代类型注解）
- 依赖：`openai`、`python-dotenv`
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
| `THINKING_EFFORT` | 思考强度，取值来自 `ReasoningEffort` 字面量 |

缺项时抛出 `RuntimeError: 缺少{变量名}，请到.env中配置`；`THINKING_EFFORT` 非法时抛出 `RuntimeError` 并列出全部合法值。当前 `openai` SDK 中的合法值集合为：`high` / `low` / `max` / `medium` / `minimal` / `none` / `xhigh`（以实际安装版本为准，程序会自动反射获取，不做硬编码）。

### 3. 运行

工具路径均相对于**当前工作目录**，因此建议在仓库根目录启动：

```bash
cd nano_code
python python/agent.py
```

（在 `python/` 目录下 `python agent.py` 也能正常读到 `.env`，但此时 `glob` / `grep` / 相对路径的 `read` 都会以 `python/` 为根，看不到整个仓库。）

在终端输入问题后回车即可。工具调用过程会打印在终端（格式为 `[工具名] 参数JSON`）：

```
[read] {"path": "README.md"}
[glob] {"pattern": "**/*.py"}
[grep] {"pattern": "def run_"}
[edit] {"path": "README.md", "old_string": "超时 120 秒", "new_string": "超时 60 秒"}
[write] {"path": "README.md", "content": "..."}
```

最后输出模型的最终回答。输入读到空行也会照常发给模型；按 `Ctrl+C` 退出（`Ctrl+D` 会抛未捕获的 `EOFError`，同样会终止进程）。

## 工作原理

```
用户输入 input()
   │
   ▼
history += {"role": "user", "content": query}
   │
   ▼
┌────────────────────────────────────┐
│ client.responses.create(           │
│   model=MODEL,                     │
│   input=history,                   │
│   reasoning={"effort": EFFORT},    │
│   tools=TOOLS)                     │
└────────────────────────────────────┘
   │
   ▼  history += response.output（model_dump(exclude_none=True)）
   │
   ├── 有 function_call ?
   │      │ 是：逐个执行
   │      ▼
   │   print("[name] arguments")
   │   TOOL_FUNCS[name](**json.loads(arguments))
   │   （异常 → "工具执行失败: {e}"）
   │   history += function_call_output(call_id, output)
   │      └── 回到 create()（继续请求）
   │
   └── 否 → print(response.output_text)，回到最外层等待下一次输入
```

关键点：

- `history` 是 `list[ResponseInputItemParam]`，启动时先放入一条 system prompt（`你是nano_code，一个编码助手。`），之后保存完整的对话与工具调用链路；
- 模型的输出项通过 `model_dump(exclude_none=True)` 转成 dict 后并入历史，便于后续请求回放；
- 工具的真实执行函数（`run_*`）与给模型看的 `TOOLS` 定义通过名字在 `TOOL_FUNCS` 字典中对应；
- 一次响应可能返回多个 `function_call`，循环会逐个执行并各自回写结果。

## 扩展方式

新增一个工具只需两步（下面以新增一个文件统计工具为例）：

1. 实现函数，并注册到 `TOOL_FUNCS`：

   ```python
   def run_stat(path: str) -> str:
       with open(path, encoding="utf-8") as f:
           lines = sum(1 for _ in f)
       return f"{path}: {lines} 行"
   ```

   ```python
   TOOL_FUNCS = {
       # ...
       "stat": run_stat,
   }
   ```

2. 在 `TOOLS` 中补充对应的 JSON Schema 定义（`name` / `description` / `parameters`），`name` 需与 `TOOL_FUNCS` 的键一致：

   ```python
   {
       "type": "function",
       "name": "stat",
       "description": "统计指定文件的行数",
       "parameters": {
           "type": "object",
           "properties": {"path": {"type": "string", "description": "目标文件路径"}},
           "required": ["path"],
       },
       "strict": False,
   },
   ```

返回值必须是字符串；抛出异常也可以，会被统一包装成 `工具执行失败: ...` 回传给模型。

## 已知限制

- 单次工具输出有上限：`bash` / `read` 为 10000 字符，`glob` / `grep` 为 10000 条记录，长文件或大范围搜索结果会被截断（截断提示文本本身就是拼接在结果末尾的）；
- `glob` 遵循 Python `glob` 语义，默认不匹配以 `.` 开头的隐藏文件（需要时请显式写出模式，如 `.env*`）；`grep` 只跳过隐藏**目录**，隐藏文件仍会被搜索；
- `grep` 固定从当前工作目录开始搜索，不接受路径参数，仅内置跳过隐藏目录、`__pycache__`、`node_modules`、`venv`，没有自定义忽略规则，也不支持 flags/大小写等选项；非 UTF-8 文件会被静默跳过；
- `edit` 只做纯文本替换：`old_string` 必须唯一匹配，不支持正则、不支持按行号定位、也不支持一次替换多处；实现上是「整文件读入 → 字符串替换 → 整文件写回」，因此会重写整个文件（文件属性如权限位基本保留，但换行符、BOM 等不做特殊处理）；
- `read` / `write` / `edit` 只按 UTF-8 处理文本，遇到非 UTF-8 文件时 `read` 会抛出异常（回传 `工具执行失败: ...`），`edit` 则返回 `文件编码不为utf-8`；
- `write` / `edit` 不会自动创建父目录，跨目录新建文件需要先 `bash` 建目录；
- 工具没有严格的调用顺序约束：`write` / `edit` 前应先 `read`，这只是写在工具描述里靠模型自觉，运行时并不强制；
- 无对话历史持久化，进程退出后上下文丢失；
- 输入使用裸 `input()`，没有提示符；`Ctrl+D`（EOF）未被捕获；
- 无命令执行的安全沙箱与人工确认机制，`bash` 使用 `shell=True` 直接执行模型生成的命令，请在受信任环境中使用，**避免在重要目录下运行**。

## License

MIT，详见 [LICENSE](LICENSE)。
