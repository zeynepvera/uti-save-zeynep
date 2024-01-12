import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__),'../../../'))
import requests
import cv2
import numpy as np
import json
from sdks.novavision.src.media.image import Image as image
from components.VideoSave.src.models.PackageModel import ConfigExecutor,PackageModel,PackageConfigs,VideoSaveExecutor,VideoSaveRequest,VideoSaveInputs,InputImage,VideoSaveConfigs,ImageFieldType,imageFieldWeb, ImageTitle,ConfigFps
from sdks.novavision.src.base.model import Image, Images, Request


ENDPOINT_URL = "http://127.0.0.1:8000/api"

def inference():
    image_list = Image(name="image1", uID="323332", mimeType="image/jpg", encoding="base64",
                       value=image.encode64(np.asarray(cv2.imread('/opt/project/components/VideoSave/resources/yorkshire_terrier.jpg')).astype(np.float32),'image/jpg'), type="Image")

    image_list2 = Image(name="image2", uID="323332", mimeType="image/jpg", encoding="base64",
                       value=image.encode64(
                           np.asarray(cv2.imread('/opt/project/components/VideoSave/resources/yorkshire_terrier.jpg')).astype(
                               np.float32), 'image/jpg'), type="Image")

    image_list3 = Image(name="image3", uID="323332", mimeType="image/jpg", encoding="base64",
                        value=image.encode64(
                            np.asarray(cv2.imread('/opt/project/components/VideoSave/resources/yorkshire_terrier.jpg')).astype(
                                np.float32), 'image/jpg'), type="Image")

    image_list4 = Image(name="image4", uID="323332", mimeType="image/jpg", encoding="base64",
                        value=image.encode64(
                            np.asarray(cv2.imread('/opt/project/components/VideoSave/resources/yorkshire_terrier.jpg')).astype(
                                np.float32), 'image/jpg'), type="Image")

    image_list5 = Image(name="image5", uID="323332", mimeType="image/jpg", encoding="base64",
                        value=image.encode64(
                            np.asarray(cv2.imread('/opt/project/components/VideoSave/resources/yorkshire_terrier.jpg')).astype(
                                np.float32), 'image/jpg'), type="Image")

    image_list6 = Image(name="image6", uID="323332", mimeType="image/jpg", encoding="base64",
                        value=image.encode64(
                            np.asarray(cv2.imread('/opt/project/components/VideoSave/resources/yorkshire_terrier.jpg')).astype(
                                np.float32), 'image/jpg'), type="Image")

    image_list7 = Image(name="image7", uID="323332", mimeType="image/jpg", encoding="base64",
                        value=image.encode64(
                            np.asarray(cv2.imread('/opt/project/components/VideoSave/resources/yorkshire_terrier.jpg')).astype(
                                np.float32), 'image/jpg'), type="Image")

    image_list8 = Image(name="image8", uID="323332", mimeType="image/jpg", encoding="base64",
                        value=image.encode64(
                            np.asarray(cv2.imread('/opt/project/components/VideoSave/resources/yorkshire_terrier.jpg')).astype(
                                np.float32), 'image/jpg'), type="Image")

    configFps = ConfigFps(value=2)
    imageTitle = ImageTitle(value="Save Video to Web")
    imagefieldWeb = imageFieldWeb(value="web")
    imageFieldtype = ImageFieldType(value=imagefieldWeb)
    imageSaveConfigs = VideoSaveConfigs(configFps=configFps,imageFieldType=imageFieldtype,imageTitle=imageTitle)
    images = [image_list, image_list2, image_list3, image_list4, image_list5, image_list6, image_list7, image_list8]
    inputImage = InputImage(value=images)
    imageSaveInputs = VideoSaveInputs(inputImage=inputImage)
    imageSaveRequest = VideoSaveRequest(inputs=imageSaveInputs,configs=imageSaveConfigs)
    imageSaveExecutor = VideoSaveExecutor(value=imageSaveRequest)
    executor = ConfigExecutor(value=imageSaveExecutor)
    packageConfigs = PackageConfigs(executor=executor)
    request = PackageModel(configs=packageConfigs, name="VideoSave")
    request_json = json.loads(request.json())
    response = requests.post(ENDPOINT_URL, json =request_json)
    print(response.raise_for_status())
    print(response.json())



if __name__ =="__main__":
    inference()