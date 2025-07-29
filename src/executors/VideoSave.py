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

        # Absolute path kullan - daha güvenilir
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.temp_dir = os.path.join(base_dir, "../../VideoTemp")
        self.local_storage_dir = os.path.join(base_dir, "../../SavedVideos")

        # Logging ekle
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def bootstrap():
        return {"models": " "}

    def _ensure_temp_dir(self):
        try:
            # Absolute path'e çevir
            abs_temp_dir = os.path.abspath(self.temp_dir)
            if os.path.exists(abs_temp_dir):
                shutil.rmtree(abs_temp_dir)
            os.makedirs(abs_temp_dir, exist_ok=True)
            self.temp_dir = abs_temp_dir  # Update edilmiş path'i kullan
            self.logger.info(f"Temp directory created: {abs_temp_dir}")
            return True, f"Geçici dizin oluşturuldu: {abs_temp_dir}"
        except Exception as e:
            self.logger.error(f"Temp directory creation failed: {str(e)}")
            return False, f"Geçici dizin oluşturulamadı: {str(e)}"

    def _ensure_local_storage_dir(self):
        try:
            # Absolute path'e çevir
            abs_storage_dir = os.path.abspath(self.local_storage_dir)
            os.makedirs(abs_storage_dir, exist_ok=True)
            self.local_storage_dir = abs_storage_dir  # Update edilmiş path'i kullan
            self.logger.info(f"Storage directory created: {abs_storage_dir}")
            return True, f"Local storage dizin oluşturuldu: {abs_storage_dir}"
        except Exception as e:
            self.logger.error(f"Storage directory creation failed: {str(e)}")
            return False, f"Local storage dizin oluşturulamadı: {str(e)}"

    def _cleanup_temp_dir(self):
        try:
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
                self.logger.info(f"Temp directory cleaned: {self.temp_dir}")
        except Exception as e:
            self.logger.error(f"Temp directory cleanup failed: {e}")

    def get_stream_fps_and_determine_final_fps(self, cap):
        try:
            system_fps = cap.get(cv2.CAP_PROP_FPS)
            if system_fps <= 0 or system_fps > 120:  # Çok yüksek FPS değerlerini filtrele
                final_fps = self.user_fps
                return final_fps, f"Stream'in FPS değeri tespit edilemedi/geçersiz, kullanıcı FPS ({self.user_fps}) kullanılacak."
            final_fps = min(self.user_fps, system_fps)
            return final_fps, f"Sistem FPS: {system_fps}, Kullanıcı FPS: {self.user_fps}, Final FPS: {final_fps}"
        except Exception as e:
            return self.user_fps, f"FPS belirleme hatası, kullanıcı FPS kullanılacak: {str(e)}"

    def capture_stream_frames(self):
        cap = None
        try:
            # Stream bağlantı timeout ekle
            cap = cv2.VideoCapture(self.stream_url)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Buffer size'ı azalt - daha responsive

            if not cap.isOpened():
                return None, None, "Stream'e bağlanılamadı."

            final_fps, fps_msg = self.get_stream_fps_and_determine_final_fps(cap)
            frame_interval = 1.0 / final_fps
            frames = []
            start_time = time.time()
            last_frame_time = 0
            frame_count = 0
            max_frames = int(self.record_duration * final_fps) + 10  # Maksimum frame sayısı

            self.logger.info(f"Starting capture - Duration: {self.record_duration}s, FPS: {final_fps}")

            while True:
                ret, frame = cap.read()
                if not ret:
                    self.logger.warning("Failed to read frame from stream")
                    break

                current_time = time.time()

                # Frame interval kontrolü
                if current_time - last_frame_time >= frame_interval:
                    frames.append(frame.copy())
                    last_frame_time = current_time
                    frame_count += 1

                    # Progress log
                    if frame_count % 30 == 0:  # Her saniyede bir log (30 FPS varsayımı)
                        elapsed = current_time - start_time
                        self.logger.info(f"Captured {frame_count} frames in {elapsed:.1f}s")

                # Duration kontrolü
                if current_time - start_time >= self.record_duration:
                    break

                # Güvenlik kontrolü - çok fazla frame'i önle
                if len(frames) >= max_frames:
                    self.logger.warning(f"Max frame limit reached: {max_frames}")
                    break

            if not frames:
                return None, None, "Hiç frame yakalanamadı."

            self.logger.info(f"Capture completed: {len(frames)} frames")
            return frames, final_fps, f"{len(frames)} frame başarıyla yakalandı. ({fps_msg})"
        except Exception as e:
            self.logger.error(f"Stream capture error: {str(e)}")
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
            unique_id = str(uuid.uuid4())[:8]  # Unique ID ekle
            filename = f"{self.title}_{timestamp}_{unique_id}.mp4"
            output_path = os.path.join(self.temp_dir, filename)

            self.logger.info(f"Creating video: {output_path} - {width}x{height} @ {fps}fps")

            # Farklı codec'ler dene
            codecs_to_try = [
                ('mp4v', '.mp4'),
                ('XVID', '.mp4'),
                ('MJPG', '.avi'),
                ('X264', '.mp4')
            ]

            video_writer = None
            for fourcc_str, ext in codecs_to_try:
                try:
                    if ext != '.mp4':
                        output_path = output_path.replace('.mp4', ext)

                    fourcc = cv2.VideoWriter_fourcc(*fourcc_str)
                    video_writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

                    if video_writer.isOpened():
                        self.logger.info(f"Video writer opened with codec: {fourcc_str}")
                        break
                    else:
                        video_writer.release()
                        video_writer = None
                except Exception as codec_error:
                    self.logger.warning(f"Codec {fourcc_str} failed: {codec_error}")
                    if video_writer:
                        video_writer.release()
                        video_writer = None
                    continue

            if not video_writer or not video_writer.isOpened():
                return None, "Hiçbir video codec'i ile video writer başlatılamadı."

            # Frame'leri yaz
            for i, frame in enumerate(frames):
                if frame.dtype != np.uint8:
                    frame = cv2.convertScaleAbs(frame)

                # Frame boyutlarını kontrol et
                if frame.shape[:2] != (height, width):
                    frame = cv2.resize(frame, (width, height))

                video_writer.write(frame)

                # Progress
                if (i + 1) % 50 == 0:
                    self.logger.info(f"Written {i + 1}/{len(frames)} frames")

            video_writer.release()

            # Dosya kontrolü
            if not os.path.exists(output_path):
                return None, "Video dosyası oluşturulamadı."

            file_size = os.path.getsize(output_path)
            if file_size == 0:
                return None, "Video dosyası boş oluşturuldu."

            self.logger.info(f"Video created successfully: {output_path} ({file_size} bytes)")
            return output_path, f"Video oluşturuldu: {output_path} (FPS: {fps}, Size: {file_size} bytes)"

        except Exception as e:
            self.logger.error(f"Video creation error: {str(e)}")
            return None, f"Video oluşturma hatası: {str(e)}"

    def save_video_locally(self, video_path):
        try:
            success, msg = self._ensure_local_storage_dir()
            if not success:
                return False, msg

            # Unique filename oluştur
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            unique_id = str(uuid.uuid4())[:8]

            # Original dosya uzantısını koru
            _, ext = os.path.splitext(video_path)
            video_filename = f"{self.title}_{timestamp}_{unique_id}{ext}"
            local_path = os.path.join(self.local_storage_dir, video_filename)

            self.logger.info(f"Copying video: {video_path} -> {local_path}")

            # Dosya boyutunu kontrol et
            source_size = os.path.getsize(video_path)
            if source_size == 0:
                return False, "Source video file is empty"

            # Kopyalama işlemi
            shutil.copy2(video_path, local_path)

            # Kopyalama doğrulaması
            if not os.path.exists(local_path):
                return False, "Video kopyalanamadı - dosya bulunamadı"

            copied_size = os.path.getsize(local_path)
            if copied_size == 0:
                return False, "Kopyalanan video dosyası boş"

            if copied_size != source_size:
                self.logger.warning(f"File size mismatch: source={source_size}, copied={copied_size}")

            # Dosya izinlerini kontrol et
            try:
                with open(local_path, 'rb') as f:
                    f.read(1)  # Dosyayı okuyabilir miyiz test et
            except Exception as read_error:
                return False, f"Kopyalanan video dosyası okunamıyor: {read_error}"

            self.logger.info(f"Video saved successfully: {local_path} ({copied_size} bytes)")
            return True, f"Video saved locally: {local_path} ({copied_size} bytes)"

        except Exception as e:
            self.logger.error(f"Local save error: {str(e)}")
            return False, f"Error saving video locally: {str(e)}"

    def save_video(self, video_path):
        return self.save_video_locally(video_path)

    def run(self):
        message = ""
        saved_path = None

        try:
            self.logger.info(
                f"Starting VideoSave process - Stream: {self.stream_url}, Duration: {self.record_duration}s")

            # 1. Frame'leri yakala
            frames, final_fps, capture_msg = self.capture_stream_frames()
            if frames is None:
                message = f"Capture failed: {capture_msg}"
                self.logger.error(message)
            else:
                # 2. Video oluştur
                video_path, create_msg = self.create_video_from_frames(frames, final_fps)
                if video_path:
                    # 3. Videoyu kaydet
                    save_success, save_msg = self.save_video(video_path)
                    if save_success:
                        message = f"Success: {capture_msg} | {create_msg} | {save_msg}"
                        # Kaydedilen path'i extract et
                        if "Video saved locally:" in save_msg:
                            saved_path = save_msg.split("Video saved locally: ")[1].split(" (")[0]
                        self.logger.info("VideoSave process completed successfully")
                    else:
                        message = f"Video created but save failed: {save_msg}"
                        self.logger.error(f"Save failed: {save_msg}")
                else:
                    message = f"Video creation failed: {create_msg}"
                    self.logger.error(f"Creation failed: {create_msg}")

        except Exception as e:
            message = f"Process error: {str(e)}"
            self.logger.error(f"Process error: {str(e)}")
        finally:
            self._cleanup_temp_dir()

        # Response oluştur
        try:
            # Eğer başarılı ise path'i döndür, değilse error mesajını
            output_value = saved_path if saved_path else message

            outputVideoUrl = OutputVideoUrl(value=output_value)
            videoSaveOutputs = VideoSaveOutputs(outputVideoUrl=outputVideoUrl)
            videoSaveResponse = VideoSaveResponse(outputs=videoSaveOutputs)
            videoSave = VideoSave(value=videoSaveResponse)
            executor = ConfigExecutor(value=videoSave)
            packageConfigs = PackageConfigs(executor=executor)
            packageModel = PackageModel(configs=packageConfigs)
            return Response(model=packageModel).response()
        except Exception as e:
            self.logger.error(f"Response creation error: {str(e)}")
            return Response(model={"error": f"Response creation error: {str(e)}", "success": False}).response()