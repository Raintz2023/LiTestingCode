import time
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import Cursor
import pandas as pd
from auto_meshgrid import DataProcessing as dp
import skrf as rf

fig, ax = plt.subplots()
# 这是你需要修改的第一个地方，也就是你要拟合的文件地址
data = pd.read_csv(r"C:\\Users\\海鸥\\OneDrive\\桌面\\20240727\\2.7k\\0.csv")
x_re = np.array(data.loc[:, "X"])
y_im = np.array(data.loc[:, "Y"])
freq = np.array(data.loc[:, "Frequency (Hz)"])

x_yi = x_re + 1j * y_im

# 使用rf，根据vna设置来建立一个网络
freq_rf = rf.Frequency(float(freq[0]), float(freq[-1]), len(freq), 'hz')
network = rf.Network(frequency=freq_rf, s=x_yi)

# 你需要修改的第二个地方是这里
# 修改成谐振器的共振峰范围，以及共振模式，S21则是transmission，S11则是reflection
Q = rf.Qfactor(network['2.123-2.128GHz'], res_type='transmission')
res = Q.fit()
Q0 = Q.Q_unloaded(A=1.0)

fitted_ntwk = Q.fitted_network(frequency=freq_rf)
network.plot_s_db(color='C1')
fitted_ntwk.plot_s_db(label='Fitted Model', lw=2, color='C0', ls='--')

print(f'Fitted Resonant Frequency: f_L = {Q.f_L/1e9} GHz')
print(f'Fitted Loaded Q-factor: Q_L = {Q.Q_L}')
print(f'Fitted Unloaded Q-factor: Q_0 = {Q0}')

plt.show()
