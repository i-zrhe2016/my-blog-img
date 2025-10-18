Image Host（图床）

最小可用的本地图床：上传图片，拿直链。够用即可。

快速开始

1) 安装依赖

```
pip install -r requirements.txt
```

2) 运行

```
python app.py
# 默认服务： http://localhost:8000
```

怎么用

- 网页上传：打开 `/`，选择图片提交。
- 图库：`/gallery` 浏览所有图片。
- 直链：`/img/<id>.<ext>` 直接访问图片。
- API：`POST /api/upload`，`multipart/form-data` 字段名 `image`。

API 示例

```
curl -F image=@your.png http://localhost:8000/api/upload
```

存储位置

- 图片：`uploads/`
- 元数据：`data/images.jsonl`（一行一条 JSON）

可选配置（按需）

- `PORT`：端口，默认 `8000`
- `BASE_URL`：生成外链的基地址（不设则按请求推断）

备份

- 目标：加密打包后上传到 Cloudflare R2。
- 依赖：`openssl`、`rar`、`awscli`（脚本会尝试用 `apt` 安装）。
- 一次执行：

```
MASTER_PASS='你的主密码' data/backup_to_r2.sh
```

- 准备密钥（首次）：在 `data/` 生成加密凭证 `r2_secrets.enc`。

```
cat > data/r2.env <<'EOF'
AWS_ACCESS_KEY_ID=你的key
AWS_SECRET_ACCESS_KEY=你的secret
R2_BUCKET=你的bucket
R2_ENDPOINT=https://<account_id>.r2.cloudflarestorage.com
EOF
openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -md sha256 \
  -salt -in data/r2.env -out data/r2_secrets.enc
shred -u data/r2.env 2>/dev/null || rm -f data/r2.env
```

- 恢复：使用 `unrar` 解压（需主密码）。

```
unrar x -p你的主密码 all_*.rar
```

- 定时（可选）：

```
# 每天 02:30 备份
30 2 * * * cd /path/to/repo && \
  MASTER_PASS='你的主密码' data/backup_to_r2.sh >> backup.log 2>&1
```

就这些。
