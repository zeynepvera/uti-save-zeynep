from pydantic import Field, ConfigDict, validator
from typing import List, Optional, Union, Literal

from sdks.novavision.src.base.model import Package, Image, Param, Inputs, Configs, Outputs, Response, Request, Output, \
    Input, Config


class OutputVideoUrl(Output):
    name: Literal["outputVideoUrl"] = "outputVideoUrl"
    value: str
    type: Literal["string"] = "string"


class StreamUrl(Config):
    name: Literal["streamUrl"] = "streamUrl"
    value: str
    type: Literal["string"] = "string"
    field: Literal["textInput"] = "textInput"

    @validator('value')
    def validate_stream_url(cls, v):
        if not v.startswith(('http://', 'https://', 'rtmp://')):
            raise ValueError('Stream URL geçerli bir protokol ile başlamalı (http, https, rtmp)')
        return v


class RecordDuration(Config):
    name: Literal["recordDuration"] = "recordDuration"
    value: int = Field(default=10, ge=1, le=300)
    type: Literal["number"] = "number"
    field: Literal["textInput"] = "textInput"


class ImageTitle(Config):
    name: Literal["imageTitle"] = "imageTitle"
    value: str = Field(default="untitled_video", min_length=1, max_length=100)
    type: Literal["string"] = "string"
    field: Literal["textInput"] = "textInput"


class ConfigFps(Config):
    name: Literal["configFps"] = "configFps"
    value: int = Field(default=25, ge=1, le=60)  # Min 1 FPS, Max 60 FPS
    type: Literal["number"] = "number"
    field: Literal["textInput"] = "textInput"


class VideoSaveConfigs(Configs):
    streamUrl: StreamUrl
    recordDuration: RecordDuration
    imageTitle: ImageTitle
    configFps: ConfigFps


class VideoSaveRequest(Request):
    configs: VideoSaveConfigs

    model_config = ConfigDict(
        json_schema_extra={
            "target": "configs"
        }
    )


class VideoSaveOutputs(Outputs):
    outputVideoUrl: OutputVideoUrl


class VideoSaveResponse(Response):
    outputs: VideoSaveOutputs


class VideoSave(Config):
    name: Literal["VideoSave"] = "VideoSave"
    value: Union[VideoSaveRequest, VideoSaveResponse]
    type: Literal["object"] = "object"
    field: Literal["option"] = "option"

    model_config = ConfigDict(
        title="Video Save",
        json_schema_extra={
            "target": {
                "value": 0
            }
        }
    )


class ConfigExecutor(Config):
    name: Literal["ConfigExecutor"] = "ConfigExecutor"
    value: VideoSave
    type: Literal["executor"] = "executor"
    field: Literal["dependentDropdownlist"] = "dependentDropdownlist"

    model_config = ConfigDict(
        title="Task",
        json_schema_extra={
            "target": "value"
        }
    )


class PackageConfigs(Configs):
    executor: ConfigExecutor


class PackageModel(Package):
    configs: PackageConfigs
    type: Literal["component"] = "component"
    name: Literal["SaveZeynep"] = "SaveZeynep"
    uID: str = Field(default="1221112")