import os
import json
import math
import numpy as np
import pandas as pd
from scipy import stats


def log_print(*args, **kwargs):
    print(*args, **kwargs)
    f = open('test/test_dual.log', 'a')
    if len(list(args)) > 0:
        f.write(' '.join([str(i) for i in list(args)]) + '\n')
    else:
        f.write('\n')
    f.close()


class Para:
    def __init__(self, _para):
        self.D_type = None
        self.L = None  # 常规渠道提前期；应急渠道 L2=0 隐含
        self.T = None
        self.alpha = None
        self.mu_base = None
        self.A = None
        self.tau = None
        self.cv = None
        self.b = None
        self.h = None
        self.p = None  # 常规渠道良率；应急 p2=1 隐含
        self.c = None  # 兼容旧字段，等同 c1
        self.c1 = None  # 常规渠道单价
        self.c2 = None  # 应急渠道单价 (c1 < c2 < b)
        self.bound = None
        if _para:
            self.__dict__ = dict(self.__dict__, **_para)
            if self.c1 is None:
                self.c1 = self.c
            self.bound = self._calc_bound()

    def mu_t(self, t):
        return self.mu_base + self.A * math.sin(2 * math.pi * t / self.tau)

    def sigma_t(self, t):
        return self.cv * self.mu_t(t)

    def SL_t(self, t):
        """常规渠道动态目标库存（与 main_seasonal 一致）。"""
        L = self.L
        mu = self.mu_t(t + L)
        sigma = self.sigma_t(t + L)
        rho = math.sqrt((1 - self.p) / self.p)
        k = stats.norm.ppf(self.b / (self.b + self.h), 0, 1)
        return (L + 1) * mu + k * math.sqrt(
            (L + 1) * sigma ** 2 + max(L, 1) * rho ** 2 / (1 - rho ** 2) * (mu ** 2 + sigma ** 2)
        )

    def S0_t(self, t):
        """应急渠道单期报童安全水位：临界分位数 (b-c2)/(b+h)。
        c2 >= b 时应急永不划算，S0 退化为 0。"""
        if self.c2 >= self.b:
            return 0.0
        mu = self.mu_t(t)
        sigma = self.sigma_t(t)
        crit = (self.b - self.c2) / (self.b + self.h)
        z = stats.norm.ppf(crit, 0, 1)
        return mu + z * sigma

    def _calc_bound(self):
        L = self.L
        T = self.T
        p = self.p
        mu_peak = self.mu_base + abs(self.A)
        sigma_peak = self.cv * mu_peak
        confidence = 0.99
        CI = stats.norm.interval(confidence, loc=mu_peak, scale=sigma_peak)
        D_lb = max(math.floor(CI[0]), 0)
        D_ub = math.ceil(CI[1])
        Q_ub = math.ceil((1 + L) * D_ub / p)
        return {
            'D': [D_lb, D_ub],
            'qt': [0, Q_ub],
            'It': [-T * D_ub * 2, T * D_ub * 2],
        }

    def __str__(self):
        return str(self.__dict__)


# ---------- 启发式策略 ----------
# 接口约定：test(It, q_vector, t) -> (q1, q2)
# It 是常规渠道到货之后、应急到货之前、需求消耗之前的库存。

class Qt_BASE:
    """只用常规渠道的基线（应急渠道始终不订）。"""

    def __init__(self, _para):
        self.para = _para
        self.L = _para.L
        self.p = _para.p

    def test(self, It, q_vector, t=0):
        SL = self.para.SL_t(t + self.L)
        q1 = max(SL - It - np.sum(q_vector), 0)
        return float(q1), 0.0


class Qt_LIR:
    def __init__(self, _para):
        self.para = _para
        self.L = _para.L
        self.p = _para.p

    def test(self, It, q_vector, t=0):
        SL = self.para.SL_t(t + self.L)
        q1 = max(SL - It - np.sum(q_vector) * self.p, 0)
        return float(q1), 0.0


class Qt_WNH:
    def __init__(self, _para):
        self.para = _para
        self.L = _para.L
        self.p = _para.p
        self.Y = self._calc_Y()
        self.P = self._calc_P()

    def test(self, It, q_vector, t=0):
        SL = self.para.SL_t(t + self.L)
        obj1 = SL - It
        obj2 = -q_vector @ self.Y
        obj = obj1 + obj2
        q1 = np.where(obj >= 0, obj, 0) @ self.P.T
        return float(np.squeeze(q1)), 0.0

    def _calc_Y(self):
        L = self.L
        _obj = [[0], [1]]
        for i in range(1, L - 1):
            obj = []
            for x in _obj:
                for y in [0, 1]:
                    obj += [[y] + x]
            _obj = obj
        return np.array(_obj).T

    def _calc_P(self):
        p = self.p
        Y = self.Y
        L = self.L
        sum_Y = np.ones((1, L - 1)) @ Y
        return np.array([[p ** y * (1 - p) ** (L - 1 - y) for y in sum_Y[0]]])


class Qt_NV:
    """只用应急渠道的纯报童基线。"""

    def __init__(self, _para):
        self.para = _para
        self.L = _para.L

    def test(self, It, q_vector, t=0):
        S0 = self.para.S0_t(t)
        q2 = max(S0 - It, 0)
        return 0.0, float(q2)


class Qt_HEUR:
    """联合教师：常规用 WNH，应急用 NV。作为 DRL 的相对损失分母。"""

    def __init__(self, _para):
        self.para = _para
        self.wnh = Qt_WNH(_para)
        self.nv = Qt_NV(_para)

    def test(self, It, q_vector, t=0):
        q1, _ = self.wnh.test(It, q_vector, t)
        _, q2 = self.nv.test(It, q_vector, t)
        return q1, q2


# ---------- 仿真模型 ----------

class Model(Para):
    def __init__(self, _para):
        para = _para.copy()
        super(Model, self).__init__(para)
        self.I0 = 0
        self.q_vector = np.zeros(self.L).astype(int)

    def test(self, qt, **kwargs):
        T = self.T
        p = self.p
        c1 = self.c1
        c2 = self.c2
        h = self.h
        b = self.b
        alpha = self.alpha

        It = kwargs['It']
        q_vector = kwargs['q_vector']
        seed = kwargs['seed']

        np.random.seed(seed[0])
        D_list = np.array([
            np.random.normal(loc=self.mu_t(i), scale=self.sigma_t(i))
            for i in range(T)
        ])
        D_list = np.where(D_list >= 0, D_list, 0)
        np.random.seed(seed[1])
        y_list = np.random.binomial(n=1, p=p, size=T)

        total_cost = 0
        for i in range(T):
            y = y_list[i]
            Dt = D_list[i]

            # ① 常规渠道到货（受良率影响）
            It = It + q_vector[0] * y

            # ② 双输出决策
            out = qt.test(It, q_vector[1:], t=i)
            q1, q2 = out if isinstance(out, tuple) else (float(np.squeeze(out)), 0.0)
            q1 = max(float(np.squeeze(q1)), 0.0)
            q2 = max(float(np.squeeze(q2)), 0.0)

            # ③ 应急立即入库
            It = It + q2

            # ④ 需求消耗
            It = It - Dt

            cost = alpha ** i * (
                c1 * q_vector[0] * y
                + c2 * q2
                + h * max(It, 0)
                + b * max(-It, 0)
            )

            q_vector = np.append(q_vector[1:], [q1])
            total_cost += cost

        return np.round(total_cost, 2)

    def batch_test(self, test_model, seed_list, N=10, sample_id=-1):
        cfg = {'It': self.I0, 'q_vector': self.q_vector}
        cost = [[] for _ in range(len(test_model))]
        qt_list = [Qt(self) for Qt in test_model]
        try:
            for i, qt in enumerate(qt_list):
                if qt.__class__.__name__ == 'Qt_DRL':
                    qt_list[i] = qt.load_pth(sample_id)
            for i in range(N):
                cfg['seed'] = seed_list[i]
                for m, qt in enumerate(qt_list):
                    cost[m].append(self.test(qt, **cfg))
        except Exception as e:
            cost = None
        return cost

    def __str__(self):
        return str(self.__dict__)


# ---------- 实验组 ----------

class Group:
    def __init__(self, _para):
        self.D_type = None
        self.L = None
        self.T = None
        self.p = None
        self.b = None
        self.h = None
        self.c1 = None
        self.c2 = None
        self.mu_base = None
        self.A = None
        self.tau = None
        self.cv = None
        self.alpha = None
        self.bbh = None
        self.sample = None
        self.keys = None
        if _para:
            self.__dict__ = dict(self.__dict__, **_para)
            self.b = self._calc_b()
            self.sample, self.keys = self._calc_sample()

    def sample_test(self, test_model, N=10, seed_file='seed/seed_test_100_2.json'):
        model_name = [x.__name__ for x in test_model]
        seed_list_arr = None
        if os.path.exists(seed_file):
            with open(seed_file) as f:
                seed_list_arr = np.array(json.load(f))
        else:
            print('NO SEED FILE, USE RANDOM SEED!\n' * 4)
        bad_list = []
        cost_list = []
        for i, para in enumerate(self.sample):
            model = Model(para)
            log_print('test: %s/%s, N: %s, para: %s' % (i + 1, len(self.sample), N, model))
            cost = model.batch_test(test_model, seed_list_arr, N=N, sample_id=i + 1)
            if cost is None:
                bad_list.append(i + 1)
                continue
            cost_list.append(np.array(cost).tolist())
            cost_avg = np.round([np.mean(x) for x in cost], 2)
            cost_std = np.round([np.std(x, ddof=1) for x in cost], 2)
            for m, mname in enumerate(model_name):
                log_print('model: %s, avg_cost: %s, std: %s' % (mname, cost_avg[m], cost_std[m]))
        print('bad_list:', bad_list)
        with open('test/cost_list_dual.json', 'w') as f:
            json.dump(cost_list, f)

    def _calc_b(self):
        b = self.b
        if (not self.b) and self.bbh:
            b = 1 / (1 / np.array(self.bbh) - 1) * self.h
            b = np.round(b, 4).tolist()
        self.bbh = None
        return b

    def _calc_sample(self):
        _obj = []
        _keys = []
        for key in self.__dict__:
            if self.__dict__[key]:
                _keys.append(key)
        for key in _keys:
            item = self.__dict__[key]
            if not isinstance(item, list):
                item = [item]
            if len(_obj) == 0:
                _obj = [[x] for x in item]
            else:
                obj = []
                for y in _obj:
                    for x in item:
                        obj += [y + [x]]
                _obj = obj
        _obj = [dict(zip(_keys, x)) for x in _obj]
        log_print('para: %s %s, sample_size: %s' % (len(_keys), _keys, len(_obj)))
        return _obj, _keys


def get_group_dual():
    para = {
        'D_type': 'norm',
        'L': 2,
        'bbh': [0.85, 0.95],
        'h': 1,
        'p': [0.7, 0.9],
        'c1': 2,
        'c2': [3, 5],   # c1 < c2 < b（b 在 bbh 下约 5.67 / 19）
        'alpha': 0.99,
        'T': [50, 100],
        'mu_base': 10,
        'A': [0, 3, 6],
        'tau': 20,
        'cv': 0.2,
    }
    os.makedirs('test', exist_ok=True)
    open('test/test_dual.log', 'w').close()
    open('test/test.stop', 'w').write('delete this file if you want to interrupt the process')
    return Group(para)


if __name__ == '__main__':
    group = get_group_dual()
    group.sample_test(test_model=[Qt_LIR, Qt_WNH, Qt_NV, Qt_HEUR],
                      N=20,
                      seed_file='seed/seed_test_100_2.json')
