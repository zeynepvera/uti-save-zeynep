import cv2
import sys
import os
import uuid
import shutil
import datetime
import time
import logging
import base64
import numpy as np

sys.path.append(os.path.join(os.path.dirname(__file__), '../../../../'))

from sdks.novavision.src.base.component import Component
from sdks.novavision.src.helper.executor import Executor
from components.VideoSave.src.utils.response import build_response
from components.VideoSave.src.models.PackageModel import PackageModel
from sdks.novavision.src.base.application import Application
from sdks.novavision.src.media.image import Image

from components.VideoSave.src.utils.utils import buffer_push_frame

logging.basicConfig(level=logging.INFO)


class VideoSave(Component):
    application = Application()

    def __init__(self, request, bootstrap):
        super().__init__(request, bootstrap)
        self.request.model = PackageModel(**(self.request.data))

        self.image = self.request.get_param("inputImage")
        self.input_frames = []

        self.record_duration = self.request.get_param("recordDuration")
        self.title = self.request.get_param("videoTitle") or "untitled_video"
        self.user_fps = self.request.get_param("configFps")
        self.system_control = self.request.get_param("systemControl")
        raw_target = self.request.get_param("configTargetDirectory")
        if isinstance(raw_target, dict):
            self.target_type = raw_target.get("value", {}).get("value", "TargetLocal")
        else:
            self.target_type = raw_target or "TargetLocal"

        self.local_path = "/storage/videos"
        os.makedirs(self.local_path, exist_ok=True)

        self.temp_dir = "/storage/temp"
        os.makedirs(self.temp_dir, exist_ok=True)

        self.logger = logging.getLogger(__name__)
        self.saved_path = None
        self._normalize_inputs()  # <— eklendi

    @staticmethod
    def bootstrap(config: dict) -> dict:
        buffer = buffer_push_frame(config=config)
        return buffer

    def _normalize_inputs(self):
        try:
            self.record_duration = float(self.record_duration) if self.record_duration is not None else 0.0
        except Exception:
            self.record_duration = 0.0
        try:
            self.user_fps = int(self.user_fps) if self.user_fps is not None else 25
        except Exception:
            self.user_fps = 25
        self.user_fps = max(1, min(60, self.user_fps))

    def add_frame(self, frame):
        if frame is None:
            return
        if not isinstance(frame, np.ndarray):
            # base64 ya da başka tip ise dönüştür
            frame = self._to_ndarray(frame)
        if frame is None:
            return
        if frame.dtype != np.uint8:
            frame = frame.astype(np.uint8)
        if frame.ndim == 2:
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        self.input_frames.append(frame)

    def _to_ndarray(self, img):
        if isinstance(img, np.ndarray):
            return img
        if isinstance(img, str):
            try:
                raw = base64.b64decode(img)
                arr = np.frombuffer(raw, dtype=np.uint8)
                dec = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                return dec
            except Exception:
                return None
        return None

    def get_final_fps(self, frames):
        user_fps = self.user_fps
        control_val = self.system_control
        if isinstance(control_val, dict):
            control_val = control_val.get("value", {}).get("value", "True")
        control_val = str(control_val).lower() in ("true", "1", "yes")

        if not control_val:
            return user_fps

        if self.record_duration and self.record_duration > 0 and len(frames) > 1:
            est = int(round(len(frames) / float(self.record_duration)))
            return max(1, min(60, est))
        return user_fps

    def create_video_from_input_frames(self, frames):
        if not frames:
            return None
        try:
            h, w = frames[0].shape[:2]
            # Boyutları sabitle
            fixed = []
            for f in frames:
                if f.shape[:2] != (h, w):
                    f = cv2.resize(f, (w, h))
                fixed.append(f)

            filename = self.generate_filename(".mp4")
            output_path = os.path.join(self.temp_dir, filename)

            final_fps = self.get_final_fps(fixed)
            self.logger.info(f"Creating video with final FPS: {final_fps}")

            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            writer = cv2.VideoWriter(output_path, fourcc, final_fps, (w, h))
            if not writer.isOpened():
                return None

            total_frames = len(fixed)
            # Hedef frame sayısı (süre verilmişse buna uydur, yoksa hepsini yaz)
            frames_to_write = int(self.record_duration * final_fps) if self.record_duration > 0 else total_frames
            frames_to_write = max(1, frames_to_write)

            try:
                if frames_to_write <= total_frames:
                    idxs = np.linspace(0, total_frames - 1, num=frames_to_write, dtype=int)
                    for i in idxs:
                        writer.write(fixed[i])
                else:
                    # Yetersizse döndürerek çoğalt
                    for i in range(frames_to_write):
                        writer.write(fixed[i % total_frames])
            finally:
                writer.release()

            return output_path if os.path.exists(output_path) else None
        except Exception as e:
            self.logger.error(f"Video creation error: {str(e)}")
            try:
                writer.release()
            except Exception:
                pass
            return None

    def save_video(self, video_path):
        try:
            if not video_path or not os.path.exists(video_path):
                raise IOError("Video path is invalid")
            _, ext = os.path.splitext(video_path)
            video_filename = self.generate_filename(ext)

            if self.target_type == "TargetLocal":
                full_path = os.path.join(self.local_path, video_filename)
                shutil.copy2(video_path, full_path)
                if not os.path.exists(full_path):
                    raise IOError(f"Failed to save video to {full_path}")
                return full_path
            else:
                import requests
                temp_path = f"/storage/temp/{video_filename}"
                shutil.copy2(video_path, temp_path)
                api_endpoint = f"{self.environment.web_api}/storage/default/upload?access-token={self.environment.device_access_token}"
                with open(temp_path, "rb") as f:
                    files = {"file": f}
                    response = requests.post(api_endpoint, files=files, data={"title": video_filename})
                os.remove(temp_path)
                if response.status_code not in (200, 201):
                    raise Exception(f"Storage upload failed: {response.status_code}")
                return response.text
        except Exception as e:
            self.logger.error(f"save_video error: {e}")
            return None

    def process_and_save_video(self):
        self.logger.info("VideoSave process started")
        self.logger.info(f"Input frames: {len(self.input_frames)} | Duration: {self.record_duration}s | User FPS: {self.user_fps}")
        if not self.input_frames:
            self.logger.warning("No frames to write.")
            return
        video_path = self.create_video_from_input_frames(self.input_frames)
        if video_path:
            self.saved_path = self.save_video(video_path)
            if self.saved_path:
                self.logger.info(f"Video saved: {self.saved_path}")
        # işlem bittiğinde buffer'ı temizlemek istersen:
        self.input_frames = []

    def run(self):
        # Her çağrıda bir kare al ve ekle
        frame = Image.get_frame(img=self.image, redis_db=self.redis_db)
        self.add_frame(frame)

        # Dışarıdan finalize sinyali geliyorsa kaydet (örnek)
        finalize = self.request.get_param("finalize")  # True/False beklenir
        if str(finalize).lower() in ("true", "1", "yes"):
            self.process_and_save_video()

        packageModel = build_response(context=self)
        return packageModel

if __name__ == "__main__":
    Executor(sys.argv[1]).run()