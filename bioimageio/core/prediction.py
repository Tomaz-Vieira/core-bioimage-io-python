"""coming soon"""

# TODO: update
import collections.abc
import os
from fractions import Fraction
from itertools import product
from pathlib import Path
from typing import (
    Any,
    Dict,
    Hashable,
    Iterator,
    List,
    Mapping,
    NamedTuple,
    Optional,
    OrderedDict,
    Sequence,
    Tuple,
    Union,
)

import numpy as np
import xarray as xr
from numpy.typing import NDArray
from pydantic import HttpUrl
from tqdm import tqdm

from bioimageio.core.tensor import Tensor, TensorId
from bioimageio.spec import ResourceDescr, load_description
from bioimageio.spec.model import v0_4, v0_5
from bioimageio.spec.model.v0_5 import AxisType

from ._prediction_pipeline import PredictionPipeline, create_prediction_pipeline

# def _predict_with_tiling_impl(
#     prediction_pipeline: PredictionPipeline,
#     inputs: Sequence[xr.DataArray],
#     outputs: Sequence[xr.DataArray],
#     tile_shapes: Sequence[Dict[str, int]],
#     halos: Sequence[Dict[str, int]],
#     scales: Sequence[Dict[str, Tuple[int, int]]],
#     verbose: bool = False,
# ):
#     if len(inputs) > 1:
#         raise NotImplementedError("Tiling with multiple inputs not implemented yet")

#     if len(outputs) > 1:
#         raise NotImplementedError("Tiling with multiple outputs not implemented yet")

#     assert len(tile_shapes) == len(outputs)
#     assert len(halos) == len(outputs)

#     input_ = inputs[0]
#     output = outputs[0]
#     tile_shape = tile_shapes[0]
#     halo = halos[0]
#     scaling = scales[0]

#     tiles = get_tiling(shape=input_.shape, tile_shape=tile_shape, halo=halo, input_axes=input_.dims, scaling=scaling)

#     def load_tile(tile):
#         inp = input_[tile]
#         # whether to pad on the right or left of the dim for the spatial dims
#         # + placeholders for batch and axis dimension, where we don't pad
#         pad_right = [tile[ax].start == 0 if ax in "xyz" else None for ax in input_.dims]
#         return inp, pad_right

#     if verbose:
#         shape = {ax: sh for ax, sh in zip(prediction_pipeline.input_specs[0].axes, input_.shape)}
#         n_tiles = int(np.prod([np.ceil(float(shape[ax]) / (tsh - 2 * halo[ax])) for ax, tsh in tile_shape.items()]))
#         tiles = tqdm(tiles, total=n_tiles, desc="prediction with tiling")

#     # we need to use padded prediction for the individual tiles in case the
#     # border tiles don't match the requested tile shape
#     padding = {ax: tile_shape[ax] for ax in input_axes if ax in "xyz"}
#     padding["mode"] = "fixed"
#     for outer_tile, inner_tile, local_tile in tiles:
#         inp, pad_right = load_tile(outer_tile)
#         out = predict_with_padding(prediction_pipeline, inp, padding, pad_right)
#         assert len(out) == 1
#         out = out[0]
#         output[inner_tile] = out[local_tile]


def predict(
    prediction_pipeline: PredictionPipeline,
    inputs: Union[
        Tensor,
        NDArray[Any],
        Sequence[Union[Tensor, NDArray[Any]]],
        Mapping[Union[TensorId, str], Union[Tensor, NDArray[Any]]],
    ],
) -> List[xr.DataArray]:
    """Run prediction for a single set of input(s) with a bioimage.io model

    Args:
        prediction_pipeline: the prediction pipeline for the input model.
        inputs: the input(s) for this model represented as xarray data or numpy nd array.
    """
    if isinstance(inputs, collections.abc.Mapping):
        inputs_seq = [
            inputs.get(str(tid), inputs[tid]) for tid in prediction_pipeline.input_ids
        ]
    else:
        if isinstance(inputs, (Tensor, np.ndarray)):
            inputs_seq = [inputs]
        else:
            inputs_seq = inputs

        assert len(inputs_seq) == len(prediction_pipeline.input_ids)

    tagged_data = [
        ipt if isinstance(ipt, Tensor) else Tensor.from_numpy(ipt, dims=ipt_spec.axes)
        for ipt, ipt_spec in zip(inputs, prediction_pipeline.input_axes)
    ]
    return prediction_pipeline.forward(*tagged_data)


# def _parse_padding(padding, input_specs):
#     if padding is None:  # no padding
#         return padding
#     if len(input_specs) > 1:
#         raise NotImplementedError("Padding for multiple inputs not yet implemented")

#     input_spec = input_specs[0]
#     pad_keys = tuple(input_spec.axes) + ("mode",)

#     def check_padding(padding):
#         assert all(k in pad_keys for k in padding.keys())

#     if isinstance(padding, dict):  # pre-defined padding
#         check_padding(padding)
#     elif isinstance(padding, bool):  # determine padding from spec
#         if padding:
#             axes = input_spec.axes
#             shape = input_spec.shape
#             if isinstance(shape, list):  # fixed padding
#                 padding = {ax: sh for ax, sh in zip(axes, shape) if ax in "xyz"}
#                 padding["mode"] = "fixed"
#             else:  # dynamic padding
#                 step = shape.step
#                 padding = {ax: st for ax, st in zip(axes, step) if ax in "xyz"}
#                 padding["mode"] = "dynamic"
#             check_padding(padding)
#         else:  # no padding
#             padding = None
#     else:
#         raise ValueError(f"Invalid argument for padding: {padding}")
#     return padding


# def predict_with_padding(
#     prediction_pipeline: PredictionPipeline,
#     inputs: Union[xr.DataArray, List[xr.DataArray], Tuple[xr.DataArray]],
#     padding: Union[bool, Dict[str, int]] = True,
#     pad_right: bool = True,
# ) -> List[xr.DataArray]:
#     """Run prediction with padding for a single set of input(s) with a bioimage.io model.

#     Args:
#         prediction_pipeline: the prediction pipeline for the input model.
#         inputs: the input(s) for this model represented as xarray data.
#         padding: the padding settings. Pass True to derive from the model spec.
#         pad_right: whether to applying padding to the right or left of the input.
#     """
#     if not padding:
#         raise ValueError
#     assert len(inputs) == len(prediction_pipeline.input_specs)

#     output_spec = prediction_pipeline.output_specs[0]
#     if hasattr(output_spec.shape, "scale"):
#         scale = dict(zip(output_spec.axes, output_spec.shape.scale))
#         offset = dict(zip(output_spec.axes, output_spec.shape.offset))
#         network_resizes = any(sc != 1 for ax, sc in scale.items() if ax in "xyz") or any(
#             off != 0 for ax, off in offset.items() if ax in "xyz"
#         )
#     else:
#         network_resizes = False

#     padding = _parse_padding(padding, prediction_pipeline.input_specs)
#     if not isinstance(inputs, (tuple, list)):
#         inputs = [inputs]
#     if not isinstance(padding, (tuple, list)):
#         padding = [padding]
#     assert len(padding) == len(prediction_pipeline.input_specs)
#     inputs, crops = zip(
#         *[
#             image_helper.pad(inp, spec.axes, p, pad_right=pad_right)
#             for inp, spec, p in zip(inputs, prediction_pipeline.input_specs, padding)
#         ]
#     )
#     result = predict(prediction_pipeline, inputs)
#     if network_resizes:
#         crops = [
#             {
#                 ax: (
#                     slice(
#                         crp.start if crp.start is None else int(crp.start * scale[ax] + 2 * offset[ax]),
#                         crp.stop if crp.stop is None else int(crp.stop * scale[ax] + 2 * offset[ax]),
#                     )
#                     if ax in "xyz"
#                     else crp
#                 )
#                 for ax, crp in crop.items()
#             }
#             for crop in crops
#         ]
#     return [res[crop] for res, crop in zip(result, crops)]


# # simple heuristic to determine suitable shape from min and step
# def _determine_shape(min_shape, step, axes):
#     is3d = "z" in axes
#     min_len = 64 if is3d else 256
#     shape = []
#     for ax, min_ax, step_ax in zip(axes, min_shape, step):
#         if ax in "zyx" and step_ax > 0:
#             len_ax = min_ax
#             while len_ax < min_len:
#                 len_ax += step_ax
#             shape.append(len_ax)
#         else:
#             shape.append(min_ax)
#     return shape


# def _parse_tiling(tiling, input_specs, output_specs):
#     if tiling is None:  # no tiling
#         return tiling
#     if len(input_specs) > 1:
#         raise NotImplementedError("Tiling for multiple inputs not yet implemented")
#     if len(output_specs) > 1:
#         raise NotImplementedError("Tiling for multiple outputs not yet implemented")

#     input_spec = input_specs[0]
#     output_spec = output_specs[0]
#     if isinstance(output_spec.shape, list):
#         assert isinstance(input_spec.shape, list) and input_spec.shape == output_spec.shape, (
#             "When predicting with tiling, output_shape and input_shape must either be specified "
#             "explictly and must be identical, or output_shape must be"
#             "implicitly defined by input_shape, otherwise relationship between "
#             "input and output shapes per tile cannot be known."
#         )
#     axes = input_spec.axes

#     def check_tiling(tiling):
#         assert "halo" in tiling and "tile" in tiling
#         spatial_axes = [ax for ax in axes if ax in "xyz"]
#         halo = tiling["halo"]
#         tile = tiling["tile"]
#         scale = tiling.get("scale", dict())
#         assert all(halo.get(ax, 0) >= 0 for ax in spatial_axes)
#         assert all(tile.get(ax, 0) > 0 for ax in spatial_axes)
#         assert all(scale.get(ax, 1) > 0 for ax in spatial_axes)

#     if isinstance(tiling, dict) or (isinstance(tiling, bool) and tiling):
#         # NOTE we assume here that shape in input and output are the same
#         # for different input and output shapes, we should actually tile in the
#         # output space and then request the corresponding input tiles
#         # so we would need to apply the output scale and offset to the
#         # input shape to compute the tile size and halo here
#         shape = input_spec.shape
#         if not isinstance(shape, list):
#             shape = _determine_shape(shape.min, shape.step, axes)
#         assert isinstance(shape, list)
#         assert len(shape) == len(axes)

#         scale = None
#         output_shape = output_spec.shape
#         scale = [1.0] * len(output_spec.shape) if isinstance(output_shape, list) else output_shape.scale
#         assert len(scale) == len(axes)

#         halo = output_spec.halo
#         if not isinstance(halo, list):
#             halo = [0] * len(axes)
#         assert len(halo) == len(axes)

#         default_tiling = {
#             "halo": {ax: ha for ax, ha in zip(axes, halo) if ax in "xyz"},
#             "tile": {ax: sh for ax, sh in zip(axes, shape) if ax in "xyz"},
#             "scale": {ax: sc for ax, sc in zip(axes, scale) if ax in "xyz"},
#         }

#         # override metadata defaults with provided dict
#         if isinstance(tiling, dict):
#             for key in ["halo", "tile", "scale"]:
#                 default_tiling[key].update(tiling.get(key, dict()))
#         tiling = default_tiling
#         check_tiling(tiling)

#     elif isinstance(tiling, bool) and not tiling:
#         raise NotImplementedError("Should be unreachable")

#     else:
#         raise ValueError(f"Invalid argument for tiling: {tiling}")

#     return tiling


# def predict_with_tiling(
#     prediction_pipeline: PredictionPipeline,
#     inputs: Union[xr.DataArray, List[xr.DataArray], Tuple[xr.DataArray]],
#     tiling: Union[bool, Dict[str, Dict[str, int]]] = True,
#     verbose: bool = False,
# ) -> List[xr.DataArray]:
#     """Run prediction with tiling for a single set of input(s) with a bioimage.io model.

#     Args:
#         prediction_pipeline: the prediction pipeline for the input model.
#         inputs: the input(s) for this model represented as xarray data.
#         tiling: the tiling settings. Pass True to derive from the model spec.
#         verbose: whether to print the prediction progress.
#     """
#     if not tiling:
#         raise ValueError("cannot call predict_with_tiling with tiling=False")
#     assert len(inputs) == len(prediction_pipeline.input_specs)

#     tiling = _parse_tiling(tiling, prediction_pipeline.input_specs, prediction_pipeline.output_specs)
#     if not isinstance(inputs, (list, tuple)):
#         inputs = [inputs]
#     named_inputs: OrderedDict[str, xr.DataArray] = collections.OrderedDict(
#         **{
#             ipt_spec.name: xr.DataArray(ipt_data, dims=tuple(ipt_spec.axes))
#             for ipt_data, ipt_spec in zip(inputs, prediction_pipeline.input_specs)
#         }
#     )

#     outputs = []
#     for output_spec in prediction_pipeline.output_specs:
#         if isinstance(output_spec.shape, ImplicitOutputShape):
#             scale = dict(zip(output_spec.axes, output_spec.shape.scale))
#             offset = dict(zip(output_spec.axes, output_spec.shape.offset))

#             ref_input = named_inputs[output_spec.shape.reference_tensor]
#             ref_input_shape = dict(zip(ref_input.dims, ref_input.shape))
#             output_shape = tuple(int(scale[ax] * ref_input_shape[ax] + 2 * offset[ax]) for ax in output_spec.axes)
#         else:
#             if len(inputs) > 1:
#                 raise NotImplementedError
#             input_spec = prediction_pipeline.input_specs[0]
#             if input_spec.axes != output_spec.axes:
#                 raise NotImplementedError("Tiling with a different output shape is not yet supported")
#             out_axes = output_spec.axes
#             fixed_shape = tuple(output_spec.shape)
#             if not all(fixed_shape[out_axes.index(ax)] == tile_shape for ax, tile_shape in tiling["tile"].items()):
#                 raise NotImplementedError("Tiling with a different output shape is not yet supported")

#             output_shape = list(inputs[0].shape)
#             chan_id = out_axes.index("c")
#             if fixed_shape[chan_id] != output_shape[chan_id]:
#                 output_shape[chan_id] = fixed_shape[chan_id]
#             output_shape = tuple(output_shape)

#         outputs.append(xr.DataArray(np.zeros(output_shape, dtype=output_spec.data_type), dims=tuple(output_spec.axes)))

#     _predict_with_tiling_impl(
#         prediction_pipeline,
#         list(named_inputs.values()),
#         outputs,
#         tile_shapes=[tiling["tile"]],  # todo: update tiling for multiple inputs/outputs
#         halos=[tiling["halo"]],
#         scales=[tiling["scale"]],
#         verbose=verbose,
#     )

#     return outputs


# def _predict_sample(prediction_pipeline, inputs, outputs, padding, tiling):
#     if padding and tiling:
#         raise ValueError("Only one of padding or tiling is supported")

#     input_data = image_helper.load_tensors(inputs, prediction_pipeline.input_specs)
#     if padding is not None:
#         result = predict_with_padding(prediction_pipeline, input_data, padding)
#     elif tiling is not None:
#         result = predict_with_tiling(prediction_pipeline, input_data, tiling)
#     else:
#         result = predict(prediction_pipeline, input_data)

#     assert isinstance(result, list)
#     assert len(result) == len(outputs)
#     for res, out in zip(result, outputs):
#         image_helper.save_image(out, res)


# def predict_image(
#     model_rdf: DescriptionSource,
#     inputs: Union[Tuple[Path, ...], List[Path], Path],
#     outputs: Union[Tuple[Path, ...], List[Path], Path],
#     padding: Optional[Union[bool, Dict[str, int]]] = None,
#     tiling: Optional[Union[bool, Dict[str, Dict[str, int]]]] = None,
#     weight_format: Optional[str] = None,
#     devices: Optional[List[str]] = None,
#     verbose: bool = False,
# ):
#     """Run prediction for a single set of input image(s) with a bioimage.io model.

#     Args:
#         model_rdf: the bioimageio model.
#         inputs: the filepaths for the input images.
#         outputs: the filepaths for saving the input images.
#         padding: the padding settings for prediction. By default no padding is used.
#         tiling: the tiling settings for prediction. By default no tiling is used.
#         weight_format: the weight format to use for predictions.
#         devices: the devices to use for prediction.
#         verbose: run prediction in verbose mode.
#     """
#     if not isinstance(inputs, (tuple, list)):
#         inputs = [inputs]

#     if not isinstance(outputs, (tuple, list)):
#         outputs = [outputs]

#     model = load_description(model_rdf)
#     assert isinstance(model, Model)
#     if len(model.inputs) != len(inputs):
#         raise ValueError
#     if len(model.outputs) != len(outputs):
#         raise ValueError

#     with create_prediction_pipeline(
#         bioimageio_model=model, weight_format=weight_format, devices=devices
#     ) as prediction_pipeline:
#         _predict_sample(prediction_pipeline, inputs, outputs, padding, tiling)


# def predict_images(
#     model_rdf: DescriptionSource,
#     inputs: Sequence[Union[Tuple[Path, ...], List[Path], Path]],
#     outputs: Sequence[Union[Tuple[Path, ...], List[Path], Path]],
#     padding: Optional[Union[bool, Dict[str, int]]] = None,
#     tiling: Optional[Union[bool, Dict[str, Dict[str, int]]]] = None,
#     weight_format: Optional[str] = None,
#     devices: Optional[List[str]] = None,
#     verbose: bool = False,
# ):
#     """Predict multiple input images with a bioimage.io model.

#     Args:
#         model_rdf: the bioimageio model.
#         inputs: the filepaths for the input images.
#         outputs: the filepaths for saving the input images.
#         padding: the padding settings for prediction. By default no padding is used.
#         tiling: the tiling settings for prediction. By default no tiling is used.
#         weight_format: the weight format to use for predictions.
#         devices: the devices to use for prediction.
#         verbose: run prediction in verbose mode.
#     """

#     model = load_description(model_rdf)
#     assert isinstance(model, Model)

#     with create_prediction_pipeline(
#         bioimageio_model=model, weight_format=weight_format, devices=devices
#     ) as prediction_pipeline:
#         prog = zip(inputs, outputs)
#         if verbose:
#             prog = tqdm(prog, total=len(inputs))

#         for inp, outp in prog:
#             if not isinstance(inp, (tuple, list)):
#                 inp = [inp]

#             if not isinstance(outp, (tuple, list)):
#                 outp = [outp]

#             _predict_sample(prediction_pipeline, inp, outp, padding, tiling)
