#!/bin/bash
# 每日自动发布：每次发 4 章（上传草稿 → 发布上架）。
#
# 用法（在小说项目根目录运行，或用 --project-root / WEBHOVEL_PROJECT_ROOT 指定）：
#   bash 每日发布.sh                                # 发下一批 4 章
#   bash 每日发布.sh --dry-run                      # 只看将要发哪几章，不实际发布
#   bash 每日发布.sh --schedule-at "2026-10-20 20:00"   # 定时发布
#   bash 每日发布.sh --volume "第二卷：卷名"          # 指定目标卷（不传=第一个卷）
#
# 进度记录在 <项目>/发布/.publish_next（内容是「下一章要发的章号」）。
# 首次使用请把该文件内容设为起始章号（如 1）。
set -uo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${PY:-python3}"   # 可用 PY=/path/to/venv/python 覆盖（需已安装 playwright）

PROJECT_ROOT="${WEBHOVEL_PROJECT_ROOT:-}"
VOLUME="${VOLUME:-}"
DRY_RUN=0
SCHEDULE_AT=""
BATCH=4
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run)      DRY_RUN=1; shift ;;
    --schedule-at)  SCHEDULE_AT="${2:-}"; shift 2 ;;
    --volume)       VOLUME="${2:-}"; shift 2 ;;
    --project-root) PROJECT_ROOT="${2:-}"; shift 2 ;;
    --batch)        BATCH="${2:-4}"; shift 2 ;;
    *)              shift ;;
  esac
done

# 没指定项目根目录就自动探测（含 正文/ 的目录）
if [ -z "${PROJECT_ROOT}" ]; then
  PROJECT_ROOT="$("${PY}" -X utf8 -c "
import sys; sys.path.insert(0, '${SKILL_DIR}')
from project_paths import project_root
print(project_root())
")"
fi
PROGRESS="${PROJECT_ROOT}/发布/.publish_next"

# AI 声明：番茄要求勾选「是否使用AI」。AI 辅助创作统一选「是」(use_ai=1)。
USE_AI=1

# ---- 1. 环境检查 ----
if [ ! -f "${SKILL_DIR}/publisher/__init__.py" ]; then
  echo "[错误] 未找到发布模块：${SKILL_DIR}/publisher/"
  exit 1
fi
if ! "${PY}" -c "import playwright" >/dev/null 2>&1; then
  echo "[错误] 未安装 playwright：pip install playwright && playwright install chromium"
  exit 1
fi

# ---- 2. 读取进度 ----
mkdir -p "${PROJECT_ROOT}/发布"
if [ ! -f "${PROGRESS}" ]; then
  echo "1" > "${PROGRESS}"
fi
NEXT="$(tr -d '[:space:]' < "${PROGRESS}")"
if ! [[ "${NEXT}" =~ ^[0-9]+$ ]]; then
  echo "[错误] ${PROGRESS} 内容不是数字：${NEXT}"
  exit 1
fi

# ---- 3. 计算本章区间 ----
MAX="$(ls "${PROJECT_ROOT}/正文"/第*.md 2>/dev/null | sed -E 's/.*第0*([0-9]+)章.*/\1/' | sort -n | tail -1)"
if [ -z "${MAX}" ]; then
  echo "[错误] 没找到正文章节文件：${PROJECT_ROOT}/正文/"
  exit 1
fi
END=$((NEXT + BATCH - 1))
[ "${END}" -gt "${MAX}" ] && END="${MAX}"

if [ "${NEXT}" -gt "${MAX}" ]; then
  echo "[完成] 第 ${MAX} 章已全部发布，没有新章节了。"
  exit 0
fi

RANGE="${NEXT}-${END}"
echo "项目：${PROJECT_ROOT}"
echo "本次发布：第 ${NEXT}—${END} 章（共 $((END - NEXT + 1)) 章，全书最新 ${MAX} 章）"

if [ "${DRY_RUN}" -eq 1 ]; then
  echo "[dry-run] 不实际发布。进度文件：${PROGRESS}（当前 ${NEXT}）"
  [ -n "${SCHEDULE_AT}" ] && echo "[dry-run] 定时目标：${SCHEDULE_AT}"
  [ -n "${VOLUME}" ] && echo "[dry-run] 目标卷：${VOLUME}"
  exit 0
fi

# ---- 4. 上传草稿 ----
echo "--- 上传草稿 ---"
"${PY}" -X utf8 "${SKILL_DIR}/publisher/__init__.py" \
  --project-root "${PROJECT_ROOT}" \
  upload --platform fanqie --range "${RANGE}" --yes
UP_RC=$?

if [ "${UP_RC}" -ne 0 ]; then
  echo "[失败] 上传出错（退出码 ${UP_RC}），进度未推进。"
  exit "${UP_RC}"
fi

# ---- 5. 发布上架 ----
echo "--- 发布上架 ---"
PUB_LOG="$(mktemp)"
trap 'rm -f "${PUB_LOG}"' EXIT
SCHED_ARGS=()
[ -n "${SCHEDULE_AT}" ] && SCHED_ARGS+=(--schedule-at "${SCHEDULE_AT}")
VOL_ARGS=()
[ -n "${VOLUME}" ] && VOL_ARGS+=(--volume "${VOLUME}")

"${PY}" -X utf8 "${SKILL_DIR}/publisher/__init__.py" \
  --project-root "${PROJECT_ROOT}" \
  publish-drafts --platform fanqie --range "${RANGE}" --yes \
  --use-ai "${USE_AI}" "${VOL_ARGS[@]}" "${SCHED_ARGS[@]}" 2>&1 | tee "${PUB_LOG}"
PUB_RC="${PIPESTATUS[0]}"

# ---- 6. 校验实际成功章数，只有全成功才推进进度 ----
EXPECT=$((END - NEXT + 1))
SUCC="$(sed -n 's/^发布完成: 成功 \([0-9][0-9]*\),.*/\1/p' "${PUB_LOG}" | tail -1)"

if [ "${PUB_RC}" -ne 0 ]; then
  echo "[失败] 发布上架出错（退出码 ${PUB_RC}），实际成功 ${SUCC:-0}/${EXPECT} 章。进度保持 ${NEXT}，未推进。"
  exit "${PUB_RC}"
fi
if [ -z "${SUCC}" ]; then
  echo "[失败] 未能从输出解析到发布结果，按失败处理。进度保持 ${NEXT}，未推进。"
  exit 1
fi
if [ "${SUCC}" -ne "${EXPECT}" ]; then
  echo "[失败] 实际成功 ${SUCC} 章，应发 ${EXPECT} 章。进度保持 ${NEXT}，未推进。"
  exit 1
fi

echo "$((END + 1))" > "${PROGRESS}"
echo "[完成] 第 ${NEXT}—${END} 章已发布（${SUCC}/${EXPECT}）。下一批从第 $((END + 1)) 章开始。"
