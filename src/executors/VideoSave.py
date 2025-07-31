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
        self.record_duration = self.request.get_param("recordDuration") or 10
        self.title = self.request.get_param("videoTitle") or "untitled_video"
        self.user_fps = self.request.get_param("configFps") or 25

        if not self.stream_url:
            raise ValueError("streamUrl parametresi zorunludur.")

        base_dir = "/storage"
        self.temp_dir = os.path.join(base_dir, "temp")
        self.local_storage_dir = "/storage/zeynep-videos"
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def bootstrap(config: dict):
        video_name = VideoSave.application.get_param(config=config, name="videoTitle")
        return {"video_name": video_name, "outputVideoUrl": None}

    def capture_stream_frames(self):
        self.logger.info("Stream capture started")
        cap = None
        try:
            cap = cv2.VideoCapture(self.stream_url)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            if not cap.isOpened():
                self.logger.error("Failed to connect to stream")
                return None, None, None, "Stream connection failed"

            self.logger.info("Stream connection successful")

            final_fps, fps_msg = self.get_stream_fps_and_determine_final_fps(cap)
            self.logger.info(f"FPS configuration: {fps_msg}")

            frame_interval = 1.0 / final_fps
            frames = []
            start_time = time.time()
            last_frame_time = 0
            frame_count = 0
            max_frames = int(self.record_duration * final_fps) + 10

            while True:
                ret, frame = cap.read()
                if not ret:
                    self.logger.warning("Failed to read frame from stream")
                    break

                current_time = time.time()
                if current_time - last_frame_time >= frame_interval:
                    frames.append(frame.copy())
                    last_frame_time = current_time
                    frame_count += 1

                    if frame_count % 30 == 0:
                        elapsed = current_time - start_time
                        self.logger.info(f"Captured {frame_count} frames in {elapsed:.1f}s")

                if current_time - start_time >= self.record_duration:
                    break

                if len(frames) >= max_frames:
                    self.logger.warning(f"Maximum frame limit exceeded: {max_frames}")
                    break

            actual_duration = time.time() - start_time
            actual_fps = len(frames) / actual_duration if actual_duration > 0 else final_fps
            self.logger.info(f"Capture completed: {len(frames)} frames in {actual_duration:.2f}s")

            if not frames:
                return None, None, None, "No frames captured"

            return frames, final_fps, actual_fps, f"{len(frames)} frames captured successfully"

        except Exception as e:
            self.logger.error(f"Stream capture error: {str(e)}")
            return None, None, None, f"Stream capture error: {str(e)}"

        finally:
            if cap:
                cap.release()

    def get_stream_fps_and_determine_final_fps(self, cap):
        try:
            system_fps = cap.get(cv2.CAP_PROP_FPS)
            if system_fps <= 0 or system_fps > 120:
                return self.user_fps, f"Invalid system FPS detected, using user FPS: {self.user_fps}"
            final_fps = min(self.user_fps, system_fps)
            return final_fps, f"System FPS: {system_fps}, User FPS: {self.user_fps}, Final FPS: {final_fps}"
        except Exception as e:
            return self.user_fps, f"FPS detection failed, using user FPS: {str(e)}"

    def create_video_from_frames(self, frames, fps):
        self.logger.info(f"Video creation started with {len(frames)} frames")
        if not frames:
            return None, "Empty frame list"

        try:
            os.makedirs(self.temp_dir, exist_ok=True)
            height, width, _ = frames[0].shape
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            unique_id = str(uuid.uuid4())[:8]
            filename = f"{self.title}_{timestamp}_{unique_id}.mp4"
            output_path = os.path.join(self.temp_dir, filename)

            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

            if not writer.isOpened():
                return None, "Video writer initialization failed"

            for frame in frames:
                writer.write(frame)
            writer.release()

            if not os.path.exists(output_path):
                return None, "Video file creation failed"
            self.logger.info(f"Video created successfully: {output_path}")
            return output_path, f"Video created: {output_path}"
        except Exception as e:
            self.logger.error(f"Video creation error: {str(e)}")
            return None, f"Video creation error: {str(e)}"

    def save_video_locally(self, video_path):
        try:
            os.makedirs(self.local_storage_dir, exist_ok=True)

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            unique_id = str(uuid.uuid4())[:8]
            _, ext = os.path.splitext(video_path)
            video_filename = f"{self.title}_{timestamp}_{unique_id}{ext}"
            local_path = os.path.join(self.local_storage_dir, video_filename)

            self.logger.info(f"Saving video: {video_path} to {local_path}")
            shutil.copy2(video_path, local_path)

            if not os.path.exists(local_path):
                return False, "Copy operation failed"
            self.logger.info(f"Video saved successfully: {local_path}")
            return True, f"Video saved locally: {local_path}"
        except Exception as e:
            self.logger.error(f"Video save error: {str(e)}")
            return False, f"Error: {str(e)}"

    def process_and_save_video(self):
        self.logger.info("VideoSave process started")
        self.logger.info(f"Stream URL: {self.stream_url}")
        self.logger.info(f"Duration: {self.record_duration}s | FPS: {self.user_fps} | Title: {self.title}")

        saved_path = None

        try:
            frames, final_fps, actual_fps, capture_msg = self.capture_stream_frames()
            if frames is not None:
                self.logger.info(f"Processing {len(frames)} frames with FPS: {actual_fps:.2f}")
                video_path, create_msg = self.create_video_from_frames(frames, actual_fps)
                if video_path:
                    save_success, save_msg = self.save_video_locally(video_path)
                    if save_success and "Video saved locally: " in save_msg:
                        saved_path = save_msg.split("Video saved locally: ")[1]
                        self.logger.info("VideoSave process completed successfully")
        except Exception as e:
            self.logger.error(f"Process error: {e}")

        self.saved_path = saved_path

    def run(self):
        self.process_and_save_video()
        package_model = build_response(context=self)
        return package_model

if __name__ == "__main__":
    Executor(sys.argv[1]).run()

