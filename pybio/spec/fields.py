import importlib
from urllib.parse import urlparse, ParseResult
import pathlib
import sys
import uuid
import requests
import subprocess
import typing
import yaml
import contextlib

from marshmallow.fields import Str, Nested, List, Dict, Integer, Float, Tuple, ValidationError  # noqa

from pybio.spec.exceptions import InvalidDoiException, PyBioValidationException
from pybio.spec import spec_types
#import MagicTensorsValue, MagicShapeValue, Importable, URI



class SpecURI(Nested):
    # todo: improve cache location

    def _deserialize(self, value, attr, data, **kwargs):
        uri = urlparse(value)

        if uri.fragment:
            raise PyBioValidationException(f"Invalid URI: {uri}. Got URI fragment: {uri.fragment}")
        if uri.params:
            raise PyBioValidationException(f"Invalid URI: {uri}. Got URI params: {uri.params}")
        if uri.query:
            raise PyBioValidationException(f"Invalid URI: {uri}. Got URI query: {uri.query}")

        return spec_types.URI(
            loader=self.schema,
            scheme=uri.scheme,
            netloc=uri.netloc,
            path=uri.path
        )

        # TODO: Remove stuff


class URI(Str):
    def _deserialize(self, *args, **kwargs) -> ParseResult:
        uri_str = super()._deserialize(*args, **kwargs)
        return urlparse(uri_str)


class Path(Str):
    def _deserialize(self, *args, **kwargs):
        path_str = super()._deserialize(*args, **kwargs)
        return pathlib.Path(path_str)


class ImportableSource(Str):
    @staticmethod
    def _is_import(path):
        return "::" not in path

    @staticmethod
    def _is_filepath(path):
        return "::" in path

    @staticmethod
    def _import_module(path):
        spec = importlib.util.spec_from_file_location(f"user_imports.{uuid.uuid4().hex}", path)
        dep = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(dep)
        return dep

    def _deserialize(self, *args, **kwargs) -> typing.Any:
        source_str: str = super()._deserialize(*args, **kwargs)
        if self._is_import(source_str):
            last_dot_idx = source_str.rfind(".")

            module_name = source_str[:last_dot_idx]
            object_name = source_str[last_dot_idx + 1 :]
            return spec_types.Importable.Module(module_name, object_name)

        elif self._is_filepath(source_str):
            if source_str.startswith("/"):
                raise ValidationError("Only realative paths are allowed")

            parts = source_str.split("::")
            if len(parts) != 2:
                raise ValidationError("Incorrect filepath format, expected example.py::ClassName")

            module_path, object_name = parts

            spec_dir = pathlib.Path(self.context.get("spec_path", ".")).parent
            abs_path = spec_dir / pathlib.Path(module_path)

            return spec_types.Importable.Path(module_path, object_name)


class Axes(Str):
    def _deserialize(self, *args, **kwargs) -> str:
        axes_str = super()._deserialize(*args, **kwargs)
        valid_axes = "bczyx"
        if any(a not in valid_axes for a in axes_str):
            raise PyBioValidationException(f"Invalid axes! Valid axes are: {valid_axes}")

        return axes_str


class Dependencies(URI):
    pass


class Tensors(Nested):
    def __init__(self, *args, valid_magic_values: typing.List[spec_types.MagicTensorsValue], **kwargs):
        super().__init__(*args, **kwargs)
        self.valid_magic_values = valid_magic_values

    def _deserialize(
        self,
        value: typing.Any,
        attr: typing.Optional[str],
        data: typing.Optional[typing.Mapping[str, typing.Any]],
        **kwargs,
    ):
        if isinstance(value, str):
            try:
                value = spec_types.MagicTensorsValue(value)
            except ValueError as e:
                raise PyBioValidationException(str(e)) from e

            if value in self.valid_magic_values:
                return value
            else:
                raise PyBioValidationException(f"Invalid magic value: {value.value}")

        elif isinstance(value, list):
            return self._load(value, data, many=True)
            # if all(isinstance(v, str) for v in value):
            #     return namedtuple("CustomTensors", value)
            # else:
            #     return self._load(value, data, many=True)
        else:
            raise PyBioValidationException(f"Invalid input type: {type(value)}")


class Shape(Nested):
    def __init__(self, *args, valid_magic_values: typing.List[spec_types.MagicShapeValue], **kwargs):
        super().__init__(*args, **kwargs)
        self.valid_magic_values = valid_magic_values

    def _deserialize(
        self,
        value: typing.Any,
        attr: typing.Optional[str],
        data: typing.Optional[typing.Mapping[str, typing.Any]],
        **kwargs,
    ):
        if isinstance(value, str):
            try:
                value = spec_types.MagicShapeValue(value)
            except ValueError as e:
                raise PyBioValidationException(str(e)) from e

            if value in self.valid_magic_values:
                return value
            else:
                raise PyBioValidationException(f"Invalid magic value: {value.value}")

        elif isinstance(value, list):
            if any(not isinstance(v, int) for v in value):
                raise PyBioValidationException("Encountered non-integers in shape")

            return tuple(value)
        elif isinstance(value, dict):
            return self._load(value, data)
        else:
            raise PyBioValidationException(f"Invalid input type: {type(value)}")
