# webnovel-publish（番茄小说自动发布 · 定时 / 分卷 / AI 声明）

把写好的小说章节批量发布到番茄小说作者后台：上传草稿、按卷上架、定时放出、AI 声明一次配好。

> 移植自 [lujih/webnovel-writer-opencode](https://github.com/lujih/webnovel-writer-opencode) 的 `.opencode/skills/webnovel-publish`（上游 **GPL-3.0**，继承自 lingfengQAQ/webnovel-writer），许可全文见本目录 [`LICENSE`](./LICENSE)。
> 本仓库的改动：登录判定重写、`networkidle` 等待修复、草稿列表改直连接口抓取、硬编码路径/书号全部改为可移植解析。详见文末「相对上游的改动」。

## 它解决什么

在作者后台手动发一章要七八次点击；写脚本发又会连番踩坑——**不传卷名整批落进第一卷**、定时和立即混用导致读者端乱序、超过每日字数限额当天章节被拒、接口返回成功但内容根本没变。这个技能把发布链路和这些坑一起打包。

## 安装

依赖 **Python 3.8+** 与 **Playwright**（唯一非标准库依赖，仅浏览器操作时需要）：

```bash
pip install playwright && playwright install chromium
```

把整个目录复制到用户级技能目录：

```bash
cp -r webnovel-publish ~/.workbuddy/skills/
```

发布模块自带登录态持久化（`~/.webnovel-publish/browser_data/fanqie/`），首次扫码一次即可。

## 快速开始

**约定：所有命令在小说项目根目录运行**（即含 `正文/` 与 `发布/` 的目录）。脚本会自动向上探测；也可以用环境变量 `WEBHOVEL_PROJECT_ROOT` 或各脚本的 `--project-root` 指定。`book_id` 从项目的 `.webnovel/publish_config.json` 读取（或用环境变量 `FANQIE_BOOK_ID`）。

```bash
PY=python3
SKILL_DIR=~/.workbuddy/skills/webnovel-publish

# 1. 扫码登录（一次即可；--check 只验证登录态）
$PY -X utf8 $SKILL_DIR/do_login.py

# 2. 只读查询现状：账号下所有书 / 草稿箱概况 / 线上分卷 / 定时候选
$PY -X utf8 $SKILL_DIR/publish_wizard.py

# 3. 看分卷、建新卷（卷名一律取自项目 大纲/总纲.md，禁止自拟）
$PY -X utf8 $SKILL_DIR/publisher/__init__.py list-volumes --platform fanqie
$PY -X utf8 $SKILL_DIR/publisher/__init__.py create-volume "第二卷：卷名" --platform fanqie --yes

# 4. 上传草稿 → 发布上架（--schedule-at 即定时发布，去掉即立即发布）
$PY -X utf8 $SKILL_DIR/publisher/__init__.py upload    --platform fanqie --range 1-4 --yes
$PY -X utf8 $SKILL_DIR/publisher/__init__.py publish-drafts --platform fanqie --range 1-4 \
    --yes --use-ai 1 --schedule-at "2026-11-01 20:00" --volume "第一卷：卷名"
```

**日常最省事的方式**——封装好的入口，每次 4 章，只有全部成功才推进进度：

```bash
bash ~/.workbuddy/skills/webnovel-publish/每日发布.sh                  # 立即发布下一批 4 章
bash ~/.workbuddy/skills/webnovel-publish/每日发布.sh --dry-run         # 只看将要发哪几章
bash ~/.workbuddy/skills/webnovel-publish/每日发布.sh --schedule-at "2026-11-01 20:00"
bash ~/.workbuddy/skills/webnovel-publish/每日发布.sh --volume "第二卷：卷名" --batch 6
```

## 改已经上线的章节

改「已发布 / 定时」章节与首次发布是两套接口，别混用：

| 场景 | 工具 | 说明 |
|---|---|---|
| 已发布 / 定时章节 | `sync_chapters.py` | `backup` / `diff` / `apply` / `status`，按 `item_id` 精确定位，`--keep-timer` 保留原定时 |
| 草稿箱章节 | `sync_drafts.py` | `backup` / `diff` / `apply` / `restore` |
| 改完验证 | `verify_true_sync.py` | **三方对照**：线上 vs 本地 vs 改前备份，区分真同步与假推送 |

```bash
# 先备份（任何写操作之前！），再比对，最后写回并复核
$PY -X utf8 $SKILL_DIR/sync_chapters.py backup --range 1-52
$PY -X utf8 $SKILL_DIR/sync_chapters.py diff   --range 1-52
$PY -X utf8 $SKILL_DIR/sync_chapters.py apply  --range 96 --keep-title --yes
$PY -X utf8 $SKILL_DIR/verify_true_sync.py --chapters 96
```

## 排期与平台限额

| 限额 | 值 | 说明 |
|---|---|---|
| 每日提交字数 | 约 9000 字 | 9079 实测通过，12392 被拒；超限只拒当天超出的那几章 |
| 每月排定字数 | 250000 字 | |
| 定时最远可排 | ≥ 88 天 | |

工具：`schedule_publish.py`（按卷分批定时）· `even_plan.py` + `run_even_plan.py`（均摊排期与执行）· `retime.py`（改期）· `full_day_report.py` / `month_report.py`（按天/月统计，算限额必须用**线上实际 `timer_time`**，不能信排期文件）。

## 踩过的坑（都已内建对策）

- **`use_ai=1` 才是「是」**：值取自作者后台真实抓包。第三方项目里固定的 `use_ai=2` 按语义是「否」，别照抄。
- **定时与立即绝不混用**：已排定时的书一律用定时发布，否则读者端章节顺序会乱。
- **发布必须显式指定卷**：`publish-drafts` 不传 `--volume` 会落到第一个卷。
- **一次只能建一个卷，且末卷为空时不能建下一个**：要先发一章进去。
- **返回码不可信，必须逐章回读**：`cover_article` 对已发布章节会返回假成功；`[OK]` 只代表接口没报错。
- **正文必须走规范格式化链路**：`format_for_platform()` 剥 markdown 标记后再包 `<p>`，自己拼 HTML 会让读者看到字面 `**`。
- **Playwright 关浏览器时删临时文件会被安全策略拦截**，命令状态显示 failed 但功能正常——发布/登录类命令建议关闭沙箱运行。

完整的命令对照与接口细节见 [`SKILL.md`](./SKILL.md) 与 [`使用说明.md`](./使用说明.md)。

## 相对上游的改动

1. `do_login.py`（新增）：上游 `setup-auth` 只看 URL 是否像后台，未扫码也报「登录成功」；改为轮询真实书单 API 判定，支持 `--check`。
2. `publisher/adapters/fanqie.py`：4 处 `wait_until="networkidle"` 改为 `"domcontentloaded"`（番茄后台是长连接页面，永远等不到 networkidle）。
3. `get_all_drafts()` 改为全分页直连抓取 `draft_list/v1`，不再依赖页面 XHR 拦截（路由跳登录页时会永远返回空）。
4. `chapter_paths.py` / `security_utils.py`（新增 shim）：独立安装发布模块时缺失会 ImportError。
5. **路径与书号全部可移植**：新增 `project_paths.py`，项目根目录自动探测、`book_id` 从项目配置或环境变量读取，不再硬编码本机路径。

## 许可证

**GPL-3.0**（继承自上游）。再分发需同样遵循 GPL-3.0 并附上许可证副本，本目录已附全文。若不想承担开源义务，请把仓库设为 private。
