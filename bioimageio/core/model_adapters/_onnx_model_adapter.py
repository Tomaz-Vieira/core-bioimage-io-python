import warnings
from typing import Any, List, Optional, Sequence, Union

from numpy.typing import NDArray

from bioimageio.core.tensor import Tensor
from bioimageio.spec.model import v0_4, v0_5

from ._model_adapter import ModelAdapter

try:
    import onnxruntime as rt
except Exception:
    rt = None


class ONNXModelAdapter(ModelAdapter):
    def __init__(
        self,
        *,
        model_description: Union[v0_4.ModelDescr, v0_5.ModelDescr],
        devices: Optional[Sequence[str]] = None,
    ):
        if rt is None:
            raise ImportError("onnxruntime")

        super().__init__()
        self._internal_output_axes = [
            (
                tuple(out.axes)
                if isinstance(out.axes, str)
                else tuple(a.id for a in out.axes)
            )
            for out in model_description.outputs
        ]
        if model_description.weights.onnx is None:
            raise ValueError("No ONNX weights specified for {model_description.name}")

        self._session = rt.InferenceSession(str(model_description.weights.onnx.source))
        onnx_inputs = self._session.get_inputs()  # type: ignore
        self._input_names: List[str] = [ipt.name for ipt in onnx_inputs]  # type: ignore

        if devices is not None:
            warnings.warn(
                f"Device management is not implemented for onnx yet, ignoring the devices {devices}"
            )

    def forward(self, *input_tensors: Optional[Tensor]) -> List[Optional[Tensor]]:
        assert len(input_tensors) == len(self._input_names)
        input_arrays = [None if ipt is None else ipt.data for ipt in input_tensors]
        result: Union[Sequence[Optional[NDArray[Any]]], Optional[NDArray[Any]]]
        result = self._session.run(  # pyright: ignore[reportUnknownVariableType]
            None, dict(zip(self._input_names, input_arrays))
        )
        if isinstance(result, (list, tuple)):
            result_seq: Sequence[Optional[NDArray[Any]]] = result
        else:
            result_seq = [result]  # type: ignore

        return [
            None if r is None else Tensor(r, dims=axes)
            for r, axes in zip(result_seq, self._internal_output_axes)
        ]

    def unload(self) -> None:
        warnings.warn(
            "Device management is not implemented for onnx yet, cannot unload model"
        )
