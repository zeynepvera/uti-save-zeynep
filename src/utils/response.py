# components/VideoSave/src/utils/response.py

from sdks.novavision.src.helper.package import PackageHelper
from components.VideoSave.src.models.PackageModel import ConfigExecutor, PackageModel, PackageConfigs, OutputVideoUrl, VideoSave, VideoSaveOutputs, VideoSaveResponse


def build_response(context):
    output_video_url = getattr(context, "saved_path", None)
    if not output_video_url:
        output_video_url = ""
    outputVideoUrl = OutputVideoUrl(value=output_video_url)
    videoSaveOutputs = VideoSaveOutputs(outputVideoUrl=outputVideoUrl)
    videoSaveResponse = VideoSaveResponse(outputs=videoSaveOutputs)
    videoSave = VideoSave(value=videoSaveResponse)
    executor = ConfigExecutor(value=videoSave)
    packageConfigs = PackageConfigs(executor=executor)
    package = PackageHelper(packageModel=PackageModel, packageConfigs=packageConfigs)
    packageModel = package.build_model(context)
    return packageModel

