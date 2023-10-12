import numbers

from pydantic import Field, validator
from typing import List, Optional, Union, Any, Dict,Literal

from sdks.novavision.src.base.model import Package, Images, Param, Inputs, Configs, Outputs, Response, Request,Output,Input,Config

class OutputVideoUrl(Output):
    name: Literal["outputVideoUrl"] = "outputVideoUrl"
    value: str
    type: Literal["string"] = "string"

class InputImage(Input):
    name: Literal["inputImage"] = "inputImage"
    value: Images
    type: Literal["Images"] = "Images"


class VideoSaveInputs(Inputs):
    inputImage: InputImage

class ConfigFps(Config):
    name: Literal["Fps"] = "Fps"
    value: int
    type: Literal["number"] = "number"
    field: Literal["textInput"] = "textInput"

    class Config:
        title = "Fps"


class ImageTitle(Config):
    name: Literal["imageTitle"] = "imageTitle"
    value: str
    type: Literal["string"] = "string"
    field: Literal["textInput"] = "textInput"

    class Config:
        title="Image Title"

class imageFieldWeb(Config):
    name: Literal["web"] = "web"
    value: Literal["web"] = "web"
    type: Literal["string"] = "string"
    field: Literal["option"] = "option"

    class Config:
        title="Web"

class ImageFieldType(Config):
    name: Literal["imageFieldType"] = "imageFieldType"
    value: Union[imageFieldWeb]
    type: Literal["object"] = "object"
    field: Literal["dropdownlist"] = "dropdownlist"

    class Config:
        title="Type"


class VideoSaveConfigs(Configs):
    imageFieldType:ImageFieldType
    imageTitle : ImageTitle
    configFps: ConfigFps


class VideoSaveRequest(Request):
    inputs: Optional[VideoSaveInputs]
    configs: VideoSaveConfigs

    class Config:
        schema_extra = {
            "target": "configs"
        }

class VideoSaveOutputs(Outputs):
    outputVideoUrl: OutputVideoUrl

class VideoSaveResponse(Response):
    outputs: VideoSaveOutputs


class VideoSaveExecutor(Config):
    name: Literal["VideoSave"] = "VideoSave"
    value: Union[VideoSaveRequest, VideoSaveResponse]
    type: Literal["object"] = "object"
    field: Literal["option"] = "option"

    class Config:
        title = "Video Save"
        schema_extra = {
            "target": {
                "value": 0
            }
        }


class ConfigExecutor(Config):
    name: Literal["ConfigExecutor"] = "ConfigExecutor"
    value: Union[VideoSaveExecutor]
    type: Literal["executor"] = "executor"
    field: Literal["dependentDropdownlist"] = "dependentDropdownlist"

    class Config:
        title = "Task"
        schema_extra = {
            "target": "value"
        }


class PackageConfigs(Configs):
    executor: ConfigExecutor

class PackageModel(Package):
    configs: PackageConfigs
    type: Literal["component"] = "component"
    name: Literal["VideoSave"] = "VideoSave"
    uID = "1221112"