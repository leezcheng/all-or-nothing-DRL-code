from main import *

import torch
import torch.optim as optim
import torch.nn as nn
import torch.nn.functional as F

import matplotlib.pyplot as plt

Variable = lambda *args, **kwargs: torch.autograd.Variable(*args, **kwargs).cpu()


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
    def __init__(self, L):
        super(Net, self).__init__()
        self.L = L
        self.input_size = self.L
        self.num_classes = 2 ** (self.L - 1)
        self.num_classes *= 2
        self.n_hidden = [8, 16, 16]

        self.fc = FC(in_dim=self.input_size, out_dim=self.num_classes, n_hidden=self.n_hidden).cpu()
        self.softmax = nn.Softmax(dim=1)

    def forward(self, x):
        out = self.fc(x)
        out = out.view(-1, 2)
        out = self.softmax(out)
        return out


class Agent(nn.Module):
    def __init__(self, para, teacher_w):
        super(Agent, self).__init__()
        self.T = para.T
        self.L = para.L
        self.p = para.p
        self.SL = para.SL
        Y = self._calc_Y()
        Y_head = np.array([1, -1] * Y.shape[1]).reshape((-1, 2)).T
        Y = np.vstack((Y_head, -Y))
        self.Y = Variable(torch.tensor(Y, dtype=torch.float32)).cpu()

        self.net = Net(self.L).cpu()

        BASE = 0.25
        w_range = (BASE ** 2 * 2 / 2 ** (self.L - 1)) ** 0.5
        self.w_bound = np.squeeze([teacher_w - w_range, teacher_w + w_range]).T
        self.w_bound = Variable(torch.from_numpy(self.w_bound)).float().cpu()

    def act(self, state):
        w = self.net(state[1:])
        w = w * self.w_bound
        w = w @ torch.ones((w.shape[1], 1)).cpu()
        action = F.relu(torch.unsqueeze(state, dim=0) @ self.Y) @ w
        action = torch.squeeze(action)
        return action

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
        self.D_type = self.model.D_type
        self.T = self.model.T
        self.L = self.model.L
        self.SL = None
        self.It = None
        self.q_vector = None
        self.seed1 = None
        self.seed2 = None
        self.D_list = None
        self.y_list = None
        self.t = 1

    def reset(self, seed1=None, seed2=None):
        model = self.model
        p = model.p

        self.SL = Variable(torch.tensor([self.model.SL]).float()).cpu()
        self.It = Variable(torch.tensor([0.0]).float(), requires_grad=True).cpu()
        self.q_vector = [Variable(torch.tensor([0]).float(), requires_grad=True).cpu() for _ in range(self.L)]
        self.seed1, self.seed2 = seed1, seed2
        self.t = 1

        np.random.seed(self.seed1)
        if self.D_type == 'gamma':
            self.D_list = np.round(np.random.gamma(shape=self.model.k, scale=self.model.theta, size=self.T)).astype(int)
        else:
            self.D_list = np.round(np.random.normal(loc=self.model.mu, scale=self.model.sigma, size=self.T)).astype(int)
        self.D_list = np.where(self.D_list >= 0, self.D_list, 0)
        self.D_list = Variable(torch.from_numpy(self.D_list).float()).cpu()
        np.random.seed(self.seed2)
        self.y_list = np.random.binomial(n=1, p=p, size=self.T).astype(int)
        self.y_list = Variable(torch.from_numpy(self.y_list).float()).cpu()

        state = torch.cat([self.SL, self.It, torch.cat(self.q_vector[1:self.L], dim=0)], dim=0).cpu()
        return state

    def step(self, action):
        model = self.model
        alpha = model.alpha
        c = model.c
        b = model.b
        h = model.h

        i = self.t - 1
        y = self.y_list[i]
        y_next = self.y_list[i + 1] if i + 1 < len(self.y_list) else 0
        Dt = self.D_list[i]

        self.It = self.It - Dt

        cost = alpha ** i * (c * self.q_vector[i] * y + h * F.relu(self.It, False) + b * F.relu(-self.It, False))

        qt_I = torch.unsqueeze(action, dim=0)
        self.q_vector.append(qt_I)

        self.It = self.It + self.q_vector[i + 1] * y_next
        next_state = torch.cat([self.SL, self.It, torch.cat(self.q_vector[i + 2: i + 1 + self.L], dim=0)],
                               dim=0).cpu()

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

        batch_loss = []
        batch_cost = []
        # forward
        for t in range(1, T + 1):
            action = model.act(state)
            next_state, cost_loss, done = env.step(action)
            loss = cost_loss
            state = next_state
            batch_cost.append(cost_loss)
            batch_loss.append(loss)

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
    '''print(model)'''

    losses = []
    costs = []

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
            benchmark_cost = benchmark.batch_test(benchmark_models, N=BATCH_SIZE,
                                                  seed_list=np.array([seed1, seed2]).T,
                                                  sample_id=sample_id)
            benchmark_cost_avg = np.round([np.mean(x) for x in benchmark_cost], 2)
            for m, benchmark_model in enumerate(benchmark_models):
                if benchmark_model.__name__ == 'Qt_WNH':
                    benchmark_cost_gap = benchmark_cost_avg[m]
                print('model: %s, cost: %s' % (benchmark_model.__name__, benchmark_cost_avg[m]))

        '''if episode == 1:
            init_finished = False
            init_threshold = 10
            while not init_finished:
                avg_loss, avg_cost = calc(env, model, seed1, seed2, T, benchmark_cost_gap, BATCH_SIZE=-50)
                if avg_loss < init_threshold:
                    init_finished = True
                    print('finish init model, gap: %0.2f%s, cost: %0.2f, loss: %0.2f' % (
                        (avg_cost.item() / benchmark_cost_gap - 1) * 100, '%', avg_cost.item(), avg_loss.item()))
                else:
                    model, optimizer, scheduler = reset_model(para, teacher_w)
                    print('try another init model, gap: %0.2f%s, cost: %0.2f, loss: %0.2f' % (
                        (avg_cost.item() / benchmark_cost_gap - 1) * 100, '%', avg_cost.item(), avg_loss.item()))
                    init_threshold += 5'''

        avg_loss, avg_cost = calc(env, model, seed1, seed2, T, benchmark_cost_gap, BATCH_SIZE=BATCH_SIZE)

        losses.append(avg_loss.item())
        costs.append(avg_cost.item())

        gap_1 = (costs[-1] / benchmark_cost_gap - 1) * 100
        gap_2 = (costs[-2] / benchmark_cost_gap - 1) * 100 if episode >= 2 else 1e4

        print('episode: %s, lr: %0.8f, gap: %0.2f%%, cost: %0.2f, loss: %0.2f' % (
            episode, optimizer.state_dict()['param_groups'][0]['lr'],
            gap_1, costs[-1], losses[-1]))

        if episode == MAX_EPISODES or (episode >= 3 and gap_2 - gap_1 < 0.02):
            if os.path.exists('train/data/losses_sample%s.json' % sample_id):
                with open('train/data/losses_sample%s.json' % sample_id) as f:
                    arr = json.load(f)
                    gap_0 = np.log(arr[-1])
                    if gap_0 <= gap_1 and os.path.exists(
                            'train/model/model_sample%s.pth' % sample_id) and os.path.exists(
                        'train/figure/gap_sample%s.png' % sample_id):
                        return None
            break
        elif (episode == 1 and gap_1 > 5) or (episode >= 2 and gap_1 > gap_2) or (episode >= 6 and gap_1 > 0) or (
                episode <= 8 and gap_1 > -0.0 and gap_2 - gap_1 < 0.1):
            if os.path.exists('train/data/losses_sample%s.json' % sample_id):
                with open('train/data/losses_sample%s.json' % sample_id) as f:
                    arr = json.load(f)
                    gap_0 = np.log(arr[-1])
                    if gap_0 <= gap_1 and os.path.exists('train/model/model_sample%s.pth' % sample_id):
                        return None
            break
        else:
            optimizer.zero_grad()
            avg_loss.backward()
            '''nn.utils.clip_grad_norm_(model.parameters(), max_norm=0.1, norm_type=2)'''
            optimizer.step()
            if optimizer.state_dict()['param_groups'][0]['lr'] > 0.0001:
                scheduler.step()

            if episode % LOSS_STEP == 0:
                batch = np.random.choice(list(range(MAX_BATCH)), BATCH_SIZE, replace=False)
                seed1 = seed_list1[batch]
                seed2 = seed_list2[batch]

    torch.save(model.state_dict(), 'train/model/model_sample%s.pth' % sample_id)
    f = open('train/data/losses_sample%s.json' % sample_id, 'w')
    json.dump(losses, f)
    f.close()
    f = open('train/data/costs_sample%s.json' % sample_id, 'w')
    json.dump(costs, f)
    f.close()
    plt.plot(list(range(1, len(losses) + 1)), losses)
    plt.plot(list(range(1, len(losses) + 1)), [1 for _ in losses], color='r')
    plt.xlabel('episode')
    plt.title('loss')
    plt.savefig('train/figure/loss_sample%s.pdf' % sample_id, dpi=600, format='pdf')
    plt.savefig('train/figure/loss_sample%s.png' % sample_id, dpi=600, format='png')
    plt.close()
    fig = plt.figure()
    if 'RED_FLAG' in cfg and (costs[-1] / benchmark_cost_gap - 1) * 100 > cfg['RED_FLAG']:
        fig.patch.set_facecolor('lightcoral')
    plt.plot(list(range(1, len(losses) + 1)), [np.round(np.log(x), 2) for x in losses])
    plt.plot(list(range(1, len(losses) + 1)), [0 for _ in losses], color='r')
    plt.xlabel('episode')
    plt.title('gap')
    plt.savefig('train/figure/gap_sample%s.pdf' % sample_id, dpi=600, format='pdf')
    plt.savefig('train/figure/gap_sample%s.png' % sample_id, dpi=600, format='png')
    plt.close()

    return model


def proc(sample_list, model_list, **kwargs):
    stop_check = False
    RED_FLAG = -1.25
    if kwargs is not None and 'train_id' in kwargs:
        stop_check = True
        f = open('train/train-%s.stop' % kwargs['train_id'], 'w')
        f.write('delete this file if you want to interrupt the process')
        f.close()
    for sample_id in sample_list:
        for try_times in range(3):
            if stop_check and not os.path.exists('train/train-%s.stop' % kwargs['train_id']):
                break
            print('training: sample %s' % sample_id)
            if os.path.exists('train/figure/gap_sample%s.png' % sample_id):
                if os.path.exists('train/data/losses_sample%s.json' % sample_id):
                    with open('train/data/losses_sample%s.json' % sample_id) as f:
                        arr = json.load(f)
                        gap = np.log(arr[-1])
                        if gap <= RED_FLAG:
                            print(
                                "file: 'train/data/losses_sample%s.json' exists with gap <= %s%%, skip training." % (
                                    sample_id, RED_FLAG))
                            break
                else:
                    print("file: 'train/figure/gap_sample%s.png' exists, skip training." % sample_id)
                    break
            para = model_list[sample_id - 1]

            teacher_w = Qt_WNH(para).P

            with open('seed/seed_train_500_2.json') as f:
                sample_seed_full = json.load(f)
                sample_seed_full = np.array(sample_seed_full).T

            # cfg = {'MAX_EPISODES': 50, 'LOSS_STEP': 50, 'BATCH_SIZE': 500, 'MAX_BATCH': 500, 'RED_FLAG': RED_FLAG}
            cfg = {'MAX_EPISODES': 2, 'LOSS_STEP': 1, 'BATCH_SIZE': 10, 'MAX_BATCH': 20, 'RED_FLAG': RED_FLAG}
            benchmark_models = [Qt_LIR, Qt_WNH]

            model = train(para, teacher_w, sample_seed_full, benchmark_models, sample_id, cfg=cfg)


def get_train_list(train_id):
    total_id = 2
    max_sample = 432

    group = get_group()
    model_list = [Model(para) for para in group.sample]

    '!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!'
    gap_list = []
    for sample_id in range(1, 432 + 1):
        if not os.path.exists('train/model/model_sample%s.pth' % sample_id):
            gap_list.append(1e4 - sample_id)
        else:
            with open('train/data/losses_sample%s.json' % sample_id) as f:
                arr = json.load(f)
                gap = np.log(arr[-1])
                if os.path.exists('train/figure/gap_sample%s.png' % sample_id):
                    gap_list.append(gap)
                else:
                    gap_list.append(1e4 - sample_id)
    _, id = zip(*sorted(zip(gap_list, range(432)), key=lambda x: -x[0]))
    '!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!'

    model_list = model_list[:max_sample]

    size = int(len(model_list) / total_id)
    sample_list = (np.array(range(size)) * total_id + train_id).tolist()

    '!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!'
    sample_list = [id[x - 1] + 1 for x in sample_list]
    '!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!'

    return sample_list, [x if i + 1 in sample_list else None for i, x in enumerate(model_list)]


if __name__ == '__main__':
    group = get_group()
    model_list = [Model(para) for para in group.sample]

    # sample_list = list(range(1, 432 + 1))
    sample_list = [1]
    proc(sample_list, model_list)
