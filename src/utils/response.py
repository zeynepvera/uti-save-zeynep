
from sdks.novavision.src.helper.package import PackageHelper
from components.SaveZeynep.src.models.PackageModel import ConfigExecutor,  PackageModel,PackageConfigs,OutputVideoUrl
from components.SaveZeynep.src.models.PackageModel import VideoSave,VideoSaveOutputs,VideoSaveResponse



def build_response(context):
    output_video_url = OutputVideoUrl(
        name="outputVideoUrl",
        value=context.get("outputVideoUrl", ""),
        type="string"
    )
    videoSaveOutputs = VideoSaveOutputs(outputVideoUrl=output_video_url)
    videoSaveResponse = VideoSaveResponse(outputs=videoSaveOutputs)
    videoSave=VideoSave(value=videoSaveResponse)
    configexecutor = ConfigExecutor(value=videoSave)
    packageConfigs = PackageConfigs(executor=configexecutor)
    helper = PackageHelper(packageModel=PackageModel, packageConfigs=packageConfigs)
    return helper.build_model(context)