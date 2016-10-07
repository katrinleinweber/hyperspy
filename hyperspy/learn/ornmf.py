# -*- coding: utf-8 -*-
# Copyright 2016 The HyperSpy developers
#
# This file is part of  HyperSpy.
#
#  HyperSpy is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
#  HyperSpy is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with  HyperSpy.  If not, see <http://www.gnu.org/licenses/>.

import logging
from itertools import chain

import numpy as np

from hyperspy.external.progressbar import progressbar

_logger = logging.getLogger(__name__)

def _thresh(R, lambda1, M):
    res = np.abs(R) - lambda1
    return np.sign(R) * np.min(np.max(res, 0), M)

def _mrdivide(A, B):
    """like in Matlab! (solves xA = B)
    """
    if isinstance(A, np.ndarray):
        if len(set(A.shape)) == 1:
            # square array
            return np.linalg.solve(A.T, B.T).T
        else:
            return np.linalg.lstsq(A.T, B.T)[0].T
    else:
        return A / B

def _project(W):
    return _mrdivide(np.max(W, 0),
                     np.diag(np.max(np.sqrt(W**2, axis=0),
                                    axis=0)))

class OPGD:

    def __init__(self, rank, batch_size, lambda1=None, max_value=None):
        self.iterating = None
        self.rank = rank
        self.batch_size = batch_size, 
        self.lambda1 = lambda1 # TODO: Can be None, change once data comes
        # just random numbers for now
        if max_value is None:
            max_value = 15
        self.max_value = max_value
        self.maxItr1 = 1e5
        self.maxItr2 = 1e3
        self.eps1 = 1e-3
        self.eps2 = 1e-5
        self.stepMulp = 1.
        self.H = []
        self.R = []

    def _setup(self, X):
        # figure out how many features, F. K is the rank
        if isinstance(X, np.ndarray):
            F, _ = X.shape
            self.iterating = False
        else:
            x = next(X)
            F = len(x)
            X = chain([x], X)
            self.iterating = True
        self.features = F
        self.h = np.random.rand(self.rank, self.batch_size)
        self.r = np.random.rand(self.features, self.batch_size)

        self.A = np.zeros((self.rank, self.rank))
        self.B = np.zeros((self.features, self.rank))
        return X

    def fit(self, values, iterating=None):
        if self.features is None:
            values = self._setup(values)

        if iterating is None:
            iterating = self.iterating
        else:
            self.iterating = iterating

        num = None
        if isinstance(values, np.ndarray):
            # make an iterator anyway
            num = values.shape[1]
            values = iter(values)
        this_batch = []
        # when we run out of samples for the full back, re-use some
        last_batch = None
        for val in progressbar(values, leave=False, total=num):
            this_batch.append(val)
            if len(this_batch) == self.batch_size:
                self._fit_batch(np.stack(this_batch, axis=-1))
                last_batch = this_batch
                this_batch = []
        left_samples = len(this_batch)
        if left_samples > 0:
            self._fit_batch(np.stack(last_batch[left_samples-self.batch_size:]
                                     +this_batch, axis=-1))

    def _fit_batch(values):
        self._update_hr(values)
        # store the values to have a "history"
        self.H.append(self.h)
        self.R.append(self.r)
        self.A += self.h.dot(self.h.T)
        self.B += (values-self.r).dot(self.h.T)
        self._update_W()


    def _update_hr(self, values):
        n = 0
        lasttwo = np.zeros(2)
        L = np.linalg.norm(self.W,2)**2
        eta = 1./L*self.stepMulp

        while n<=2 or (np.abs((lasttwo[1] - lasttwo[0])/lasttwo[0]) >
                       self.eps1 and n<self.maxItr1):
            self.h = np.max(self.h-eta*self.W.T.dot(
                self.W.dot(self.h) + self.r - values), 0)
            self.r = _thresh(values - self.W.dot(self.h), self.lambda1,
                             self.max_val)
            n += 1
            lasttwo[0] = lasttwo[1]
            lasttwo[1] = 0.5 * np.linalg.norm(
                values - self.W.dot(h) - self.r, 'fro')**2 +
                self.lambda1*np.sum(np.abs(r))

    def _update_W(self):

        n = 0
        lasttwo = np.zeros(2)
        L = np.linalg.norm(self.A,'fro');
        eta = 1./L*self.stepMulp
        A = self.A
        B = self.B

        while n<=2 or (np.abs((lasttwo[1] - lasttwo[0])/lasttwo[0]) >
                       self.eps2 and n<self.maxItr2):
            self.W = _project(self.W - eta*(self.W.dot(A) - B))
            lasttwo[0] = lasttwo[1]
            lasttwo[1] = 0.5 * np.trace(self.W.T.dot(self.W).dot(A)) - \
                    np.trace(self.W.T.dot(B))
