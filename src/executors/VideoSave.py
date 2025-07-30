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
import logging

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
        self.record_duration = self.request.get_param("recordDuration") or 10
        self.title = self.request.get_param("imageTitle") or "untitled_video"
        self.user_fps = self.request.get_param("configFps") or 25

        if not self.stream_url:
            raise ValueError("streamUrl parametresi zorunludur.")

        base_dir = "/storage"
        self.temp_dir = os.path.join(base_dir, "temp")
        self.local_storage_dir = os.path.join(base_dir, "zeynep-videos")

        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def bootstrap():
        return {"models": " "}

    def capture_stream_frames(self):
        self.logger.info("📸 [CAPTURE] Stream yakalama başlıyor...")
        cap = None
        try:
            cap = cv2.VideoCapture(self.stream_url)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            if not cap.isOpened():
                self.logger.error("❌ [CAPTURE] cap.isOpened = False → Stream'e bağlanılamadı!")
                return None, None, "Stream'e bağlanılamadı."
            else:
                self.logger.info("✅ [CAPTURE] Stream bağlantısı başarılı")

            final_fps, fps_msg = self.get_stream_fps_and_determine_final_fps(cap)
            self.logger.info(f"[CAPTURE] FPS bilgisi: {fps_msg}")

            frame_interval = 1.0 / final_fps
            frames = []
            start_time = time.time()
            last_frame_time = 0
            frame_count = 0
            max_frames = int(self.record_duration * final_fps) + 10

            while True:
                ret, frame = cap.read()
                if not ret:
                    self.logger.warning("⚠️ [CAPTURE] Stream'den frame okunamadı.")
                    break

                current_time = time.time()
                if current_time - last_frame_time >= frame_interval:
                    frames.append(frame.copy())
                    last_frame_time = current_time
                    frame_count += 1

                    if frame_count % 30 == 0:
                        elapsed = current_time - start_time
                        self.logger.info(f"📦 [CAPTURE] {frame_count} frame alındı ({elapsed:.1f}s)")

                if current_time - start_time >= self.record_duration:
                    break

                if len(frames) >= max_frames:
                    self.logger.warning(f"⚠️ [CAPTURE] Max frame limiti aşıldı: {max_frames}")
                    break

            if not frames:
                self.logger.error(" [CAPTURE] Hiç frame yakalanamadı.")
                return None, None, "Hiç frame yakalanamadı."

            self.logger.info(f"✅ [CAPTURE] Toplam frame: {len(frames)}")
            return frames, final_fps, f"{len(frames)} frame başarıyla yakalandı. ({fps_msg})"
        except Exception as e:
            self.logger.error(f"Stream capture error: {str(e)}")
            return None, None, f"Stream yakalama hatası: {str(e)}"
        finally:
            if cap:
                cap.release()

    def create_video_from_frames(self, frames, fps):
        self.logger.info(f"🎞️ [VIDEO] create_video_from_frames başlatıldı. Frame sayısı: {len(frames)}")
        if not frames:
            return None, "Frame listesi boş."

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
                return None, "Video writer açılamadı."

            for frame in frames:
                writer.write(frame)
            writer.release()

            if not os.path.exists(output_path):
                return None, "Video dosyası oluşturulamadı."
            self.logger.info(f"✅ [VIDEO] Video başarıyla oluşturuldu → {output_path}")
            return output_path, f"Video oluşturuldu: {output_path}"
        except Exception as e:
            self.logger.error(f"Video oluşturma hatası: {str(e)}")
            return None, f"Video oluşturma hatası: {str(e)}"

    def save_video_locally(self, video_path):
        try:
            os.makedirs(self.local_storage_dir, exist_ok=True)

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            unique_id = str(uuid.uuid4())[:8]
            _, ext = os.path.splitext(video_path)
            video_filename = f"{self.title}_{timestamp}_{unique_id}{ext}"
            local_path = os.path.join(self.local_storage_dir, video_filename)

            self.logger.info(f"💾 [SAVE] Video kaydediliyor: {video_path} → {local_path}")
            shutil.copy2(video_path, local_path)

            if not os.path.exists(local_path):
                return False, "Kopyalama başarısız."
            self.logger.info(f"✅ [SAVE] Kopyalama başarılı: {local_path}")
            return True, f"Video saved locally: {local_path}"
        except Exception as e:
            self.logger.error(f"Video kayıt hatası: {str(e)}")
            return False, f"Hata: {str(e)}"

    def save_video(self, video_path):
        return self.save_video_locally(video_path)

    def run(self):
        self.logger.info("🚀 [RUN] VideoSave.run() başladı")
        self.logger.info(f"🔗 [RUN] Stream URL: {self.stream_url}")
        self.logger.info(f"⏱️ [RUN] Süre: {self.record_duration}s | FPS: {self.user_fps} | Başlık: {self.title}")

        message = ""
        saved_path = None

        try:
            frames, final_fps, capture_msg = self.capture_stream_frames()
            if frames is None:
                message = f"Capture failed: {capture_msg}"
                self.logger.error(message)
            else:
                self.logger.info(f"🎬 [RUN] Frame sayısı: {len(frames)}, FPS: {final_fps}")
                video_path, create_msg = self.create_video_from_frames(frames, final_fps)
                if video_path:
                    save_success, save_msg = self.save_video(video_path)
                    if save_success:
                        message = f"✅ Success: {capture_msg} | {create_msg} | {save_msg}"
                        if "Video saved locally:" in save_msg:
                            saved_path = save_msg.split("Video saved locally: ")[1].split(" (")[0]
                        self.logger.info("✅ [RUN] VideoSave işlemi başarıyla tamamlandı.")
                    else:
                        message = f"Video created but save failed: {save_msg}"
                        self.logger.error(f"Save failed: {save_msg}")
                else:
                    message = f"Video creation failed: {create_msg}"
                    self.logger.error(f"Creation failed: {create_msg}")
        except Exception as e:
            message = f"Process error: {str(e)}"
            self.logger.error(f"Process error: {str(e)}")

        try:
            output_value = saved_path if saved_path else message
            return Response(model=PackageModel(
                configs=PackageConfigs(
                    executor=ConfigExecutor(
                        value=VideoSaveResponse(
                            outputs=VideoSaveOutputs(
                                outputVideoUrl=OutputVideoUrl(value=output_value)
                            )
                        )
                    )
                )
            )).response()
        except Exception as e:
            self.logger.error(f"Response creation error: {str(e)}")
            return Response(model={"error": f"Response creation error: {str(e)}", "success": False}).response()
