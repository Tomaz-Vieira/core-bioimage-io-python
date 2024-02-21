import warnings
from pathlib import Path
from typing import Any, Dict, List, Sequence, cast

import numpy as np
import torch
from numpy.testing import assert_array_almost_equal

from bioimageio.spec import load_description
from bioimageio.spec.model import v0_4, v0_5
from bioimageio.core.weight_converter.torch.utils import load_model
from bioimageio.spec.common import InvalidDescription
from bioimageio.spec.utils import download


def add_onnx_weights(
    model_spec: "str | Path | v0_4.ModelDescr | v0_5.ModelDescr",
    *,
    output_path: Path,
    use_tracing: bool = True,
    test_decimal: int = 4,
    verbose: bool = False,
    opset_version: "int | None" = None,
):
    """Convert model weights from format 'pytorch_state_dict' to 'onnx'.

    Args:
        source_model: model without onnx weights
        opset_version: onnx opset version
        use_tracing: whether to use tracing or scripting to export the onnx format
        test_decimal: precision for testing whether the results agree
    """
    if isinstance(model_spec, (str, Path)):
        loaded_spec = load_description(Path(model_spec))
        if isinstance(loaded_spec, InvalidDescription):
            raise ValueError(f"Bad resource description: {loaded_spec}")
        if not isinstance(loaded_spec, (v0_4.ModelDescr, v0_5.ModelDescr)):
            raise TypeError(
                f"Path {model_spec} is a {loaded_spec.__class__.__name__}, expected a v0_4.ModelDescr or v0_5.ModelDescr"
            )
        model_spec = loaded_spec

    state_dict_weights_descr = model_spec.weights.pytorch_state_dict
    if state_dict_weights_descr is None:
        raise ValueError(f"The provided model does not have weights in the pytorch state dict format")

    with torch.no_grad():
        if isinstance(model_spec, v0_4.ModelDescr):
            downloaded_test_inputs = [download(inp) for inp in model_spec.test_inputs]
        else:
            downloaded_test_inputs = [inp.test_tensor.download() for inp in model_spec.inputs]

        input_data: List[np.ndarray[Any, Any]] = [np.load(dl.path).astype("float32") for dl in downloaded_test_inputs]
        input_tensors = [torch.from_numpy(inp) for inp in input_data]

        model = load_model(state_dict_weights_descr)

        expected_tensors = model(*input_tensors)
        if isinstance(expected_tensors, torch.Tensor):
            expected_tensors = [expected_tensors]
        expected_outputs: List[np.ndarray[Any, Any]] = [out.numpy() for out in expected_tensors]

        if use_tracing:
            torch.onnx.export(
                model,
                tuple(input_tensors) if len(input_tensors) > 1 else input_tensors[0],
                str(output_path),
                verbose=verbose,
                opset_version=opset_version,
            )
        else:
            raise NotImplementedError

    try:
        import onnxruntime as rt  # pyright: ignore [reportMissingTypeStubs]
    except ImportError:
        msg = "The onnx weights were exported, but onnx rt is not available and weights cannot be checked."
        warnings.warn(msg)
        return

    # check the onnx model
    sess = rt.InferenceSession(str(output_path))
    onnx_input_node_args = cast(List[Any], sess.get_inputs())  # fixme: remove cast, try using rt.NodeArg instead of Any
    onnx_inputs: Dict[str, np.ndarray[Any, Any]] = {
        input_name.name: inp for input_name, inp in zip(onnx_input_node_args, input_data)
    }
    outputs = cast(Sequence[np.ndarray[Any, Any]], sess.run(None, onnx_inputs))  # FIXME: remove cast

    try:
        for exp, out in zip(expected_outputs, outputs):
            assert_array_almost_equal(exp, out, decimal=test_decimal)
        return 0
    except AssertionError as e:
        msg = f"The onnx weights were exported, but results before and after conversion do not agree:\n {str(e)}"
        warnings.warn(msg)
        return 1
