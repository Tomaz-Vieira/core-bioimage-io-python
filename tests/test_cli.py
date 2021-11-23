import subprocess

import numpy as np
import pytest

from bioimageio.core import load_resource_description


def test_validate_model(unet2d_nuclei_broad_model):
    ret = subprocess.run(["bioimageio", "validate", unet2d_nuclei_broad_model])
    assert ret.returncode == 0


def test_cli_package(unet2d_nuclei_broad_model):
    ret = subprocess.run(["bioimageio", "package", unet2d_nuclei_broad_model])
    assert ret.returncode == 0


def test_cli_test_model(unet2d_nuclei_broad_model):
    ret = subprocess.run(["bioimageio", "test-model", unet2d_nuclei_broad_model])
    assert ret.returncode == 0


def test_cli_test_model_with_weight_format(unet2d_nuclei_broad_model):
    ret = subprocess.run(
        ["bioimageio", "test-model", unet2d_nuclei_broad_model, "--weight-format", "pytorch_state_dict"]
    )
    assert ret.returncode == 0


def test_cli_test_resource(unet2d_nuclei_broad_model):
    ret = subprocess.run(["bioimageio", "test-model", unet2d_nuclei_broad_model])
    assert ret.returncode == 0


def test_cli_test_resource_with_weight_format(unet2d_nuclei_broad_model):
    ret = subprocess.run(
        ["bioimageio", "test-model", unet2d_nuclei_broad_model, "--weight-format", "pytorch_state_dict"]
    )
    assert ret.returncode == 0


def _test_cli_predict_image(model, tmp_path, extra_kwargs=None):
    spec = load_resource_description(model)
    in_path = spec.test_inputs[0]
    out_path = tmp_path.with_suffix(".npy")
    cmd = ["bioimageio", "predict-image", model, "--inputs", str(in_path), "--outputs", str(out_path)]
    if extra_kwargs is not None:
        cmd.extend(extra_kwargs)
    ret = subprocess.run(cmd)
    assert ret.returncode == 0
    assert out_path.exists()


def test_cli_predict_image(unet2d_nuclei_broad_model, tmp_path):
    _test_cli_predict_image(unet2d_nuclei_broad_model, tmp_path)


def test_cli_predict_image_with_weight_format(unet2d_nuclei_broad_model, tmp_path):
    _test_cli_predict_image(unet2d_nuclei_broad_model, tmp_path, ["--weight-format", "pytorch_state_dict"])


def _test_cli_predict_images(model, tmp_path, extra_kwargs=None):
    n_images = 3
    shape = (1, 1, 128, 128)
    expected_shape = (1, 1, 128, 128)

    in_folder = tmp_path / "inputs"
    in_folder.mkdir()
    out_folder = tmp_path / "outputs"
    out_folder.mkdir()

    expected_outputs = []
    for i in range(n_images):
        path = in_folder / f"im-{i}.npy"
        im = np.random.randint(0, 255, size=shape).astype("uint8")
        np.save(path, im)
        expected_outputs.append(out_folder / f"im-{i}.npy")

    input_pattern = str(in_folder / "*.npy")
    cmd = ["bioimageio", "predict-images", model, input_pattern, str(out_folder)]
    if extra_kwargs is not None:
        cmd.extend(extra_kwargs)
    ret = subprocess.run(cmd)
    assert ret.returncode == 0

    for out_path in expected_outputs:
        assert out_path.exists()
        assert np.load(out_path).shape == expected_shape


def test_cli_predict_images(unet2d_nuclei_broad_model, tmp_path):
    _test_cli_predict_images(unet2d_nuclei_broad_model, tmp_path)


def test_cli_predict_images_with_weight_format(unet2d_nuclei_broad_model, tmp_path):
    _test_cli_predict_images(unet2d_nuclei_broad_model, tmp_path, ["--weight-format", "pytorch_state_dict"])


def test_torch_to_torchscript(unet2d_nuclei_broad_model, tmp_path):
    out_path = tmp_path.with_suffix(".pt")
    ret = subprocess.run(
        ["bioimageio", "convert-torch-weights-to-torchscript", str(unet2d_nuclei_broad_model), str(out_path)]
    )
    assert ret.returncode == 0
    assert out_path.exists()


@pytest.mark.skipif(pytest.skip_onnx, reason="requires torch and onnx")
def test_torch_to_onnx(unet2d_nuclei_broad_model, tmp_path):
    out_path = tmp_path.with_suffix(".onnx")
    ret = subprocess.run(["bioimageio", "convert-torch-weights-to-onnx", str(unet2d_nuclei_broad_model), str(out_path)])
    assert ret.returncode == 0
    assert out_path.exists()
