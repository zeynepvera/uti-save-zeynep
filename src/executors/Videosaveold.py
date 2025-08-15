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

logging.basicConfig(level=logging.INFO)


class VideoSave(Component):
    application = Application()

    def __init__(self, request, bootstrap):
        super().__init__(request, bootstrap)
        self.request.model = PackageModel(**(self.request.data))

        self.image = self.request.get_param("inputImage")
        self.input_frames = []  # Boş liste olarak initialize et

        #self.input_frames = self._extract_frames_from_input(self.image)
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
        self.logger = logging.getLogger(__name__)


    def generate_filename(self, extension=".mp4"):
        """Generate unique filename"""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        return f"{self.title}{timestamp}{unique_id}{extension}"

    @staticmethod
    def bootstrap(config: dict):
        video_name = VideoSave.application.get_param(config=config, name="videoTitle")
        return {"video_name": video_name, "outputVideoUrl": None}

    def get_system_fps_from_input(self, frames, sample_duration=2.0):
        """Input frame'lerden sistem FPS'ini gerçek zamanlı olarak hesapla"""
        if not frames:
            return 25

        start_time = time.time()
        frame_count = 0

        while (time.time() - start_time) < sample_duration:
            if frame_count < len(frames):
                # Gerçek frame işleme simülasyonu
                frame = frames[frame_count % len(frames)]
                # Basit işlem yaparak gerçekçi gecikme oluştur
                _ = cv2.resize(frame, (100, 100))
                frame_count += 1
            else:
                break

            # Frame işleme süresini simüle et
            time.sleep(0.01)

        duration = time.time() - start_time
        system_fps = round(frame_count / duration, 2) if duration > 0 else 25
        system_fps = max(1, min(60, system_fps))

        self.logger.info(f"System FPS: {system_fps} ({frame_count} frames in {duration:.2f}s)")
        return system_fps

    def get_final_fps(self, frames):
        """Sistem kontrolüne göre final FPS'i belirle"""
        system_fps = self.get_system_fps_from_input(frames)

        if isinstance(self.system_control, dict):
            control_value = self.system_control.get("value", {}).get("value", "True")
        else:
            control_value = "True"

        if control_value == "True":  # System Control ENABLE
            self.logger.info(f"System Control enabled - using system FPS: {system_fps}")
            return system_fps
        else:  # System Control DISABLE
            user_fps = self.user_fps
            final_fps = min(user_fps, system_fps)  # Küçük olanı seç

            if user_fps <= system_fps:
                self.logger.info(f"User FPS ({user_fps}) <= System FPS ({system_fps}) - using user FPS: {final_fps}")
            else:
                self.logger.info(f"User FPS ({user_fps}) > System FPS ({system_fps}) - using system FPS: {final_fps}")

            return final_fps

    def create_video_from_input_frames(self, frames):

        print("frames:", frames)
        """Input frame'lerden video oluştur"""
        try:
            os.makedirs(self.temp_dir, exist_ok=True)
            print("frames[0].shape:", frames[0].shape)
            height, width, _ = frames[0].shape
            filename = self.generate_filename()
            output_path = os.path.join(self.temp_dir, filename)

            # FPS'i frame'lere göre belirle
            final_fps = self.get_final_fps(frames)
            self.logger.info(f"Creating video with final FPS: {final_fps}")

            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            writer = cv2.VideoWriter(output_path, fourcc, final_fps, (width, height))

            if not writer.isOpened():
                return None

            # İstenen süreye göre frame'leri ayarla
            total_frames = len(frames)
            frames_to_write = int(self.record_duration * final_fps)

            if frames_to_write > total_frames:
                # Frame'leri tekrarla (yetersiz frame varsa)
                for i in range(frames_to_write):
                    frame_index = i % total_frames
                    writer.write(frames[frame_index])
            else:
                # Frame'leri düzenli aralıklarla seç (fazla frame varsa)
                step = total_frames / frames_to_write
                for i in range(frames_to_write):
                    frame_index = int(i * step)
                    writer.write(frames[frame_index])

            writer.release()
            return output_path if os.path.exists(output_path) else None

        except Exception as e:
            self.logger.error(f"Video creation error: {str(e)}")
            return None

    def save_video(self, video_path):
        try:
            _, ext = os.path.splitext(video_path)
            video_filename = self.generate_filename(ext)

            if self.target_type == "TargetLocal":
                os.makedirs(self.local_path, exist_ok=True)
                full_path = os.path.join(self.local_path, video_filename)
                shutil.copy2(video_path, full_path)

                if not os.path.exists(full_path):
                    raise IOError(f"Failed to save video to {full_path}")

                return full_path

            else:
                import requests

                os.makedirs("/storage/temp", exist_ok=True)
                temp_path = f"/storage/temp/{video_filename}"
                shutil.copy2(video_path, temp_path)

                api_endpoint = f"{self.environment.web_api}/storage/default/upload?access-token={self.environment.device_access_token}"

                with open(temp_path, "rb") as f:
                    files = {"file": f}
                    response = requests.post(api_endpoint, files=files, data={"title": video_filename})

                os.remove(temp_path)

                if response.status_code != 200:
                    raise Exception(f"Storage upload failed: {response.status_code}")

                return response.text

        except Exception as e:
            self.logger.error(f"save_video error: {e}")
            return None

    import numpy as np
    import cv2

    def _to_ndarray(self,frame) -> np.ndarray:
        # Zaten ndarray ise direkt dön
        if isinstance(frame, np.ndarray):
            return frame

        # PyTorch, JAX, vb. tensörler
        if hasattr(frame, "numpy") and callable(frame.numpy):
            return frame.numpy()

        if hasattr(frame, "to_numpy") and callable(frame.to_numpy):
            return frame.to_numpy()

        # PIL.Image veya benzeri – numpy'a çevir
        try:
            return np.asarray(frame)
        except Exception:
            pass

        # Bazı wrapper'larda ham veri "data" ya da "value" altında olabilir
        for attr in ("data", "value", "array"):
            if hasattr(frame, attr):
                return np.asarray(getattr(frame, attr))

        raise TypeError(f"normalize_frame: Desteklenmeyen görüntü türü: {type(frame)}")

    def normalize_frame(self, frame) -> np.ndarray:
        # 1) Her koşulda ndarray'e çevir
        frame = self._to_ndarray(frame)

        # 2) Tür normalizasyonu: float ise [0,1] veya [0,255] olabilir
        if frame.dtype != np.uint8:
            # m'yi daima skaler float olarak al
            m = float(np.max(frame)) if frame.size else 1.0
            if m <= 1.0:
                frame = frame * 255.0
            frame = np.clip(frame, 0, 255).astype(np.uint8)

        # 3) Kanal düzeni: gri -> BGR, BGRA -> BGR
        if frame.ndim == 2:
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        elif frame.ndim == 3 and frame.shape[2] == 4:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

        return frame

    def process_and_save_video(self,frames):
        self.logger.info("VideoSave process started")
        self.logger.info(f"Input frames: {len(self.input_frames)} | Duration: {self.record_duration}s | User FPS: {self.user_fps}")


        video_path = self.create_video_from_input_frames(self.input_frames)
        if video_path:
            self.saved_path = self.save_video(video_path)
            if self.saved_path:
                self.logger.info("VideoSave process completed successfully")

    def run(self):

        img = Image.get_frame(img=self.image, redis_db=self.redis_db)
        frame = self.normalize_frame(img)
        print(frame)
        self.input_frames.append(frame)
        self.process_and_save_video(self.input_frames)


        packageModel = build_response(context=self)
        return packageModel


if __name__ == "__main__":
    Executor(sys.argv[1]).run()
