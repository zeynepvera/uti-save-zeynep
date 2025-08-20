import sys
import os
import uuid
import shutil
import datetime
import time
import logging
import base64
import numpy as np
import cv2

import time

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
    frames = []
    is_video_saved = False
    start_time = None
    end_time = None  # NEW: to store end time


    def __init__(self, request, bootstrap):

        super().__init__(request, bootstrap)


        self.request.model = PackageModel(**(self.request.data))

        self.title = self.request.get_param("videoTitle") or "untitled_video"
        raw_target = self.request.get_param("configTargetDirectory")

        self.image = self.request.get_param("inputImage")

        self.record_duration = self.request.get_param("recordDuration")
        print(f"Record duration: {self.record_duration} saniye")


        self.system_control = self.request.get_param("systemControl")
        print(f"System Control: {self.system_control}")

        self.user_fps = self.request.get_param("configFps")
        print(f"User FPS: {self.user_fps} ")


        if isinstance(raw_target, dict):
            self.target_type = raw_target.get("value", {}).get("value", "TargetLocal")
        else:
            self.target_type = raw_target or "TargetLocal"

        self.local_path = "/storage/videos"
        os.makedirs(self.local_path, exist_ok=True)

        self.temp_dir = "/storage/temp"
        self.logger = logging.getLogger(__name__)

        self.recording_complete = False



    @staticmethod
    def bootstrap(config: dict):
        video_name = VideoSave.application.get_param(config=config, name="videoTitle")
        return {"video_name": video_name, "outputVideoUrl": None}

    @staticmethod
    def _resample_frames(frames: list, target_count: int) -> list:


        if not frames:
            return []
        n = len(frames)
        if target_count <= 1:
            return [frames[0]]
        if n == target_count:
            return frames

        # k in [0..M-1] için kaynak indeks: round( k * (N-1) / (M-1) )
        resampled = []
        for k in range(target_count):
            idx = round(k * (n - 1) / (target_count - 1))
            resampled.append(frames[idx])
        return resampled

    def get_target_fps(self):

        print("self.frames:", len(self.frames))
        print("self.record_duration:", self.record_duration)
        real_fps=len(self.frames)/self.record_duration

        if self.system_control == "True":
            return real_fps

        else:
            if self.user_fps > real_fps:
                self.logger.info(
                    f"User FPS ({self.user_fps}) is higher than real FPS ({real_fps:.2f}), using real FPS.")
                return real_fps
            else:
                self.logger.info(f"User FPS ({self.user_fps}) will be used.")
                return self.user_fps


    def process_frame_db(self):
        """Frame processing and video recording control."""
        try:
            if VideoSave.is_video_saved:
                print("Video already saved, skipping.")
                return True

            current_frame = Image.get_frame(img=self.image, redis_db=self.redis_db)
            if current_frame is None:
                return True

            if not isinstance(current_frame, np.ndarray):
                if hasattr(current_frame, 'value') and isinstance(current_frame.value, np.ndarray):
                    current_frame = current_frame.value
                else:
                    print("Frame could not be converted to numpy array")
                    return False


            VideoSave.frames.append(current_frame)

            if VideoSave.start_time is None:
                VideoSave.start_time = time.time()

                used_fps = self.get_target_fps()
                self.logger.info(f"Video recording started: '{self.title}'")
                self.logger.info(f"FPS to be used: {used_fps:.2f}")
                self.logger.info(f"Target duration: {self.record_duration} seconds")

            elapsed_time = time.time() - VideoSave.start_time
            print("-" * 50)
            print(f"Recording window: {elapsed_time:.2f} / {self.record_duration} s")
            print(f"Collected frames: {len(VideoSave.frames)}")
            print("-" * 50)

            if elapsed_time >= self.record_duration and not VideoSave.is_video_saved:
                VideoSave.end_time = time.time()  # NEW: set end time
                self._finalize_and_save()
                VideoSave.is_video_saved = True
                VideoSave.start_time = None
                VideoSave.end_time = None  # reset for next use
                VideoSave.frames = []

            return True

        except Exception as e:
            print(f"Frame processing error: {str(e)}")
            return False

    def _finalize_and_save(self):
        try:
            frames_in = VideoSave.frames[:]
            if not frames_in:
                self.logger.warning("Kaydedilecek frame yok.")
                return None

            # Kullanılacak FPS'i belirle
            target_fps = self.get_target_fps()
            self.logger.info(f"Kullanılacak FPS: {target_fps:.2f}")
            target_count = max(1, int(round(self.record_duration * target_fps)))
            frames_out = self._resample_frames(frames_in, target_count)

            # Video kaydetme işlemi
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{self.title}_{timestamp}.mp4"
            output_path = os.path.join(self.local_path, filename)

            if frames_out:
                height, width = frames_out[0].shape[:2]
                fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                writer = cv2.VideoWriter(output_path, fourcc, target_fps, (width, height))

                for frame in frames_out:
                    if frame.dtype != np.uint8:
                        frame = np.clip(frame, 0, 255).astype(np.uint8)
                    writer.write(frame)

                writer.release()

                # Log bilgileri
                self.logger.info("-" * 50)
                self.logger.info(f"Video kaydı tamamlandı: {output_path}")
                self.logger.info(f"Toplam işlenen frame: {len(frames_in)}")
                self.logger.info(f"Kayıt için kullanılan FPS: {target_fps:.2f}")
                self.logger.info(f"Gerçekleşen süre: {len(frames_out) / target_fps:.2f} saniye")
                self.logger.info("-" * 50)

                return output_path

        except Exception as e:
            self.logger.error(f"Video kayıt hatası: {str(e)}")
            return None


    def run(self):

        self.process_frame_db()
        return build_response(context=self)

##
if __name__ == "__main__":
    Executor(sys.argv[1]).run()
