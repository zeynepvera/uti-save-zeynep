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

sys.path.append(os.path.join(os.path.dirname(__file__), '../../'))

from src.models.PackageModel import (
    PackageConfigs, ConfigExecutor, VideoSaveResponse,
    VideoSaveOutputs, OutputVideoUrl, PackageModel, VideoSave as VideoSaveConfig
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

        # Validate and convert parameters to correct types
        self.user_fps = int(self.user_fps) if self.user_fps else 25
        self.record_duration = int(self.record_duration) if self.record_duration else 10
        
        # Validate ranges
        if self.user_fps < 1 or self.user_fps > 60:
            raise ValueError("FPS must be between 1 and 60")
        if self.record_duration < 1 or self.record_duration > 300:
            raise ValueError("Record duration must be between 1 and 300 seconds")
        # Dosya adı güvenliği - zararlı karakterleri temizle
        import re
        safe_title = re.sub(r'[<>:"/\\|?*]', '_', self.title)
        self.title = safe_title[:50]  # Maksimum 50 karakter
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
                system_fps = 30  # Default fallback FPS
                print("Warning: Could not detect stream FPS, using default 30 FPS")

            # Use minimum to avoid issues with high FPS streams
            final_fps = min(self.user_fps, system_fps)

            return final_fps, f"Sistem FPS: {system_fps}, Kullanıcı FPS: {self.user_fps}, Final FPS: {final_fps}"

        except Exception as e:
            return 25, f"FPS belirleme hatası, varsayılan 25 FPS kullanılıyor: {str(e)}"

    def capture_stream_frames(self):
        cap = None
        try:
            cap = cv2.VideoCapture(self.stream_url)

            if not cap.isOpened():
                return None, None, "Stream'e bağlanılamadı."

            final_fps, fps_msg = self.get_stream_fps_and_determine_final_fps(cap)
            print(fps_msg)

            frames = []
            start_time = time.time()
            frame_interval = 1.0 / final_fps
            last_frame_time = 0
            
            # Maksimum frame sayısını hesapla (bellek koruması için)
            max_frames = self.record_duration * final_fps
            if max_frames > 3000:  # 50 saniye * 60 FPS = 3000 frame limiti
                print(f"Uyarı: Çok fazla frame ({max_frames}), bellek problemi olabilir!")

            print(f"Stream yakalanıyor... {self.record_duration} saniye kayıt yapılacak.")
            print(f"Final FPS: {final_fps}, Tahmini frame sayısı: {max_frames}")

            while True:
                ret, frame = cap.read()
                if not ret:
                    print("Frame okunamadı, stream sona erdi.")
                    break

                current_time = time.time()

                if current_time - last_frame_time >= frame_interval:
                    # Frame boyutunu kontrol et ve gerekirse küçült (bellek tasarrufu)
                    height, width = frame.shape[:2]
                    if width > 1920 or height > 1080:
                        # 1080p'den büyükse küçült
                        scale_factor = min(1920/width, 1080/height)
                        new_width = int(width * scale_factor)
                        new_height = int(height * scale_factor)
                        frame = cv2.resize(frame, (new_width, new_height))
                        
                    frames.append(frame.copy())
                    last_frame_time = current_time
                    
                    # Bellek koruması - çok fazla frame birikirse uyar
                    if len(frames) % 100 == 0:
                        print(f"Yakalanan frame sayısı: {len(frames)}")

                if current_time - start_time >= self.record_duration:
                    break

            if len(frames) == 0:
                return None, None, "Hiç frame yakalanamadı."

            print(f"Toplam {len(frames)} frame yakalandı.")
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

        video_writer = None
        try:
            height, width, _ = frames[0].shape
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(self.temp_dir, f"{self.title}_{timestamp}.mp4")

            # H.264 codec kullan - daha iyi sıkıştırma ve uyumluluk
            fourcc = cv2.VideoWriter_fourcc(*'avc1')  # H.264 codec
            video_writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

            if not video_writer.isOpened():
                # Alternatif codec dene
                fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                video_writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
                
                if not video_writer.isOpened():
                    return None, "Video writer başlatılamadı - codec sorunu olabilir."

            written_frames = 0
            for frame in frames:
                # Frame formatını kontrol et ve düzelt
                if frame.dtype != np.uint8:
                    frame = cv2.convertScaleAbs(frame)
                
                if len(frame.shape) == 3 and frame.shape[2] == 3:
                    # Frame boyutunu kontrol et
                    if frame.shape[:2] != (height, width):
                        frame = cv2.resize(frame, (width, height))
                    
                    video_writer.write(frame)
                    written_frames += 1
                else:
                    print(f"Uyarı: Beklenmeyen frame boyutu atlanıyor: {frame.shape}")
                    continue

            if written_frames == 0:
                return None, "Hiçbir frame yazılamadı - tüm frameler geçersiz."

            return output_path, f"Video oluşturuldu: {output_path} (FPS: {fps}, Frames: {written_frames})"

        except Exception as e:
            return None, f"Video oluşturma hatası: {str(e)}"
        finally:
            # Video writer'ı mutlaka kapat
            if video_writer is not None:
                video_writer.release()
                
            # Dosya oluşturulup oluşturulmadığını kontrol et
            if 'output_path' in locals() and os.path.exists(output_path):
                file_size = os.path.getsize(output_path)
                if file_size == 0:
                    os.remove(output_path)  # Boş dosyayı sil
                    return None, "Video dosyası boş oluştu ve silindi."

    def save_video_to_storage(self, video_path):
        """Upload video to storage service - FileSave mantığına uygun şekilde"""
        try:
            if not hasattr(self, 'environment'):
                return False, "Environment configuration not available for storage upload"

            api_endpoint = f"{self.environment.web_api}/storage/default/upload?access-token={self.environment.device_access_token}"

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            final_filename = f"{self.title}_{timestamp}.mp4"

            with open(video_path, "rb") as f:
                files = {"file": (final_filename, f, "video/mp4")}
                data = {"title": final_filename}

                # Timeout ve error handling ekle
                response = requests.post(
                    api_endpoint,
                    files=files,
                    data=data,
                    timeout=60  # Video dosyaları büyük olabilir
                )

            if response.status_code == 200:
                try:
                    response_data = response.json()
                    file_url = response_data.get('url', 'Upload successful')
                    return True, f"Video uploaded successfully to storage: {file_url}"
                except:
                    return True, f"Video uploaded successfully: {response.text}"
            else:
                return False, f"Storage upload failed: {response.status_code} - {response.text}"

        except requests.exceptions.Timeout:
            return False, "Storage upload timed out (file too large or network issue)"
        except requests.exceptions.ConnectionError:
            return False, "Could not connect to storage service"
        except Exception as e:
            return False, f"Error uploading video to storage: {str(e)}"

    def save_video(self, video_path):
        """Save video either locally or to storage - İyileştirilmiş versiyon"""
        if self.target_directory == "local":
            return self.save_video_locally(video_path)
        elif self.target_directory == "storage":
            return self.save_video_to_storage(video_path)
        else:
            return False, f"Invalid target directory: {self.target_directory}. Must be 'local' or 'storage'"

    def save_video_locally(self, video_path):
        """Save video to local directory - Hata kontrolü iyileştirildi"""
        try:
            success, msg = self._ensure_local_storage_dir()
            if not success:
                return False, msg

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            video_filename = f"{self.title}_{timestamp}.mp4"
            local_path = os.path.join(self.local_storage_dir, video_filename)

            print(f"Video will be saved to: {os.path.abspath(local_path)}")

            shutil.copy2(video_path, local_path)

            if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
                file_size = os.path.getsize(local_path)
                return True, f"Video saved locally: {local_path} (Size: {file_size} bytes)"
            else:
                return False, "Failed to copy the video or file is empty"

        except PermissionError:
            return False, f"Permission denied: Cannot write to {self.local_storage_dir}"
        except OSError as e:
            return False, f"OS error while saving video: {str(e)}"
        except Exception as e:
            return False, f"Error saving video locally: {str(e)}"
    def run(self):
        message = ""
        success = False
        debug_info = []

        try:
            print(f"Video kaydetme işlemi başlatılıyor...")
            print(f"Stream URL: {self.stream_url}")
            print(f"Kayıt süresi: {self.record_duration} saniye")
            print(f"Hedef FPS: {self.user_fps}")
            print(f"Kayıt yeri: {self.target_directory}")
            
            frames, final_fps, capture_msg = self.capture_stream_frames()
            debug_info.append(f"Frame yakalama: {capture_msg}")

            if frames is None:
                message = f"Capture failed: {capture_msg}"
                print(f"HATA: {message}")
            else:
                print(f"Frame yakalama başarılı: {len(frames)} frame")
                video_path, create_msg = self.create_video_from_frames(frames, final_fps)
                debug_info.append(f"Video oluşturma: {create_msg}")

                if video_path:
                    print(f"Video oluşturma başarılı: {video_path}")
                    save_success, save_msg = self.save_video(video_path)
                    debug_info.append(f"Video kaydetme: {save_msg}")

                    if save_success:
                        message = f"BAŞARILI: {' | '.join(debug_info)}"
                        success = True
                        print(f"İşlem tamamlandı: {message}")
                    else:
                        message = f"Video oluştu ama kaydetme başarısız: {save_msg}"
                        print(f"HATA: {message}")
                else:
                    message = f"Video oluşturma başarısız: {create_msg}"
                    print(f"HATA: {message}")

        except Exception as e:
            message = f"İşlem hatası: {str(e)}"
            print(f"KRITIK HATA: {message}")
            import traceback
            print(f"Hata detayı: {traceback.format_exc()}")
        finally:
            print("Geçici dosyalar temizleniyor...")
            self._cleanup_temp_dir()

        try:
            outputVideoUrl = OutputVideoUrl(value=message)
            videoSaveOutputs = VideoSaveOutputs(outputVideoUrl=outputVideoUrl)
            videoSaveResponse = VideoSaveResponse(outputs=videoSaveOutputs)

            videoSave = VideoSaveConfig(value=videoSaveResponse)
            executor = ConfigExecutor(value=videoSave)
            packageConfigs = PackageConfigs(executor=executor)
            packageModel = PackageModel(configs=packageConfigs)

            return Response(model=packageModel).response()

        except Exception as e:
            error_msg = f"Response oluşturma hatası: {str(e)}"
            print(f"YANIT HATASI: {error_msg}")
            return Response(model={"error": error_msg, "success": False}).response()
