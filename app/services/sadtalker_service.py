# app/services/sadtalker_service.py
import os
import shutil
import uuid
from dataclasses import dataclass
from typing import Optional

from app.config import get_config
from src.gradio_demo import SadTalker  # dùng wrapper hiện tại của bạn


@dataclass
class SadTalkerParams:
    preprocess_type: str = "crop"
    is_still_mode: bool = False
    enhancer: bool = False
    batch_size: int = 2
    size_of_image: int = 256
    pose_style: int = 0
    exp_scale: float = 1.0


class SadTalkerService:
    """
    Wrapper an toàn cho Flask/Worker:
    - copy input vào temp_dir rồi gọi SadTalker.test() (vì test() sẽ move)
    """

    def __init__(self):
        cfg = get_config()
        self.cfg = cfg
        self._sad = SadTalker(
            checkpoint_path=cfg.SADTALKER_CHECKPOINT_DIR,
            config_path=cfg.SADTALKER_CONFIG_DIR,
            lazy_load=True
        )

    def generate(self, job_id: str, source_image_path: str, audio_path: str, params: SadTalkerParams) -> str:
        tmp_dir = os.path.join(self.cfg.TMP_DIR, "sadtalker_inputs", job_id, str(uuid.uuid4()))
        os.makedirs(tmp_dir, exist_ok=True)

        # copy để SadTalker.move không làm mất file gốc
        src_copy = os.path.join(tmp_dir, os.path.basename(source_image_path))
        aud_copy = os.path.join(tmp_dir, os.path.basename(audio_path))
        shutil.copy2(source_image_path, src_copy)
        shutil.copy2(audio_path, aud_copy)

        # output SadTalker vào results/<job_id>/sadtalker/...
        out_dir = os.path.join(self.cfg.RESULTS_DIR, job_id, "sadtalker")
        os.makedirs(out_dir, exist_ok=True)

        return self._sad.test(
            source_image=src_copy,
            driven_audio=aud_copy,
            preprocess=params.preprocess_type,
            still_mode=params.is_still_mode,
            use_enhancer=params.enhancer,
            batch_size=params.batch_size,
            size=params.size_of_image,
            pose_style=params.pose_style,
            exp_scale=params.exp_scale,
            result_dir=out_dir,
        )
