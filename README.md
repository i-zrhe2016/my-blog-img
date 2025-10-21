Image Host（图床）

概述

轻量本地图床服务（Flask）：网页上传、图库、直链与 API，数据存于本地文件系统。

特性

- 网页上传与预览（/）
- 自动将非 PNG 图片转换为 PNG
- 上传后自动通过 TinyPNG 压缩 PNG / JPEG
- 图库浏览（/gallery）
- 直链访问（/img/<id>.<ext>）
- 简单 API：上传、查询、删除
- 本地 JSONL 元数据（data/images.jsonl）

环境要求

- Python 3.10+
- 可访问 TinyPNG API 的网络（默认使用内置 API key，可通过环境变量覆盖）

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

本地验证

- 使用 Flask `test_client()` 可模拟上传，检查响应中的 `converted`、`optimized`、`size` 等字段是否符合预期。
- 无外网时可 monkeypatch `tinify.from_buffer`，示例：

```python
import io
from PIL import Image
import tinify

class FakeResult:
    def __init__(self, data: bytes):
        self._data = data
    def to_buffer(self) -> bytes:
        return self._data[: max(1, len(self._data)//2)]

tinify.from_buffer = lambda data: FakeResult(data)

from app import create_app

app = create_app()
client = app.test_client()

img = Image.new('RGB', (20, 20), color=(0, 128, 255))
buf = io.BytesIO()
img.save(buf, format='JPEG')

resp = client.post(
    '/api/upload',
    data={'image': (io.BytesIO(buf.getvalue()), 'demo.jpg')},
    content_type='multipart/form-data'
)
print(resp.json)
```

配置

- `PORT`：服务端口，默认 `8000`
- `BASE_URL`：生成外链基地址（不设则按请求推断）
- `DEFAULT_BASE_URL`：默认外链基地址，默认 `https://img.zrhe2016.cc`
- `MAX_CONTENT_LENGTH`：最大上传字节数，默认 10MB
- `TRUST_PROXY`：`1/true` 时信任反代请求头
- `SECRET_KEY`：Flask 会话密钥
- `ADMIN_TOKEN`：设置后开启受保护删除接口
- `TINYPNG_KEY`：TinyPNG API Key，默认使用内置密钥，可在生产环境自行替换

TinyPNG 压缩

- TinyPNG 会处理 PNG 及经转换后的 PNG（包括原始 JPG/JPEG/GIF/WebP 等）。
- 若未设置 `TINYPNG_KEY`，应用会回退到内置 key；建议线上环境使用自己的 key 以避免额度耗尽。
- TinyPNG 服务不可用时（网络受限或请求失败）会跳过压缩并记录日志，上传仍会成功。

格式转换

- 所有非 PNG 图片（如 JPG/JPEG/GIF/WebP）都会先转换为 PNG 再保存，并保留原始尺寸与扩展名信息。
- 转换后再交由 TinyPNG 压缩，保证最终文件体积最小化。

API

- `POST /api/upload`
  - 表单：`multipart/form-data`，字段名 `image`
  - 响应：`{ id, url, markdown, html, size, original_size, sha256, optimized, converted, extension, original_ext }`
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
- TinyPNG 会在转换后的 PNG 上执行压缩；若服务不可用则直接存原始 PNG
- 在无外网环境下可通过 monkeypatch `tinify.from_buffer` 的方式模拟压缩流程，详见 `app.py` 中测试示例
- GIF/WebP 等动画素材转换为 PNG 时会只保留首帧，若需保留动画请谨慎使用
