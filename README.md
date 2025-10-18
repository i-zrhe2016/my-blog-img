Image Host（图床）

概述

轻量本地图床服务（Flask）：网页上传、图库、直链与 API，数据存于本地文件系统。

特性

- 网页上传与预览（/）
- 图库浏览（/gallery）
- 直链访问（/img/<id>.<ext>）
- 简单 API：上传、查询、删除
- 本地 JSONL 元数据（data/images.jsonl）

环境要求

- Python 3.10+

安装

```
pip install -r requirements.txt
```

运行

```
# 开发
python app.py  # http://localhost:8000

# 生产（可选）
gunicorn -b 0.0.0.0:8000 'app:app'
```

配置

- `PORT`：服务端口，默认 `8000`
- `BASE_URL`：生成外链基地址（不设则按请求推断）
- `DEFAULT_BASE_URL`：默认外链基地址，默认 `https://img.zrhe2016.cc`
- `MAX_CONTENT_LENGTH`：最大上传字节数，默认 10MB
- `TRUST_PROXY`：`1/true` 时信任反代请求头
- `SECRET_KEY`：Flask 会话密钥
- `ADMIN_TOKEN`：设置后开启受保护删除接口

API

- `POST /api/upload`
  - 表单：`multipart/form-data`，字段名 `image`
  - 响应：`{ id, url, markdown, html, size, sha256 }`
- `GET /links/<id>`
  - 返回该图片常用链接与元数据：`{ id, url, markdown, html, record }`
- `POST /api/delete/<id>?token=<ADMIN_TOKEN>`
  - 受保护删除：`{ ok: true }`（需配置 `ADMIN_TOKEN`）

例子

```
curl -F image=@your.png http://localhost:8000/api/upload
```

目录结构

- `app.py`：主应用
- `uploads/`：图片文件
- `data/images.jsonl`：元数据（每行一条 JSON）
- `templates/`：页面模板

备份

- 作用：加密打包后上传 Cloudflare R2
- 依赖：`openssl`、`rar`、`awscli`（脚本会尝试用 `apt` 安装）
- 执行：

```
MASTER_PASS='你的主密码' data/backup_to_r2.sh
```

- 首次准备密钥：

```
cat > data/r2.env <<'EOF'
AWS_ACCESS_KEY_ID=你的key
AWS_SECRET_ACCESS_KEY=你的secret
R2_BUCKET=你的bucket
R2_ENDPOINT=https://<account_id>.r2.cloudflarestorage.com
EOF
openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -md sha256 -salt \
  -in data/r2.env -out data/r2_secrets.enc
shred -u data/r2.env 2>/dev/null || rm -f data/r2.env
```

- 恢复：`unrar x -p你的主密码 all_*.rar`
- 定时示例：

```
30 2 * * * cd /path/to/repo && \
  MASTER_PASS='你的主密码' data/backup_to_r2.sh >> backup.log 2>&1
```

注意

- 仅按扩展名做基本类型校验，生产可按需增加内容检测
- JSONL 适合轻量场景；复杂查询/并发请考虑数据库
