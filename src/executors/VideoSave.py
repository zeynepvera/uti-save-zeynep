import cv2
import sys
import os
import uuid
import shutil
import datetime
import time
import logging

sys.path.append(os.path.join(os.path.dirname(__file__), '../../../../'))

from sdks.novavision.src.base.component import Component
from sdks.novavision.src.helper.executor import Executor
from components.SaveZeynep.src.utils.response import build_response
from components.SaveZeynep.src.models.PackageModel import PackageModel
from sdks.novavision.src.base.application import Application

logging.basicConfig(level=logging.INFO)

class VideoSave(Component):
    application = Application()

    def __init__(self, request, bootstrap):
        super().__init__(request, bootstrap)
        self.request.model = PackageModel(**(self.request.data))

        self.stream_url = self.request.get_param("streamUrl")
        self.record_duration = self.request.get_param("recordDuration")
        self.title = self.request.get_param("videoTitle") or "untitled_video"
        self.user_fps = self.request.get_param("configFps")

        raw_target = self.request.get_param("ConfigTargetDirectory")
        if isinstance(raw_target, dict):
            self.target_type = raw_target.get("value", {}).get("value", "TargetLocal")
        else:
            self.target_type = raw_target or "TargetLocal"

        self.local_path = "/storage/zeynep-videos"

        if not self.stream_url:
            raise ValueError("streamUrl parameter is required.")

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

    def capture_stream_frames(self):
        cap = None
        try:
            cap = cv2.VideoCapture(self.stream_url)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            if not cap.isOpened():
                self.logger.error("Failed to connect to stream")
                return None, None

            final_fps, fps_msg = self.get_stream_fps_and_determine_final_fps(cap)
            self.logger.info(f"FPS configuration: {fps_msg}")

            frame_interval = 1.0 / final_fps
            required_frame_count = int(self.record_duration * final_fps)
            frames = []
            start_time = time.time()
            last_frame_time = 0

            while len(frames) < required_frame_count:
                ret, frame = cap.read()
                if not ret:
                    break

                current_time = time.time()
                if current_time - last_frame_time >= frame_interval:
                    frames.append(frame.copy())
                    last_frame_time = current_time

            self.logger.info(f"Capture completed: {len(frames)} frames in {time.time() - start_time:.2f}s")

            if not frames:
                return None, None

            return frames, final_fps

        except Exception as e:
            self.logger.error(f"Stream capture error: {str(e)}")
            return None, None

        finally:
            if cap:
                cap.release()

    def get_stream_fps_and_determine_final_fps(self, cap):
        try:
            system_fps = self.estimate_stream_fps(cap)
            if system_fps <= 0 or system_fps > 120:
                return self.user_fps, f"System FPS invalid, using user FPS: {self.user_fps}"
            else:
                final_fps = min(self.user_fps, system_fps)
                return final_fps, f"System FPS: {system_fps}, Final FPS: {final_fps}"
        except Exception as e:
            return self.user_fps, f"FPS estimation failed, using user FPS: {self.user_fps}"

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

    def create_video_from_frames(self, frames, fps):
        if not frames:
            return None

        try:
            os.makedirs(self.temp_dir, exist_ok=True)
            height, width, _ = frames[0].shape
            filename = self._generate_filename()
            output_path = os.path.join(self.temp_dir, filename)

            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

            if not writer.isOpened():
                return None

            for frame in frames:
                writer.write(frame)
            writer.release()

            return output_path if os.path.exists(output_path) else None

        except Exception as e:
            self.logger.error(f"Video creation error: {str(e)}")
            return None

    def save_video(self, video_path):
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
        self.logger.info("VideoSave process started")
        self.logger.info(f"Stream: {self.stream_url} | Duration: {self.record_duration}s | FPS: {self.user_fps}")

        frames, final_fps = self.capture_stream_frames()
        if frames is not None:
            video_path = self.create_video_from_frames(frames, final_fps)
            if video_path:
                self.saved_path = self.save_video(video_path)
                if self.saved_path:
                    self.logger.info("VideoSave process completed successfully")

    def run(self):
        self.process_and_save_video()
        return build_response(context=self)

if __name__ == "__main__":
    Executor(sys.argv[1]).run()