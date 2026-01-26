# app/routes/media.py
import os
from flask import Blueprint, jsonify, send_file, abort

from app.services.storage_service import StorageService

media = Blueprint("media", __name__, url_prefix="/media")


def _safe_realpath(p: str) -> str:
    return os.path.realpath(p)


def _is_under_dir(path: str, root_dir: str) -> bool:
    path = _safe_realpath(path)
    root_dir = _safe_realpath(root_dir)
    return path.startswith(root_dir + os.sep) or path == root_dir


def _get_video_path_from_progress(job_id: str) -> str | None:
    store = StorageService()
    prog = store.read_progress(job_id)
    if prog.get("state") != "done":
        return None
    video_path = prog.get("video_path")
    if not video_path:
        return None

    # Chặn path traversal: video_path phải nằm trong results/<job_id>/
    results_root = store.job_result_dir(job_id)
    if not _is_under_dir(video_path, results_root):
        return None

    if not os.path.isfile(video_path):
        return None
    return video_path


@media.get("/jobs/<job_id>/video")
def stream_video(job_id: str):
    """
    Xem trực tiếp (inline) trong <video>.
    """
    video_path = _get_video_path_from_progress(job_id)
    if not video_path:
        return jsonify({"ok": False, "error": "Video not ready"}), 404

    # inline để video tag play được
    return send_file(video_path, mimetype="video/mp4", as_attachment=False)


@media.get("/jobs/<job_id>/download/video")
def download_video(job_id: str):
    """
    Download video (attachment). (Tuỳ chọn - nếu bạn muốn tách riêng khỏi API)
    """
    video_path = _get_video_path_from_progress(job_id)
    if not video_path:
        return jsonify({"ok": False, "error": "Video not ready"}), 404

    return send_file(video_path, mimetype="video/mp4", as_attachment=True, download_name="lecture_final.mp4")


@media.get("/jobs/<job_id>/uploads/<kind>")
def get_upload(job_id: str, kind: str):
    """
    (Tuỳ chọn) Serve lại file upload để preview nếu cần:
    kind: source_image | pptx | voice_sample
    """
    store = StorageService()
    p = store.get_uploaded(job_id, kind)
    if not p or not os.path.isfile(p):
        abort(404)

    # Chặn path traversal: file upload phải nằm trong uploads/<job_id>/
    uploads_root = store.job_upload_dir(job_id)
    if not _is_under_dir(p, uploads_root):
        abort(403)

    return send_file(p, as_attachment=False)
