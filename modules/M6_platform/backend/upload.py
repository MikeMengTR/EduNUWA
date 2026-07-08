import os
import sys

# 确保能 import M1 模块
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from flask import request
from auth import require_auth, require_role, ok, err
from teachers import get_teacher_dir, list_all_teachers

UPLOAD_FOLDER = os.path.join(_project_root, "data", "_uploads")
ALLOWED_EXTENSIONS = {"mp4", "mkv", "mov", "avi", "wav", "mp3", "m4a", "flac", "pdf", "pptx"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def register_routes(app):
    @app.route("/api/v1/uploads", methods=["POST"])
    @require_role("teacher")
    def upload_material():
        if "file" not in request.files:
            return err("请选择文件")

        file = request.files["file"]
        if file.filename == "":
            return err("请选择文件")
        if not allowed_file(file.filename):
            return err(f"不支持的文件类型，支持: {', '.join(ALLOWED_EXTENSIONS)}")

        # 找到教师的 teacher_id
        all_t = list_all_teachers()
        card = next((t for t in all_t if t.get("user_id") == request.user_id), None)
        if not card:
            return err("请先创建教师卡片", 4040, 404)

        teacher_id = card["teacher_id"]
        teacher_dir = get_teacher_dir(teacher_id)
        output_dir = teacher_dir

        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        ext = file.filename.rsplit(".", 1)[1].lower()
        import secrets
        safe_name = f"{secrets.token_hex(8)}.{ext}"
        save_path = os.path.join(UPLOAD_FOLDER, safe_name)
        file.save(save_path)

        try:
            from modules.M1_ingest import submit_ingest_task

            task_id = submit_ingest_task(
                teacher_id=teacher_id,
                upload_paths=[save_path],
                output_dir=output_dir,
                config={
                    "enable_refine": request.form.get("refine", "true") == "true",
                    "save_audio_samples": True,
                },
            )
            return ok({
                "task_id": task_id,
                "filename": file.filename,
                "teacher_id": teacher_id,
            }, "上传成功，开始处理")
        except ImportError as e:
            return ok({
                "task_id": None,
                "filename": file.filename,
                "teacher_id": teacher_id,
                "warning": f"M1 模块未加载: {e}，文件已保存但未触发处理",
            }, "文件已保存（M1 未加载）")

    @app.route("/api/v1/tasks/<task_id>", methods=["GET"])
    @require_auth
    def query_task(task_id):
        try:
            from modules.M1_ingest import query_ingest_progress
            info = query_ingest_progress(task_id)
            if info is None:
                return err("任务不存在", 4040, 404)
            return ok(info)
        except ImportError:
            return err("M1 模块未加载", 5030, 503)
