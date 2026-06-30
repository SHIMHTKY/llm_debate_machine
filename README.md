# LLM Debate Studio

LLM Debate Studio 是一个面向多模型自动辩论的本地可视化实验平台。你可以为裁判、正方和反方分别配置模型，让两个辩手围绕同一辩题展开多轮辩论，并由裁判模型进行总结评分。

项目目前提供现代化 Web UI、实时辩论流、历史回放、Markdown 记录预览与导出、模型供应商配置、通用工具配置、辩手预设配置、并行辩论、暗色模式、Token 与工具调用统计等功能。

## 主要功能

- 可视化辩论：像聊天界面一样展示正方、反方、裁判和系统消息。
- 多模型配置：裁判、正方、反方均可独立配置模型。
- 供应商管理：统一维护 API Key、Base URL、Azure Deployment、API Version 等供应商信息。
- 辩手配置：辩手只需要选择供应商并填写模型名，可绑定可用工具。
- 工具配置：当前支持 Tavily 搜索工具模板，可创建通用工具后分配给辩手。
- 历史回放：左侧侧边栏保存 simple 会话记录，点击即可回看。
- Markdown 预览：简版、细版、错误日志均可在弹窗中排版预览并导出。
- 并行运行：最多支持 3 场辩论同时运行，互不干扰。
- 过程控制：支持暂停、继续、停止辩论、用户插入发言、指定发送对象、撤回与恢复辩论。
- 统计能力：可选开启正反方 Token 消耗和网络搜索调用次数统计。

## 快速开始

建议使用 Python 3.10 或以上版本。

```powershell
pip install -r requirements.txt
python main.py
```

默认服务地址：

```text
http://127.0.0.1:8000
```

也可以通过环境变量修改监听地址和端口：

```powershell
$env:DEBATE_STUDIO_HOST="127.0.0.1"
$env:DEBATE_STUDIO_PORT="8000"
python main.py
```

## 使用流程

1. 打开页面右上角设置按钮。
2. 在模型与工具配置中创建供应商，填写 API Key、Base URL 或 Azure 相关参数。
3. 在配置工具中创建 Tavily 搜索工具，按需填写工具 Key 和参数。
4. 在配置辩手中创建正方、反方可用的辩手配置，并绑定供应商和工具。
5. 在主页选择正方、反方辩手，填写辩题和轮数范围。
6. 点击开始辩论，等待实时辩论流和裁判总结。
7. 辩论结束后可在回放页预览或导出简版、细版、错误记录。

## 配置与隐私

敏感配置默认保存在本地 `data/settings.json`，该文件已被 `.gitignore` 排除，不会进入 Git 提交。

API Key 在界面中保存后会以黑点形式展示，重新打开设置时不会明文显示，但内部仍会继续生效。清空对应 Key 并保存可删除旧 Key。

运行记录和日志默认保存在：

- `data/debates/`
- `logs/`

这些目录也已被 `.gitignore` 排除，避免误提交历史记录、错误日志或隐私信息。

如果需要清理全部本地记录和隐私配置，可以使用项目根目录的 `factory_reset.bat`。执行前请确认不再需要现有记录。

## 项目结构

```text
llm_debat_machine/
├─ backend/
│  ├─ api/          # FastAPI 接口、会话管理、事件流与运行控制
│  ├─ config/       # 设置读取、归一化、前端配置输出
│  ├─ debate/       # 辩论图、模型创建、提示词、工具、日志与统计
│  └─ storage/      # 会话、记录、导出与归档存储
├─ frontend/
│  ├─ app.js        # 前端交互逻辑
│  ├─ index.html    # 页面结构
│  ├─ styles.css    # UI 样式
│  ├─ workspace.md  # 首页工作区说明与更新日志
│  └─ Notice.txt    # 设置页须知内容
├─ data/            # 本地配置与辩论记录，默认不提交
├─ logs/            # 运行日志，默认不提交
├─ factory_reset.bat
├─ main.py
└─ requirements.txt
```

## 开发说明

前端是原生 HTML、CSS、JavaScript，不依赖构建工具。修改 `frontend/app.js` 或 `frontend/styles.css` 后，建议同步更新 `frontend/index.html` 中资源版本号，避免浏览器缓存旧文件。

后端使用 FastAPI、LangGraph、LangChain OpenAI 相关组件。辩论运行通过后端会话管理器调度，前端通过 SSE 接收实时事件。

## 注意事项

- 请勿提交 `.env`、`data/settings.json`、`data/debates/`、`logs/` 等包含隐私或运行数据的文件。
- 如果使用 Azure 模型，需要正确配置 `azure_deployment` 和 `api_version`。
- 如果使用兼容 OpenAI 的网关，请在供应商中选择 ChatOpenAI 并填写兼容的 Base URL。
- 部分模型的思考模式需要通过 ChatOpenAI 的 `extra_body` 配置，例如 `{"enable_thinking": true}`。
- 网络搜索调用依赖 Tavily API Key，未配置或未绑定工具时工具调用次数会显示为 0。
