import cv2
import json
import numpy as np
import sys
import os
import base64
import uuid
import requests
import shutil
import datetime
import threading
import time

sys.path.append(os.path.join(os.path.dirname(__file__), '../../../../'))

from components.SaveZeynep.src.models.PackageModel import (
    PackageConfigs, ConfigExecutor, VideoSaveResponse,
    VideoSaveOutputs, OutputVideoUrl, PackageModel
)

from sdks.novavision.src.base.response import Response
from sdks.novavision.src.base.component import Component


class VideoSave(Component):
    def __init__(self, request, bootstrap):
        super().__init__(request)
        self.request.model = PackageModel(**(self.request.data))

        self.stream_url = self.request.get_param("streamUrl")
        self.record_duration = self.request.get_param("recordDuration")
        self.title = self.request.get_param("imageTitle")
        self.user_fps = self.request.get_param("configFps")
        self.target_directory = self.request.get_param("targetDirectory")

        if not self.stream_url:
            raise ValueError("streamUrl parametresi zorunludur.")

        self.user_fps = self.user_fps or 25
        self.record_duration = self.record_duration or 10
        self.title = self.title or "untitled_video"
        self.target_directory = self.target_directory or "local"

        self.temp_dir = "components/SaveZeynep/VideoTemp"
        self.local_storage_dir = "components/SaveZeynep/SavedVideos"

    @staticmethod
    def bootstrap():
        model = {"models": " "}
        return model

    def _ensure_temp_dir(self):
        try:
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
            os.makedirs(self.temp_dir, exist_ok=True)
            return True, "Geçici dizin oluşturuldu"
        except Exception as e:
            return False, f"Geçici dizin oluşturulamadı: {str(e)}"

    def _ensure_local_storage_dir(self):
        try:
            os.makedirs(self.local_storage_dir, exist_ok=True)
            return True, "Local storage dizin oluşturuldu"
        except Exception as e:
            return False, f"Local storage dizin oluşturulamadı: {str(e)}"

    def _cleanup_temp_dir(self):
        try:
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
        except Exception as e:
            print(f"Geçici dizin temizlenirken hata: {e}")

    def get_stream_fps_and_determine_final_fps(self, cap):
        try:
            system_fps = cap.get(cv2.CAP_PROP_FPS)
            if system_fps <= 0:
                return None, "Stream'in FPS değeri tespit edilemedi"
            final_fps = min(self.user_fps, system_fps)
            return final_fps, f"Sistem FPS: {system_fps}, Kullanıcı FPS: {self.user_fps}, Final FPS: {final_fps}"
        except Exception as e:
            return None, f"FPS belirleme hatası: {str(e)}"

    def capture_stream_frames(self):
        cap = None
        try:
            cap = cv2.VideoCapture(self.stream_url)
            if not cap.isOpened():
                return None, None, "Stream'e bağlanılamadı."
            final_fps, fps_msg = self.get_stream_fps_and_determine_final_fps(cap)
            if final_fps is None:
                return None, None, fps_msg

            print(fps_msg)
            frames = []
            start_time = time.time()
            frame_interval = 1.0 / final_fps
            last_frame_time = 0

            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                current_time = time.time()
                if current_time - last_frame_time >= frame_interval:
                    frames.append(frame.copy())
                    last_frame_time = current_time
                if current_time - start_time >= self.record_duration:
                    break

            if len(frames) == 0:
                return None, None, "Hiç frame yakalanamadı."

            return frames, final_fps, f"{len(frames)} frame başarıyla yakalandı. ({fps_msg})"
        except Exception as e:
            return None, None, f"Stream yakalama hatası: {str(e)}"
        finally:
            if cap:
                cap.release()

    def create_video_from_frames(self, frames, fps):
        if not frames:
            return None, "Frame listesi boş."
        success, msg = self._ensure_temp_dir()
        if not success:
            return None, msg
        try:
            height, width, _ = frames[0].shape
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(self.temp_dir, f"{self.title}_{timestamp}.mp4")
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            video_writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
            if not video_writer.isOpened():
                return None, "Video writer başlatılamadı."
            for frame in frames:
                if frame.dtype != np.uint8:
                    frame = cv2.convertScaleAbs(frame)
                video_writer.write(frame)
            video_writer.release()
            if not os.path.exists(output_path):
                return None, "Video dosyası oluşturulamadı."
            return output_path, f"Video oluşturuldu: {output_path} (FPS: {fps})"
        except Exception as e:
            return None, f"Video oluşturma hatası: {str(e)}"

    def save_video_locally(self, video_path):
        try:
            success, msg = self._ensure_local_storage_dir()
            if not success:
                return False, msg
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            video_filename = f"{self.title}_{timestamp}.mp4"
            local_path = os.path.join(self.local_storage_dir, video_filename)
            shutil.copy2(video_path, local_path)
            if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
                return True, f"Video saved locally: {local_path}"
            else:
                return False, "Failed to copy the video or file is empty"
        except Exception as e:
            return False, f"Error saving video locally: {str(e)}"

    def save_video_to_storage(self, video_path):
        try:
            if not hasattr(self, 'environment') or not self.environment:
                return False, "Environment config not found"
            api_endpoint = f"{self.environment.web_api}/storage/default/upload?access-token={self.environment.device_access_token}"
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            final_filename = f"{self.title}_{timestamp}.mp4"
            with open(video_path, "rb") as f:
                files = {"file": f}
                data = {"title": final_filename}
                response = requests.post(api_endpoint, files=files, data=data, timeout=60)
            if response.status_code == 200:
                try:
                    file_url = response.json().get('url', 'Upload successful')
                    return True, f"Video uploaded successfully: {file_url}"
                except:
                    return True, f"Video uploaded successfully: {response.text}"
            else:
                return False, f"Storage upload failed: {response.status_code} - {response.text}"
        except Exception as e:
            return False, f"Error uploading video to storage: {str(e)}"

    def save_video(self, video_path):
        if self.target_directory == "local":
            return self.save_video_locally(video_path)
        elif self.target_directory == "storage":
            return self.save_video_to_storage(video_path)
        else:
            return False, f"Invalid target directory: {self.target_directory}"

    def run(self):
        message = ""
        try:
            frames, final_fps, capture_msg = self.capture_stream_frames()
            if frames is None:
                message = f"Capture failed: {capture_msg}"
            else:
                video_path, create_msg = self.create_video_from_frames(frames, final_fps)
                if video_path:
                    save_success, save_msg = self.save_video(video_path)
                    if save_success:
                        message = f"Success: {capture_msg} | {create_msg} | {save_msg}"
                    else:
                        message = f"Video created but save failed: {save_msg}"
                else:
                    message = f"Video creation failed: {create_msg}"
        except Exception as e:
            message = f"Process error: {str(e)}"
        finally:
            self._cleanup_temp_dir()
        try:
            outputVideoUrl = OutputVideoUrl(value=message)
            videoSaveOutputs = VideoSaveOutputs(outputVideoUrl=outputVideoUrl)
            videoSaveResponse = VideoSaveResponse(outputs=videoSaveOutputs)
            videoSave = VideoSave(value=videoSaveResponse)
            executor = ConfigExecutor(value=videoSave)
            packageConfigs = PackageConfigs(executor=executor)
            packageModel = PackageModel(configs=packageConfigs)
            return Response(model=packageModel).response()
        except Exception as e:
            return Response(model={"error": f"Response creation error: {str(e)}", "success": False}).response()
