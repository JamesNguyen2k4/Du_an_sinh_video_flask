# app/routes/api.py
from flask import Blueprint, request, jsonify, send_file

from app.services.storage_service import StorageService
from app.services.pptx_service import extract_slides_from_pptx, format_slides_as_text
from app.services.tts_service import TTSService
from app.config import get_config

api = Blueprint("api", __name__, url_prefix="/api")


def _normalize_voice_mode(v: str) -> str:
    v = (v or "").strip().lower()
    # accept both vi labels & internal
    if v in ["giọng nhân bản", "clone"]:
        return "clone"
    return "builtin"


@api.post("/jobs")
def create_job():
    store = StorageService()
    job_id = store.create_job()
    return jsonify({"job_id": job_id})


@api.post("/jobs/<job_id>/upload")
def upload(job_id: str):
    store = StorageService()
    kind = request.form.get("kind", "")
    file = request.files.get("file")
    try:
        path = store.save_upload(job_id, kind, file)
        return jsonify({"ok": True, "path": path})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@api.post("/jobs/<job_id>/config")
def save_config(job_id: str):
    store = StorageService()
    data = request.get_json(force=True, silent=False) or {}

    # normalize keys you already use in lecture_job
    if "voice_mode" in data:
        data["voice_mode"] = _normalize_voice_mode(data["voice_mode"])

    store.save_job_config(job_id, data)
    return jsonify({"ok": True})


@api.get("/jobs/<job_id>/config")
def get_config(job_id: str):
    store = StorageService()
    return jsonify(store.load_job_config(job_id))


@api.post("/jobs/<job_id>/clone-voice")
def clone_voice(job_id: str):
    """
    Clone giọng từ voice_sample upload hoặc file đính kèm.
    """
    store = StorageService()
    tts = TTSService()

    # allow file direct
    f = request.files.get("file")
    if f:
        sample_path = store.save_upload(job_id, "voice_sample", f)
    else:
        sample_path = store.get_uploaded(job_id, "voice_sample")

    if not sample_path:
        return jsonify({"ok": False, "error": "Missing voice_sample. Upload first."}), 400

    ok, name, err = tts.create_clone_from_mp3(sample_path)
    if not ok:
        return jsonify({"ok": False, "error": err or "clone failed"}), 400

    # also return available clones
    return jsonify({"ok": True, "display_name": name, "voices": tts.list_cloned_voice_display_names()})


@api.get("/voices/cloned")
def list_cloned_voices():
    tts = TTSService()
    return jsonify({"voices": tts.list_cloned_voice_display_names()})


@api.post("/jobs/<job_id>/extract")
def extract(job_id: str):
    store = StorageService()
    pptx = store.get_uploaded(job_id, "pptx")
    if not pptx:
        return jsonify({"ok": False, "error": "Missing PPTX. Upload first."}), 400

    slides = extract_slides_from_pptx(pptx)
    slides_text = format_slides_as_text(slides)

    store.save_slides_data(job_id, slides)
    store.save_slides_text(job_id, slides_text)

    return jsonify({"ok": True, "slides_data": slides, "slides_text": slides_text})


@api.post("/jobs/<job_id>/slides-text")
def save_slides_text(job_id: str):
    store = StorageService()
    payload = request.get_json(force=True, silent=False) or {}
    text = payload.get("slides_text", "")
    store.save_slides_text(job_id, text)
    return jsonify({"ok": True})


@api.get("/jobs/<job_id>/status")
def status(job_id: str):
    store = StorageService()
    return jsonify(store.read_progress(job_id))


@api.get("/jobs/<job_id>/result")
def result(job_id: str):
    store = StorageService()
    prog = store.read_progress(job_id)
    if prog.get("state") != "done":
        return jsonify({"ok": False, "error": "Not ready", "status": prog}), 400

    video_path = prog.get("video_path")
    if not video_path:
        return jsonify({"ok": False, "error": "Missing video_path"}), 400

    return send_file(video_path, as_attachment=True)
from rq_queue import queue
from app.jobs.lecture_job import run_lecture_job

@api.post("/jobs/<job_id>/generate")
def generate(job_id: str):
    # enqueue background job
    rq_job = queue.enqueue(run_lecture_job, job_id, job_timeout=60*60)  # 1h
    return jsonify({"ok": True, "rq_id": rq_job.id})
