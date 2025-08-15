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


    def _generate_filename(self, extension=".mp4"):
        """Generate unique filename"""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        return f"{self.title}_{timestamp}_{unique_id}{extension}"

    @staticmethod
    def bootstrap(config: dict):
        video_name = VideoSave.application.get_param(config=config, name="videoTitle")
        return {"video_name": video_name, "outputVideoUrl": None}


    def estimate_stream_fps(self, cap, sample_duration=2.0):
        start = time.time()
        frame_count = 0

        while (time.time() - start) < sample_duration:
            ret, frame = cap.read()
            if not ret:
                break
            frame_count += 1

        duration = time.time() - start
        return round(frame_count / duration, 2) if duration > 0 else 0.0


    def get_stream_fps_and_determine_final_fps(self, img):
        try:
            system_fps = self.estimate_stream_fps(img)

            if self.system_control == "Enable":
                if system_fps <= 1:
                    system_fps=1
                    
                final_fps=system_fps      
            else:
                final_fps = min(self.user_fps, system_fps)

            return final_fps, f"System FPS: {system_fps}, Final FPS: {final_fps}",system_fps
        except Exception as e:
            return self.user_fps, f"FPS estimation failed, using user FPS: {self.user_fps}",system_fps


    def capture_input_frames(self):
        """Frames are captured from inputImage"""
        frames = []
        start_time = time.time()

        if not self.image:
            self.logger.error("No input images found")
            return frames

        self.logger.info(f"inputImage structure: {self.image}")

        final_fps, fps_msg,self.system_fps = self.get_stream_fps_and_determine_final_fps(self.image)


        # Image objesinin value alanında direkt numpy array varsa
        if hasattr(self.image, 'value') and isinstance(self.image.value, np.ndarray):
            frame = self.image.value
            if frame is not None:
                # record_duration * fps kadar aynı frame'i ekle
                total_frames = int(self.record_duration * self.system_fps)
                frames = [frame.copy() for _ in range(total_frames)]
                self.logger.info(f"Created {len(frames)} frames from numpy array")

        self.logger.info(f"Captured {len(frames)} frames in {time.time() - start_time:.2f}s")
        return frames

    def create_video_from_frames(self, frames, fps):
        """Create video from frames"""
        if not frames:
            return None

        try:
            os.makedirs(self.temp_dir, exist_ok=True)

            # Frame'i uint8 formatına dönüştür
            first_frame = frames[0]
            if first_frame.dtype != np.uint8:
                first_frame = np.clip(first_frame, 0, 255).astype(np.uint8)

            height, width, _ = first_frame.shape
            filename = self._generate_filename()
            output_path = os.path.join(self.temp_dir, filename)

            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

            if not writer.isOpened():
                self.logger.error("Failed to open video writer")
                return None

            for frame in frames:
                # Her frame'i uint8'e dönüştür
                if frame.dtype != np.uint8:
                    frame = np.clip(frame, 0, 255).astype(np.uint8)
                writer.write(frame)

            writer.release()
            self.logger.info(f"Video saved successfully: {output_path}")
            return output_path if os.path.exists(output_path) else None

        except Exception as e:
            self.logger.error(f"Video creation error: {str(e)}")
            return None

    def save_video(self, video_path):
        """Save video to local or cloud"""
        try:
            _, ext = os.path.splitext(video_path)
            video_filename = self._generate_filename(ext)

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

    def process_and_save_video(self):
        """Main function to process video and save it"""
        self.logger.info("VideoSave process started")
        frames = self.capture_input_frames()
        if frames:
            video_path = self.create_video_from_frames(frames, self.system_fps)
            if video_path:
                self.logger.info("VideoSave process completed successfully")

    def run(self):
        """Run the video save process"""
        self.image = Image.get_frame(img=self.image, redis_db=self.redis_db)
        self.process_and_save_video()
        packageModel = build_response(context=self)
        return packageModel


if __name__ == "__main__":
    Executor(sys.argv[1]).run()
