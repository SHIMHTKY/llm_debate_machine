# 前端工作台设计与验收

## 设计方向

参考 [IBM Carbon 的 UI Shell](https://carbondesignsystem.com/components/UI-shell-left-panel/usage/) 和 [Vercel Geist](https://vercel.com/geist/introduction) 的导航与信息层级，采用连续分栏、细线分隔、小字号和明确的操作色。没有引入这两个库的运行时依赖。

- 浅色使用灰白底和蓝色操作色；暗色使用蓝黑底，正文和次要文字分别设置对比色。
- 容器使用直角，输入和按钮最多 2px 圆角。详情切换按钮仍保留圆形，以延续原有功能约定。
- 主页为最大 1040px 的居中创建区：辩题全宽、双方模型并排、轮数与启动操作同排；窄屏纵向排列。移除常驻说明栏，更新记录改为按钮弹窗，按需读取 `workspace.md` 的更新日志部分。
- 桌面历史侧栏可收起，使用浏览器本地存储记住状态；不超过 720px 时变为独立抽屉，不覆盖桌面偏好。低于 620px 的短屏配置页退为整体滚动，避免子面板不可达。
- 不引入远程字体，英文优先使用本地 Bahnschrift，中文保留系统中文字体，技术标签使用等宽字体。
- 动效用于侧栏宽度与滑移、遮罩淡入淡出、颜色切换、弹窗进入和新消息出现，尊重 `prefers-reduced-motion`。刷新恢复侧栏状态时不播放动画。

## 文件职责

| 文件 | 职责 |
| --- | --- |
| `frontend/index.html` | 固定结构及资源版本号 |
| `frontend/styles.css` | 五个样式模块的版本化入口 |
| `frontend/styles/foundation.css` | 主题变量、基础控件与动效 |
| `frontend/styles/workspace.css` | 外壳、历史、主页和响应式抽屉 |
| `frontend/styles/conversation.css` | 实时发言、输入、回放与评议 |
| `frontend/styles/configuration.css` | 设置、供应商/工具/辩手和积木编辑 |
| `frontend/styles/dialogs.css` | 弹窗、Markdown、调用详情和任务条 |
| `frontend/shell.js` | 抽屉、键盘导航、弹窗焦点与背景隔离 |
| `frontend/motion.js` | 可中断弹窗与提示条动效、轻量入场、减少动态效果响应 |
| `frontend/app.js` | 业务状态、API 交互与更新记录按需加载 |

资源版本统一为 `20260928-motion-4`。后续改动应同时更新 HTML 和 CSS import URL 的版本。

## 隔离验收

在项目目录执行：

```powershell
python tests/frontend_preview.py --port 18766
python tests/frontend_preview.py --port 18767 --empty
python -m unittest discover -s tests -v
node --check frontend/app.js
node --check frontend/shell.js
node --check frontend/motion.js
node --test tests/frontend_changelog.test.cjs tests/frontend_motion.test.cjs
git diff --check
```

预览服务器只服务真实前端文件和内存中的虚构数据，不读取或修改生产设置、会话、日志，也不会请求模型。刷新浏览器保留当前进程的模拟修改；重启预览服务器恢复 fixture。该服务器不能作为正式后端使用。

2026-09-28 已在内置浏览器检查 `1440x900`、`1100x800`、`390x844`、`667x375`：

- 主页等宽分栏、长标题省略、空历史与空归档状态。
- 设置及供应商、工具、辩手切换；列表与编辑区独立滚动。
- 手机人工编排编辑器与横屏配置页的底部可达性。
- 深浅主题、工具字段的对比色、手机历史抽屉。
- 暂停、草稿撤回、继续、模拟新建及终止会话，终止后显示回放。
- 完成/错误回放，消息详情中工具参数、模型思考、工具结果分色。
- 模拟翻译加载、任务条、缓存和语言标签，Markdown 错误预览。
- 标题编辑 Escape 后焦点恢复，以及配置子页打开时焦点进入。

31 项本地自动测试通过，其中 6 项为新增前端 DOM/资源契约测试。真实模型调用及线上环境未验证；内置浏览器未返回 Markdown 下载完成事件，文件落盘未确认，原下载实现未变更。

侧栏后续调整补充验证：6 项前端契约测试通过；检查 1440px、1000px 和 390px 宽度，确认收起/展开、刷新记忆、草稿保留、弹窗不改变桌面偏好、手机焦点循环及 Escape 返回、单双栏自适应和暗色主题。浏览器无脚本警告或错误。

主页后续调整：7 项更新日志测试与 6 项前端契约测试通过，覆盖日志提取、空内容、代码围栏、错误提示重试，以及关闭重开后拒绝过期响应。浏览器检查了 1440px、1100px、390px 宽度，亮暗主题、弹窗独立滚动、Escape 焦点恢复、辩题草稿保留及手机底部操作可达性，未出现脚本警告或错误。项目介绍仍保留在原 Markdown 文件中，但不再显示于主页或更新记录弹窗。

## 动效复核

- 六类弹窗使用同一生命周期。遮罩淡入淡出，窗口仅轻微位移且保持不透明；退出完成前保持背景隔离。快速重开会取消旧动画与旧清理回调。
- 设置内配置页面仅在首次打开和切换页面时入场，字段重绘不反复播放整面板动画；关闭时保留内容到退场完成。
- 实时消息按 ID 复用节点，仅新行入场。重复状态更新不重启动画，阅读上文时不会强制滚到底部。
- 错误提示、翻译/总结任务条及发送对象标签使用可中断进退场；标签业务状态立即更新，视觉退出不延迟操作。
- `prefers-reduced-motion` 同时覆盖 CSS、Web Animations 与平滑滚动；偏好在动画中途改变时立即结束动画。该分支通过自动测试验证，未修改操作系统偏好。
- 浏览器检查设置、归档、更新记录、标题、Markdown、调用细节及任务条，覆盖桌面浅色和手机暗色。隔离预览不调用真实模型。
- 本轮 18 项 Node 行为测试与 7 项 Python 前端契约测试通过，涵盖动画竞态、即时关闭、减少动态效果、消息复用与滚动策略。
