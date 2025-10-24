import io
import os
import json
import hashlib
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

import tinify
from PIL import Image

from flask import Flask, request, redirect, url_for, render_template, flash, jsonify, send_from_directory, abort
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename


# Config
BASE_DIR = Path(__file__).parent.resolve()
UPLOAD_DIR = BASE_DIR / "uploads"
DATA_DIR = BASE_DIR / "data"
META_FILE = DATA_DIR / "images.jsonl"

DEFAULT_TINYPNG_KEY = "ccspxh13F7PZpMSq1WPmsvf4Y8BF9rcn"
SUPPORTED_TINYPNG_EXTS = {"png", "jpg", "jpeg"}

# 10 MB default
MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", 10 * 1024 * 1024))
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
# Default public base; can be overridden by BASE_URL or DEFAULT_BASE_URL envs
DEFAULT_BASE_URL = os.getenv("DEFAULT_BASE_URL", "https://img.zrhe2016.cc").strip()


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret")
    app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
    # If running behind reverse proxy (e.g., Nginx), honor X-Forwarded-* headers
    if os.getenv("TRUST_PROXY", "").lower() in {"1", "true", "yes"}:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)

    # Ensure directories exist
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not META_FILE.exists():
        META_FILE.touch()

    env_key = os.getenv("TINYPNG_KEY")
    if env_key is not None:
        tinify_key = env_key.strip()
    else:
        tinify_key = DEFAULT_TINYPNG_KEY
    if tinify_key:
        tinify.key = tinify_key
    else:
        tinify_key = None

    @app.route("/")
    def index():
        base = (os.getenv("BASE_URL") or DEFAULT_BASE_URL or request.url_root).rstrip("/")
        return render_template("index.html", base_url=base)

    def allowed_file(filename: str) -> bool:
        return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

    def sha256_bytes(blob: bytes) -> str:
        h = hashlib.sha256()
        h.update(blob)
        return h.hexdigest()

    def optimize_with_tinify(blob: bytes, ext: str) -> tuple[bytes, bool]:
        if not tinify_key or ext.lower() not in SUPPORTED_TINYPNG_EXTS:
            return blob, False
        try:
            source = tinify.from_buffer(blob)
            optimized_blob = source.to_buffer()
        except tinify.Error as exc:  # type: ignore[attr-defined]
            app.logger.warning("TinyPNG optimization failed for %s: %s", ext, exc)
            return blob, False
        return optimized_blob, True

    def convert_to_png(blob: bytes, ext: str) -> tuple[bytes, bool]:
        if ext.lower() == "png":
            return blob, False
        try:
            with Image.open(io.BytesIO(blob)) as image:
                if getattr(image, "is_animated", False):
                    try:
                        image.seek(0)
                    except EOFError:
                        pass
                if image.mode not in {"RGB", "RGBA"}:
                    # Preserve alpha channel where available
                    if "A" in image.mode:
                        image = image.convert("RGBA")
                    else:
                        image = image.convert("RGB")
                else:
                    image = image.copy()
                buffer = io.BytesIO()
                image.save(buffer, format="PNG")
                return buffer.getvalue(), True
        except Exception as exc:  # noqa: BLE001
            app.logger.warning("PNG conversion failed for %s: %s", ext, exc)
        return blob, False

    def generate_id() -> str:
        return hashlib.sha1(f"{time.time_ns()}-{os.getpid()}".encode()).hexdigest()[:12]

    def build_public_url(image_id: str, ext: str) -> str:
        base = (os.getenv("BASE_URL") or DEFAULT_BASE_URL or request.url_root).rstrip("/")
        return f"{base}/img/{image_id}.{ext}"

    def append_meta(record: Dict[str, Any]) -> None:
        with open(META_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def load_all() -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        if not META_FILE.exists():
            return items
        with open(META_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return items

    def find_by_id(image_id: str) -> Optional[Dict[str, Any]]:
        for item in load_all()[::-1]:
            if item.get("id") == image_id:
                return item
        return None

    def rewrite_meta_excluding(exclude_id: str) -> None:
        items = load_all()
        new_items = [it for it in items if it.get("id") != exclude_id]
        tmp = META_FILE.with_suffix(".jsonl.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            for it in new_items:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")
        os.replace(tmp, META_FILE)

    def admin_token() -> Optional[str]:
        tok = os.getenv("ADMIN_TOKEN", "").strip()
        return tok or None

    def require_token(token_from_client: Optional[str]) -> bool:
        tok = admin_token()
        if not tok:
            return True  # no token set -> allow
        return token_from_client == tok

    @app.route("/upload", methods=["POST"]) 
    def upload():
        if "image" not in request.files:
            flash("未找到文件字段 image")
            return redirect(url_for("index"))
        file = request.files["image"]
        if file.filename == "":
            flash("未选择文件")
            return redirect(url_for("index"))
        if not allowed_file(file.filename):
            flash("不支持的文件类型")
            return redirect(url_for("index"))

        original_name = secure_filename(file.filename)
        ext = original_name.rsplit(".", 1)[1].lower()
        original_ext = ext

        blob = file.read()
        original_size = len(blob)
        if original_size == 0:
            flash("空文件")
            return redirect(url_for("index"))
        if original_size > MAX_CONTENT_LENGTH:
            flash("文件过大")
            return redirect(url_for("index"))

        converted_blob, converted = convert_to_png(blob, ext)
        if converted:
            blob = converted_blob
            ext = "png"

        optimized_blob, optimized = optimize_with_tinify(blob, ext)
        final_blob = optimized_blob
        final_size = len(final_blob)
        final_digest = sha256_bytes(final_blob)

        image_id = generate_id()
        save_name = f"{image_id}.{ext}"
        save_path = UPLOAD_DIR / save_name
        with open(save_path, "wb") as out:
            out.write(final_blob)

        url = build_public_url(image_id, ext)
        record = {
            "id": image_id,
            "ext": ext,
            "filename": original_name,
            "stored_name": save_name,
            "path": str(save_path.relative_to(BASE_DIR)),
            "size": final_size,
            "sha256": final_digest,
            "original_size": original_size,
            "original_ext": original_ext,
            "uploaded_at": datetime.utcnow().isoformat() + "Z",
            "url": url,
            "optimized": optimized,
            "converted": converted,
        }
        append_meta(record)

        # Render result page with links
        return render_template(
            "uploaded.html",
            record=record,
            direct_url=url,
            markdown=f"![{original_name}]({url})",
            html=f"<img src=\"{url}\" alt=\"{original_name}\">",
            delete_token=admin_token(),
        )

    @app.post("/api/upload")
    def api_upload():
        if "image" not in request.files:
            return jsonify({"error": "field 'image' required"}), 400
        file = request.files["image"]
        if file.filename == "":
            return jsonify({"error": "empty filename"}), 400
        if not allowed_file(file.filename):
            return jsonify({"error": "unsupported file type"}), 400

        original_name = secure_filename(file.filename)
        ext = original_name.rsplit(".", 1)[1].lower()
        original_ext = ext
        blob = file.read()
        original_size = len(blob)
        if original_size == 0:
            return jsonify({"error": "empty file"}), 400
        if original_size > MAX_CONTENT_LENGTH:
            return jsonify({"error": "file too large"}), 413

        converted_blob, converted = convert_to_png(blob, ext)
        if converted:
            blob = converted_blob
            ext = "png"

        optimized_blob, optimized = optimize_with_tinify(blob, ext)
        final_blob = optimized_blob
        final_size = len(final_blob)
        final_digest = sha256_bytes(final_blob)
        image_id = generate_id()
        save_name = f"{image_id}.{ext}"
        save_path = UPLOAD_DIR / save_name
        with open(save_path, "wb") as out:
            out.write(final_blob)

        url = build_public_url(image_id, ext)
        record = {
            "id": image_id,
            "ext": ext,
            "filename": original_name,
            "stored_name": save_name,
            "path": str(save_path.relative_to(BASE_DIR)),
            "size": final_size,
            "sha256": final_digest,
            "original_size": original_size,
            "original_ext": original_ext,
            "uploaded_at": datetime.utcnow().isoformat() + "Z",
            "url": url,
            "optimized": optimized,
            "converted": converted,
        }
        append_meta(record)

        return jsonify({
            "id": image_id,
            "url": url,
            "markdown": f"![{original_name}]({url})",
            "html": f"<img src=\"{url}\" alt=\"{original_name}\">",
            "size": final_size,
            "sha256": final_digest,
            "original_size": original_size,
            "optimized": optimized,
            "converted": converted,
            "extension": ext,
            "original_ext": original_ext,
        })

    @app.get("/img/<path:filename>")
    def serve_image(filename: str):
        # filename expected like "<id>.<ext>"
        # Prevent path traversal by only serving from upload dir
        safe_name = secure_filename(filename)
        if safe_name != filename:
            abort(404)
        file_path = UPLOAD_DIR / safe_name
        if not file_path.exists():
            abort(404)
        return send_from_directory(UPLOAD_DIR, safe_name, as_attachment=False)

    @app.get("/links/<image_id>")
    def links(image_id: str):
        record = find_by_id(image_id)
        if not record:
            abort(404)
        url = record["url"]
        return jsonify({
            "id": image_id,
            "url": url,
            "markdown": f"![{record['filename']}]({url})",
            "html": f"<img src=\"{url}\" alt=\"{record['filename']}\">",
            "record": record,
        })

    @app.get("/gallery")
    def gallery():
        items = load_all()[::-1]

        def month_label(uploaded_at: Optional[str]) -> str:
            if not uploaded_at:
                return "未分类"
            normalized = uploaded_at.replace("Z", "+00:00")
            try:
                dt = datetime.fromisoformat(normalized)
            except ValueError:
                return "未分类"
            return dt.strftime("%Y年%m月")

        grouped: List[Dict[str, Any]] = []
        buckets: Dict[str, List[Dict[str, Any]]] = {}
        for item in items:
            label = month_label(item.get("uploaded_at"))
            bucket = buckets.get(label)
            if bucket is None:
                bucket = []
                buckets[label] = bucket
                grouped.append({"label": label, "entries": bucket})
            bucket.append(item)

        return render_template("gallery.html", groups=grouped, delete_token=admin_token())

    @app.post("/delete/<image_id>")
    def delete_image(image_id: str):
        if not require_token(request.form.get("token")):
            flash("无权限：缺少或错误的删除令牌")
            return redirect(url_for("gallery"))
        rec = find_by_id(image_id)
        if not rec:
            flash("未找到该图片")
            return redirect(url_for("gallery"))
        # remove file
        path = rec.get("path")
        try:
            if path:
                abs_path = (BASE_DIR / path).resolve()
                # ensure inside uploads dir
                if abs_path.is_file() and abs_path.parent == UPLOAD_DIR.resolve():
                    abs_path.unlink(missing_ok=True)
        except Exception:
            pass
        # rewrite metadata without the record
        rewrite_meta_excluding(image_id)
        flash(f"已删除：{rec.get('filename', image_id)}")
        return redirect(url_for("gallery"))

    @app.post("/api/delete/<image_id>")
    def api_delete(image_id: str):
        if not require_token(request.values.get("token")):
            return jsonify({"error": "forbidden"}), 403
        rec = find_by_id(image_id)
        if not rec:
            return jsonify({"error": "not_found"}), 404
        # delete file
        path = rec.get("path")
        try:
            if path:
                abs_path = (BASE_DIR / path).resolve()
                if abs_path.is_file() and abs_path.parent == UPLOAD_DIR.resolve():
                    abs_path.unlink(missing_ok=True)
        except Exception as e:
            return jsonify({"error": "delete_failed", "detail": str(e)}), 500
        rewrite_meta_excluding(image_id)
        return jsonify({"ok": True, "deleted": image_id})

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=True)
