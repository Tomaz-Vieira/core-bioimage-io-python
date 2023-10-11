from __future__ import annotations

import collections.abc
import io
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Annotated, Any, Dict, List, Literal, Mapping, NamedTuple, Optional, Sequence, TextIO, Union, cast
from zipfile import ZIP_DEFLATED, ZipFile, is_zipfile

import pooch
from annotated_types import Len, Predicate
from pydantic import AnyUrl, DirectoryPath, FilePath, HttpUrl, TypeAdapter
from ruamel.yaml import YAML

from bioimageio.core.utils import get_parent_url
from bioimageio.spec import ResourceDescription
from bioimageio.spec import load_description as load_description
from bioimageio.spec._internal.base_nodes import ResourceDescriptionBase
from bioimageio.spec._internal.constants import DISCOVER
from bioimageio.spec._internal.types import FileName, RdfContent, RelativeFilePath, ValidationContext, YamlValue
from bioimageio.spec.description import InvalidDescription, dump_description
from bioimageio.spec.model.v0_4 import WeightsFormat
from bioimageio.spec.package import extract_file_name, get_resource_package_content
from bioimageio.spec.summary import ValidationSummary

yaml = YAML(typ="safe")

StrictFileSource = Union[HttpUrl, FilePath]
FileSource = Union[StrictFileSource, str]
RdfSource = Union[FileSource, ResourceDescription]

LEGACY_RDF_NAME = "rdf.yaml"


KnownHash = Annotated[str, Len(64 + len("sha256:")), Predicate(lambda x: str.startswith(x, "sha256:"))]


def read_description(
    rdf_source: FileSource,
    /,
    *,
    format_version: Union[Literal["discover"], Literal["latest"], str] = DISCOVER,
) -> Union[ResourceDescription, InvalidDescription]:
    rdf = download_rdf(rdf_source)
    return load_description(
        rdf.content,
        context=ValidationContext(root=rdf.root, file_name=rdf.file_name),
        format_version=format_version,
    )


def read_description_and_validate(
    rdf_source: FileSource,
    /,
    *,
    format_version: Union[Literal["discover"], Literal["latest"], str] = DISCOVER,
) -> Union[ResourceDescription, InvalidDescription]:
    rdf = download_rdf(rdf_source)
    return load_description_and_validate(
        rdf.content, context=ValidationContext(root=rdf.root, file_name=rdf.file_name), format_version=format_version
    )


def load_description_and_validate(
    rdf_content: RdfContent,
    /,
    *,
    context: Optional[ValidationContext] = None,
    format_version: Union[Literal["discover"], Literal["latest"], str] = DISCOVER,
) -> Union[ResourceDescription, InvalidDescription]:
    """load and validate a BioImage.IO description from the content of a resource description file (RDF)"""
    rd = load_description(rdf_content, context=context, format_version=format_version)
    # todo: add dynamic validation
    return rd


def validate(
    rdf_source: Union[FileSource, RdfContent],
    /,
    *,
    context: Optional[ValidationContext] = None,
    format_version: Union[Literal["discover"], Literal["latest"], str] = DISCOVER,
) -> List[ValidationSummary]:
    if isinstance(rdf_source, dict):
        rd = load_description_and_validate(rdf_source, context=context, format_version=format_version)
    else:
        rd = read_description_and_validate(rdf_source, format_version=format_version)

    return rd.validation_summaries


def write_description(rd: Union[ResourceDescription, RdfContent], /, file: Union[FilePath, TextIO]):
    if isinstance(rd, ResourceDescriptionBase):
        content = dump_description(rd)
    else:
        content = rd

    if isinstance(file, Path):
        with file.open("w", encoding="utf-8") as f:
            yaml.dump(content, f)
    else:
        yaml.dump(content, file)


def prepare_resource_package(
    rdf_source: RdfSource,
    /,
    *,
    weights_priority_order: Optional[Sequence[WeightsFormat]] = None,
) -> Dict[FileName, Union[FilePath, RdfContent]]:
    """Prepare to package a resource description; downloads all required files.

    Args:
        rdf_source: A bioimage.io resource description (as file, raw YAML content or description class)
        context: validation context
        weights_priority_order: If given only the first weights format present in the model is included.
                                If none of the prioritized weights formats is found all are included.
    """
    if isinstance(rdf_source, ResourceDescriptionBase):
        rd = rdf_source
        _ctxt = rd._internal_validation_context  # pyright: ignore[reportPrivateUsage]
        context = ValidationContext(root=_ctxt["root"], file_name=_ctxt["file_name"])
    else:
        rdf = download_rdf(rdf_source)
        context = ValidationContext(root=rdf.root, file_name=rdf.file_name)
        rd = load_description(
            rdf.content,
            context=context,
        )

    if isinstance(rd, InvalidDescription):
        raise ValueError(f"{rdf_source} is invalid: {rd.validation_summaries[0]}")

    package_content = get_resource_package_content(rd, weights_priority_order=weights_priority_order)

    local_package_content: Dict[FileName, Union[FilePath, RdfContent]] = {}
    for k, v in package_content.items():
        if not isinstance(v, collections.abc.Mapping):
            v = resolve_source(v, root=context.root)

        local_package_content[k] = v

    return local_package_content


def write_zip(
    path: os.PathLike[str],
    content: Mapping[FileName, Union[str, FilePath, Dict[Any, Any]]],
    *,
    compression: int,
    compression_level: int,
) -> None:
    """Write a zip archive.

    Args:
        path: output path to write to.
        content: dict mapping archive names to local file paths, strings (for text files), or dict (for yaml files).
        compression: The numeric constant of compression method.
        compression_level: Compression level to use when writing files to the archive.
                           See https://docs.python.org/3/library/zipfile.html#zipfile.ZipFile

    """
    with ZipFile(path, "w", compression=compression, compresslevel=compression_level) as myzip:
        for arc_name, file in content.items():
            if isinstance(file, dict):
                buf = io.StringIO()
                YAML.dump(file, buf)
                file = buf.getvalue()

            if isinstance(file, str):
                myzip.writestr(arc_name, file.encode("utf-8"))
            else:
                myzip.write(file, arcname=arc_name)


def write_package(
    rdf_source: RdfSource,
    /,
    *,
    compression: int = ZIP_DEFLATED,
    compression_level: int = 1,
    output_path: Optional[os.PathLike[str]] = None,
    weights_priority_order: Optional[  # model only
        Sequence[
            Literal[
                "keras_hdf5",
                "onnx",
                "pytorch_state_dict",
                "tensorflow_js",
                "tensorflow_saved_model_bundle",
                "torchscript",
            ]
        ]
    ] = None,
) -> FilePath:
    """Package a bioimage.io resource as a zip file.

    Args:
        rd: bioimage.io resource description
        context:
        compression: The numeric constant of compression method.
        compression_level: Compression level to use when writing files to the archive.
                           See https://docs.python.org/3/library/zipfile.html#zipfile.ZipFile
        output_path: file path to write package to
        weights_priority_order: If given only the first weights format present in the model is included.
                                If none of the prioritized weights formats is found all are included.

    Returns:
        path to zipped bioimage.io package in BIOIMAGEIO_CACHE_PATH or 'output_path'
    """
    package_content = prepare_resource_package(
        rdf_source,
        weights_priority_order=weights_priority_order,
    )
    if output_path is None:
        output_path = Path(NamedTemporaryFile(suffix=".bioimageio.zip", delete=False).name)
    else:
        output_path = Path(output_path)

    write_zip(output_path, package_content, compression=compression, compression_level=compression_level)
    return output_path


class _LocalFile(NamedTuple):
    path: FilePath
    original_root: Union[AnyUrl, DirectoryPath]
    original_file_name: str


class _LocalRdf(NamedTuple):
    content: RdfContent
    root: Union[AnyUrl, DirectoryPath]
    file_name: str


def download(
    source: FileSource,
    /,
    *,
    known_hash: Optional[KnownHash] = None,
) -> _LocalFile:
    source = _interprete_file_source(source)
    if isinstance(source, AnyUrl):
        if source.scheme not in ("http", "https"):
            raise NotImplementedError(source.scheme)

        if os.environ.get("CI", "false").lower() in ("1", "t", "true", "yes", "y"):
            headers = {"User-Agent": "ci"}
            progressbar = False
        else:
            headers = {}
            progressbar = True

        if (user_agent := os.environ.get("BIOIMAGEIO_USER_AGENT")) is not None:
            headers["User-Agent"] = user_agent

        downloader = pooch.HTTPDownloader(headers=headers, progressbar=progressbar)
        _ls: Any = pooch.retrieve(url=str(source), known_hash=known_hash, downloader=downloader)
        local_source = Path(_ls)
        root: Union[HttpUrl, DirectoryPath] = get_parent_url(source)
    else:
        local_source = source
        root = source.parent

    return _LocalFile(
        local_source,
        root,
        extract_file_name(source),
    )


def download_rdf(source: FileSource, /, *, known_hash: Optional[KnownHash] = None, rdf_encoding: str = "utf-8"):
    local_source, root, file_name = download(source, known_hash=known_hash)
    if is_zipfile(local_source):
        out_path = local_source.with_suffix(local_source.suffix + ".unzip")
        with ZipFile(local_source, "r") as f:
            rdfs = [fname for fname in f.namelist() if fname.endswith(".bioimageio.yaml")]
            if len(rdfs) > 1:
                raise ValueError(f"Multiple RDFs in one package not yet supported (found {rdfs}).")
            elif len(rdfs) == 1:
                rdf_file_name = rdfs[0]
            elif LEGACY_RDF_NAME in f.namelist():
                rdf_file_name = LEGACY_RDF_NAME
            else:
                raise ValueError(
                    f"No RDF found in {local_source}. (Looking for any '*.bioimageio.yaml' file or an 'rdf.yaml' file)."
                )

            f.extractall(out_path)
            local_source = out_path / rdf_file_name

    with local_source.open(encoding=rdf_encoding) as f:
        content: YamlValue = yaml.load(f)

    if not isinstance(content, collections.abc.Mapping):
        raise TypeError(f"Expected RDF content to be a mapping, but got '{type(content)}'.")

    return _LocalRdf(cast(RdfContent, content), root, file_name)


def resolve_source(
    source: Union[FileSource, RelativeFilePath],
    /,
    *,
    known_hash: Optional[KnownHash] = None,
    root: Union[DirectoryPath, AnyUrl, None] = None,
) -> FilePath:
    if isinstance(source, RelativeFilePath):
        if root is None:
            raise ValueError(f"Cannot resolve relative file path '{source}' without root.")

        source = source.get_absolute(root)

    return download(source, known_hash=known_hash).path


def _interprete_file_source(file_source: FileSource) -> StrictFileSource:
    return TypeAdapter(StrictFileSource).validate_python(file_source)
    # todo: prettier file source validation error
    # try:
    # except ValidationError as e:
