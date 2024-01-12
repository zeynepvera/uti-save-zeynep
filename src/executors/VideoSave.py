import cv2
import json

import numpy as np
import sys
import os
import base64
import uuid
import requests

import shutil

sys.path.append(os.path.join(os.path.dirname(__file__),'../'))

from sdks.novavision.src.media.image import Image
from components.VideoSave.src.models.PackageModel import PackageConfigs,ConfigExecutor,VideoSaveExecutor,PackageModel,VideoSaveResponse,VideoSaveOutputs,OutputVideoUrl
from sdks.novavision.src.base.response import Response
from sdks.novavision.src.base.capsule import Capsule


class VideoSave(Capsule):
    def __init__(self, request, bootstrap):
        self.error_list = []
        super().__init__(request)
        self.request.model = PackageModel(**(self.request.data))
        # self.images = self.request.get_param("Images")
        self.images = self.request.get_param("inputImage")
        self.islist = Image.is_list(self.images)
        self.title = self.request.get_param("imageTitle")
        self.fps = self.request.get_param("Fps")

    @staticmethod
    def bootstrap():
        model = {"models":" "}
        return model

    def run(self):
        if os.path.exists("components/VideoSave/VideoImage"):
            shutil.rmtree("components/VideoSave/VideoImage")
        os.mkdir("components/VideoSave/VideoImage")

        images = []
        if self.islist:
            for img in self.images:
                img = Image.get_image(img)
                mimetype = img.mimeType.split("/")[-1]
                directory = f"components/VideoSave/VideoImage/{str(uuid.uuid4().int)[:6]}.{mimetype}"
                cv2.imwrite(directory, img.value)
                images.append(img.value)

            height, width, layers = images[0].shape
            video = cv2.VideoWriter("video.mp4", cv2.VideoWriter_fourcc(*'mp4v'), self.fps, (width, height))
            for image in images:
                if image.dtype != np.uint8:
                    image = cv2.convertScaleAbs(image)
                video.write(image)
            video.release()

            shutil.rmtree("components/VideoSave/VideoImage")

            api_endpoint = "https://dev.suite.novavision.ai/api/storage/default/upload?access-token=k40SygDWcgPaS3vtij3d8cRRsz8uQyhf"
            files = {"file": (open("video.mp4", "rb"))}
            response = requests.post(api_endpoint, files=files, data={"title": self.title})

            if response.status_code == 200:
                message = "Video uploaded successfully"
            else:
                message = f"An error occurred while loading the video. HTTP Error Code: {response.status_code}"

        else:
            message = "The image object cannot be processed, the image list must be sent."

        outputVideoUrl = OutputVideoUrl(value=message)
        videoSaveOutputs = VideoSaveOutputs(outputVideoUrl=outputVideoUrl)
        videoSaveResponse = VideoSaveResponse(outputs=videoSaveOutputs)
        videoSaveExecutor = VideoSaveExecutor(value=videoSaveResponse)
        executor = ConfigExecutor(value=videoSaveExecutor)
        packageConfigs = PackageConfigs(executor=executor)
        packageModel = PackageModel(configs=packageConfigs)
        return Response(model=packageModel).response()