import traceback
import warnings
from typing import List, Literal, Optional, Union

import numpy as np
import xarray as xr

from bioimageio.core import __version__ as bioimageio_core_version
from bioimageio.core import create_prediction_pipeline, PredictionPipeline
from bioimageio.spec import InvalidDescr, ResourceDescr, build_description, dump_description, load_description
from bioimageio.spec._internal.common_nodes import ResourceDescrBase
from bioimageio.spec._internal.io_utils import load_array
from bioimageio.spec.common import BioimageioYamlContent, FileSource
from bioimageio.spec.model import v0_4, v0_5
from bioimageio.spec.model.v0_5 import WeightsFormat
from bioimageio.spec.summary import ErrorEntry, InstalledPackage, ValidationDetail, ValidationSummary


def test_model(
    source: FileSource,
    weight_format: Optional[WeightsFormat] = None,
    devices: Optional[List[str]] = None,
    decimal: int = 4,
) -> ValidationSummary:
    """Test whether the test output(s) of a model can be reproduced."""
    return test_description(
        source, weight_format=weight_format, devices=devices, decimal=decimal, expected_type="model"
    )


def test_description(
    source: Union[ResourceDescr, FileSource, BioimageioYamlContent],
    *,
    format_version: Union[Literal["discover", "latest"], str] = "discover",
    weight_format: Optional[WeightsFormat] = None,
    devices: Optional[List[str]] = None,
    decimal: int = 4,
    expected_type: Optional[str] = None,
) -> ValidationSummary:
    """Test RDF dynamically, e.g. model inference of test inputs"""
    rd = load_description_and_test(
        source,
        format_version=format_version,
        weight_format=weight_format,
        devices=devices,
        decimal=decimal,
        expected_type=expected_type,
    )
    return rd.validation_summary


def load_description_and_test(
    source: Union[ResourceDescr, FileSource, BioimageioYamlContent],
    *,
    format_version: Union[Literal["discover", "latest"], str] = "discover",
    weight_format: Optional[WeightsFormat] = None,
    devices: Optional[List[str]] = None,
    decimal: int = 4,
    expected_type: Optional[str] = None,
) -> Union[ResourceDescr, InvalidDescr]:
    """Test RDF dynamically, e.g. model inference of test inputs"""
    if (
        isinstance(source, ResourceDescrBase)
        and format_version != "discover"
        and source.format_version != format_version
    ):
        warnings.warn(f"deserializing source to ensure we validate and test using format {format_version}")
        source = dump_description(source)

    if isinstance(source, ResourceDescrBase):
        rd = source
    elif isinstance(source, dict):
        rd = build_description(source, format_version=format_version)
    else:
        rd = load_description(source, format_version=format_version)

    rd.validation_summary.env.append(InstalledPackage(name="bioimageio.core", version=bioimageio_core_version))

    if expected_type is not None:
        _test_expected_resource_type(rd, expected_type)

    if isinstance(rd, (v0_4.ModelDescr, v0_5.ModelDescr)):
        _test_model_inference(rd, weight_format, devices, decimal)
        if not isinstance(rd, v0_4.ModelDescr):
            _test_model_inference_with_parametrized_inputs(rd, weight_format, devices)

    return rd


def _test_model_inference(
    model: Union[v0_4.ModelDescr, v0_5.ModelDescr],
    weight_format: Optional[WeightsFormat],
    devices: Optional[List[str]],
    decimal: int,
) -> None:
    error: Optional[str] = None
    tb: List[str] = []
    try:
        if isinstance(model, v0_4.ModelDescr):
            inputs = [xr.DataArray(load_array(src), dims=d.axes) for src, d in zip(model.test_inputs, model.inputs)]
            expected = [xr.DataArray(load_array(src), dims=d.axes) for src, d in zip(model.test_outputs, model.outputs)]
        else:
            inputs = [
                xr.DataArray(load_array(d.test_tensor.download().path), dims=tuple(a.id for a in d.axes))
                for d in model.inputs
            ]
            expected = [
                xr.DataArray(load_array(d.test_tensor.download().path), dims=tuple(a.id for a in d.axes))
                for d in model.outputs
            ]

        with create_prediction_pipeline(
            bioimageio_model=model, devices=devices, weight_format=weight_format
        ) as prediction_pipeline:
            results = prediction_pipeline.forward(*inputs)

        if len(results) != len(expected):
            error = (error or "") + (
                f"Expected {len(expected)} outputs, but got {len(results)}"
            )
        else:
            for res, exp in zip(results, expected):
                try:
                    np.testing.assert_array_almost_equal(res, exp, decimal=decimal)
                except AssertionError as e:
                    error = (error or "") + f"Output and expected output disagree:\n {e}"
    except Exception as e:
        error = str(e)
        tb = traceback.format_tb(e.__traceback__)

    model.validation_summary.add_detail(
        ValidationDetail(
            name="Reproduce test outputs from test inputs",
            status="passed" if error is None else "failed",
            errors=(
                []
                if error is None
                else [
                    ErrorEntry(
                        loc=("weights",) if weight_format is None else ("weights", weight_format),
                        msg=error,
                        type="bioimageio.core",
                        traceback=tb,
                    )
                ]
            ),
        )
    )

def _test_model_inference_with_parametrized_inputs(
    model: v0_5.ModelDescr,
    weight_format: Optional[WeightsFormat],
    devices: Optional[List[str]],
) -> None:
    if not any(isinstance(a.size, v0_5.ParameterizedSize) for ipt in model.inputs for a in ipt.axes):
        return

    error: Optional[str] = None
    tb: List[str] = []
    try:
        test_inputs = [
            xr.DataArray(load_array(d.test_tensor.download().path), dims=tuple(a.id for a in d.axes))
            for d in model.inputs
        ]
        def generate_test_cases():
            for n in [0, 1, 2, 3]:



        with create_prediction_pipeline(
            bioimageio_model=model, devices=devices, weight_format=weight_format
        ) as prediction_pipeline:
            for n, inputs, exptected_output_shape in generate_test_cases():
                results = prediction_pipeline.forward(*inputs)

                if len(results) != len(exptected_output_shape):
                    error = (error or "") + (
                        f"Expected {len(exptected_output_shape)} outputs, but got {len(results)}"
                    )
                else:
                    for res, exp in zip(results, exptected_output_shape):
                        if res.shape != exp:
                            error = (error or "") + f"(n={n}) Expected output shape {exptected_output_shape}, but got {res.shape}\n"

                if error:
                    break
    except Exception as e:
        error = str(e)
        tb = traceback.format_tb(e.__traceback__)

    model.validation_summary.add_detail(
        ValidationDetail(
            name="Reproduce test outputs from test inputs",
            status="passed" if error is None else "failed",
            errors=(
                []
                if error is None
                else [
                    ErrorEntry(
                        loc=("weights",) if weight_format is None else ("weights", weight_format),
                        msg=error,
                        type="bioimageio.core",
                        traceback=tb,
                    )
                ]
            ),
        )
    )


def _test_expected_resource_type(rd: Union[InvalidDescr, ResourceDescr], expected_type: str):
    has_expected_type = rd.type == expected_type
    rd.validation_summary.details.append(
        ValidationDetail(
            name="Has expected resource type",
            status="passed" if has_expected_type else "failed",
            errors=(
                []
                if has_expected_type
                else [ErrorEntry(loc=("type",), type="type", msg=f"expected type {expected_type}, found {rd.type}")]
            ),
        )
    )


# def debug_model(
#     model_rdf: Union[RawResourceDescr, ResourceDescr, URI, Path, str],
#     *,
#     weight_format: Optional[WeightsFormat] = None,
#     devices: Optional[List[str]] = None,
# ):
#     """Run the model test and return dict with inputs, results, expected results and intermediates.

#     Returns dict with tensors "inputs", "inputs_processed", "outputs_raw", "outputs", "expected" and "diff".
#     """
#     inputs_raw: Optional = None
#     inputs_processed: Optional = None
#     outputs_raw: Optional = None
#     outputs: Optional = None
#     expected: Optional = None
#     diff: Optional = None

#     model = load_description(
#         model_rdf, weights_priority_order=None if weight_format is None else [weight_format]
#     )
#     if not isinstance(model, Model):
#         raise ValueError(f"Not a bioimageio.model: {model_rdf}")

#     prediction_pipeline = create_prediction_pipeline(
#         bioimageio_model=model, devices=devices, weight_format=weight_format
#     )
#     inputs = [
#         xr.DataArray(load_array(str(in_path)), dims=input_spec.axes)
#         for in_path, input_spec in zip(model.test_inputs, model.inputs)
#     ]
#     input_dict = {input_spec.name: input for input_spec, input in zip(model.inputs, inputs)}

#     # keep track of the non-processed inputs
#     inputs_raw = [deepcopy(input) for input in inputs]

#     computed_measures = {}

#     prediction_pipeline.apply_preprocessing(input_dict, computed_measures)
#     inputs_processed = list(input_dict.values())
#     outputs_raw = prediction_pipeline.predict(*inputs_processed)
#     output_dict = {output_spec.name: deepcopy(output) for output_spec, output in zip(model.outputs, outputs_raw)}
#     prediction_pipeline.apply_postprocessing(output_dict, computed_measures)
#     outputs = list(output_dict.values())

#     if isinstance(outputs, (np.ndarray, xr.DataArray)):
#         outputs = [outputs]

#     expected = [
#         xr.DataArray(load_array(str(out_path)), dims=output_spec.axes)
#         for out_path, output_spec in zip(model.test_outputs, model.outputs)
#     ]
#     if len(outputs) != len(expected):
#         error = f"Number of outputs and number of expected outputs disagree: {len(outputs)} != {len(expected)}"
#         print(error)
#     else:
#         diff = []
#         for res, exp in zip(outputs, expected):
#             diff.append(res - exp)

#     return {
#         "inputs": inputs_raw,
#         "inputs_processed": inputs_processed,
#         "outputs_raw": outputs_raw,
#         "outputs": outputs,
#         "expected": expected,
#         "diff": diff,
#     }
