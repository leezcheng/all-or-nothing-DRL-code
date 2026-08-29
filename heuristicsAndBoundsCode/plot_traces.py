import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# 读取跑出的过程数据
df_heur = pd.read_csv('test/trace_HEUR.csv')
df_drl = pd.read_csv('test/trace_DRL.csv')

# 计算累积成本
df_heur['Cumulative Cost'] = df_heur['Period Cost'].cumsum()
df_drl['Cumulative Cost'] = df_drl['Period Cost'].cumsum()

# 创建包含 3 个子图的画布
fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 14), sharex=True)

# 共用设置
colors = {'HEUR': '#AAAAAA', 'DRL': '#4169E1'} # 灰色 vs 亮蓝色
t = df_heur['Period (t)']

# ----------------- 子图 1：期末留存库存情况 -----------------
ax1.plot(t, df_heur['End Stock (It)'], label='HEUR (Combined Heuristic)', color=colors['HEUR'], linestyle='--', linewidth=2, marker='o', markersize=4)
ax1.plot(t, df_drl['End Stock (It)'], label='DRL (Extended Model)', color=colors['DRL'], linewidth=2.5, marker='s', markersize=4)
ax1.axhline(0, color='red', linestyle=':', alpha=0.6, label='Out of Stock (Zero Line)') # 缺货警戒线
ax1.set_title('1. End of Period Inventory Level ($I_t$)', fontsize=14, fontweight='bold')
ax1.set_ylabel('Inventory Level')
ax1.legend(loc='upper right')
ax1.grid(True, linestyle='--', alpha=0.5)

# ----------------- 子图 2：单期发生成本对比 -----------------
ax2.plot(t, df_heur['Period Cost'], label='HEUR Period Cost', color=colors['HEUR'], linestyle='--', linewidth=2)
ax2.plot(t, df_drl['Period Cost'], label='DRL Period Cost', color=colors['DRL'], linewidth=2.5)
ax2.set_title('2. Period Cost (Lower is better)', fontsize=14, fontweight='bold')
ax2.set_ylabel('Cost per Period')
ax2.legend(loc='upper right')
ax2.grid(True, linestyle='--', alpha=0.5)

# ----------------- 子图 3：累计总成本对比 -----------------
ax3.plot(t, df_heur['Cumulative Cost'], label=f"HEUR Total Cost: {df_heur['Cumulative Cost'].iloc[-1]:.2f}", color=colors['HEUR'], linestyle='--', linewidth=2)
ax3.plot(t, df_drl['Cumulative Cost'], label=f"DRL Total Cost: {df_drl['Cumulative Cost'].iloc[-1]:.2f}", color=colors['DRL'], linewidth=2.5)

# 标记最后结算点
ax3.scatter([t.iloc[-1]], [df_heur['Cumulative Cost'].iloc[-1]], color=colors['HEUR'], zorder=5)
ax3.scatter([t.iloc[-1]], [df_drl['Cumulative Cost'].iloc[-1]], color=colors['DRL'], zorder=5)

ax3.set_title('3. Cumulative Total Cost Over Time', fontsize=14, fontweight='bold')
ax3.set_xlabel('Period ($t$)', fontsize=13)
ax3.set_ylabel('Cumulative Cost')
ax3.legend(loc='upper left', fontsize=11)
ax3.grid(True, linestyle='--', alpha=0.5)

plt.tight_layout()
plt.savefig('test/trace_comparison.png', dpi=300, bbox_inches='tight')
print("Successfully generated test/trace_comparison.png")
