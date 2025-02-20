from typing import (
    Iterable,
    List,
    Mapping,
    NamedTuple,
    Optional,
    Sequence,
    Set,
    Tuple,
    Union,
)

from typing_extensions import assert_never

from bioimageio.spec.model import AnyModelDescr, v0_4, v0_5
from bioimageio.spec.model.v0_5 import TensorId

from .digest_spec import get_member_ids
from .proc_ops import (
    AddKnownDatasetStats,
    EnsureDtype,
    Processing,
    UpdateStats,
    get_proc_class,
    postproc_v4_to_processing,
    postproc_v5_to_processing,
    preproc_v4_to_processing,
    preproc_v5_to_processing,
)
from .sample import Sample
from .stat_calculators import StatsCalculator
from .stat_measures import (
    DatasetMeasure,
    DatasetMeasureBase,
    Measure,
    MeasureValue,
    SampleMeasure,
    SampleMeasureBase,
)

TensorDescr = Union[
    v0_4.InputTensorDescr,
    v0_4.OutputTensorDescr,
    v0_5.InputTensorDescr,
    v0_5.OutputTensorDescr,
]


class PreAndPostprocessing(NamedTuple):
    pre: List[Processing]
    post: List[Processing]


class _SetupProcessing(NamedTuple):
    pre: List[Processing]
    post: List[Processing]
    pre_measures: Set[Measure]
    post_measures: Set[Measure]


def setup_pre_and_postprocessing(
    model: AnyModelDescr,
    dataset_for_initial_statistics: Iterable[Sample],
    keep_updating_initial_dataset_stats: bool = False,
    fixed_dataset_stats: Optional[Mapping[DatasetMeasure, MeasureValue]] = None,
) -> PreAndPostprocessing:
    """
    Get pre- and postprocessing operators for a `model` description.
    userd in `bioimageio.core.create_prediction_pipeline"""
    prep, post, prep_meas, post_meas = _prepare_setup_pre_and_postprocessing(model)

    missing_dataset_stats = {
        m
        for m in prep_meas | post_meas
        if fixed_dataset_stats is None or m not in fixed_dataset_stats
    }
    if missing_dataset_stats:
        initial_stats_calc = StatsCalculator(missing_dataset_stats)
        for sample in dataset_for_initial_statistics:
            initial_stats_calc.update(sample)

        initial_stats = initial_stats_calc.finalize()
    else:
        initial_stats = {}

    prep.insert(
        0,
        UpdateStats(
            StatsCalculator(prep_meas, initial_stats),
            keep_updating_initial_dataset_stats=keep_updating_initial_dataset_stats,
        ),
    )
    if post_meas:
        post.insert(
            0,
            UpdateStats(
                StatsCalculator(post_meas, initial_stats),
                keep_updating_initial_dataset_stats=keep_updating_initial_dataset_stats,
            ),
        )

    if fixed_dataset_stats:
        prep.insert(0, AddKnownDatasetStats(fixed_dataset_stats))
        post.insert(0, AddKnownDatasetStats(fixed_dataset_stats))

    return PreAndPostprocessing(prep, post)


class RequiredMeasures(NamedTuple):
    pre: Set[Measure]
    post: Set[Measure]


class RequiredDatasetMeasures(NamedTuple):
    pre: Set[DatasetMeasure]
    post: Set[DatasetMeasure]


class RequiredSampleMeasures(NamedTuple):
    pre: Set[SampleMeasure]
    post: Set[SampleMeasure]


def get_requried_measures(model: AnyModelDescr) -> RequiredMeasures:
    s = _prepare_setup_pre_and_postprocessing(model)
    return RequiredMeasures(s.pre_measures, s.post_measures)


def get_required_dataset_measures(model: AnyModelDescr) -> RequiredDatasetMeasures:
    s = _prepare_setup_pre_and_postprocessing(model)
    return RequiredDatasetMeasures(
        {m for m in s.pre_measures if isinstance(m, DatasetMeasureBase)},
        {m for m in s.post_measures if isinstance(m, DatasetMeasureBase)},
    )


def get_requried_sample_measures(model: AnyModelDescr) -> RequiredSampleMeasures:
    s = _prepare_setup_pre_and_postprocessing(model)
    return RequiredSampleMeasures(
        {m for m in s.pre_measures if isinstance(m, SampleMeasureBase)},
        {m for m in s.post_measures if isinstance(m, SampleMeasureBase)},
    )

def _prepare_v4_preprocs(tensor_descrs: Sequence[v0_4.InputTensorDescr]) -> Tuple[List[Processing], Set[Measure]]:
    procs: List[Processing] = []
    for t_descr in tensor_descrs:
        member_id = TensorId(str(t_descr.name))
        procs.append(
            EnsureDtype(input=member_id, output=member_id, dtype=t_descr.data_type)
        )
        for proc_d in t_descr.preprocessing:
            procs.append(preproc_v4_to_processing(t_descr, proc_d))
    measures = {m for proc in procs for m in proc.required_measures}
    return (procs, measures)

def _prepare_v4_postprocs(tensor_descrs: Sequence[v0_4.OutputTensorDescr]) -> Tuple[List[Processing], Set[Measure]]:
    procs: List[Processing] = []
    for t_descr in tensor_descrs:
        member_id = TensorId(str(t_descr.name))
        procs.append(
            EnsureDtype(input=member_id, output=member_id, dtype=t_descr.data_type)
        )
        for proc_d in t_descr.postprocessing:
            procs.append(postproc_v4_to_processing(t_descr, proc_d))
    measures = {m for proc in procs for m in proc.required_measures}
    return (procs, measures)

def _prepare_v5_preprocs(tensor_descrs: Sequence[v0_5.InputTensorDescr]) -> Tuple[List[Processing], Set[Measure]]:
    procs: List[Processing] = []
    for t_descr in tensor_descrs:
        for proc_d in t_descr.preprocessing:
            procs.append(preproc_v5_to_processing(t_descr, proc_d))
    measures = {m for proc in procs for m in proc.required_measures}
    return (procs, measures)

def _prepare_v5_postprocs(tensor_descrs: Sequence[v0_5.OutputTensorDescr]) -> Tuple[List[Processing], Set[Measure]]:
    procs: List[Processing] = []
    for t_descr in tensor_descrs:
        for proc_d in t_descr.postprocessing:
            procs.append(postproc_v5_to_processing(t_descr, proc_d))
    measures = {m for proc in procs for m in proc.required_measures}
    return (procs, measures)


def _prepare_setup_pre_and_postprocessing(model: AnyModelDescr) -> _SetupProcessing:
    if isinstance(model, v0_4.ModelDescr):
        pre, pre_measures = _prepare_v4_preprocs(model.inputs)
        post, post_measures = _prepare_v4_postprocs(model.outputs)
    elif isinstance(model, v0_5.ModelDescr):
        pre, pre_measures = _prepare_v5_preprocs(model.inputs)
        post, post_measures = _prepare_v5_postprocs(model.outputs)
    else:
        assert_never(model)

    return _SetupProcessing(
        pre=pre,
        post=post,
        pre_measures=pre_measures,
        post_measures=post_measures,
    )
