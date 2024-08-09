import matplotlib.pyplot as plt
import numpy as np
import os
import pandas as pd
import time
import math
from lmfit import Model
from matplotlib.widgets import Cursor


class DataProcessing:
    def __init__(self, path):
        self.path = path

    def meshgrid(self, **kwargs):
        # 传递可变实参，并且设置默认值
        split_point = kwargs.get('split_point', 1)
        bias = kwargs.get('bias', 0)
        normalized = kwargs.get('normalized', 1)

        # 条件表达式
        reverse_bull = True if int(os.listdir(self.path)[0].split('.')[0]) < 0 else False

        # 获取地址中所有'.csv'扩展名的文件，按文件名中的数字部分进行排序
        csv_files = sorted([file for file in os.listdir(self.path) if file.endswith('.csv')],
                           key=lambda x: int(x.split('.')[0]), reverse=reverse_bull)

        # 创建空Dataframe
        field_meshgrid = pd.DataFrame()
        freq_meshgrid = pd.DataFrame()
        s21_meshgrid = pd.DataFrame()

        # 开始读取特定文件
        for csv_file in csv_files:
            # 给出具体文件地址，并且选中读取
            file_path = os.path.join(self.path, csv_file)
            df = pd.read_csv(file_path)
            df = df.loc[df.iloc[:, 1] > 2e9, :]
            # 提取特定列竖向拼接成三个Dataframe网格
            field_meshgrid = pd.concat([field_meshgrid, df.iloc[:, 0]], axis=1)
            freq_meshgrid = pd.concat([freq_meshgrid, df.iloc[:, 1]], axis=1)
            s21_meshgrid = pd.concat([s21_meshgrid, df.iloc[:, 2]], axis=1)

        freq_meshgrid = freq_meshgrid / 1e9
        s21_meshgrid_normalized = np.zeros_like(s21_meshgrid)

        if normalized == -1:
            s21_meshgrid_1st = np.array(s21_meshgrid.iloc[:split_point, 0] + bias)
            s21_meshgrid_2nd = np.array(s21_meshgrid.iloc[split_point:, len(s21_meshgrid.columns) - 1])
            s21_meshgrid_normalized = np.append(s21_meshgrid_1st, s21_meshgrid_2nd, axis=0)

        elif normalized >= 1:
            s21_meshgrid_normalized = np.array(s21_meshgrid.iloc[:, normalized - 1])

        return field_meshgrid, freq_meshgrid, s21_meshgrid, s21_meshgrid_normalized

    @staticmethod
    def bathymetric(ax_, *args):
        field_meshgrid, freq_meshgrid, s21_meshgrid, s21_meshgrid_normalized = args
        s21_meshgrid = s21_meshgrid.sub(s21_meshgrid_normalized, axis='index')  # 每列都减去归一化s21列
        # s21_meshgrid[s21_meshgrid > 0.001] = 0
        ax_.contourf(field_meshgrid, freq_meshgrid, s21_meshgrid, 100, cmap='viridis')


if __name__ == '__main__':
    fig, ax = plt.subplots()
    data = DataProcessing(path=r"C:\Users\海鸥\OneDrive\桌面\20240727\2.6k")    # 需要修改的第一个地方
    # normalized = 0代表不归一化；normalized>0代表减去第几个数据；normalized=-1代表一种特殊去背噪的方法
    meshgrid = data.meshgrid(normalized=0)
    # 绘制出三维等深图
    data.bathymetric(ax, *meshgrid)
    plt.show()

