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
from collections import deque
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
        self.buffer_size = self.request.get_param("bufferSize")
        self.record_duration = self.request.get_param("recordDuration")
        self.title = self.request.get_param("imageTitle")
        self.fps = self.request.get_param("configFps")
        self.storage_type = self.request.get_param("storageType")

        if self.storage_type and self.storage_type.get("value") == "cloud":
            self.upload_url = self.request.get_param("uploadUrl")
            if not self.upload_url:
                raise ValueError(" for Cloud storage uploadUrlis necessary  ")
        else:
            self.upload_url = None

        if not self.stream_url:
            raise ValueError("streamUrl parametresi zorunludur.")

        self.buffer_size = self.buffer_size or 100
        self.fps = self.fps or 25
        self.record_duration = self.record_duration or 10
        self.title = self.title or "untitled_video"

        self.temp_dir = "components/VideoSave/VideoTemp"
        self.local_storage_dir = "components/VideoSave/SavedVideos"

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
        """Geçici dizini temizle"""
        try:
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
        except Exception as e:
            print(f"Geçici dizin temizlenirken hata: {e}")

    def capture_stream_frames(self):
        """MJPEG stream'den frame'leri yakala"""
        cap = None
        try:
            cap = cv2.VideoCapture(self.stream_url)

            if not cap.isOpened():
                return None, "Stream'e bağlanılamadı."

            frame_buffer = deque(maxlen=self.buffer_size)
            start_time = time.time()

            print(f"Stream yakalanıyor... {self.record_duration} saniye kayıt yapılacak.")

            while True:
                ret, frame = cap.read()
                if not ret:
                    print("Frame okunamadı, stream sona erdi.")
                    break

                frame_buffer.append(frame.copy())

                if time.time() - start_time >= self.record_duration:
                    break

            if len(frame_buffer) == 0:
                return None, "Hiç frame yakalanamadı."

            return list(frame_buffer), f"{len(frame_buffer)} frame başarıyla yakalandı."

        except Exception as e:
            return None, f"Stream yakalama hatası: {str(e)}"
        finally:
            if cap is not None:
                cap.release()

    def create_video_from_frames(self, frames):
        if not frames:
            return None, "Frame listesi boş."

        success, msg = self._ensure_temp_dir()
        if not success:
            return None, msg

        try:
            # Video özellikleri
            height, width, _ = frames[0].shape
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(self.temp_dir, f"{self.title}_{timestamp}.mp4")

            # Video writer oluştur
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            video_writer = cv2.VideoWriter(output_path, fourcc, self.fps, (width, height))

            if not video_writer.isOpened():
                return None, "Video writer başlatılamadı."

            # Frame'leri videoya yaz
            for frame in frames:
                if frame.dtype != np.uint8:
                    frame = cv2.convertScaleAbs(frame)
                video_writer.write(frame)

            video_writer.release()

            if not os.path.exists(output_path):
                return None, "Video dosyası oluşturulamadı."

            return output_path, f"Video oluşturuldu: {output_path}"

        except Exception as e:
            return None, f"Video oluşturma hatası: {str(e)}"

    def save_video_locally(self, video_path):
        """Videoyu local storage'a kaydet"""
        try:
            # Local storage dizini oluştur
            success, msg = self._ensure_local_storage_dir()
            if not success:
                return False, msg

            # Hedef dosya yolu
            video_filename = os.path.basename(video_path)
            local_path = os.path.join(self.local_storage_dir, video_filename)

            # Dosyayı kopyala
            shutil.copy2(video_path, local_path)

            if os.path.exists(local_path):
                return True, f"Video local storage'a kaydedildi: {local_path}"
            else:
                return False, "Video kopyalanamadı"

        except Exception as e:
            return False, f"Local kaydetme hatası: {str(e)}"

    def upload_to_cloud(self, video_path):
        """Videoyu buluta yükle (şimdilik placeholder)"""
        # TODO: Cloud storage implementasyonu
        return False, "Cloud storage henüz implement edilmedi"

    def run(self):
        message = ""
        success = False

        try:
            # Stream yakalama modunda çalış
            frames, capture_msg = self.capture_stream_frames()

            if frames is None:
                message = f"❌ {capture_msg}"
            else:
                # Video oluştur
                video_path, create_msg = self.create_video_from_frames(frames)

                if video_path:
                    # Storage type'a göre kaydetme
                    storage_type_value = "local"  # Default
                    if self.storage_type and isinstance(self.storage_type, dict):
                        storage_type_value = self.storage_type.get("value", "local")

                    if storage_type_value == "cloud":
                        save_success, save_msg = self.upload_to_cloud(video_path)
                        save_type = "buluta yüklendi"
                    else:
                        save_success, save_msg = self.save_video_locally(video_path)
                        save_type = "local'e kaydedildi"

                    if save_success:
                        message = f" {capture_msg} | {create_msg} | Video {save_type}: {save_msg}"
                        success = True
                    else:
                        message = f"️ Video oluşturuldu ancak kaydetme başarısız: {save_msg}"
                else:
                    message = f"❌ {create_msg}"

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