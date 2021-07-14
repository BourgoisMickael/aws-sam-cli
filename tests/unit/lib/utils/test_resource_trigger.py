from samcli.lib.providers.provider import ResourceIdentifier
from parameterized import parameterized
from unittest.case import TestCase
from unittest.mock import MagicMock, patch, ANY
from samcli.lib.utils.resource_trigger import (
    APIGatewayCodeTrigger,
    CodeResourceTrigger,
    LambdaFunctionCodeTrigger,
    LambdaImageCodeTrigger,
    LambdaLayerCodeTrigger,
    LambdaZipCodeTrigger,
    ResourceTrigger,
    TemplateTrigger,
)
from samcli.local.lambdafn.exceptions import FunctionNotFound, ResourceNotFound
from samcli.lib.providers.exceptions import MissingCodeUri, MissingDefinitionUri


class TestResourceTrigger(TestCase):
    @patch("samcli.lib.utils.resource_trigger.PathHandler")
    @patch("samcli.lib.utils.resource_trigger.RegexMatchingEventHandler")
    @patch("samcli.lib.utils.resource_trigger.Path")
    def test_single_file_path_handler(self, path_mock, handler_mock, bundle_mock):
        path = MagicMock()
        path_mock.return_value = path
        file_path = MagicMock()
        file_path.__str__.return_value = "/parent/file"

        parent_path = MagicMock()
        parent_path.__str__.return_value = "/parent/"

        file_path.parent = parent_path

        path.resolve.return_value = file_path

        ResourceTrigger.get_single_file_path_handler("/parent/file")

        path_mock.assert_called_once_with("/parent/file")
        handler_mock.assert_called_once_with(
            regexes=["^\\/parent\\/file$"], ignore_regexes=[], ignore_directories=True, case_sensitive=True
        )
        bundle_mock.assert_called_once_with(path=parent_path, event_handler=handler_mock.return_value, recursive=False)

    @patch("samcli.lib.utils.resource_trigger.PathHandler")
    @patch("samcli.lib.utils.resource_trigger.PatternMatchingEventHandler")
    @patch("samcli.lib.utils.resource_trigger.Path")
    def test_dir_path_handler(self, path_mock, handler_mock, bundle_mock):
        path = MagicMock()
        path_mock.return_value = path
        folder_path = MagicMock()

        path.resolve.return_value = folder_path

        ResourceTrigger.get_dir_path_handler("/parent/folder/")

        path_mock.assert_called_once_with("/parent/folder/")
        handler_mock.assert_called_once_with(
            patterns=["*"], ignore_patterns=[], ignore_directories=False, case_sensitive=True
        )
        bundle_mock.assert_called_once_with(
            path=folder_path, event_handler=handler_mock.return_value, recursive=True, static_folder=True
        )


class TestTemplateTrigger(TestCase):
    @patch("samcli.lib.utils.resource_trigger.DefinitionValidator")
    @patch("samcli.lib.utils.resource_trigger.Path")
    @patch("samcli.lib.utils.resource_trigger.ResourceTrigger.get_single_file_path_handler")
    def test_get_path_handler(self, single_file_handler_mock, path_mock, validator_mock):
        trigger = TemplateTrigger("template.yaml", MagicMock())
        result = trigger.get_path_handlers()
        self.assertEqual(result, [single_file_handler_mock.return_value])
        self.assertEqual(single_file_handler_mock.return_value.event_handler.on_any_event, trigger._validator_wrapper)

    @patch("samcli.lib.utils.resource_trigger.DefinitionValidator")
    @patch("samcli.lib.utils.resource_trigger.Path")
    def test_validator_wrapper(self, path_mock, validator_mock):
        on_template_change_mock = MagicMock()
        event_mock = MagicMock()
        validator_mock.return_value.validate.return_value = True
        trigger = TemplateTrigger("template.yaml", on_template_change_mock)
        trigger._validator_wrapper(event_mock)
        on_template_change_mock.assert_called_once_with(event_mock)


class TestCodeResourceTrigger(TestCase):
    @patch.multiple(CodeResourceTrigger, __abstractmethods__=set())
    @patch("samcli.lib.utils.resource_trigger.get_resource_by_id")
    def test_init(self, get_resource_by_id_mock):
        stacks = [MagicMock(), MagicMock()]
        on_code_change_mock = MagicMock()
        trigger = CodeResourceTrigger(ResourceIdentifier("A"), stacks, on_code_change_mock)
        self.assertEqual(trigger._resource, get_resource_by_id_mock.return_value)
        self.assertEqual(trigger._on_code_change, on_code_change_mock)

    @patch.multiple(CodeResourceTrigger, __abstractmethods__=set())
    @patch("samcli.lib.utils.resource_trigger.get_resource_by_id")
    def test_init_invalid(self, get_resource_by_id_mock):
        stacks = [MagicMock(), MagicMock()]
        on_code_change_mock = MagicMock()
        get_resource_by_id_mock.return_value = None

        with self.assertRaises(ResourceNotFound):
            CodeResourceTrigger(ResourceIdentifier("A"), stacks, on_code_change_mock)


class TestLambdaFunctionCodeTrigger(TestCase):
    @patch.multiple(LambdaFunctionCodeTrigger, __abstractmethods__=set())
    @patch("samcli.lib.utils.resource_trigger.SamFunctionProvider")
    @patch("samcli.lib.utils.resource_trigger.get_resource_by_id")
    def test_init(self, get_resource_by_id_mock, function_provider_mock):
        stacks = [MagicMock(), MagicMock()]
        on_code_change_mock = MagicMock()
        function_mock = function_provider_mock.return_value.get.return_value

        code_uri_mock = MagicMock()
        LambdaFunctionCodeTrigger._get_code_uri = code_uri_mock

        trigger = LambdaFunctionCodeTrigger(ResourceIdentifier("A"), stacks, on_code_change_mock)
        self.assertEqual(trigger._function, function_mock)
        self.assertEqual(trigger._code_uri, code_uri_mock.return_value)

    @patch.multiple(LambdaFunctionCodeTrigger, __abstractmethods__=set())
    @patch("samcli.lib.utils.resource_trigger.SamFunctionProvider")
    @patch("samcli.lib.utils.resource_trigger.get_resource_by_id")
    def test_init_invalid(self, get_resource_by_id_mock, function_provider_mock):
        stacks = [MagicMock(), MagicMock()]
        on_code_change_mock = MagicMock()
        function_provider_mock.return_value.get.return_value = None

        code_uri_mock = MagicMock()
        LambdaFunctionCodeTrigger._get_code_uri = code_uri_mock

        with self.assertRaises(FunctionNotFound):
            LambdaFunctionCodeTrigger(ResourceIdentifier("A"), stacks, on_code_change_mock)

    @patch.multiple(LambdaFunctionCodeTrigger, __abstractmethods__=set())
    @patch("samcli.lib.utils.resource_trigger.ResourceTrigger.get_dir_path_handler")
    @patch("samcli.lib.utils.resource_trigger.SamFunctionProvider")
    @patch("samcli.lib.utils.resource_trigger.get_resource_by_id")
    def test_get_path_handlers(self, get_resource_by_id_mock, function_provider_mock, get_dir_path_handler_mock):
        stacks = [MagicMock(), MagicMock()]
        on_code_change_mock = MagicMock()
        function_mock = function_provider_mock.return_value.get.return_value

        code_uri_mock = MagicMock()
        LambdaFunctionCodeTrigger._get_code_uri = code_uri_mock

        bundle = MagicMock()
        get_dir_path_handler_mock.return_value = bundle

        trigger = LambdaFunctionCodeTrigger(ResourceIdentifier("A"), stacks, on_code_change_mock)
        result = trigger.get_path_handlers()

        self.assertEqual(result, [bundle])
        self.assertEqual(bundle.self_create, on_code_change_mock)
        self.assertEqual(bundle.self_delete, on_code_change_mock)
        self.assertEqual(bundle.event_handler.on_any_event, on_code_change_mock)


class TestLambdaZipCodeTrigger(TestCase):
    @patch("samcli.lib.utils.resource_trigger.SamFunctionProvider")
    @patch("samcli.lib.utils.resource_trigger.get_resource_by_id")
    def test_get_code_uri(self, get_resource_by_id_mock, function_provider_mock):
        stacks = [MagicMock(), MagicMock()]
        on_code_change_mock = MagicMock()
        function_mock = function_provider_mock.return_value.get.return_value
        trigger = LambdaZipCodeTrigger(ResourceIdentifier("A"), stacks, on_code_change_mock)
        result = trigger._get_code_uri()
        self.assertEqual(result, function_mock.codeuri)


class TestLambdaImageCodeTrigger(TestCase):
    @patch("samcli.lib.utils.resource_trigger.SamFunctionProvider")
    @patch("samcli.lib.utils.resource_trigger.get_resource_by_id")
    def test_get_code_uri(self, get_resource_by_id_mock, function_provider_mock):
        stacks = [MagicMock(), MagicMock()]
        on_code_change_mock = MagicMock()
        function_mock = function_provider_mock.return_value.get.return_value
        trigger = LambdaImageCodeTrigger(ResourceIdentifier("A"), stacks, on_code_change_mock)
        result = trigger._get_code_uri()
        self.assertEqual(result, function_mock.metadata.get.return_value)


class TestLambdaLayerCodeTrigger(TestCase):
    @patch("samcli.lib.utils.resource_trigger.SamLayerProvider")
    @patch("samcli.lib.utils.resource_trigger.get_resource_by_id")
    def test_init(self, get_resource_by_id_mock, layer_provider_mock):
        stacks = [MagicMock(), MagicMock()]
        on_code_change_mock = MagicMock()
        layer_mock = layer_provider_mock.return_value.get.return_value

        trigger = LambdaLayerCodeTrigger(ResourceIdentifier("A"), stacks, on_code_change_mock)
        self.assertEqual(trigger._layer, layer_mock)
        self.assertEqual(trigger._code_uri, layer_mock.codeuri)

    @patch("samcli.lib.utils.resource_trigger.ResourceTrigger.get_dir_path_handler")
    @patch("samcli.lib.utils.resource_trigger.SamLayerProvider")
    @patch("samcli.lib.utils.resource_trigger.get_resource_by_id")
    def test_get_path_handlers(self, get_resource_by_id_mock, layer_provider_mock, get_dir_path_handler_mock):
        stacks = [MagicMock(), MagicMock()]
        on_code_change_mock = MagicMock()
        layer_mock = layer_provider_mock.return_value.get.return_value

        bundle = MagicMock()
        get_dir_path_handler_mock.return_value = bundle

        trigger = LambdaLayerCodeTrigger(ResourceIdentifier("A"), stacks, on_code_change_mock)
        result = trigger.get_path_handlers()

        self.assertEqual(result, [bundle])
        self.assertEqual(bundle.self_create, on_code_change_mock)
        self.assertEqual(bundle.self_delete, on_code_change_mock)
        self.assertEqual(bundle.event_handler.on_any_event, on_code_change_mock)


class TestAPIGatewayCodeTrigger(TestCase):
    @patch("samcli.lib.utils.resource_trigger.DefinitionValidator")
    @patch("samcli.lib.utils.resource_trigger.Path")
    @patch("samcli.lib.utils.resource_trigger.ResourceTrigger.get_single_file_path_handler")
    @patch("samcli.lib.utils.resource_trigger.get_resource_by_id")
    def test_get_path_handler(self, get_resource_by_id_mock, single_file_handler_mock, path_mock, validator_mock):
        stacks = [MagicMock(), MagicMock()]
        trigger = APIGatewayCodeTrigger("definition.json", stacks, MagicMock())
        result = trigger.get_path_handlers()
        self.assertEqual(result, [single_file_handler_mock.return_value])
        self.assertEqual(single_file_handler_mock.return_value.event_handler.on_any_event, trigger._validator_wrapper)

    @patch("samcli.lib.utils.resource_trigger.DefinitionValidator")
    @patch("samcli.lib.utils.resource_trigger.Path")
    @patch("samcli.lib.utils.resource_trigger.get_resource_by_id")
    def test_validator_wrapper(self, get_resource_by_id_mock, path_mock, validator_mock):
        stacks = [MagicMock(), MagicMock()]
        on_definition_change_mock = MagicMock()
        event_mock = MagicMock()
        validator_mock.return_value.validate.return_value = True
        trigger = APIGatewayCodeTrigger("definition.json", stacks, on_definition_change_mock)
        trigger._validator_wrapper(event_mock)
        on_definition_change_mock.assert_called_once_with(event_mock)
