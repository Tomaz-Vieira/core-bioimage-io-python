from __future__ import annotations

import subprocess
import warnings
from itertools import chain
from typing import Dict, List

from loguru import logger
from pytest import FixtureRequest, fixture

from bioimageio.spec import __version__ as bioimageio_spec_version

try:
    import torch

    torch_version = tuple(map(int, torch.__version__.split(".")[:2]))
    logger.warning(f"detected torch version {torch_version}.x")
except ImportError:
    torch = None
    torch_version = None
skip_torch = torch is None

try:
    import onnxruntime  # type: ignore
except ImportError:
    onnxruntime = None
skip_onnx = onnxruntime is None

try:
    import tensorflow  # type: ignore

    tf_major_version = int(tensorflow.__version__.split(".")[0])  # type: ignore
except ImportError:
    tensorflow = None
    tf_major_version = None

try:
    import keras  # type: ignore
except ImportError:
    keras = None

skip_tensorflow = tensorflow is None

warnings.warn(f"testing with bioimageio.spec {bioimageio_spec_version}")

# TODO: use models from new collection on S3
MODEL_SOURCES: Dict[str, str] = {
    "hpa_densenet": (
        "https://raw.githubusercontent.com/bioimage-io/spec-bioimage-io/main/example_descriptions/models/hpa-densenet/rdf.yaml"
    ),
    "stardist": (
        "https://raw.githubusercontent.com/bioimage-io/spec-bioimage-io/main/example_descriptions/models"
        "/stardist_example_model/v0_4.bioimageio.yaml"
    ),
    "shape_change": (
        "https://raw.githubusercontent.com/bioimage-io/spec-bioimage-io/main/example_descriptions/models/"
        "upsample_test_model/v0_4.bioimageio.yaml"
    ),
    "stardist_wrong_shape": (
        "https://raw.githubusercontent.com/bioimage-io/spec-bioimage-io/main/example_descriptions/models/"
        "stardist_example_model/rdf_wrong_shape.yaml"
    ),
    "stardist_wrong_shape2": (
        "https://raw.githubusercontent.com/bioimage-io/spec-bioimage-io/main/example_descriptions/models/"
        "stardist_example_model/rdf_wrong_shape2_v0_4.yaml"
    ),
    "unet2d_diff_output_shape": (
        "https://raw.githubusercontent.com/bioimage-io/spec-bioimage-io/main/example_descriptions/models/"
        "unet2d_diff_output_shape/v0_4.bioimageio.yaml"
    ),
    "unet2d_expand_output_shape": (
        "https://raw.githubusercontent.com/bioimage-io/spec-bioimage-io/main/example_descriptions/models/"
        "unet2d_nuclei_broad/expand_output_shape_v0_4.bioimageio.yaml"
    ),
    "unet2d_fixed_shape": (
        "https://raw.githubusercontent.com/bioimage-io/spec-bioimage-io/main/example_descriptions/models/"
        "unet2d_fixed_shape/v0_4.bioimageio.yaml"
    ),
    "unet2d_keras_tf2": (
        "https://raw.githubusercontent.com/bioimage-io/spec-bioimage-io/main/example_descriptions/models/"
        "unet2d_keras_tf2/v0_4.bioimageio.yaml"
    ),
    "unet2d_keras": (
        "https://raw.githubusercontent.com/bioimage-io/spec-bioimage-io/main/example_descriptions/models/"
        "unet2d_keras_tf/v0_4.bioimageio.yaml"
    ),
    "unet2d_multi_tensor": (
        "https://raw.githubusercontent.com/bioimage-io/spec-bioimage-io/main/example_descriptions/models/"
        "unet2d_multi_tensor/v0_4.bioimageio.yaml"
    ),
    "unet2d_nuclei_broad_model": (
        "https://raw.githubusercontent.com/bioimage-io/spec-bioimage-io/main/example_descriptions/models/"
        "unet2d_nuclei_broad/bioimageio.yaml"
    ),
}

# test models for various frameworks
TORCH_MODELS = (
    []
    if torch is None
    else [
        "shape_change",
        "unet2d_diff_output_shape",
        "unet2d_expand_output_shape",
        "unet2d_fixed_shape",
        "unet2d_multi_tensor",
        "unet2d_nuclei_broad_model",
    ]
)
TORCHSCRIPT_MODELS = (
    []
    if torch is None
    else [
        "unet2d_multi_tensor",
        "unet2d_nuclei_broad_model",
    ]
)
ONNX_MODELS = [] if onnxruntime is None else ["hpa_densenet"]
TENSORFLOW_MODELS = (
    []
    if tensorflow is None
    else (
        ["stardist"]
        if tf_major_version == 1
        else [
            "unet2d_keras_tf2",
        ]
    )
)
KERAS_MODELS = (
    []
    if keras is None
    else ["unet2d_keras"] if tf_major_version == 1 else ["unet2d_keras_tf2"]
)
TENSORFLOW_JS_MODELS: List[str] = []  # TODO: add a tensorflow_js example model

ALL_MODELS = sorted(
    {
        m
        for m in chain(
            TORCH_MODELS,
            TORCHSCRIPT_MODELS,
            ONNX_MODELS,
            TENSORFLOW_MODELS,
            KERAS_MODELS,
            TENSORFLOW_JS_MODELS,
        )
    }
)


@fixture(scope="session")
def mamba_cmd():
    mamba_cmd = "micromamba"
    try:
        _ = subprocess.run(["which", mamba_cmd], check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        mamba_cmd = "mamba"
        try:
            _ = subprocess.run(["which", mamba_cmd], check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            mamba_cmd = None

    return mamba_cmd


#
# model groups of the form any_<weight format>_model that include all models providing a specific weight format
#


@fixture(params=TORCH_MODELS)
def any_torch_model(request: FixtureRequest):
    return MODEL_SOURCES[request.param]


@fixture(params=TORCHSCRIPT_MODELS)
def any_torchscript_model(request: FixtureRequest):
    return MODEL_SOURCES[request.param]


@fixture(params=ONNX_MODELS)
def any_onnx_model(request: FixtureRequest):
    return MODEL_SOURCES[request.param]


@fixture(params=TENSORFLOW_MODELS)
def any_tensorflow_model(request: FixtureRequest):
    return MODEL_SOURCES[request.param]


@fixture(params=KERAS_MODELS)
def any_keras_model(request: FixtureRequest):
    return MODEL_SOURCES[request.param]


@fixture(params=TENSORFLOW_JS_MODELS)
def any_tensorflow_js_model(request: FixtureRequest):
    return MODEL_SOURCES[request.param]


# fixture to test with all models that should run in the current environment
# we exclude any 'wrong' model here
@fixture(params=sorted({m for m in ALL_MODELS if "wrong" not in m}))
def any_model(request: FixtureRequest):
    return MODEL_SOURCES[request.param]


# TODO it would be nice to just generate fixtures for all the individual models dynamically
#
# temporary fixtures to test not with all, but only a manual selection of models
# (models/functionality should be improved to get rid of this specific model group)
#


@fixture(
    params=[] if skip_torch else ["unet2d_nuclei_broad_model", "unet2d_fixed_shape"]
)
def unet2d_fixed_shape_or_not(request: FixtureRequest):
    return MODEL_SOURCES[request.param]


@fixture(
    params=(
        []
        if skip_onnx or skip_torch
        else ["unet2d_nuclei_broad_model", "unet2d_multi_tensor"]
    )
)
def convert_to_onnx(request: FixtureRequest):
    return MODEL_SOURCES[request.param]


@fixture(
    params=(
        []
        if tf_major_version is None
        else ["unet2d_keras"] if tf_major_version == 1 else ["unet2d_keras_tf2"]
    )
)
def unet2d_keras(request: FixtureRequest):
    return MODEL_SOURCES[request.param]


# written as model group to automatically skip on missing torch
@fixture(params=[] if skip_torch else ["unet2d_nuclei_broad_model"])
def unet2d_nuclei_broad_model(request: FixtureRequest):
    return MODEL_SOURCES[request.param]


# written as model group to automatically skip on missing torch
@fixture(params=[] if skip_torch else ["unet2d_diff_output_shape"])
def unet2d_diff_output_shape(request: FixtureRequest):
    return MODEL_SOURCES[request.param]


# written as model group to automatically skip on missing torch
@fixture(params=[] if skip_torch else ["unet2d_expand_output_shape"])
def unet2d_expand_output_shape(request: FixtureRequest):
    return MODEL_SOURCES[request.param]


# written as model group to automatically skip on missing torch
@fixture(params=[] if skip_torch else ["unet2d_fixed_shape"])
def unet2d_fixed_shape(request: FixtureRequest):
    return MODEL_SOURCES[request.param]


# written as model group to automatically skip on missing torch
@fixture(params=[] if skip_torch else ["shape_change"])
def shape_change_model(request: FixtureRequest):
    return MODEL_SOURCES[request.param]


# written as model group to automatically skip on missing tensorflow 1
@fixture(params=["stardist_wrong_shape"] if tf_major_version == 1 else [])
def stardist_wrong_shape(request: FixtureRequest):
    return MODEL_SOURCES[request.param]


# written as model group to automatically skip on missing tensorflow 1
@fixture(params=["stardist_wrong_shape2"] if tf_major_version == 1 else [])
def stardist_wrong_shape2(request: FixtureRequest):
    return MODEL_SOURCES[request.param]


# written as model group to automatically skip on missing tensorflow 1
@fixture(params=["stardist"] if tf_major_version == 1 else [])
def stardist(request: FixtureRequest):
    return MODEL_SOURCES[request.param]
