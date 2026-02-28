# app/services/storage_service.py
import os
import json
import uuid
from dataclasses import asdict
from typing import Any, Optional

from werkzeug.datastructures import FileStorage

from app.config import get_config


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


class StorageService:
    """
    Flow B:
    uploads/<job_id>/...
    results/<job_id>/...
    """

    def __init__(self):
        self.cfg = get_config()
        _ensure_dir(self.cfg.UPLOAD_DIR)
        _ensure_dir(self.cfg.RESULTS_DIR)
        _ensure_dir(self.cfg.TMP_DIR)

    def create_job(self) -> str:
        job_id = str(uuid.uuid4())
        _ensure_dir(self.job_upload_dir(job_id))
        _ensure_dir(self.job_result_dir(job_id))
        return job_id

    # ---- Paths ----
    def job_upload_dir(self, job_id: str) -> str:
        return os.path.join(self.cfg.UPLOAD_DIR, job_id)

    def job_result_dir(self, job_id: str) -> str:
        return os.path.join(self.cfg.RESULTS_DIR, job_id)

    def upload_path(self, job_id: str, name: str) -> str:
        return os.path.join(self.job_upload_dir(job_id), name)

    def result_path(self, job_id: str, name: str) -> str:
        return os.path.join(self.job_result_dir(job_id), name)

    # ---- Uploads ----
    def save_upload(self, job_id: str, kind: str, file: FileStorage) -> str:
        """
        kind:
          - source_image  -> uploads/<job_id>/source_image.png
          - pptx          -> uploads/<job_id>/slides.pptx
          - voice_sample  -> uploads/<job_id>/voice_sample.mp3
        """
        if file is None:
            raise ValueError("file is required")

        kind = (kind or "").strip()
        filename = (file.filename or "").lower()

        if kind == "source_image":
            ext = os.path.splitext(filename)[1] or ".png"
            path = self.upload_path(job_id, f"source_image{ext}")
        elif kind == "pptx":
            path = self.upload_path(job_id, "slides.pptx")
        elif kind == "voice_sample":
            ext = os.path.splitext(filename)[1] or ".mp3"
            path = self.upload_path(job_id, f"voice_sample{ext}")
        else:
            raise ValueError(f"Unknown upload kind: {kind}")

        _ensure_dir(os.path.dirname(path))
        file.save(path)
        return path

    def get_uploaded(self, job_id: str, kind: str) -> Optional[str]:
        up = self.job_upload_dir(job_id)
        if not os.path.isdir(up):
            return None

        if kind == "pptx":
            p = os.path.join(up, "slides.pptx")
            return p if os.path.isfile(p) else None

        if kind == "source_image":
            # allow any image ext saved
            for fn in os.listdir(up):
                if fn.startswith("source_image"):
                    p = os.path.join(up, fn)
                    return p if os.path.isfile(p) else None
            return None

        if kind == "voice_sample":
            for fn in os.listdir(up):
                if fn.startswith("voice_sample"):
                    p = os.path.join(up, fn)
                    return p if os.path.isfile(p) else None
            return None

        return None

    # ---- JSON / Text persisted per job ----
    def save_job_config(self, job_id: str, data: dict) -> str:
        path = self.result_path(job_id, "config.json")
        _ensure_dir(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data or {}, f, ensure_ascii=False, indent=2)
        return path

    def load_job_config(self, job_id: str) -> dict:
        path = self.result_path(job_id, "config.json")
        if not os.path.isfile(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_slides_text(self, job_id: str, text: str) -> str:
        path = self.result_path(job_id, "slides_text.md")
        _ensure_dir(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as f:
            f.write(text or "")
        return path

    def load_slides_text(self, job_id: str) -> str:
        path = self.result_path(job_id, "slides_text.md")
        if not os.path.isfile(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def save_slides_data(self, job_id: str, slides_data: list[dict]) -> str:
        path = self.result_path(job_id, "slides_data.json")
        _ensure_dir(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as f:
            json.dump(slides_data or [], f, ensure_ascii=False, indent=2)
        return path

    def load_slides_data(self, job_id: str) -> list[dict]:
        path = self.result_path(job_id, "slides_data.json")
        if not os.path.isfile(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    # ---- Progress ----
    def write_progress(self, job_id: str, payload: dict) -> str:
        path = self.result_path(job_id, "progress.json")
        _ensure_dir(os.path.dirname(path))  
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload or {}, f, ensure_ascii=False, indent=2)
        return path

    def read_progress(self, job_id: str) -> dict:
        path = self.result_path(job_id, "progress.json")
        if not os.path.isfile(path):
            return {"state": "created"}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
