from pydantic import Field, ConfigDict, field_validator, BaseModel, validator
from typing import Union, Literal, Union, List, Optional
from sdks.novavision.src.base.model import Package, Configs, Inputs, Response, Request, Output, Input, Config, Image, \
    Outputs


class InputImage(Input):
    name: Literal["inputImage"] = "inputImage"
    value: Union[List[Image], Image]
    type: str = "object"

    @validator("type", pre=True, always=True)
    def set_type_based_on_value(cls, value, values):
        value = values.get('value')
        if isinstance(value, Image):
            return "object"
        elif isinstance(value, list):
            return "list"

    class Config:
        title = "Input Image"


class Output(BaseModel):
    name: str
    value: str
    type: str


class OutputVideoUrl(Output):
    name: Literal["outputVideoUrl"] = "outputVideoUrl"
    value: str
    type: Literal["string"] = "string"


class VideoSaveInputs(Inputs):
    inputImage: InputImage


class RecordDuration(Config):
    """    Duration of the video recording in seconds.
    """

    name: Literal["recordDuration"] = "recordDuration"
    value: int = Field(default=10, ge=1, le=300)
    type: Literal["number"] = "number"
    field: Literal["textInput"] = "textInput"

    class Config:
        title = "Record Duration"


class VideoTitle(Config):
    """    Title of the video to be saved.
    """

    name: Literal["videoTitle"] = "videoTitle"
    value: str = Field(default="untitled_video", min_length=1, max_length=100)
    type: Literal["string"] = "string"
    field: Literal["textInput"] = "textInput"

    class Config:
        title = "Video Title"


class ConfigFps(Config):
    """    Frames per second (FPS) for recording. If the entered value exceeds the system limit, the system’s maximum FPS will be used.
    """

    name: Literal["configFps"] = "configFps"
    value: int = Field(default=25, ge=1, le=60)
    type: Literal["number"] = "number"
    field: Literal["textInput"] = "textInput"

    class Config:
        title = "Customer FPS"


class SystemControlFalse(Config):
    configFps: ConfigFps
    name: Literal["SystemControlFalse"] = "SystemControlFalse"
    value: Literal["False"] = "False"
    type: Literal["string"] = "string"
    field: Literal["option"] = "option"

    class Config:
        title = "Disable"


class SystemControlTrue(Config):
    name: Literal["SystemControlTrue"] = "SystemControlTrue"
    value: Literal["True"] = "True"
    type: Literal["string"] = "string"
    field: Literal["option"] = "option"

    class Config:
        title = "Enable"


class SystemControl(Config):
    """
    Controls for enabling or disabling system FPS settings.
    """
    name: Literal["systemControl"] = "systemControl"
    value: Union[SystemControlTrue, SystemControlFalse]
    type: Literal["object"] = "object"
    field: Literal["dependentDropdownlist"] = "dependentDropdownlist"

    class Config:
        title = "System  FPS Control"


class TargetCloud(Config):
    name: Literal["TargetCloud"] = "TargetCloud"
    value: Literal["TargetCloud"] = "TargetCloud"
    type: Literal["string"] = "string"
    field: Literal["option"] = "option"

    class Config:
        title = "Cloud"


class TargetLocal(Config):
    name: Literal["TargetLocal"] = "TargetLocal"
    value: Literal["TargetLocal"] = "TargetLocal"
    type: Literal["string"] = "string"
    field: Literal["option"] = "option"

    class Config:
        title = "Local"


class ConfigTargetDirectory(Config):
    """Location where the recorded video will be stored.
    """

    name: Literal["configTargetDirectory"] = "configTargetDirectory"
    value: Union[TargetCloud, TargetLocal]
    type: Literal["object"] = "object"
    field: Literal["dependentDropdownlist"] = "dependentDropdownlist"

    class Config:
        title = "Directory Place"


class VideoSaveConfigs(Configs):
    videoTitle: VideoTitle
    systemControl: SystemControl
    recordDuration: RecordDuration
    configTargetDirectory: ConfigTargetDirectory


class VideoSaveRequest(Request):
    inputs: Optional[VideoSaveInputs]
    configs: VideoSaveConfigs
    model_config = ConfigDict(
        json_schema_extra={
            "target": "configs"
        }
    )


class VideoSaveOutputs(BaseModel):
    outputVideoUrl: OutputVideoUrl


class VideoSaveResponse(BaseModel):
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
    name: Literal["VideoSave"] = "VideoSave"
    uID: str = Field(default="1221112")