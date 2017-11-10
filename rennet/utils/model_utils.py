"""
@motjuste
Created: 08-11-2017

Utilities for working with models
"""
from __future__ import print_function, division
import numpy as np
import warnings


class BaseRennetModel(object):
    """Base class for rennet models"""

    def preprocess(self, filepath, *arge, **kwargs):
        raise NotImplementedError

    def predict(self, *args, **kwargs):
        raise NotImplementedError

    def postprocess(self, *args, **kwargs):
        raise NotImplementedError

    def output(self, *args, **kwargs):
        raise NotImplementedError

    def export(self, to_file, *args, **kwargs):
        raise NotImplementedError

    @classmethod
    def from_model_file(cls, model_fp, *args, **kwargs):
        raise NotImplementedError


def mergepreds_avg(preds, weights=None, **kwargs):
    # FIXME: handle single pred provided as preds
    p = np.stack(preds, axis=-1)
    if weights is not None:
        if isinstance(weights, (int, float)):
            weights = [weights] * len(preds)

        assert len(weights) == len(preds), "provide weights for each pred: "+\
            "not {} vs expected {}".format(len(weights), len(preds))

        for i, w in enumerate(weights):
            p[..., i] *= w

    p = p.sum(axis=-1)

    return p / p.sum(axis=1)[..., None]


def validate_rennet_version(minversion, srcversion):
    from rennet import __version__ as curversion

    getversion = lambda version: tuple(map(int, version.split('.')))
    _curversion = getversion(curversion)
    _minversion = getversion(minversion)
    _srcversion = getversion(srcversion)

    if _curversion < _minversion:
        raise RuntimeError(
            "Please update rennet. Current: {}, Minimum Required for this model: {}".
            format(curversion, minversion))

    if _curversion < _srcversion:
        warnings.warn(
            RuntimeWarning(
                "Please update rennet to the latest version for best compatibility and stability"
            ))