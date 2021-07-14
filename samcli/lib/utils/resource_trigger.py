"""ResourceTrigger Classes for Creating PathHandlers According to a Resource"""
import re
from pathlib import Path
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, cast
from typing_extensions import Protocol

from watchdog.events import (
    FileSystemEvent,
    PatternMatchingEventHandler,
    RegexMatchingEventHandler,
)

from samcli.lib.providers.exceptions import MissingCodeUri, MissingDefinitionUri

from samcli.lib.providers.sam_layer_provider import SamLayerProvider
from samcli.lib.providers.sam_function_provider import SamFunctionProvider
from samcli.lib.utils.definition_validator import DefinitionValidator
from samcli.local.lambdafn.exceptions import FunctionNotFound, ResourceNotFound

from samcli.lib.utils.path_observer import PathHandler
from samcli.lib.providers.provider import Function, LayerVersion, ResourceIdentifier, Stack, get_resource_by_id


class OnChangeCallback(Protocol):
    """Callback Type"""

    def __call__(self, event: Optional[FileSystemEvent] = None) -> None:
        pass


class ResourceTrigger(ABC):
    """Abstract class for creating PathHandlers for a resource.
    PathHandlers returned by get_path_handlers() can then be used with an observer for
    detecting file changes associated with the resource."""

    def __init__(self) -> None:
        pass

    @abstractmethod
    def get_path_handlers(self) -> List[PathHandler]:
        """List of PathHandlers that corresponds to a resource
        Returns
        -------
        List[PathHandler]
            List of PathHandlers that corresponds to a resource
        """
        raise NotImplementedError("get_path_handleres is not implemented.")

    @staticmethod
    def get_single_file_path_handler(file_path_str: str) -> PathHandler:
        """Get PathHandler for watching a single file

        Parameters
        ----------
        file_path_str : str
            File path in string

        Returns
        -------
        PathHandler
            The PathHandler for the file specified
        """
        file_path = Path(file_path_str).resolve()
        folder_path = file_path.parent
        file_handler = RegexMatchingEventHandler(
            regexes=[f"^{re.escape(str(file_path))}$"], ignore_regexes=[], ignore_directories=True, case_sensitive=True
        )
        return PathHandler(path=folder_path, event_handler=file_handler, recursive=False)

    @staticmethod
    def get_dir_path_handler(dir_path_str: str) -> PathHandler:
        """Get PathHandler for watching a single directory

        Parameters
        ----------
        dir_path_str : str
            Folder path in string

        Returns
        -------
        PathHandler
            The PathHandler for the folder specified
        """
        dir_path = Path(dir_path_str).resolve()
        file_handler = PatternMatchingEventHandler(
            patterns=["*"], ignore_patterns=[], ignore_directories=False, case_sensitive=True
        )
        return PathHandler(path=dir_path, event_handler=file_handler, recursive=True, static_folder=True)


class TemplateTrigger(ResourceTrigger):
    _template_file: str
    _on_template_change: OnChangeCallback
    _validator: DefinitionValidator

    def __init__(self, template_file: str, on_template_change: OnChangeCallback) -> None:
        """
        Parameters
        ----------
        template_file : str
            Template file to be watched
        on_template_change : OnChangeCallback
            Callback when template changes
        """
        super().__init__()
        self._template_file = template_file
        self._on_template_change = on_template_change
        self._validator = DefinitionValidator(Path(self._template_file))

    def _validator_wrapper(self, event: Optional[FileSystemEvent] = None) -> None:
        """Wrapper for callback that only executes if the template is valid and non-trivial changes are detected.

        Parameters
        ----------
        event : Optional[FileSystemEvent], optional
        """
        if self._validator.validate():
            self._on_template_change(event)

    def get_path_handlers(self) -> List[PathHandler]:
        file_path_handler = ResourceTrigger.get_single_file_path_handler(self._template_file)
        file_path_handler.event_handler.on_any_event = self._validator_wrapper
        return [file_path_handler]


class CodeResourceTrigger(ResourceTrigger):
    """Parent class for ResourceTriggers that are for a single template resource."""

    _resource: Dict[str, Any]
    _on_code_change: OnChangeCallback

    def __init__(self, resource_identifier: ResourceIdentifier, stacks: List[Stack], on_code_change: OnChangeCallback):
        """
        Parameters
        ----------
        resource_identifier : ResourceIdentifier
            ResourceIdentifier
        stacks : List[Stack]
            List of stacks
        on_code_change : OnChangeCallback
            Callback when the resource files are changed.

        Raises
        ------
        ResourceNotFound
            Raised when the resource cannot be found in the stacks.
        """
        super().__init__()
        resource = get_resource_by_id(stacks, resource_identifier)
        if not resource:
            raise ResourceNotFound()
        self._resource = resource
        self._on_code_change = on_code_change


class LambdaFunctionCodeTrigger(CodeResourceTrigger):
    _function: Function
    _code_uri: str

    def __init__(self, function_identifier: ResourceIdentifier, stacks: List[Stack], on_code_change: OnChangeCallback):
        """
        Parameters
        ----------
        function_identifier : ResourceIdentifier
            ResourceIdentifier for the function
        stacks : List[Stack]
            List of stacks
        on_code_change : OnChangeCallback
            Callback when function code files are changed.

        Raises
        ------
        FunctionNotFound
            raised when the function cannot be found in stacks
        MissingCodeUri
            raised when there is no CodeUri property in the function definition.
        """
        super().__init__(function_identifier, stacks, on_code_change)
        function = SamFunctionProvider(stacks).get(str(function_identifier))
        if not function:
            raise FunctionNotFound()
        self._function = function

        code_uri = self._get_code_uri()
        if not code_uri:
            raise MissingCodeUri()
        self._code_uri = code_uri

    @abstractmethod
    def _get_code_uri(self) -> Optional[str]:
        """
        Returns
        -------
        Optional[str]
            Path for the folder to be watched.
        """
        raise NotImplementedError()

    def get_path_handlers(self) -> List[PathHandler]:
        """
        Returns
        -------
        List[PathHandler]
            PathHandlers for the code folder associated with the function
        """
        dir_path_handler = ResourceTrigger.get_dir_path_handler(self._code_uri)
        dir_path_handler.self_create = self._on_code_change
        dir_path_handler.self_delete = self._on_code_change
        dir_path_handler.event_handler.on_any_event = self._on_code_change
        return [dir_path_handler]


class LambdaZipCodeTrigger(LambdaFunctionCodeTrigger):
    def _get_code_uri(self) -> Optional[str]:
        return self._function.codeuri


class LambdaImageCodeTrigger(LambdaFunctionCodeTrigger):
    def _get_code_uri(self) -> Optional[str]:
        if not self._function.metadata:
            return None
        return cast(Optional[str], self._function.metadata.get("DockerContext", None))


class LambdaLayerCodeTrigger(CodeResourceTrigger):
    _layer: LayerVersion
    _code_uri: str

    def __init__(
        self,
        layer_identifier: ResourceIdentifier,
        stacks: List[Stack],
        on_code_change: OnChangeCallback,
    ):
        """
        Parameters
        ----------
        layer_identifier : ResourceIdentifier
            ResourceIdentifier for the layer
        stacks : List[Stack]
            List of stacks
        on_code_change : OnChangeCallback
            Callback when layer code files are changed.

        Raises
        ------
        ResourceNotFound
            raised when the layer cannot be found in stacks
        MissingCodeUri
            raised when there is no CodeUri property in the function definition.
        """
        super().__init__(layer_identifier, stacks, on_code_change)
        layer = SamLayerProvider(stacks).get(str(layer_identifier))
        if not layer:
            raise ResourceNotFound()
        self._layer = layer
        code_uri = self._layer.codeuri
        if not code_uri:
            raise MissingCodeUri()
        self._code_uri = code_uri

    def get_path_handlers(self) -> List[PathHandler]:
        """
        Returns
        -------
        List[PathHandler]
            PathHandlers for the code folder associated with the layer
        """
        dir_path_handler = ResourceTrigger.get_dir_path_handler(self._code_uri)
        dir_path_handler.self_create = self._on_code_change
        dir_path_handler.self_delete = self._on_code_change
        dir_path_handler.event_handler.on_any_event = self._on_code_change
        return [dir_path_handler]


class APIGatewayCodeTrigger(CodeResourceTrigger):
    _validator: DefinitionValidator
    _definition_file: str

    def __init__(
        self,
        rest_api_identifier: ResourceIdentifier,
        stacks: List[Stack],
        on_code_change: OnChangeCallback,
    ):
        """
        Parameters
        ----------
        rest_api_identifier : ResourceIdentifier
            ResourceIdentifier for the RestApi
        stacks : List[Stack]
            List of stacks
        on_code_change : OnChangeCallback
            Callback when RestApi definition file is changed.

        Raises
        ------
        MissingDefinitionUri
            raised when there is no DefinitionUri property in the RestApi definition.
        """
        super().__init__(rest_api_identifier, stacks, on_code_change)
        definition_file = self._resource.get("Properties", {}).get("DefinitionUri", None)
        if not definition_file:
            raise MissingDefinitionUri()
        self._definition_file = definition_file
        self._validator = DefinitionValidator(Path(self._definition_file))

    def _validator_wrapper(self, event: Optional[FileSystemEvent] = None):
        """Wrapper for callback that only executes if the definition is valid and non-trivial changes are detected.

        Parameters
        ----------
        event : Optional[FileSystemEvent], optional
        """
        if self._validator.validate():
            self._on_code_change(event)

    def get_path_handlers(self) -> List[PathHandler]:
        """
        Returns
        -------
        List[PathHandler]
            A single PathHandler for watching the definition file.
        """
        file_path_handler = ResourceTrigger.get_single_file_path_handler(self._definition_file)
        file_path_handler.event_handler.on_any_event = self._validator_wrapper
        return [file_path_handler]
