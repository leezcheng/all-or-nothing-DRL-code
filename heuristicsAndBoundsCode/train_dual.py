import math
from main_dual import *

import torch
import torch.optim as optim
import torch.nn as nn
import torch.nn.functional as F

import matplotlib.pyplot as plt

Variable = lambda *args, **kwargs: torch.autograd.Variable(*args, **kwargs).cpu()

# 应急缩放盒子：q2 = (1 + EPS_Q2 * tanh(logit)) * ReLU(S0 - It)
# 即 q2 在 NV 教师值 ±EPS_Q2 倍内调整。
EPS_Q2 = 0.5


class FC(nn.Module):
    def __init__(self, in_dim, out_dim, n_hidden):
        _num = [in_dim] + n_hidden + [out_dim]
        super(FC, self).__init__()
        self.layer_list = []
        for i in range(len(n_hidden)):
            self.layer_list.append(nn.Sequential(nn.Linear(_num[i], _num[i + 1]), nn.ReLU(True)))
        self.layer_list.append(nn.Sequential(nn.Linear(_num[-2], _num[-1])))
        self.layer_list = nn.ModuleList(self.layer_list)

    def forward(self, x):
        out = x
        for layer in self.layer_list:
            out = layer(out)
        return out


class Net(nn.Module):
    """输出 2^L + 1 维：前 2^L 维做常规渠道路径加权（与扩展一一致），最后 1 维做应急缩放。"""

    def __init__(self, L, time_feat_dim=3):
        super(Net, self).__init__()
        self.L = L
        self.input_size = 1 + (L - 1) + time_feat_dim
        self.q1_dim = 2 ** (self.L - 1) * 2  # 路径加权的 raw logits 数
        self.q2_dim = 1                      # 应急缩放
        self.out_dim = self.q1_dim + self.q2_dim
        self.n_hidden = [16, 32, 32]

        self.fc = FC(in_dim=self.input_size, out_dim=self.out_dim, n_hidden=self.n_hidden).cpu()
        self.softmax = nn.Softmax(dim=1)

    def forward(self, x):
        out = self.fc(x)
        q1_logits = out[..., :self.q1_dim].view(-1, 2)
        q1_w = self.softmax(q1_logits)            # (2^(L-1), 2) softmax 在最后一维
        q2_scale = out[..., self.q1_dim:]         # (1,) raw logit
        return q1_w, q2_scale


class Agent(nn.Module):
    """单 agent 双输出。
    State layout (与扩展一一致):
      state[0]                = SL_t(t+L)
      state[1]                = It (常规到货后、应急到货前的库存)
      state[2 : 2+(L-1)]      = q_vector[1:L]
      state[2+(L-1) : ... ]   = [sin(2πt/τ), cos(2πt/τ), t/T]
    """

    def __init__(self, para, teacher_w):
        super(Agent, self).__init__()
        self.T = para.T
        self.L = para.L
        self.p = para.p
        Y = self._calc_Y()
        Y_head = np.array([1, -1] * Y.shape[1]).reshape((-1, 2)).T
        Y = np.vstack((Y_head, -Y))
        self.Y = Variable(torch.tensor(Y, dtype=torch.float32)).cpu()

        self.net = Net(self.L, time_feat_dim=3).cpu()

        BASE = 0.25
        w_range = (BASE ** 2 * 2 / 2 ** (self.L - 1)) ** 0.5
        self.w_bound = np.squeeze([teacher_w - w_range, teacher_w + w_range]).T
        self.w_bound = Variable(torch.from_numpy(self.w_bound)).float().cpu()

    def act(self, state, S0):
        """返回 (q1, q2)，均为 0 维 tensor。
        S0: 当前期 t 的应急安全水位 (tensor 0-d)。"""
        sl_it_q = state[:1 + 1 + (self.L - 1)]
        net_input = state[1:]
        It = state[1]

        q1_w, q2_scale = self.net(net_input)
        # q1: 原路径加权
        w = q1_w * self.w_bound
        w = w @ torch.ones((w.shape[1], 1)).cpu()
        q1 = F.relu(torch.unsqueeze(sl_it_q, dim=0) @ self.Y) @ w
        q1 = torch.squeeze(q1)

        # q2: NV 教师 ± EPS_Q2 倍盒子
        q2_factor = 1.0 + EPS_Q2 * torch.tanh(torch.squeeze(q2_scale))
        q2 = q2_factor * F.relu(S0 - It)

        return q1, q2

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


class Env:
    def __init__(self, _para):
        self.model = _para if isinstance(_para, Model) else Model(_para)
        self.T = self.model.T
        self.L = self.model.L
        self.tau = self.model.tau
        self.It = None
        self.q_vector = None
        self.seed1 = None
        self.seed2 = None
        self.D_list = None
        self.y_list = None
        self.t = 1

    def _time_feat(self, t):
        s = math.sin(2 * math.pi * t / self.tau)
        c = math.cos(2 * math.pi * t / self.tau)
        tn = t / self.T
        return Variable(torch.tensor([s, c, tn]).float()).cpu()

    def _SL_at(self, t):
        return Variable(torch.tensor([self.model.SL_t(t + self.L)]).float()).cpu()

    def S0_at(self, t):
        return Variable(torch.tensor([self.model.S0_t(t)]).float()).cpu().squeeze()

    def reset(self, seed1=None, seed2=None):
        model = self.model
        p = model.p

        self.It = Variable(torch.tensor([0.0]).float(), requires_grad=True).cpu()
        self.q_vector = [Variable(torch.tensor([0]).float(), requires_grad=True).cpu() for _ in range(self.L)]
        self.seed1, self.seed2 = seed1, seed2
        self.t = 1

        np.random.seed(self.seed1)
        D_list = np.array([
            np.random.normal(loc=model.mu_t(i), scale=model.sigma_t(i))
            for i in range(self.T)
        ])
        D_list = np.where(D_list >= 0, D_list, 0)
        self.D_list = Variable(torch.from_numpy(D_list).float()).cpu()
        np.random.seed(self.seed2)
        self.y_list = np.random.binomial(n=1, p=p, size=self.T).astype(int)
        self.y_list = Variable(torch.from_numpy(self.y_list).float()).cpu()

        # 初始 state：t=0 时的 SL、It、空 pipeline 后段、时间编码
        sl0 = self._SL_at(0)
        tf0 = self._time_feat(0)
        # 注：reset 时 self.It=0，但 step 末尾会把"常规当期到货后"的 It 写回 state，
        # 所以 reset 这里直接给 It=0（首期 q_vector[0] 为 0，到货也是 0），无需额外加。
        state = torch.cat([sl0, self.It, torch.cat(self.q_vector[1:self.L], dim=0), tf0], dim=0).cpu()
        return state

    def step(self, action):
        """action = (q1, q2)，由 Agent.act 给出。"""
        model = self.model
        alpha = model.alpha
        c1 = model.c1
        c2 = model.c2
        b = model.b
        h = model.h

        i = self.t - 1
        y = self.y_list[i]
        y_next = self.y_list[i + 1] if i + 1 < len(self.y_list) else 0
        Dt = self.D_list[i]

        q1, q2 = action
        q1 = F.relu(q1)
        q2 = F.relu(q2)

        # ① 应急立即入库（常规到货已在 reset/上一 step 末尾完成）
        self.It = self.It + q2

        # ② 需求消耗
        self.It = self.It - Dt

        # 成本：c1 仅在常规渠道当期到货部分（q_vector[i] 是当前 t 的常规订单，y 是其良率）
        cost = alpha ** i * (
            c1 * self.q_vector[i] * y
            + c2 * q2
            + h * F.relu(self.It, False)
            + b * F.relu(-self.It, False)
        )

        # 把 q1 入队（未来到货）
        qt_I = torch.unsqueeze(q1, dim=0)
        self.q_vector.append(qt_I)

        # 下期常规到货叠加
        self.It = self.It + self.q_vector[i + 1] * y_next

        # 下期 state
        next_t = i + 1
        sl_next = self._SL_at(next_t)
        tf_next = self._time_feat(next_t)
        next_state = torch.cat(
            [sl_next, self.It, torch.cat(self.q_vector[i + 2: i + 1 + self.L], dim=0), tf_next],
            dim=0,
        ).cpu()

        done = self.t >= self.T
        self.t += 1
        return next_state, cost, done


def reset_model(para, teacher_w):
    model = Agent(para, teacher_w).cpu()
    optimizer = optim.Adam(model.parameters(), lr=0.003)
    scheduler = optim.lr_scheduler.StepLR(optimizer, step_size=1, gamma=0.98, last_epoch=-1)
    return model, optimizer, scheduler


def calc(env, model, seed1, seed2, T, benchmark_cost_gap, BATCH_SIZE):
    episode_loss = []
    episode_cost = []
    for id in range(BATCH_SIZE) if BATCH_SIZE > 0 else np.random.choice(range(len(seed1)), -BATCH_SIZE, replace=False):
        state = env.reset(seed1=seed1[id], seed2=seed2[id])
        batch_loss, batch_cost = [], []
        for t in range(1, T + 1):
            S0 = env.S0_at(t - 1)  # 当前决策期 t-1（0-indexed 与 step 内一致）
            q1, q2 = model.act(state, S0)
            next_state, cost_loss, done = env.step((q1, q2))
            state = next_state
            batch_cost.append(cost_loss)
            batch_loss.append(cost_loss)
        loss_value = torch.sum(torch.cat(batch_loss))
        cost_value = torch.sum(torch.cat(batch_cost))
        episode_loss.append(torch.unsqueeze(loss_value, dim=0))
        episode_cost.append(torch.unsqueeze(cost_value, dim=0))

    avg_loss = torch.mean(torch.cat(episode_loss))
    avg_loss = (avg_loss / benchmark_cost_gap - 1) * 100
    avg_loss = torch.exp(avg_loss)
    avg_cost = torch.mean(torch.cat(episode_cost))
    return avg_loss, avg_cost


def train(para, teacher_w, sample_seed, benchmark_models, sample_id, cfg=None):
    env = Env(para)
    T = env.T
    benchmark = para

    model, optimizer, scheduler = reset_model(para, teacher_w)
    losses, costs = [], []
    seed_list1 = sample_seed[0]
    seed_list2 = sample_seed[1]

    MAX_EPISODES = cfg['MAX_EPISODES']
    LOSS_STEP = cfg['LOSS_STEP']
    BATCH_SIZE = cfg['BATCH_SIZE']
    MAX_BATCH = len(seed_list1) if cfg['MAX_BATCH'] <= 0 else cfg['MAX_BATCH']

    batch = np.random.choice(list(range(MAX_BATCH)), BATCH_SIZE, replace=False)
    seed1 = seed_list1[batch]
    seed2 = seed_list2[batch]

    benchmark_cost_gap = None
    for episode in range(1, MAX_EPISODES + 1):
        if LOSS_STEP == 1 or episode % LOSS_STEP == 1:
            benchmark_cost = benchmark.batch_test(
                benchmark_models, N=BATCH_SIZE,
                seed_list=np.array([seed1, seed2]).T, sample_id=sample_id,
            )
            benchmark_cost_avg = np.round([np.mean(x) for x in benchmark_cost], 2)
            for m, bm in enumerate(benchmark_models):
                if bm.__name__ == 'Qt_HEUR':
                    benchmark_cost_gap = benchmark_cost_avg[m]
                print('model: %s, cost: %s' % (bm.__name__, benchmark_cost_avg[m]))

        avg_loss, avg_cost = calc(env, model, seed1, seed2, T, benchmark_cost_gap, BATCH_SIZE=BATCH_SIZE)
        losses.append(avg_loss.item())
        costs.append(avg_cost.item())

        gap_1 = (costs[-1] / benchmark_cost_gap - 1) * 100
        gap_2 = (costs[-2] / benchmark_cost_gap - 1) * 100 if episode >= 2 else 1e4
        print('episode: %s, lr: %0.8f, gap: %0.2f%%, cost: %0.2f, loss: %0.2f' % (
            episode, optimizer.state_dict()['param_groups'][0]['lr'], gap_1, costs[-1], losses[-1]))

        if episode == MAX_EPISODES or (episode >= 3 and gap_2 - gap_1 < 0.02):
            break
        elif (episode == 1 and gap_1 > 5) or (episode >= 2 and gap_1 > gap_2) or (episode >= 6 and gap_1 > 0):
            break
        else:
            optimizer.zero_grad()
            avg_loss.backward()
            optimizer.step()
            if optimizer.state_dict()['param_groups'][0]['lr'] > 0.0001:
                scheduler.step()
            if episode % LOSS_STEP == 0:
                batch = np.random.choice(list(range(MAX_BATCH)), BATCH_SIZE, replace=False)
                seed1 = seed_list1[batch]
                seed2 = seed_list2[batch]

    os.makedirs('train/model', exist_ok=True)
    os.makedirs('train/data', exist_ok=True)
    os.makedirs('train/figure', exist_ok=True)
    torch.save(model.state_dict(), 'train/model/model_dual_sample%s.pth' % sample_id)
    with open('train/data/losses_dual_sample%s.json' % sample_id, 'w') as f:
        json.dump(losses, f)
    with open('train/data/costs_dual_sample%s.json' % sample_id, 'w') as f:
        json.dump(costs, f)
    plt.plot(list(range(1, len(losses) + 1)), [np.round(np.log(x), 2) for x in losses])
    plt.plot(list(range(1, len(losses) + 1)), [0 for _ in losses], color='r')
    plt.xlabel('episode')
    plt.title('gap (dual)')
    plt.savefig('train/figure/gap_dual_sample%s.png' % sample_id, dpi=300, format='png')
    plt.close()
    return model


def proc(sample_list, model_list, **kwargs):
    for sample_id in sample_list:
        if model_list[sample_id - 1] is None:
            continue
        para = model_list[sample_id - 1]
        teacher_w = Qt_WNH(para).P

        with open('seed/seed_train_500_2.json') as f:
            sample_seed_full = np.array(json.load(f)).T

        cfg = {'MAX_EPISODES': 30, 'LOSS_STEP': 5, 'BATCH_SIZE': 30, 'MAX_BATCH': 200, 'RED_FLAG': -0.5}
        benchmark_models = [Qt_HEUR]
        train(para, teacher_w, sample_seed_full, benchmark_models, sample_id, cfg=cfg)


if __name__ == '__main__':
    group = get_group_dual()
    model_list = [Model(para) for para in group.sample]
    proc([1], model_list)
