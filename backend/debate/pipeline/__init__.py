"""线性辩论流水线。

这个目录承载实际运行中的辩论流程实现。
与旧的 graph 组织方式相比，这里明确按职责拆成：

- `common.py`：文本清洗、JSON 解析、usage 提取；
- `agent.py`：模型调用和工具调用；
- `history.py`：历史裁剪、用户插话可见性与回应规则；
- `phases_judge.py`：裁判阶段；
- `phases_debater.py`：正反方发言阶段；
- `transitions.py`：阶段迁移规则；
- `context.py`：运行期上下文构建。

这样维护者阅读时可以先理解“一个阶段怎么执行”，
再理解“阶段之间如何跳转”。
"""

