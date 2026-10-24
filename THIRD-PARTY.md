# 第三方来源与许可

本仓库收录了若干移植/改编自第三方的技能。逐个列明来源、许可与改动范围，便于追溯与合规。

| 目录 | 来源 | 许可 | 本仓库改动 |
|---|---|---|---|
| `impeccable/` | [pbakaus/impeccable](https://github.com/pbakaus/impeccable)（技能 4.3.1 / engine 0.1.5） | Apache-2.0 | 58 处 `.agents/skills/impeccable` 路径替换为 `~/.workbuddy/skills/impeccable`；`agents/*.toml` 转 `.md`；description 追加中文触发词；新增中文 README；SKILL.md 顶部加 WorkBuddy 适配说明 |
| `webnovel-writer/` | 上游 `webnovel-writer 6.2.1` | GPL-3.0 | 合并原 `webnovel-autopilot` 为 `skills/webnovel-autopilot/`；修正 `wnw`/`refs` 硬编码 macOS 虚拟环境路径；重写 README |
| `tdd/` `code-review/` `codebase-design/` `diagnosing-bugs/` `domain-modeling/` `prototype/` `research/` `pr/` `wizard/` `ask-matt/` `grill-with-docs/` `triage/` `improve-codebase-architecture/` `setup-matt-pocock-skills/` `to-spec/` `to-tickets/` `implement/` `implement-spec/` `wayfinder/` `retro/` | [mattpocock/skills](https://github.com/mattpocock/skills) 的 `skills/engineering/`（共 20 个） | MIT | frontmatter 去掉 `disable-model-invocation`、加 `agent_created: true`；每个 SKILL.md 顶部插入中文「WorkBuddy 适配说明」（子代理映射 / 触发方式 / issue tracker 落地方式）；方法正文未改 |
| `workbuddy-history-recovery/` | 本项目原创 | MIT | — |

## 合规提示

- **GPL-3.0 有传染性**：`webnovel-writer/` 的再分发需同样遵循 GPL-3.0，仓库内已附全文。若不想承担开源义务，请把仓库设为 private。
- **Apache-2.0 / MIT**：再分发需保留许可与版权声明，已随各目录附带。
- 上游若有更新，重新拉取后按上表「改动」一列重做适配即可。
