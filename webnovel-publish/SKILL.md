---
name: webnovel-publish
description: 将小说章节发布到番茄小说/七猫，含定时发布、AI 声明与分卷管理。触发条件："发布小说"、"发布章节"、"上传到番茄"、"发布草稿"、"每日发布"、"发新的一批"、"定时发布"、"清理草稿"、"查看分卷"、"新建分卷"、"发到某一卷"。
compatibility: workbuddy
---

# 小说自动发布（WorkBuddy 适配版）

> 本技能移植自 lujih/webnovel-writer-opencode 的 `.opencode/skills/webnovel-publish`，
> 发布模块已独立安装在本目录 `publisher/` 下，不依赖原仓库、不受写作技能更新影响。

## 交互式发布向导（首选流程）

用户说「发布小说 / 发章节 / 发新的一批」等**模糊指令**时，必须先查询、给选项、等用户确认，
不要直接开跑。选择控件自带自由输入框，用户既能点选项也能手输。

### Step 1：查询现状（只读，不写任何数据）

```bash
PY=python3                      # 需已安装 playwright；也可指向你的虚拟环境解释器
SKILL_DIR=$HOME/.workbuddy/skills/webnovel-publish
PROJECT_ROOT=/path/to/novel     # 小说项目根目录（含 正文/ 与 发布/）

"$PY" -X utf8 "$SKILL_DIR/publish_wizard.py" --project-root "$PROJECT_ROOT"
# 项目未绑定 / 想查别的书：加 --book-id <book_id>
# 不传 --project-root 时会自动向上探测含 正文/ 的目录，也可设环境变量 WEBHOVEL_PROJECT_ROOT
```

返回 JSON：`books`（账号下所有书）/ `drafts`（草稿箱篇数、章号范围、建议的下一批、缺失提示）
/ `volumes`（线上已有哪些卷、每卷章节数）/ `outline_volumes`（大纲定义的卷名）
/ `volume_advice`（建议发到哪个卷、能否建下一卷、下一卷大纲名）
/ `local_max_chapter`（本地最新写到第几章）/ `publish_next`（项目记录的下一批起点）
/ `schedule_candidates`（未来几天 20:00 的定时候选）。

> 发布、查询类命令建议带 `dangerouslyDisableSandbox` 运行（见文末「沙箱」坑）。

### Step 2：向用户确认五个要素

一次性问清，**每项都要给出基于 Step 1 结果的选项**，同时允许用户手输：

| 要素 | 选项来源 | 备注 |
|------|---------|------|
| 发到哪本书 | `books` 列表 | 多本书必须问；仅一本且已绑定可跳过，但仍要报出书名让用户确认 |
| 发哪几章 | `drafts.suggest_range`（如 49-52） | 接受任意范围或单章，如 `53-56`、`60` |
| **发到哪个卷** | `volumes` 列表 | 番茄的书是分卷的。不传 `--volume` 会落到**第一卷**（历史默认，通常不对） |
| 什么时候发 | 立即发布 / `schedule_candidates` 的几个 20:00 | 见下方「定时 vs 立即」 |
| AI 声明 | 是（`--use-ai 1`）/ 否（`--use-ai 0`） | 推荐「是」 |

> ⛔ **问完必须等答复，不许自行按推荐值执行。**
> 给出选项并标注「推荐」不等于用户选了它——用户未明确回答时，任何写操作
> （发布 / 上传 / 建卷 / 删除）都不得启动。只读查询（向导、`list-volumes`、`--dry-run`）
> 可以先跑。
> 若询问控件卡在「等待用户确认｜答案在排队叫号」，**改成纯文字提问**让用户直接回复，
> 不要替他用默认值。（2026-10-18 踩过：用户中断控件后擅自按推荐组合执行，被当场叫停。）

### Step 2.5：卷的处理（重要）

```bash
# 查看线上卷情况（每个卷多少章）
"$PY" -X utf8 "$SKILL_DIR/publisher/__init__.py" --project-root "$PROJ" \
  list-volumes --platform fanqie

# 发布时指定目标卷（volume_id 或卷名均可，卷名支持模糊匹配但需唯一命中）
  ... publish-drafts --platform fanqie --range 50 --volume "第三卷：你的卷名" ...

# 新建卷
"$PY" -X utf8 "$SKILL_DIR/publisher/__init__.py" --project-root "$PROJ" \
  create-volume "第四卷：新卷名" --platform fanqie --yes
```

四条必须遵守的规则（前三条为番茄平台限制，2026-10-18 实测确认）：

1. **一次只能新建一个卷。**
2. **末卷为空时不允许再建新卷。** 刚建的卷还空着 → 不能接着建下一个，
   必须先往该卷发布至少一章使其非空。`list-volumes` 与向导会主动给出此警告。
   因此「发到新卷」的正确顺序是：**先发一章到当前末卷 → 再建新卷 → 再发到新卷**。
3. 已有章节的卷在 UI 上不可删除（`tomato-delete.disabled`），删卷要趁空。
4. **卷名一律以项目的「大纲/总纲.md」为准，禁止自拟、禁止看剧情起名。**
   创建接口需要传**完整卷名**（如「第三卷：你的卷名」），UI 会自动加「第N卷：」前缀
   但直接用接口时必须自己写全。

### Step 3：执行

常规「下一批 4 章」（脚本会自动推进 `发布/.publish_next`）：

```bash
bash "$SKILL_DIR/每日发布.sh"                     # 立即发布
bash "$SKILL_DIR/每日发布.sh" --schedule-at "2026-10-20 20:00"   # 定时发布
```

自定义范围 / 单章（**不会**自动推进进度，成功后再手动把 `发布/.publish_next` 改为末章+1）：

```bash
# 草稿缺失（warnings 里有 missing）时先补传
"$PY" -X utf8 "$SKILL_DIR/publisher/__init__.py" --project-root "$PROJECT_ROOT" \
  upload --platform fanqie --range 49-52 --yes

# 发布。带 --schedule-at 即定时，去掉即立即发布
"$PY" -X utf8 "$SKILL_DIR/publisher/__init__.py" --project-root "$PROJECT_ROOT" \
  publish-drafts --platform fanqie --range 49-52 --yes \
  --use-ai 1 --schedule-at "2026-10-20 20:00"
```

### Step 4：核验与汇报

再跑一次 `publish_wizard.py`，确认草稿箱篇数按预期减少；然后汇报：
**发了第几章到第几章、立即还是定时到什么时候、下一批建议从第几章开始、全书最新写到第几章**。

判定成功的标准：输出里 `发布完成: 成功 N` 的 N 必须等于应发章数。
出现 `[FAIL] 第X章 草稿箱无对应草稿` 表示要先 `upload` 补传，不要绕过。

## 本机调用方式（重要：与原版命令不同）

原版用 `python .opencode/scripts/webnovel.py publish ...`，本机请直接调用 publisher 入口：

```bash
PY=python3                      # 需已安装 playwright；也可指向你的虚拟环境解释器
SKILL_DIR=$HOME/.workbuddy/skills/webnovel-publish
PROJECT_ROOT=/path/to/novel     # 小说项目根目录（含 正文/ 与 发布/）

# 首次扫码登录（一次即可）── 用可靠版 do_login.py，别用 setup-auth
# setup-auth 只判断 URL 是否像后台，未登录也会误报成功（实测坑）
"$PY" -X utf8 "$SKILL_DIR/do_login.py"            # 弹窗扫码，最多等 300 秒
"$PY" -X utf8 "$SKILL_DIR/do_login.py" --check    # 只验证登录态是否有效

# 查看书单、拿 book_id
"$PY" -X utf8 "$SKILL_DIR/publisher/__init__.py" --project-root "$PROJECT_ROOT" \
  list-books --platform fanqie

# 上传章节到草稿箱
"$PY" -X utf8 "$SKILL_DIR/publisher/__init__.py" --project-root "$PROJECT_ROOT" \
  upload --platform fanqie --range 9-12 --yes

# 发布草稿箱中的章节（正式上架）
"$PY" -X utf8 "$SKILL_DIR/publisher/__init__.py" --project-root "$PROJECT_ROOT" \
  publish-drafts --platform fanqie --range 9-12 --yes

# 定时发布 + AI 声明（推荐组合）
"$PY" -X utf8 "$SKILL_DIR/publisher/__init__.py" --project-root "$PROJECT_ROOT" \
  publish-drafts --platform fanqie --range 9-12 --yes \
  --use-ai 1 --schedule-at "2026-10-20 20:00"

# 指定目标卷发布（卷名或 volume_id）
"$PY" -X utf8 "$SKILL_DIR/publisher/__init__.py" --project-root "$PROJECT_ROOT" \
  publish-drafts --platform fanqie --range 50 --yes \
  --use-ai 1 --schedule-at "2026-10-21 20:00" --volume "第三卷：你的卷名"

# 查看 / 新建分卷（卷名必须取自 大纲/总纲.md）
"$PY" -X utf8 "$SKILL_DIR/publisher/__init__.py" --project-root "$PROJECT_ROOT" \
  list-volumes --platform fanqie
"$PY" -X utf8 "$SKILL_DIR/publisher/__init__.py" --project-root "$PROJECT_ROOT" \
  create-volume "第四卷：新卷名" --platform fanqie --yes

# 一句话带定时跑下一批 4 章（内置 use_ai=1，自动推进进度）
bash "$SKILL_DIR/每日发布.sh" --schedule-at "2026-10-20 20:00"
bash "$SKILL_DIR/每日发布.sh"            # 立即发布
bash "$SKILL_DIR/每日发布.sh" --dry-run  # 只看将要发哪几章
```

**日常推荐**：直接用封装好的 `每日发布.sh`（本技能根目录，每次 4 章，自动推进进度；
在小说项目根目录运行，或用 `WEBHOVEL_PROJECT_ROOT` 指定项目）。

## 关键事实

- `upload` 只存**草稿**；必须再跑 `publish-drafts` 才真正上架。
- 已上传章节记录在 `~/.webnovel-publish/upload_log/{项目名}/fanqie_{book_id}.json`，
  重复上传会自动跳过。**这个日志与番茄后台不互通**——手动上传过的章节不会被记录，
  所以必须显式传 `--range`，否则会从第 1 章重传造成重复。
- 登录态保存在 `~/.webnovel-publish/browser_data/fanqie/`（Playwright 持久化目录），
  过期需重跑 `do_login.py`（**不是** `setup-auth`，见下）。
- `--yes` 在非交互环境（定时任务/CI）必须带上。
- `--book` 首次传一次即可把 book_id 持久写入 `{项目}/.webnovel/publish_config.json`，
  之后可省略；也可直接手写该文件：
  `{"bindings":{"fanqie":{"book_id":"<id>","book_name":"<书名>"}}}`
- **发布必须考虑卷**：不传 `--volume` 会落到第一卷。`publish-drafts` 只认
  `volume_id` / `volume_name` 两个字段，两者需匹配同一卷。
- 新建卷接口：`POST /api/author/volume/add_volume/v0/`，表单为
  `aid`/`app_name`/`book_id`/`volume_name`（**完整卷名**，UI 会自动加「第N卷：」前缀
  但接口不会）。卷列表：`GET /api/author/volume/volume_list/v1/?book_id=`。

## 本机已做的四处补丁（重跑前不用再改）

1. `do_login.py`（新增，技能根目录）——**登录一律用它**。
   上游 `setup-auth` 的 `_is_writer_url()` 只看 URL 是否像后台，
   **未扫码也会打印「登录成功」**（实测踩到：报 OK 后调 list-books 直接
   `登录信息有误`）。`do_login.py` 改为轮询真实书单 API 判定，
   支持 `--check`（只验证不开窗）与 `--wait N`（等待秒数）。
2. `publisher/adapters/fanqie.py`——4 处 `wait_until="networkidle"`
   已改为 `"domcontentloaded"`（并补 `asyncio.sleep`）。
   番茄后台是长连接页面，**永远等不到 networkidle**，会 30s 超时崩掉。
3. `chapter_paths.py` / `security_utils.py`（新增 shim，技能根目录）——
   `_find_chapter_file()` 与 `_read_book_meta()` 依赖这两个模块，
   独立安装发布模块时缺失会直接 ImportError。
4. `publisher/adapters/fanqie.py` 的 `get_all_drafts()`——原实现用
   「导航到 chapter-manage 页面 + 拦截 draft_list XHR 响应」取首页，
   但番茄页面路由会跳登录页，导致**永远返回空、误报「草稿箱为空」**
   （实测：直接 fetch 同一 API 明明有 4 篇）。
   已改为**全分页直接 fetch** `draft_list/v1`，并按章节号升序排序，
   保证 `publish-drafts` 按章顺序消费草稿。

## 配套工具（技能根目录，均可 `--help` 看用法）

除 `publisher/` 主模块外，根目录还有一批排期 / 同步 / 复核脚本。约定：
**在小说项目根目录运行**（或设 `WEBHOVEL_PROJECT_ROOT` / 传 `--project-root`），
`book_id` 自动从项目 `.webnovel/publish_config.json` 读取（也可用环境变量 `FANQIE_BOOK_ID`）。

| 脚本 | 用途 |
|------|------|
| `每日发布.sh` | 封装「上传草稿 → 发布上架」的日常入口，每次 N 章，**只有全部成功才推进进度** |
| `sync_chapters.py` | 改**已发布/定时**章节：`backup` / `diff` / `apply` / `status`，按 item_id 精确定位 |
| `sync_drafts.py` | 改**草稿箱**章节：`backup` / `diff` / `apply` / `restore` |
| `verify_true_sync.py` | 三方对照复核（线上 vs 本地 vs 改前备份），判断是真同步还是假推送 |
| `schedule_publish.py` | 按卷划分把草稿分批定时发布：`plan` 出表 / `run` 执行 / `chapter` 单批发 |
| `run_even_plan.py` / `even_plan.py` | 按外部排期 JSON 执行 / 生成「均摊」排期 |
| `retime.py` | 改已排章节的定时时间（`--chapter` 单章 / `--plan` 按方案批量） |
| `full_day_report.py` / `month_report.py` | 按天/月统计线上已排字数，防超日限（约 9000 字）月限（250000 字） |
| `plan_full.py` / `replan_wc.py` / `wc_stats.py` | 排期演算：装天、重排、字数统计（纯本地计算） |
| `verify_plan.py` / `verify_scheduled.py` / `verify_schedule_full.py` | 回读校验排期：卷归属 / 定时时间 / 发布状态 / 正文一致性 |
| `spotcheck.py` | 抽查本地与线上的具体文本差异（只读） |
| `list_drafts.py` / `do_login.py` | 看草稿箱 / 登录（`--check` 只验证登录态） |

> ⚠️ 排任何批量定时前，先确认平台三条硬限额：每日约 9000 字、每月 250000 字、
> 定时最远可排 ≥ 88 天。算每日/每月字数必须用**线上实际 `timer_time`**，
> 不能信排期文件（失败章改期后两者会不一致）。

## 两个运行期坑

- **沙箱**：Playwright 关浏览器时要删大量临时文件，会被 safe-delete 拦下，
  命令状态显示 `failed` 但功能其实正常。**发布/登录类命令要带
  `dangerouslyDisableSandbox` 跑**，否则状态会误导。
- **AI 声明（已支持，2026-10-18 起）**：`publish-drafts` 新增 `--use-ai`，
  **1=「是」、0=「否」**（值取自番茄后台真实抓包，可信）。
  按平台合规要求选「是」，即 `--use-ai 1`（本技能自带的 `每日发布.sh` 已内置 `USE_AI=1`）。
  第三方项目 tomato-writer-mcp 里的 `use_ai=2` 实际是「否」，**不要照抄**。
- **定时 vs 立即（重要）**：番茄支持原生定时发布，`--schedule-at "YYYY-MM-DD HH:MM"`
  或 `--schedule-at`（配合 `timer_status=1` + `timer_time`）即可排到指定时刻。
  **两者绝对不可混用**——若已有章节排在明天的定时队列里，此时立即发布后面的章节，
  会让读者先看到后面的章节，造成不可逆的顺序错乱。**已排定时的书一律用定时发布。**

---

<!-- 以下为上游原文，命令写法以本机为准 -->

---
name: webnovel-publish
description: 将小说章节自动发布到国内主流小说平台（番茄等）。触发条件："发布小说"、"发布章节"、"上传到番茄"、"自动发布"、"清理草稿"、"发布草稿"。
compatibility: opencode
---

# 小说自动发布

## 目标

将已完成小说章节自动发布到目标平台。首次需手动扫码登录，后续全自动运行。

## 支持平台

| 平台 | 标识 | 认证方式 | 状态 |
|------|------|---------|------|
| 番茄小说 | fanqie | 扫码登录（一次） | 可用 |
| 七猫小说 | qimao | 扫码登录（一次） | 实验性 |

## 环境设置

```bash
export SCRIPTS_DIR="${PWD}/.opencode/scripts"
test -d "${SCRIPTS_DIR}" || { echo "错误: 未找到 ${SCRIPTS_DIR}，请确保当前目录是 webnovel-writer 仓库根目录"; exit 1; }

export PROJECT_ROOT="$(python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PWD}" where)"
test -n "$PROJECT_ROOT" && test -f "${PROJECT_ROOT}/.webnovel/state.json" || { echo "错误: PROJECT_ROOT 解析失败，请用 --project-root 显式指定"; exit 1; }
echo "项目路径: ${PROJECT_ROOT}"

python -c "import playwright" 2>/dev/null || { echo "请先安装: pip install playwright && playwright install chromium"; exit 1; }
```

## 交互式流程

### Step 0：确认参数

若用户指令模糊，按优先级询问：

| 优先级 | 参数 | 何时必须询问 | 选项 |
|--------|------|-------------|------|
| 1 | 平台 | 未指定平台 | fanqie / qimao |
| 2 | 操作 | 未指定操作 | 首次配置 / 创建新书 / 上传章节 |
| 3 | book_id | 上传时未绑定书籍 | 输入 ID 或书名 |
| 4 | 范围 | 未指定章节范围 | 全部 / 指定范围 |
| 5 | 模式 | 未指定 | 当前仅支持草稿（draft） |

**可直接执行**：
- "发布到番茄" → 平台明确，进入菜单流程
- "上传第 90-95 章" → 操作和范围明确
- "发布全部到番茄" → 平台和范围明确

### Step 1：首次配置（登录）

```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" publish setup-auth --platform fanqie
```

弹出浏览器窗口，扫码登录后自动保存认证状态。后续无需重复。  
认证存储在 `~/.webnovel-publish/browser_data/{platform}/`。

### Step 2：查看书单

```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" publish list-books --platform fanqie
```

确认目标书籍是否存在，获取 book_id。

### Step 3：创建新书

```bash
# 交互式（会询问书名、简介）
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" publish create-book \
  --platform fanqie \
  --project-root "${PROJECT_ROOT}"

# 非交互式（跳过确认）
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" publish create-book \
  --platform fanqie \
  --project-root "${PROJECT_ROOT}" \
  --yes \
  --abstract "自定义简介"
```

自动从 `state.json` 读取：书名、题材、简介、主角名。  
创建成功后自动绑定 book_id 到项目（写入 `.webnovel/publish_config.json`）。

### Step 4：上传章节

```bash
# 上传全部（使用项目绑定的 book_id）
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" publish upload \
  --platform fanqie \
  --project-root "${PROJECT_ROOT}"

# 指定 book_id 或书名（首次上传自动绑定）
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" publish upload \
  --platform fanqie \
  --book 7631548393474493502 \
  --project-root "${PROJECT_ROOT}"

# 指定范围
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" publish upload \
  --platform fanqie \
  --range 90-95 \
  --project-root "${PROJECT_ROOT}"

# 跳过交互确认（脚本/CI 环境）
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" publish upload \
  --platform fanqie \
  --yes \
  --project-root "${PROJECT_ROOT}"
```

已上传章节自动跳过，支持断点续传。  
上传日志存储在 `~/.webnovel-publish/upload_log/{project_name}/{platform}_{book_id}.json`。

### Step 5：草稿管理（新增功能）

#### 5.1 清理重复草稿

```bash
# 预览模式（不实际删除，查看哪些章节有重复）
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" publish clean-drafts \
  --platform fanqie \
  --project-root "${PROJECT_ROOT}" \
  --dry-run

# 清理重复草稿（同章节号保留最新修改时间的，删除旧版本）
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" publish clean-drafts \
  --platform fanqie \
  --project-root "${PROJECT_ROOT}"

# 跳过确认
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" publish clean-drafts \
  --platform fanqie \
  --project-root "${PROJECT_ROOT}" \
  -y
```

**适用场景**：多次上传同一章导致草稿箱有重复，想保留最新版本删除旧版本。

#### 5.2 清空草稿箱

```bash
# 清空草稿箱所有章节（跳过已发布的）
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" publish clear-drafts \
  --platform fanqie \
  --project-root "${PROJECT_ROOT}"
```

**适用场景**：想清空草稿箱重新开始，但不删除已正式发布的章节。

#### 5.3 删除全部草稿

```bash
# 删除草稿箱全部章节（包括已发布的，需二次确认 yes）
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" publish delete-drafts \
  --platform fanqie \
  --project-root "${PROJECT_ROOT}"

# 跳过确认（危险操作）
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" publish delete-drafts \
  --platform fanqie \
  --project-root "${PROJECT_ROOT}" \
  -y
```

**危险操作**：会删除所有草稿，包括已发布状态的章节，并清除上传记录。

#### 5.4 发布草稿

```bash
# 发布草稿箱中的章节（将草稿改为已发布状态）
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" publish publish-drafts \
  --platform fanqie \
  --range 1-10 \
  --project-root "${PROJECT_ROOT}"

# 发布全部草稿
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" publish publish-drafts \
  --platform fanqie \
  --project-root "${PROJECT_ROOT}"
```

**适用场景**：章节已在草稿箱，想批量发布到正式站。  
**注意**：发布时会用草稿箱现有的 item_id，标题和内容从本地文件读取。

## 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--platform` | 平台标识 | fanqie |
| `--book` | 书籍 ID 或书名 | 从项目绑定读取 |
| `--range` | 章节范围（1-50 / 1,3,5 / all） | all |
| `--mode` | 发布模式（当前仅 draft） | draft |
| `--yes` / `-y` | 跳过交互确认 | — |
| `--dry-run` | 预览模式（仅 clean-drafts 支持） | — |
| `--abstract` | 书籍简介（create-book） | 自动生成 |
| `--project-root` | 书项目根目录 | 自动探测 |

## 子命令列表

| 命令 | 功能 | 典型用法 |
|------|------|---------|
| `setup-auth` | 扫码登录平台 | 首次使用 |
| `list-books` | 列出已有书籍 | 查询 book_id |
| `create-book` | 创建新书 | 自动从项目元数据生成 |
| `upload` | 上传章节到草稿箱 | 日常更新 |
| `clean-drafts` | 清理重复草稿 | 多次上传同章后去重 |
| `clear-drafts` | 清空草稿箱（跳过已发布） | 重新开始前清理 |
| `delete-drafts` | 删除全部草稿（危险） | 完全清空草稿箱 |
| `publish-drafts` | 发布草稿到正式站 | 批量上架 |

## 自动绑定机制

- 首次 `create-book` 成功后自动绑定 book_id 到 `.webnovel/publish_config.json`
- 首次 `upload --book <id>` 成功后自动持久化绑定
- 后续 `upload` 无需传 `--book`，自动从绑定读取
- 多书项目：用 `--book` 指定目标即可

## 卸载与重置

```bash
# 清除认证状态
rm -rf ~/.webnovel-publish/browser_data/

# 清除上传日志
rm -rf ~/.webnovel-publish/upload_log/

# 清除项目绑定
rm "${PROJECT_ROOT}/.webnovel/publish_config.json"
```

## 充分性闸门

- [ ] Playwright 已安装且 Chromium 可用
- [ ] 平台认证状态有效
- [ ] 目标书籍 book_id 已知或在书单中
- [ ] 上传日志一致（不会重复上传）
- [ ] 章节文件存在且非空

## 常见问题

| 问题 | 解决 |
|------|------|
| 登录超时 | 重新运行 setup-auth，3 分钟内扫码 |
| 认证过期 | 重新运行 setup-auth（认证目录存在不代表有效） |
| 浏览器不弹 | 检查显示器配置，确保非 headless |
| Playwright 未安装 | `pip install playwright && playwright install chromium` |
| 项目未绑定 | 传 `--book <id>` 或先 `create-book` |
| book_id 不匹配 | 检查是否误用了其他书的 ID |
| 非交互环境报错 | 添加 `--yes` 跳过确认 |
| 草稿箱有重复章节 | 运行 `clean-drafts --dry-run` 预览，再去掉 `--dry-run` 执行 |
| 想重新上传所有章节 | 先 `delete-drafts` 删除草稿和上传记录，再重新 `upload` |
| 草稿上传了但想发布 | 运行 `publish-drafts --range <范围>` |
