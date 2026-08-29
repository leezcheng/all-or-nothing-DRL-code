import matplotlib.pyplot as plt
import numpy as np

# Dual Sourcing Results
models_dual = ['LIR', 'WNH', 'NV', 'HEUR\n(Combined)', 'Extended DRL']
costs_dual = [1869.76, 1865.98, 1490.59, 1394.10, 1268.51]

# Seasonal Demand Results
models_seasonal = ['LIR', 'WNH', 'Extended DRL']
costs_seasonal = [1869.76, 1865.98, 1850.74]

fig, axes = plt.subplots(1, 2, figsize=(12, 5))

# Plot for Dual
colors_dual = ['#AAAAAA', '#AAAAAA', '#AAAAAA', '#777777', '#4169E1']
bars1 = axes[0].bar(models_dual, costs_dual, color=colors_dual, edgecolor='black', zorder=3)
axes[0].set_title('Dual Sourcing Scenario: Average Cost', fontsize=12, fontweight='bold')
axes[0].set_ylabel('Average Cost (Lower is better)')
axes[0].grid(axis='y', linestyle='--', alpha=0.7, zorder=0)

# Add text labels on top of bars
for bar in bars1:
    yval = bar.get_height()
    axes[0].text(bar.get_x() + bar.get_width()/2.0, yval + 15, round(yval, 2), ha='center', va='bottom', fontsize=10, fontweight='bold')

# Plot for Seasonal
colors_seasonal = ['#AAAAAA', '#AAAAAA', '#4169E1']
bars2 = axes[1].bar(models_seasonal, costs_seasonal, color=colors_seasonal, edgecolor='black', zorder=3)
axes[1].set_title('Seasonal Demand Scenario: Average Cost', fontsize=12, fontweight='bold')
axes[1].set_ylabel('Average Cost (Lower is better)')
axes[1].grid(axis='y', linestyle='--', alpha=0.7, zorder=0)
axes[1].set_ylim([1750, 1890]) # Zoom in to show the difference clearly

for bar in bars2:
    yval = bar.get_height()
    axes[1].text(bar.get_x() + bar.get_width()/2.0, yval + 2, round(yval, 2), ha='center', va='bottom', fontsize=10, fontweight='bold')

plt.tight_layout()
import os
os.makedirs('test', exist_ok=True)
plt.savefig('test/performance_comparison.png', dpi=300, bbox_inches='tight')
print("Successfully generated test/performance_comparison.png")
