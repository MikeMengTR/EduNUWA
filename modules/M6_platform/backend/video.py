import json
import os
import secrets
import time
import re
from datetime import datetime, timezone
from flask import request, Response
from auth import require_auth, require_role, ok, err
from teachers import get_teacher_dir, load_teacher_card, list_all_teachers

ALLOWED_VIDEO_EXT = {"mp4", "webm", "mkv", "mov", "avi"}

def get_videos_dir(teacher_id):
    d = os.path.join(get_teacher_dir(teacher_id), "videos")
    os.makedirs(d, exist_ok=True)
    return d

def get_video_manifest(teacher_id):
    path = os.path.join(get_videos_dir(teacher_id), "videos_manifest.json")
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_video_manifest(teacher_id, manifest):
    path = os.path.join(get_videos_dir(teacher_id), "videos_manifest.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

def register_routes(app):
    @app.route("/api/v1/videos/upload", methods=["POST"])
    @require_role("teacher")
    def upload_video():
        if "file" not in request.files:
            return err("请选择视频文件")

        file = request.files["file"]
        if not file.filename:
            return err("请选择视频文件")

        ext = file.filename.rsplit(".", 1)[-1].lower()
        if ext not in ALLOWED_VIDEO_EXT:
            return err(f"不支持的格式，允许: {', '.join(ALLOWED_VIDEO_EXT)}")

        all_t = list_all_teachers()
        card = next((t for t in all_t if t.get("user_id") == request.user_id), None)
        if not card:
            return err("请先创建教师卡片", 4040, 404)

        teacher_id = card["teacher_id"]
        video_id = f"VID_{secrets.token_hex(6)}"
        safe_name = f"{video_id}.{ext}"
        videos_dir = get_videos_dir(teacher_id)
        save_path = os.path.join(videos_dir, safe_name)
        file.save(save_path)

        title = request.form.get("title", file.filename.rsplit(".", 1)[0])
        description = request.form.get("description", "")

        manifest = get_video_manifest(teacher_id)
        entry = {
            "video_id": video_id,
            "title": title,
            "description": description,
            "filename": safe_name,
            "teacher_id": teacher_id,
            "teacher_name": card.get("display_name", card.get("real_name", "")),
            "subject": card.get("subject", ""),
            "file_size": os.path.getsize(save_path),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        manifest.append(entry)
        save_video_manifest(teacher_id, manifest)

        return ok(entry, "视频上传成功")

    @app.route("/api/v1/videos", methods=["GET"])
    @require_auth
    def list_videos():
        role = request.args.get("role", "")
        subject = request.args.get("subject", "").lower()

        all_videos = []
        if os.path.exists(os.path.join(os.path.dirname(__file__), "..", "data", "teachers")):
            for tid in os.listdir(os.path.join(os.path.dirname(__file__), "..", "data", "teachers")):
                manifest = get_video_manifest(tid)
                for v in manifest:
                    v["_tid"] = tid
                    all_videos.append(v)

        # 教师只能看自己的
        if role == "teacher":
            all_t = list_all_teachers()
            card = next((t for t in all_t if t.get("user_id") == request.user_id), None)
            if card:
                all_videos = [v for v in all_videos if v.get("teacher_id") == card["teacher_id"]]

        if subject:
            all_videos = [v for v in all_videos if subject in v.get("subject", "").lower()]

        all_videos.sort(key=lambda v: v.get("created_at", ""), reverse=True)
        return ok(all_videos)

    @app.route("/api/v1/videos/<video_id>", methods=["GET"])
    @require_auth
    def get_video(video_id):
        v = _find_video(video_id)
        if not v:
            return err("视频不存在", 4040, 404)
        return ok(v)

    @app.route("/api/v1/videos/<video_id>", methods=["DELETE"])
    @require_role("teacher")
    def delete_video(video_id):
        v = _find_video(video_id)
        if not v:
            return err("视频不存在", 4040, 404)

        tid = v["_tid"]
        path = os.path.join(get_videos_dir(tid), v["filename"])
        if os.path.exists(path):
            os.remove(path)

        manifest = get_video_manifest(tid)
        manifest = [m for m in manifest if m["video_id"] != video_id]
        save_video_manifest(tid, manifest)
        return ok(None, "删除成功")

    @app.route("/api/v1/videos/<video_id>/stream", methods=["GET"])
    @require_auth
    def stream_video(video_id):
        v = _find_video(video_id)
        if not v:
            return err("视频不存在", 4040, 404)

        path = os.path.join(get_videos_dir(v["_tid"]), v["filename"])
        file_size = os.path.getsize(path)
        range_header = request.headers.get("Range")

        if not range_header:
            # 全量返回
            def generate():
                with open(path, "rb") as f:
                    while chunk := f.read(8192):
                        yield chunk
            return Response(generate(), mimetype="video/mp4",
                          headers={"Content-Length": str(file_size),
                                   "Accept-Ranges": "bytes"})

        # Range 请求 — 支持拖动
        m = re.match(r"bytes=(\d+)-(\d*)", range_header)
        if not m:
            return err("无效的 Range 请求", 4000, 400)

        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else min(start + 1024 * 1024, file_size - 1)

        if start >= file_size:
            return err("Range 超出文件大小", 4160, 416)

        def generate_range():
            with open(path, "rb") as f:
                f.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    chunk = f.read(min(8192, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        return Response(generate_range(), status=206, mimetype="video/mp4",
                      headers={
                          "Content-Range": f"bytes {start}-{end}/{file_size}",
                          "Accept-Ranges": "bytes",
                          "Content-Length": str(end - start + 1),
                      })

    @app.route("/api/v1/teachers/<teacher_id>/videos", methods=["GET"])
    @require_auth
    def teacher_videos(teacher_id):
        manifest = get_video_manifest(teacher_id)
        return ok(manifest)


def _find_video(video_id):
    teachers_root = os.path.join(os.path.dirname(__file__), "..", "data", "teachers")
    if not os.path.exists(teachers_root):
        return None
    for tid in os.listdir(teachers_root):
        manifest = get_video_manifest(tid)
        for v in manifest:
            if v["video_id"] == video_id:
                v["_tid"] = tid
                return v
    return None
