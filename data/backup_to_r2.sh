#!/usr/bin/env bash
set -euo pipefail
umask 077

# 全量打包指定目录（默认当前目录）为加密 RAR，并上传到 Cloudflare R2（S3 API）
# - 凭证与端点等配置固定为脚本所在目录的 r2_secrets.enc，使用单一主密码解密

usage() {
  cat <<EOF
用法：
  $(basename "$0") [--source 目录]

说明：
  - 默认打包“脚本所在目录的上级目录”；可通过 --source 指定要打包的目录
  - 固定使用脚本同目录下的 r2_secrets.enc 解密凭证
EOF
}

need() { command -v "$1" >/dev/null 2>&1 || { echo "[ERROR] 需要依赖：$1"; exit 1; }; }
need openssl

# 检查/安装依赖：rar 与 awscli（如有 apt 权限）
ensure_dep() {
  if ! command -v "$1" >/dev/null 2>&1; then
    if command -v apt-get >/dev/null 2>&1; then
      export DEBIAN_FRONTEND=noninteractive
      apt-get update -y >/dev/null 2>&1 || true
      apt-get install -y "$1" >/dev/null 2>&1 || true
    fi
  fi
  command -v "$1" >/dev/null 2>&1 || { echo "[ERROR] 未找到依赖：$1"; exit 1; }
}

ensure_dep rar
ensure_dep aws

SOURCE_DIR="."
while [[ $# -gt 0 ]]; do
  case "$1" in
    -s|--source)
      SOURCE_DIR="${2:-}"; shift 2 ;;
    -h|--help|help)
      usage; exit 0 ;;
    *)
      echo "[ERROR] 未知参数：$1"; usage; exit 1 ;;
  esac
done

# 计算脚本目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
SECRETS_FILE="$SCRIPT_DIR/r2_secrets.enc"
[[ -f "$SECRETS_FILE" ]] || { echo "[ERROR] 缺少 $SECRETS_FILE，请先运行 $SCRIPT_DIR/r2_encrypt_secrets.sh 生成"; exit 1; }

# 若未显式指定，则默认备份脚本所在目录的上级目录
if [[ "$SOURCE_DIR" == "." ]]; then
  SOURCE_DIR="$SCRIPT_DIR/.."
fi

MASTER_PASS="${MASTER_PASS:-${BACKUP_MASTER_PASS:-}}"
if [[ -z "${MASTER_PASS:-}" ]]; then
  read -r -s -p "Master password: " MASTER_PASS; echo
fi

tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT

plain_env="$tmpdir/r2.env"
set +e
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -md sha256 \
  -in "$SECRETS_FILE" -out "$plain_env" -pass pass:"$MASTER_PASS"
dec_rc=$?
set -e
if [[ $dec_rc -ne 0 ]]; then
  echo "[ERROR] 解密失败：主密码不正确或 r2_secrets.enc 已损坏" >&2
  echo "        可使用 MASTER_PASS 环境变量避免输入错误，例如：" >&2
  echo "        MASTER_PASS='你的密码' ./backup_to_r2.sh [--source 目录]" >&2
  exit 2
fi

# shellcheck disable=SC1090
set -a; source "$plain_env"; set +a
shred -u "$plain_env" 2>/dev/null || rm -f "$plain_env"

# 归档文件生成在临时目录，避免被自身打包
# 规范化源目录为绝对路径
if command -v realpath >/dev/null 2>&1; then
  SRC="$(realpath -m "$SOURCE_DIR")"
else
  SRC="$(cd "$SOURCE_DIR" 2>/dev/null && pwd -P)"
fi
[[ -n "${SRC:-}" && -d "$SRC" ]] || { echo "[ERROR] 源目录无效：$SOURCE_DIR"; exit 1; }

DATE=$(date +%Y%m%d_%H%M%S)
OUTFILE="$tmpdir/all_${DATE}.rar"

echo "[INFO] 源目录：$SRC"
echo "[INFO] 创建加密 RAR：$OUTFILE"
# -hp 使用同一主密码对 RAR 内容与文件名全加密；-ma5 使用 RAR5 格式；-r 递归
rar a -r -ma5 -hp"$MASTER_PASS" "$OUTFILE" "$SRC"

OBJECT_KEY=$(basename -- "$OUTFILE")

echo "[INFO] 上传到 R2：s3://$R2_BUCKET/$OBJECT_KEY"
aws s3 cp "$OUTFILE" "s3://$R2_BUCKET/$OBJECT_KEY" \
  --endpoint-url "$R2_ENDPOINT" \
  --no-progress

echo "[INFO] 校验已上传对象列表"
aws s3 ls "s3://$R2_BUCKET/$OBJECT_KEY" --endpoint-url "$R2_ENDPOINT" || true

echo "[INFO] 完成"
