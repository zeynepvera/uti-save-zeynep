import cv2
import json

import tensorflow as tf
import numpy as np
import sys
import os
import base64
import urllib.request
import requests

import shutil

sys.path.append(os.path.join(os.path.dirname(__file__),'../'))
from PIL import Image as PILImage
import io

from sdks.novavision.src.base.model import Image as ImageModel
from sdks.novavision.src.media.image import Image as image
from components.VideoSave.src.models.PackageModel import PackageConfigs,ConfigExecutor,VideoSaveExecutor,PackageModel,VideoSaveResponse,VideoSaveOutputs,Images,OutputVideoUrl
from sdks.novavision.src.base.response import Response
from sdks.novavision.src.base.capsule import Capsule

class VideoSave(Capsule):
    def __init__(self, request, bootstrap):
        self.error_list = []
        super().__init__(request)
        self.request.model = PackageModel(**(self.request.data))
        self.images = self.request.get_param("Images")
        self.title = self.request.get_param("imageTitle")
        self.fps = self.request.get_param("Fps")

    @staticmethod
    def bootstrap():
        model = {"models":" "}
        return model

    def run(self):
        base64_images = []
        i = 0

        #Dosyayı Oluşturuyoruz
        os.mkdir("components/VideoSave/VideoImage")

        for img in self.images:
            img.value = image.encode64(img.value, img.mimeType)
            img2 = PILImage.open(io.BytesIO(base64.decodebytes(bytes(img.value, "utf-8"))))
            mimetype = img.mimeType.split("/")[-1]
            imagetype = 'components/VideoSave/VideoImage/ImageSave'+str(i)+'.'+ mimetype
            img2.save(imagetype)
            i = i + 1
            base64_images.append(imagetype)

        #Her fotoğrafı bir OpenCV matrisine dönüştürüyoruz
        images = [cv2.imread(path) for path in base64_images]

        #Videoyu oluşturmak için OpenCV'nin VideoWriter sınıfını kullanıyoruz
        # fourcc = cv2.VideoWriter_fourcc(*"h264_nvenc")
        fourcc = cv2.VideoWriter_fourcc('m','p','4','v')
        video = cv2.VideoWriter("video10.mp4", fourcc, self.fps, (images[0].shape[1], images[0].shape[0]))

        #Her fotoğrafı videoya ekliyoruz
        for im in images:
            video.write(im)

        #Videoyu kapatıyoruz
        video.release()

        #Dosyayı Siliyoruz
        shutil.rmtree("components/VideoSave/VideoImage")

        api_endpoint = "https://dev.suite.novavision.ai/api/storage/default/upload?access-token=k40SygDWcgPaS3vtij3d8cRRsz8uQyhf"
        files = {
             "file": (open("video10.mp4", "rb"))
        }
        response = requests.post(api_endpoint, files=files, data={"title": self.title})

        # Kontrol İşlemi
        if response.status_code == 200:
            print("Video başarıyla yüklendi.")
        else:
            print("Video yüklenirken bir hata oluştu. HTTP Hata Kodu:", response.status_code)

        outputVideoUrl = OutputVideoUrl(value='x')
        videoSaveOutputs = VideoSaveOutputs(outputVideoUrl=outputVideoUrl)
        videoSaveResponse = VideoSaveResponse(outputs=videoSaveOutputs)
        videoSaveExecutor = VideoSaveExecutor(value=videoSaveResponse)
        executor = ConfigExecutor(value=videoSaveExecutor)
        packageConfigs = PackageConfigs(executor=executor)
        packageModel = PackageModel(configs=packageConfigs)
        return Response(model=packageModel).response()