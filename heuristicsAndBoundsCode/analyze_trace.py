import numpy as np
import pandas as pd
from main_dual import *
from test_dual import Qt_DRL

def trace_episode(qt, model, seed):
    T = model.T
    p = model.p
    c1 = model.c1
    c2 = model.c2
    h = model.h
    b = model.b
    alpha = model.alpha

    It = model.I0
    q_vector = np.zeros(model.L).astype(int)

    np.random.seed(seed[0])
    D_list = np.array([
        np.random.normal(loc=model.mu_t(i), scale=model.sigma_t(i))
        for i in range(T)
    ])
    D_list = np.where(D_list >= 0, D_list, 0)
    np.random.seed(seed[1])
    y_list = np.random.binomial(n=1, p=p, size=T)

    total_cost = 0
    records = []

    for i in range(T):
        y = y_list[i]
        Dt = D_list[i]
        
        # Original state
        start_It = It
        reg_arrival = q_vector[0] * y

        # ① 常规渠道到货
        It = It + reg_arrival

        # ② 决策
        out = qt.test(It, q_vector[1:], t=i)
        q1, q2 = out if isinstance(out, tuple) else (float(np.squeeze(out)), 0.0)
        q1 = max(float(np.squeeze(q1)), 0.0)
        q2 = max(float(np.squeeze(q2)), 0.0)

        # ③ 应急当期入库
        It = It + q2

        # ④ 需求消耗
        It = It - Dt

        cost = alpha ** i * (
            c1 * reg_arrival
            + c2 * q2
            + h * max(It, 0)
            + b * max(-It, 0)
        )

        records.append({
            'Period (t)': i,
            'Demand (Dt)': round(Dt, 2),
            'Yield (y)': y,
            'Reg Arrival': round(reg_arrival, 2),
            'Stock After Arrival': round(start_It + reg_arrival, 2),
            'Order Reg (q1)': round(q1, 2),
            'Order Emg (q2)': round(q2, 2),
            'End Stock (It)': round(It, 2),
            'Period Cost': round(cost, 2),
        })

        q_vector = np.append(q_vector[1:], [q1])
        total_cost += cost

    return pd.DataFrame(records), total_cost

if __name__ == '__main__':
    # 抽取第 1 个样本参数
    group = get_group_dual()
    para = group.sample[0]
    model = Model(para)
    
    # 实例化测试算法
    qt_heur = Qt_HEUR(model)
    qt_drl = Qt_DRL(model).load_pth(sample_id=1)
    
    # 取一个固定的seed
    import json
    with open('seed/seed_test_500_2.json') as f:
        seeds = json.load(f)
    seed = seeds[0] # The first seed pair
    
    # Run tracing
    df_heur, cost_heur = trace_episode(qt_heur, model, seed)
    df_drl, cost_drl = trace_episode(qt_drl, model, seed)
    
    print(f"--- Qt_HEUR Total Cost: {cost_heur:.2f} ---")
    print(df_heur.head(10).to_string(index=False))
    print("...\n")
    
    print(f"--- Qt_DRL Total Cost: {cost_drl:.2f} ---")
    print(df_drl.head(10).to_string(index=False))
    print("...")
    
    # 保存结果到 csv
    df_heur.to_csv('test/trace_HEUR.csv', index=False)
    df_drl.to_csv('test/trace_DRL.csv', index=False)
    print("\nTraces saved to test/trace_HEUR.csv and test/trace_DRL.csv")
