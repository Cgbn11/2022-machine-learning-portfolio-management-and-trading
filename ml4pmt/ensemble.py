import numpy as np 
import pandas as pd 
from sklearn.linear_model import LinearRegression
from sklearn.base import TransformerMixin
from sklearn.model_selection import TimeSeriesSplit

class Mbj(TransformerMixin): 
    def __init__(self, positive=False): 
        self.positive=positive 
        
    def fit(self, X, y=None): 
        m = LinearRegression(fit_intercept=False, positive=self.positive)
        m.fit(X, y = np.ones(len(X)))
        self.coef_ = m.coef_ / np.sqrt(np.sum(m.coef_**2))
        return self

    def transform(self, X): 
        return X.dot(self.coef_)
    

class StackingBacktester:
    def __init__(
        self,
        estimators,
        ret,
        max_train_size=36,
        test_size=1,
        start_date="1945-01-01",
        end_date=None,
        window=60, 
        min_periods=60, 
        final_estimator = Mbj()
    ):

        self.start_date = start_date
        self.end_date = end_date
        self.estimators = estimators
        self.ret = ret[: self.end_date]
        self.cv = TimeSeriesSplit(
            max_train_size=max_train_size,
            test_size=test_size,
            n_splits=1 + len(ret.loc[start_date:end_date]) // test_size,
        )
        self.window = window
        self.min_periods = min_periods
        self.final_estimator = final_estimator 

    def train(self, features, target):
        cols =self.ret.columns 
        idx = self.ret.index[np.concatenate([test for _, test in self.cv.split(self.ret)])]

        _h = {k: [] for k in list(self.estimators.keys()) + ['ensemble']}
        _pnls = {k: [] for k in self.estimators.keys()}
        _coef = []
        for i, (train, test) in enumerate(self.cv.split(self.ret)): 
            h_ = {}
            if (i> self.min_periods): 
                pnl_window = np.stack([np.array(v[-self.window:]) for k, v in _pnls.items()], axis=1)
                coef_ = self.final_estimator.fit(pnl_window).coef_
                _coef += [coef_]
            else: 
                _coef += [np.zeros(3)] 
            for k, m in self.estimators.items(): 
                m.fit(features[train], target[train])
                h_[k] = m.predict(features[test])
                _h[k] += [h_[k]]
                if i+1 <len(idx):
                    _pnls[k] += [self.ret.loc[idx[i+1]].dot(np.squeeze(h_[k]))]
            if (i>self.min_periods): 
                h_ensemble = np.stack([np.squeeze(v) for v in h_.values()], axis=1).dot(coef_).reshape(-1, 1)
                V_ = m.named_steps['meanvariance'].V_
                h_ensemble = h_ensemble / np.sqrt(np.diag(h_ensemble.T.dot(V_.dot(h_ensemble))))
            else: 
                h_ensemble = np.zeros([len(cols), 1])
            _h['ensemble'] += [h_ensemble.T]
            
        self.h_ = {k: pd.DataFrame(np.concatenate(_h[k]), index=idx, columns=cols) 
                   for k in _h.keys()}
        self.pnls_ = pd.concat({k: v.shift(1).mul(self.ret).sum(axis=1)[self.start_date:] 
                                for k, v in self.h_.items()}, 
                               axis=1)
        self.coef_ = pd.DataFrame(np.stack(_coef), index=idx, columns=self.estimators.keys())
        return self
