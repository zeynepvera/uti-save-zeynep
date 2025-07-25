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
        self.error_list = []
        super().__init__(request)
        self.request.model = PackageModel(**(self.request.data))

        self.stream_url = self.request.get_param("streamUrl")
        self.record_duration = self.request.get_param("recordDuration")
        self.title = self.request.get_param("imageTitle")
        self.user_fps = self.request.get_param("configFps")

        if not self.stream_url:
            raise ValueError("streamUrl parametresi zorunludur.")

        self.user_fps = self.user_fps or 25
        self.record_duration = self.record_duration or 10
        self.title = self.title or "untitled_video"

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
        """Local storage dizini güvenli şekilde oluştur"""
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

            print(f"Stream yakalanıyor... {self.record_duration} saniye kayıt yapılacak.")
            print(f"Final FPS: {final_fps}")

            while True:
                ret, frame = cap.read()
                if not ret:
                    print("Frame okunamadı, stream sona erdi.")
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
            if cap is not None:
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
        """Videoyu local storage'a kaydet"""
        try:
            success, msg = self._ensure_local_storage_dir()
            if not success:
                return False, msg


            video_filename = os.path.basename(video_path)
            local_path = os.path.join(self.local_storage_dir, video_filename)

            print(f"Video kaydedilecek tam yol: {os.path.abspath(local_path)}")

            shutil.copy2(video_path, local_path)

            if os.path.exists(local_path):
                return True, f"Video local storage'a kaydedildi: {local_path}"
            else:
                return False, "Video kopyalanamadı"

        except Exception as e:
            return False, f"Local kaydetme hatası: {str(e)}"

    def run(self):
        message = ""
        success = False

        try:
            frames, final_fps, capture_msg = self.capture_stream_frames()

            if frames is None:
                message = f" {capture_msg}"
            else:
                video_path, create_msg = self.create_video_from_frames(frames, final_fps)

                if video_path:
                    save_success, save_msg = self.save_video_locally(video_path)

                    if save_success:
                        message = f" {capture_msg} | {create_msg} | {save_msg}"
                        success = True
                    else:
                        message = f" Video oluşturuldu ancak kaydetme başarısız: {save_msg}"
                else:
                    message = f" {create_msg}"

        except Exception as e:
            message = f" İşlem sırasında hata oluştu: {str(e)}"
        finally:
            self._cleanup_temp_dir()

        try:
            outputVideoUrl = OutputVideoUrl(value=message)
            videoSaveOutputs = VideoSaveOutputs(outputVideoUrl=outputVideoUrl)
            videoSaveResponse = VideoSaveResponse(outputs=videoSaveOutputs)

            from components.SaveZeynep.src.models.PackageModel import VideoSave as VideoSaveModel
            videoSave = VideoSaveModel(value=videoSaveResponse)

            executor = ConfigExecutor(value=videoSave)
            packageConfigs = PackageConfigs(executor=executor)
            packageModel = PackageModel(configs=packageConfigs)

            return Response(model=packageModel).response()

        except Exception as e:
            # Fallback response
            return Response(model={"error": f"Response oluşturma hatası: {str(e)}"}).response()