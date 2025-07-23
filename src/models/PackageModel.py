import numbers

from pydantic import Field, validator
from typing import List, Optional, Union, Any, Literal

from sdks.novavision.src.base.model import Package, Image, Param, Inputs, Configs, Outputs, Response, Request, Output, Input, Config


class OutputVideoUrl(Output):
    name: Literal["outputVideoUrl"] = "outputVideoUrl"
    value: str
    type: Literal["string"] = "string"


class InputImage(Input):
    name: Literal["inputImage"] = "inputImage"
    value: Union[List[Image], Image]
    type = "object"

    @validator("type", pre=True, always=True)
    def set_type_based_on_value(cls, value, values):
        value = values.get('value')
        if isinstance(value, Image):
            return "object"
        elif isinstance(value, list):
            return "list"

    class Config:
        title = "Image"


class VideoSaveInputs(Inputs):
    inputImage: InputImage


class ConfigFps(Config):
    """
        It corresponds to the number of frames per second to be written.
    """
    name: Literal["Fps"] = "Fps"
    value: int
    type: Literal["number"] = "number"
    field: Literal["textInput"] = "textInput"



class ImageTitle(Config):
    """
        A custom name can be given to the file.
    """
    name: Literal["imageTitle"] = "imageTitle"
    value: str
    type: Literal["string"] = "string"
    field: Literal["textInput"] = "textInput"



class imageFieldWeb(Config):
    name: Literal["web"] = "web"
    value: Literal["web"] = "web"
    type: Literal["string"] = "string"
    field: Literal["option"] = "option"

    class Config:
        title = "Web"


class ImageFieldType(Config):
    """
        The video can be saved to the cloud or local storage.
    """
    name: Literal["imageFieldType"] = "imageFieldType"
    value: Union[imageFieldWeb]
    type: Literal["object"] = "object"
    field: Literal["dropdownlist"] = "dropdownlist"

    class Config:
        title="Storage Type"


class VideoSaveConfigs(Configs):
    imageFieldType: ImageFieldType
    imageTitle: ImageTitle
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


class VideoSave(Config):
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
    value: Union[VideoSave]
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
    name: Literal["SaveZeynep"] = "SaveZeynep"
    uID: str = "1221112"