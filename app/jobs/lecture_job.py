# app/jobs/lecture_job.py
import os
import time

from app.services.storage_service import StorageService
from app.services.lecture_service import LectureParams, build_lecture_from_inputs
from app.services.sadtalker_service import SadTalkerService


def run_lecture_job(job_id: str) -> dict:
    store = StorageService()

    # ✅ đảm bảo thư mục results/<job_id> tồn tại (kể cả khi job_id không qua /jobs)
    os.makedirs(store.job_result_dir(job_id), exist_ok=True)

    cfg = store.load_job_config(job_id)

    source_image = store.get_uploaded(job_id, "source_image")
    pptx = store.get_uploaded(job_id, "pptx")
    slides_text = store.load_slides_text(job_id)

    # progress callback -> ghi progress.json
    def progress_cb(i: int, total: int, msg: str):
        store.write_progress(job_id, {
            "state": "running",
            "current": i,
            "total": total,
            "message": msg,
            "updated_at": int(time.time())
        })

    store.write_progress(job_id, {"state": "running", "message": "Starting...", "updated_at": int(time.time())})

    params = LectureParams(
        language=cfg.get("language", "vi"),
        voice_mode=cfg.get("voice_mode", "builtin"),
        gender=cfg.get("gender", "Nữ"),
        builtin_voice=cfg.get("builtin_voice"),
        cloned_voice_name=cfg.get("cloned_voice_name"),
        cloned_lang=cfg.get("cloned_lang"),
        preprocess_type=cfg.get("preprocess_type", "crop"),
        is_still_mode=bool(cfg.get("is_still_mode", False)),
        enhancer=bool(cfg.get("enhancer", False)),
        batch_size=int(cfg.get("batch_size", 2)),
        size_of_image=int(cfg.get("size_of_image", 256)),
        pose_style=int(cfg.get("pose_style", 0)),
        speech_rate=float(cfg.get("speech_rate", 1.0)),
    )

    sad_service = SadTalkerService()
    sad_talker_obj = sad_service._sad

    try:
        video_path, status = build_lecture_from_inputs(
            sad_talker=sad_talker_obj,
            pptx_path=pptx,
            source_image_path=source_image,
            params=params,
            user_slides_text=slides_text,
            job_id=job_id,
            progress_cb=progress_cb
        )
    except Exception as e:
        store.write_progress(job_id, {
            "state": "failed",
            "message": f"Exception: {e}",
            "updated_at": int(time.time())
        })
        return {"ok": False, "status": str(e)}

    if not video_path:
        store.write_progress(job_id, {"state": "failed", "message": status, "updated_at": int(time.time())})
        return {"ok": False, "status": status}

    # ✅ normalize tuyệt đối để Flask send_file không bị lệch path theo cwd/app/
    video_path = os.path.abspath(video_path)

    # ✅ nếu file chưa tồn tại thật, fail luôn để UI không gọi result bị 500
    if not os.path.exists(video_path):
        store.write_progress(job_id, {
            "state": "failed",
            "message": "Video path returned but file not found on disk",
            "video_path": video_path,
            "cwd": os.getcwd(),
            "updated_at": int(time.time())
        })
        return {"ok": False, "status": "video file not found", "video_path": video_path}

    store.write_progress(job_id, {
        "state": "done",
        "message": status,
        "video_path": video_path,
        "updated_at": int(time.time())
    })
    return {"ok": True, "video_path": video_path, "status": status}