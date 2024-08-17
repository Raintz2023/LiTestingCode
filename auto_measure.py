import pyvisa as visa
import numpy as np
import pandas as pd
from tqdm import trange
import os
import time
import atexit
from collections import namedtuple
import MultiPyVu as mpv
import matplotlib.pyplot as plt
from auto_meshgrid import DataProcessing as dp
from typing import NamedTuple


class AutoMeasure:
    def __init__(self, save_path: str):
        self.save_path = save_path
        self.ppms = mpv.Client("222.195.78.246", 5000)
        self.ppms.open()
        # 在所有代码执行完后执行close_all
        atexit.register(self.close_all)
        self.rm = visa.ResourceManager()

    def close_all(self):
        """
        Close ppms after all measurements are done
        :return: None
        """
        print('Closing ppms client...')
        self.ppms.close_client()

    def coupling_measure(self, start_field: int, stop_field: int, field_step: int):

        # GPIB下设置的VNA资源描述符
        vna = self.rm.open_resource("GPIB0::16::INSTR")

        # 选中'My_measure'测量
        vna.write(":CALC:PAR:SEL 'My_measure' ")

        # 查询起始频率
        start_freq = vna.query_ascii_values(":SENS:FREQ:STAR?")

        # 查询终止频率
        stop_freq = vna.query_ascii_values(":SENS:FREQ:STOP?")

        # 查询测量点数
        points = vna.query_ascii_values(":SENSe1:SWEep:POIN?")

        # 查询平均次数
        average_times = vna.query_ascii_values(":SENSe1:AVERage:COUNt?")

        # 设置磁场归零
        self.ppms.set_field(0, 200, self.ppms.field.approach_mode.linear)
        time.sleep(0.5)
        self.ppms.wait_for(delay_sec=5, timeout_sec=0, bitmask=self.ppms.subsystem.field)

        # 磁场归零，根据目前磁场来估算归零等待时间
        print('Waiting for the magnetic field to return to zero')

        # 磁场到设置的起始磁场
        self.ppms.set_field(start_field, 200, self.ppms.field.approach_mode.linear)
        time_to_start = int(abs(start_field)/200) + 5
        print(f'Waiting for the magnetic field to return to {start_field} Gs...')
        time.sleep(time_to_start)

        vna.write(":SENSe1:AVERage:CLEar")
        time.sleep(average_times[0] * 4)

        # 获取曲线的起始点测量原始数据
        raw_data = vna.query_ascii_values(":CALCulate:DATA? SDATA")

        '''
        处理原始数据，原始数据为X+Yi形式，
        "第一个点实部，第一个点虚部，第二个点实部，第二个点虚部...",
        如果想画出对数幅度形式，采用20*log(*sqrt(X^2+Y^2))换算
        '''
        print('Commencing testing....')
        figure, ax = plt.subplots(nrows=1, ncols=1)
        for i in range(int((stop_field-start_field)/field_step)+1):

            # 创建一系列空列表用来存储S21数据
            s21 = np.array([])
            x = np.array([])
            y = np.array([])

            for j in range(0, len(raw_data), 2):
                x = np.append(x, raw_data[j])
                y = np.append(y, raw_data[j + 1])
                log_magnitude = 20 * np.log10(np.sqrt(raw_data[j] ** 2 + raw_data[j + 1] ** 2))
                s21 = np.append(s21, log_magnitude)

            freq = np.linspace(start_freq, stop_freq, int(points[0]))     # 根据仪器设置来获得频率点
            field_now = start_field + i * field_step    # 获得磁场接近值
            field_vector = np.full(int(points[0]), field_now)    # 将磁场扩充为整个列表

            # 将获取的频率点和S21点合并成一个三列矩阵
            freq_s21 = pd.DataFrame(np.column_stack((field_vector, freq, s21, x, y)),
                                    columns=['Field (Oe)', 'Frequency (Hz)', 'S21 (dBm)', 'X', 'Y'])

            # 确保保存文件夹存在，如果不存在则创建
            if not os.path.exists(self.save_path):     # 返回值为True 或者 False
                os.makedirs(self.save_path)

            # 动态命名法，给文件命名
            file_name = f"{field_now}.csv"

            # 最终包含文件名的路径
            save_path = os.path.join(self.save_path, file_name)

            # 保存矩阵到CSV文件，%g的精度，','为分隔符
            freq_s21.to_csv(save_path, header=True, index=False, encoding='utf-8-sig')
            print(f"{field_now} has been saved to: {save_path}")

            # 获得两组数据后开始绘图
            if i >= 1:
                data = dp(path=self.save_path)
                meshgrid = data.meshgrid(normalized=0)
                data.bathymetric(ax, *meshgrid)

            # 在磁场达到终止点时直接停止测量
            if i == (stop_field-start_field) / field_step:
                print("Testing has concluded...")
                break

            self.ppms.set_field((i+1)*field_step+start_field, 200, self.ppms.field.approach_mode.linear)
            time.sleep(0.5)
            self.ppms.wait_for(delay_sec=5, timeout_sec=0, bitmask=self.ppms.subsystem.field)

            vna.write(":SENSe1:AVERage:CLEar")

            # 暂停，等待平均完成
            time.sleep(average_times[0]*4)

            # 获取下一组数据
            raw_data = vna.query_ascii_values(":CALCulate:DATA? SDATA")

    def fmr_init(self) -> "通过rm连接到的vna和sr830":
        """
        :return: 传输给fmr_measure的init参数
        """

        # GPIB下设备资源描述符
        vna = self.rm.open_resource("GPIB0::16::INSTR")
        sr830 = self.rm.open_resource("GPIB0::8::INSTR")
        k6221 = self.rm.open_resource("GPIB0::12::INSTR")

        # sr830的设置
        sr830.write("SENS 17")  # 幅度
        sr830.write("OFLT 9")   # 时间常数
        sr830.write("FMOD 0")
        sr830.write("RSLP 1")
        sr830.write("ISRC 0")
        sr830.write("ICPL 0")

        # k6221的设置
        k6221.write("*RCL 1")   # 选择 User1 setup
        k6221.write(":SOUR:WAVE:AMPL 0.04")     # 幅值设置成40mA
        k6221.write(":SOUR:WAVE:ARM")   # 进入wave模式
        time.sleep(0.5)
        k6221.write(":SOUR:WAVE:INIT")  # Trigger
        k6221.write(":SOUR:WAVE:FREQ 776.3")

        # vna的设置成微波源
        vna.write("*CLS")
        vna.write(":CALC:PAR:DEL:ALL")
        vna.write(":CALC:PAR:DEF:EXT 'My_measure', 'S1_1'")
        vna.write(":CALC:PAR:SEL 'My_measure'")
        vna.write(":SENSe1:SWEep:POIN 2")
        vna.write(":DISP:WIND1:TRAC1:FEED 'My_measure'")

        # 返回初始化好的VNA和SR830
        return vna, sr830

    def fmr_measure(self, start_field: int, stop_field: int, field_step: int,
                    data_fetch_time: float, source_frequency: float, source_power: int,
                    vna: "fmr_init的return中的vna", sr830: "fmr_init返回中的sr830"):

        """
        :param start_field: 测量起始磁场
        :param stop_field: 测量终止磁场
        :param field_step: 磁场变化步长
        :param data_fetch_time: 获取SR830数据的时间，例如每0.2s读取一次
        :param source_frequency: 微波源频率
        :param source_power: 微波源功率
        :param vna: fmr_init 返回的vna
        :param sr830: fmr_init 返回的sr830
        :return: None
        该函数用于测量FMR，此时vna被用作微波源，保存的数据名称为 微波源频率.csv
        """

        vna.write(":CALC:PAR:SEL 'My_measure'")
        vna.write(f":SOUR:POW {source_power}")
        vna.write(f":SENS:FREQ:STAR {source_frequency}e9")
        vna.write(f":SENS:FREQ:STOP {source_frequency}e9")

        self.ppms.set_field(0, 200, self.ppms.field.approach_mode.linear)
        time.sleep(0.5)
        self.ppms.wait_for(delay_sec=5, timeout_sec=0, bitmask=self.ppms.subsystem.field)

        self.ppms.set_field(start_field, 200, self.ppms.field.approach_mode.linear)
        time.sleep(0.5)
        self.ppms.wait_for(delay_sec=5, timeout_sec=0, bitmask=self.ppms.subsystem.field)

        self.ppms.set_field(stop_field, field_step, self.ppms.field.approach_mode.linear)

        x = []
        y = []
        fields = []
        fig = plt.figure(figsize=(12, 5))
        while True:
            # 清除之前的绘图
            plt.clf()
            # 获取数据,分割成三部分
            data = sr830.query("SNAP?1, 2").rstrip().partition(',')
            field, status_field = self.ppms.get_field()

            # 接近目标磁场终止
            if abs(field - stop_field) <= 1:
                break

            # 更新数据轴
            x.append(float(data[0]))
            y.append(float(data[2]))
            fields.append(field)

            plt.subplot(1, 2, 1)
            plt.plot(fields, x, marker='o')
            plt.title('X')
            plt.xlabel('H (Gs)')
            plt.subplot(1, 2, 2)
            plt.plot(fields, y, label='Y', marker='o')
            plt.title('Y')
            plt.xlabel('H (Gs)')

            fig.suptitle(f'{source_frequency} GHz', fontsize=16)
            plt.show(block=False)
            plt.pause(data_fetch_time)

        plt.close()
        # column_stack和hstack的区别在于column_stack可以直接竖向拼接而不需要转置
        fields_xy = np.column_stack((fields, x, y))

        if not os.path.exists(self.save_path):
            os.makedirs(self.save_path)

        file_name = f"{source_frequency}Ghz.csv"
        save_path = os.path.join(self.save_path, file_name)

        np.savetxt(save_path, fields_xy, fmt=['%g', '%g', '%g'], delimiter=',')
        print(f"{source_frequency}Ghz has been saved to: {save_path}")

    def ppms_set_temperature(self, target, rate):
        self.ppms.set_temperature(target, rate, self.ppms.temperature.approach_mode.fast_settle)
        time.sleep(0.5)
        self.ppms.wait_for(delay_sec=5, timeout_sec=0, bitmask=self.ppms.subsystem.temperature)

    def ppms_set_field(self, target, rate):
        self.ppms.set_field(target, rate, self.ppms.field.approach_mode.linear)
        time.sleep(0.5)
        self.ppms.wait_for(delay_sec=5, timeout_sec=0, bitmask=self.ppms.subsystem.field)

    def ppms_get_temperature(self):
        t, st = self.ppms.get_temperature()
        return t

    def ppms_get_field(self):
        f, sf = self.ppms.get_field()
        return f

    def vna_read_save(self, name_folder, name_field,
                      vna_self, start_freq, stop_freq, points, average_times, s_parameter) -> None:
        """
        读取当前VNA的数据，并且保存到指定路径，name_folder是要保存数据的文件夹名称，name_field是保存数据的名称
        """
        start = start_freq[0]
        stop = stop_freq[0]
        point = int(points[0])
        average = average_times[0]
        s = s_parameter[0]

        # 重新平均
        vna_self.write(":SENSe1:AVERage:CLEar")

        # 暂停，等待平均完成
        time.sleep(average * 4)

        # 查询原始数据
        raw_data = vna_self.query_ascii_values(":CALCulate:DATA? SDATA")

        # 创建一系列空列表用来存储S21数据
        x = np.array([])
        y = np.array([])
        s21 = np.array([])

        for i in range(0, len(raw_data), 2):
            x = np.append(x, raw_data[i])
            y = np.append(y, raw_data[i + 1])
            log_magnitude = 20 * np.log10(np.sqrt(raw_data[i] ** 2 + raw_data[i + 1] ** 2))
            s21 = np.append(s21, log_magnitude)

        freq = np.linspace(start, stop, point)
        field = np.full(point, name_field)

        # plt.plot(freq, s21)

        # 将获取的频率点和S21点合并成一个矩阵
        field_freq_s21 = pd.DataFrame(np.column_stack((field, freq, s21, x, y)),
                                      columns=['Field (Oe)', 'Frequency (Hz)', f'{s} (dBm)', 'X', 'Y'])

        save_folder = os.path.join(self.save_path, f"{name_folder}")

        # 确保保存文件夹存在，如果不存在则创建
        if not os.path.exists(save_folder):
            os.makedirs(save_folder)

        save_field = os.path.join(save_folder, f"{name_field}.csv")

        # 保存矩阵到CSV文件，%g的精度，','为分隔符
        field_freq_s21.to_csv(save_field, header=True, index=False, encoding='utf-8-sig')

        print(f"{name_field} has been saved to: {save_field}")

    def vna_status(self) -> "一个包含vna所有设置的NamedTuple":
        """
        和VNA建立连接，并且返回VNA自身及其设置
        """
        # GPIB下设置的VNA资源描述符
        vna_self = self.rm.open_resource("GPIB0::16::INSTR")

        # 选中'My_measure'测量
        vna_self.write(":CALC:PAR:SEL 'My_measure'")

        # 查询起始频率
        start_freq = vna_self.query_ascii_values(":SENS:FREQ:STAR?")

        # 查询终止频率
        stop_freq = vna_self.query_ascii_values(":SENS:FREQ:STOP?")

        # 查询测量点数
        points = vna_self.query_ascii_values(":SENSe1:SWEep:POIN?")

        # 查询平均次数
        average_times = vna_self.query_ascii_values(":SENSe1:AVERage:COUNt?")

        # 查询S参数
        s_parameter = vna_self.query(":CALC:PAR:CAT?").strip().split(',')[1][0:3]

        # 设置一个命名元组用来保存VNA的所有设置，方便之后调用属性
        VNAStatus = namedtuple("VNAStatus",
                               ["vna_self", "start_freq", "stop_freq", "points", "average_times", "s_parameter"])

        # 返回VNA以及其状态
        return VNAStatus(vna_self, start_freq, stop_freq, points, average_times, s_parameter)

    def vna_setup(self, s_parameter, power, bandwidth,
                  start_frequency, stop_frequency, points, average_counts) -> None:

        vna_s = self.rm.open_resource("GPIB0::16::INSTR")

        # 选中测量
        vna_s.write(":CALC:PAR:SEL 'My_measure' ")

        # 连续扫，若要关闭在后面加OFF
        vna_s.write("INITiate:CONTinuous")

        # 设置S参数
        vna_s.write(f":CALC:PAR:MOD:EXT {s_parameter} ")

        # 功率
        vna_s.write(f":SOUR:POW {int(power)}")

        # 中频带宽
        vna_s.write(f":SENSe1:BANDwidth {int(bandwidth)}")

        # 起始频率
        vna_s.write(f":SENSe1:FREQ:STAR {float(start_frequency)}e9")

        # 终止频率
        vna_s.write(f":SENSe1:FREQ:STOP {float(stop_frequency)}e9")

        # 测量点数
        vna_s.write(f":SENSe1:SWEep:POIN {int(points)}")

        # 设置数据平均次数，等待3s，这样防止自动比例出错
        vna_s.write(":SENSe1:AVERage:STATe ON")
        vna_s.write(f":SENSe1:AVERage:COUNt {int(average_counts)}")


if __name__ == '__main__':
    path = r"C:\Users\海鸥\OneDrive\桌面\documents\fmr"
    measure = AutoMeasure(path)

    measure.ppms_set_field(1000, 100)

    init = measure.fmr_init
    measure.fmr_measure(start_field=0, stop_field=1000, field_step=100, data_fetch_time=0.5, source_frequency=5,
                        source_power=-5, vna=init[0], sr830=init[1])
