# app/config.py
import os
from dataclasses import dataclass

@dataclass(frozen=True)
class AppConfig:
    # External tools
    LIBREOFFICE_PATH: str = os.getenv(
        "LIBREOFFICE_PATH",
        r"C:\Program Files\LibreOffice\program\soffice.exe"
    )
    POPPLER_PATH: str | None = os.getenv("POPPLER_PATH") or None

    # Storage
    TMP_DIR: str = os.getenv("TMP_DIR", "./tmp")
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "./uploads")
    RESULTS_DIR: str = os.getenv("RESULTS_DIR", "./results")
    CLONED_VOICES_DIR: str = os.getenv("CLONED_VOICES_DIR", "./cloned_voices")
    TTS_TMP_DIR: str = os.getenv("TTS_TMP_DIR", "./tmp/tts")
    FFMPEG_PATH: str = os.getenv("FFMPEG_PATH", "ffmpeg")
    PIP_RATIO: float = float(os.getenv("PIP_RATIO", "0.10"))
    PIP_MARGIN: int = int(os.getenv("PIP_MARGIN", "50"))
    PIP_FPS: int = int(os.getenv("PIP_FPS", "25"))
    FONT_PATH: str = os.getenv("FONT_PATH", "DejaVuSans.ttf")
    SADTALKER_CHECKPOINT_DIR: str = os.getenv("SADTALKER_CHECKPOINT_DIR", "./checkpoints")
    SADTALKER_CONFIG_DIR: str = os.getenv("SADTALKER_CONFIG_DIR", "./src/config")
    SADTALKER_RESULTS_DIR: str = os.getenv("SADTALKER_RESULTS_DIR", "./results")

def get_config() -> AppConfig:
    return AppConfig()
