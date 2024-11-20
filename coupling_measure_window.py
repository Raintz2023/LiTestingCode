import os.path
import time
import sys
import pyvisa as visa
import numpy as np
import pandas as pd
import MultiPyVu as mpv
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from PyQt5.QtGui import QFont
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import (QApplication, QWidget, QGridLayout, QLabel, QLineEdit,
                             QPushButton, QDesktopWidget, QCheckBox)
from auto_meshgrid import DataProcessing as dp
import pathlib
from colorama import Fore


class PpmsController:
    """
        This class is used to establish a connection with PPMS.
        Before running this module, please ensure that the server side connecting to the PPMS is opened.
    """
    # 不同于__init__，这个会在该程序运行时直接创建self属性，而不需要实例化
    ppms = mpv.Client("222.195.78.246", 5000)
    ppms.open()


class VnaController:
    """
        This class is used to establish a connection with the VNA,
        and clear previous measurements before creating a new measurement.
        Please note that VNA should be connected to this computer using GPIB.
    """
    rm = visa.ResourceManager()
    vna = rm.open_resource("GPIB0::16::INSTR")


class ParameterThread(QThread):
    """
    This class is used to create a Thread for reading physical quantities,
    continuously retrieving the temperature and magnetic field from the PPMS in real-time.
    """
    # 不接收信号，而传递出多个数据信号的Thread定义***
    parameter_updated_signal = pyqtSignal(float, float)

    def __init__(self):
        # 定义一个标识符，用来判断是否暂停ParameterThread
        super().__init__()
        self._is_running = True

    def run(self):
        while self._is_running:
            temperature = float(PpmsController.ppms.get_temperature()[0])
            time.sleep(0.5)
            # 读取必须存在间隔，否则PPMS返回物理量会报错。
            # 原因在于发送读取指令是瞬时的，假如不存在时间间隔，两个读取指令几乎同时发送，
            # 而PPMS响应前者读取温度操作时，回复的是当前磁场，仪器报错。
            field = float(PpmsController.ppms.get_field()[0])
            self.parameter_updated_signal.emit(temperature, field)

    def stop_thread(self):
        self._is_running = False

    def start_thread(self):
        self._is_running = True
        # 等待上一个进程完全结束
        self.wait()
        self.start()


class StartMeasureThread(QThread):
    """
    This class is used to set parameters for multiple tests and initiate the testing process.
    """
    # 接受多个参数，调用内建方法，然后传递出测试结束信号，不传递出数据的Thread
    finished_signal = pyqtSignal()

    def __init__(self, ax, canvas, path, start_field, stop_field, field_step,
                 start_temp, stop_temp, temp_step, f_loop, s_parameter):
        """
        :param ax: 控件中的坐标轴，用于绘图
        :param canvas: 控件中的画布，用于更新绘图
        :param path: 保存数据的路径，必填项
        :param start_field: 扫频起始磁场，必填项
        :param stop_field: 扫频终止磁场，必填项
        :param field_step: 扫频磁场步长，必填项
        :param start_temp: 变温起始温度，必填项，用于确定创建当前温度文件夹
        :param stop_temp: 变温终止温度，选填项
        :param temp_step: 变温温度步长，选填项
        :param f_loop: 循环场，选填项
        :param s_parameter: 循环s参数，选填项
        """
        super().__init__()
        self.ax = ax
        self.canvas = canvas
        self.path = path
        self.start_field = start_field
        self.stop_field = stop_field
        self.field_step = field_step
        self.start_temp = start_temp
        self.stop_temp = stop_temp
        self.temp_step = temp_step
        self.s_parameter = s_parameter
        self.f_loop = f_loop
        self._is_not_running = False
        self.ppms = PpmsController.ppms
        self.vna = VnaController.vna

    def run(self):
        """
        测试的最外层循环，即变温加循环场
        :return: None
        """
        print(Fore.BLUE + f"All testing has started".center(110, '^'))
        print('\n')
        # 获取当前vna的一些属性，方便之后调用
        self.vna.write(":CALC:PAR:SEL 'My_measure' ")
        self.start_freq = self.vna.query_ascii_values(":SENS:FREQ:STAR?")
        self.stop_freq = self.vna.query_ascii_values(":SENS:FREQ:STOP?")
        self.points = self.vna.query_ascii_values(":SENSe1:SWEep:POIN?")
        self.average_times = self.vna.query_ascii_values(":SENSe1:AVERage:COUNt?")
        # 最外层变温循环
        for i in range(int((self.stop_temp - self.start_temp) / self.temp_step) + 1):
            print(Fore.YELLOW + f"An experiment at "
                  f"{round(self.start_temp + i * self.temp_step, 1)} K is now under way".center(100, '*'))
            print('\n')
            # 判断stop是否按下
            if self._is_not_running:
                break
            # 根据读取的温度来给外层文件夹命名
            folder_temp = f"{round(self.start_temp + i * self.temp_step, 1)}k"
            save_folder_outer = pathlib.Path(os.path.join(self.path, folder_temp))
            if not os.path.exists(save_folder_outer):
                os.makedirs(save_folder_outer)

            if self._is_not_running:
                break
            # 可选循环场，f_loop中包含四部分，分别是循环[起始场，终止场，步长，测量点]
            # 最后一个测量点为总循环场次数
            f_loop_points = self.f_loop[-1]

            if self._is_not_running:
                break
            if f_loop_points == 0:  # 不进行场循环，不填时默认为0
                # 直接进入循环S参数的测量
                self.s_normal_measure(save_folder_outer)

            save_folder_temp = save_folder_outer    # 保存临时文件名
            # 若不为零则进入先场循环后进行S测试的模式
            for j in range(f_loop_points):
                if self._is_not_running:
                    break
                # 测量点一旦出现，开始测量，否则继续场循环
                if (j+1) in self.f_loop[3:]:
                    save_folder_outer = save_folder_temp    # 调用临时文件名，若不提前保存原始文件名则会造成文件名累积嵌套
                    if self._is_not_running:
                        break
                    print(Fore.RED + f'The field loop {j+1} times testing is now under way'.center(90, '~'))
                    print('\n')
                    save_folder_outer = save_folder_outer.joinpath(f'{j+1}_times')  # 文件夹嵌套循环场
                    if not os.path.exists(save_folder_outer):
                        os.makedirs(save_folder_outer)
                    self.s_normal_measure(save_folder_outer)    # 传递外层文件名，进行循环S测试
                    print(Fore.RED + f'The field loop {j+1} times testing is over'.center(90, '~'))
                    print('\n')

                else:
                    if (j+1) % 5 == 0:  # 打印循环场次数提醒
                        print(Fore.RED + f'The field loop is now {j+1} times'.center(90, '~'))
                        print('\n')
                    # 循环磁场
                    self.ppms.set_field(self.f_loop[0], 200, self.ppms.field.approach_mode.linear)
                    time.sleep(0.5)
                    self.ppms.wait_for(delay_sec=3, timeout_sec=0, bitmask=self.ppms.subsystem.field)
                    if self._is_not_running:
                        break
                    self.ppms.set_field(self.f_loop[1], 200, self.ppms.field.approach_mode.linear)
                    time.sleep(0.5)
                    self.ppms.wait_for(delay_sec=3, timeout_sec=0, bitmask=self.ppms.subsystem.field)
                    if self._is_not_running:
                        break

            print(Fore.YELLOW + f"The experiment at "
                  f"{round(self.start_temp + i * self.temp_step, 1)} K is over".center(100, '*'))
            print('\n')
            # 没到终止温度，跳到下个温度
            if self.stop_temp != self.start_temp:
                self.ppms.set_temperature(round(self.start_temp + (i + 1) * self.temp_step, 1), 5,
                                          self.ppms.temperature.approach_mode.fast_settle)
                time.sleep(1)
                self.ppms.wait_for(delay_sec=10, timeout_sec=0, bitmask=self.ppms.subsystem.temperature)
                if self._is_not_running:
                    break
                        
        print('\n')
        print(Fore.BLUE + f"All testing has concluded".center(110, '^'))

        # 发送测试结束信号
        self.finished_signal.emit()

    def normal_measure(self, save_folder_inner):
        """
        普通进行一次扫频测试，为最内层循环
        :param save_folder_inner: 保存最终数据的最内层文件路径
        :return: None
        """
        # 磁场到设置的起始磁场
        self.ppms.set_field(self.start_field, 200, self.ppms.field.approach_mode.linear)
        time.sleep(0.5)
        self.ppms.wait_for(delay_sec=5, timeout_sec=0, bitmask=self.ppms.subsystem.field)

        self.vna.write(":SENSe1:AVERage:CLEar")
        time.sleep(self.average_times[0] * 4)
        raw_data = np.array(self.vna.query_ascii_values(":CALCulate:DATA? SDATA"))

        print(Fore.CYAN + f'Commencing {str(save_folder_inner.name).title()} testing'.center(80, '+'))

        for i in range(int((self.stop_field - self.start_field) / self.field_step) + 1):
            # 判断是否终止该次测量
            if self._is_not_running:
                break
            # 创建一系列空列表用来存储S21数据
            s21 = np.array([])
            x = np.array([])
            y = np.array([])

            if self._is_not_running:
                break
            for j in range(0, len(raw_data), 2):
                x = np.append(x, raw_data[j])
                y = np.append(y, raw_data[j + 1])
                log_magnitude = 20 * np.log10(np.sqrt(raw_data[j] ** 2 + raw_data[j + 1] ** 2))
                s21 = np.append(s21, log_magnitude)

            if self._is_not_running:
                break
            freq = np.linspace(self.start_freq, self.stop_freq, int(self.points[0]))  # 根据仪器设置来获得频率点
            field = self.start_field + i * self.field_step  # 获得磁场接近值
            field_vector = np.full(int(self.points[0]), field)  # 将磁场扩充为整个列表

            # 确保保存文件夹存在，如果不存在则创建
            if not os.path.exists(save_folder_inner):
                os.makedirs(save_folder_inner)

            # 动态命名法，给文件命名
            file_name = f"{field}.csv"

            # 最终包含文件名的路径,并转化成Path实例
            final_path = save_folder_inner.joinpath(file_name)

            if self._is_not_running:
                break
            # 保存矩阵到CSV文件，逗号为分隔符
            field_freq_s21 = pd.DataFrame(np.column_stack((field_vector, freq, s21, x, y)),
                                          columns=['Field (Oe)', 'Frequency (Hz)',
                                                   f'{save_folder_inner.name} (dBm)', 'X', 'Y'])

            field_freq_s21.to_csv(final_path, header=True, index=False, encoding='utf-8-sig')

            print(Fore.GREEN + f"Field {field} Oe has been saved".center(75, '-'))

            if self._is_not_running:
                break
            # 获得两组数据后开始绘图
            if i >= 1:
                data = dp(path=save_folder_inner)
                meshgrid = data.meshgrid(normalized=0)
                self.ax.clear()
                data.bathymetric(self.ax, *meshgrid)
                self.ax.set_title(f"{final_path.parent.parent.parent.name}-"
                                  f"{final_path.parent.parent.name}-{final_path.parent.name}", fontsize='30')
                self.ax.set_xlabel('Field (Oe)', fontsize='30')
                self.ax.set_ylabel('Frequency (GHz)', fontsize='30')
                self.ax.xaxis.set_tick_params(labelsize=20)  # x轴
                self.ax.yaxis.set_tick_params(labelsize=20)  # y轴
                self.canvas.draw()
                self.canvas.updateGeometry()

            # 在磁场达到终止磁场时直接停止测量
            if i == (self.stop_field - self.start_field) / self.field_step:
                print(Fore.CYAN + f"{str(save_folder_inner.name).title()} testing ends".center(80, '+'))
                print('\n')
                break

            if self._is_not_running:
                break
            # 下一个磁场
            self.ppms.set_field((i + 1) * self.field_step + self.start_field, 200, self.ppms.field.approach_mode.linear)
            time.sleep(0.5)
            self.ppms.wait_for(delay_sec=3, timeout_sec=0, bitmask=self.ppms.subsystem.field)

            if self._is_not_running:
                break
            self.vna.write(":SENSe1:AVERage:CLEar")
            time.sleep(self.average_times[0] * 4)

            # 获取下一组数据
            raw_data = self.vna.query_ascii_values(":CALCulate:DATA? SDATA")

    def s_normal_measure(self, save_folder_outer):
        """
        加上S参数循环的普通扫频测试
        :param save_folder_outer: 外层文件夹，包含变温，或含有磁场循环
        :return: None
        """
        # 检验需要测量的S参数
        for s in self.s_parameter:
            if self._is_not_running:
                break
            if s != 0:
                # 改变vna的S参数
                self.vna.write(f":CALC:PAR:MOD:EXT {s}")
                # 创建最内层文件夹，传递给普通测量
                save_folder_inner = save_folder_outer.joinpath(s)
                if self._is_not_running:
                    break
                self.normal_measure(save_folder_inner)  # 将一次扫描测试封转成一个普通测量
            else:
                continue

    def stop_measure(self):
        self._is_not_running = True


class MyWindow(QWidget):
    """
    在我的窗口里面切记只放一些控件，按钮，Thread，以及不费时函数，
    什么是不费时函数？
    就是函数里面只有简单的读取操作，而不进行数据处理和实时绘图等等耗时操作。
    这些操作要写进Thread中，交给多线程处理，
    否则如果在主线程里运行耗时操作，我的窗口可能会卡死！！！
    """
    def __init__(self):
        super().__init__()  # 继承QWidget父类的初始化，用来使用一些Q控件
        self.s_21 = 0
        self.s_12 = 0
        self.s_11 = 0
        self.s_22 = 0
        self.init_ui()

    def init_ui(self):
        desktop = QDesktopWidget()
        # 获取屏幕分辨率
        screen_rect = desktop.screenGeometry()
        screen_width = screen_rect.width()
        screen_height = screen_rect.height()

        def width_trans(w):
            return int((w/2560) * screen_width)

        def height_trans(w):
            return int((w/1600) * screen_height)

        width = 180
        height = 45

        # 测试相关控件
        self.input_measure_path = QLineEdit()
        self.input_measure_path.setFixedSize(width_trans(2 * width + 30), height_trans(height))
        self.input_measure_start_field = QLineEdit()
        self.input_measure_start_field .setFixedSize(width_trans(width), height_trans(height))
        self.input_measure_stop_field = QLineEdit()
        self.input_measure_stop_field .setFixedSize(width_trans(width), height_trans(height))
        self.input_measure_field_step = QLineEdit()
        self.input_measure_field_step.setFixedSize(width_trans(width), height_trans(height))

        label_measure = QLabel('Measure')
        label_measure.setFixedSize(width_trans(3 * width), height_trans(height))
        label_measure_path = QLabel('*Path:')
        label_measure_path.setFixedSize(width_trans(width), height_trans(height))
        label_measure_start_field = QLabel('*Start Field:')
        label_measure_start_field.setFixedSize(width_trans(width), height_trans(height))
        label_measure_stop_field = QLabel('*Stop Field:')
        label_measure_stop_field.setFixedSize(width_trans(width), height_trans(height))
        label_measure_field_step = QLabel('*Field Step:')
        label_measure_field_step.setFixedSize(width_trans(width), height_trans(height))

        # 循环和额外操作相关控件
        label_loop_temperature = QLabel('T-Loop')
        label_loop_temperature.setFixedSize(width_trans(2 * width), height_trans(2 * height))
        label_loop_start_temperature = QLabel('*Start Temp:')
        label_loop_start_temperature.setFixedSize(width_trans(width), height_trans(height))
        label_loop_stop_temperature = QLabel('Stop Temp:')
        label_loop_stop_temperature.setFixedSize(width_trans(width), height_trans(height))
        label_loop_temperature_step = QLabel('Temp Step:')
        label_loop_temperature_step.setFixedSize(width_trans(width), height_trans(height))

        label_loop_field = QLabel('F-Loop')
        label_loop_field.setFixedSize(width_trans(2 * width), height_trans(2 * height))
        label_loop_start_field = QLabel('Start Field:')
        label_loop_start_field.setFixedSize(width_trans(width), height_trans(height))
        label_loop_stop_field = QLabel('Stop Field:')
        label_loop_stop_field.setFixedSize(width_trans(width), height_trans(height))
        label_loop_field_step = QLabel('Field Step:')
        label_loop_field_step.setFixedSize(width_trans(width), height_trans(height))
        label_loop_measure_points = QLabel('Break Points:')
        label_loop_measure_points.setFixedSize(width_trans(width), height_trans(height))

        self.input_loop_start_temperature = QLineEdit()
        self.input_loop_start_temperature.setFixedSize(round(width_trans(width)), height_trans(height))
        self.input_loop_stop_temperature = QLineEdit()
        self.input_loop_stop_temperature.setFixedSize(round(width_trans(width)), height_trans(height))
        self.input_loop_temperature_step = QLineEdit()
        self.input_loop_temperature_step.setFixedSize(round(width_trans(width)), height_trans(height))

        self.input_loop_start_field = QLineEdit()
        self.input_loop_start_field.setFixedSize(round(width_trans(width)), height_trans(height))
        self.input_loop_stop_field = QLineEdit()
        self.input_loop_stop_field.setFixedSize(round(width_trans(width)), height_trans(height))
        self.input_loop_field_step = QLineEdit()
        self.input_loop_field_step.setFixedSize(round(width_trans(width)), height_trans(height))
        self.input_loop_measure_points = QLineEdit()
        self.input_loop_measure_points.setFixedSize(round(width_trans(width)), height_trans(height))


        # 监控物理场控件
        self.label_monitor_field = QLabel('Field : Unknown')
        self.label_monitor_field.setFixedSize(width_trans(width * 2), height_trans(height))
        self.label_monitor_temp = QLabel('Temp : Unknown')
        self.label_monitor_temp.setFixedSize(width_trans(width * 2), height_trans(height))

        # 绘图控件
        self.figure = Figure()
        self.ax = self.figure.add_subplot(111)
        self.canvas = FigureCanvas(self.figure)
        # self.canvas也是继承QWidget的一个类，因此利用setFixedSize可以设置大小***
        self.canvas.setFixedSize(1200, 1000)

        # 按钮控件
        self.btn_start_measure = QPushButton('START')
        self.btn_start_measure.setFixedSize(width_trans(2 * width + 30), height_trans(height))
        self.btn_stop_measure = QPushButton('STOP')
        self.btn_stop_measure.setFixedSize(width_trans(width + 15), height_trans(height))

        # 检测控件
        label_s_parameters = QLabel('S-Loop')
        label_s_parameters.setFixedSize(width_trans(width), height_trans(height))
        self.s21_checkbox = QCheckBox('-S21', self)
        self.s21_checkbox.setFixedSize(width_trans(width), height_trans(height))
        self.s12_checkbox = QCheckBox('-S12', self)
        self.s12_checkbox.setFixedSize(width_trans(width), height_trans(height))
        self.s11_checkbox = QCheckBox('-S11', self)
        self.s11_checkbox.setFixedSize(width_trans(width), height_trans(height))
        self.s22_checkbox = QCheckBox('-S22', self)
        self.s22_checkbox.setFixedSize(width_trans(width), height_trans(height))

        # 设置字体
        font1 = QFont()
        font1.setPointSize(9)
        font1.setBold(True)
        font1.setFamily('Arial')
        font2 = QFont()
        font2.setPointSize(16)
        font2.setBold(True)
        font2.setFamily('Microsoft Yahei')
        font3 = QFont()
        font3.setPointSize(12)
        font3.setBold(True)
        font3.setFamily('Arial')
        label_measure.setFont(font2)
        label_measure_path.setFont(font1)
        label_s_parameters.setFont(font2)
        label_measure_start_field.setFont(font1)
        label_measure_stop_field.setFont(font1)
        label_measure_field_step.setFont(font1)
        label_loop_temperature.setFont(font2)
        label_loop_start_temperature.setFont(font1)
        label_loop_stop_temperature.setFont(font1)
        label_loop_temperature_step.setFont(font1)
        label_loop_field.setFont(font2)
        label_loop_start_field.setFont(font1)
        label_loop_stop_field.setFont(font1)
        label_loop_field_step.setFont(font1)
        label_loop_measure_points.setFont(font1)
        self.btn_start_measure.setFont(font2)
        self.btn_stop_measure.setFont(font2)
        self.label_monitor_field.setFont(font3)
        self.label_monitor_temp.setFont(font3)
        self.s21_checkbox.setFont(font3)
        self.s12_checkbox.setFont(font3)
        self.s22_checkbox.setFont(font3)
        self.s11_checkbox.setFont(font3)

        # 设置窗口布局
        layout = QGridLayout(self)
        layout.setRowStretch(8, 1)
        layout.setColumnStretch(13, 1)
        addition = 7

        layout.addWidget(self.canvas, 0, 0, 7, 6)

        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(4)

        layout.addWidget(label_loop_temperature, 1 + addition, 0, 1, 2)
        layout.addWidget(label_loop_start_temperature, 2 + addition, 0, 1, 1)
        layout.addWidget(self.input_loop_start_temperature, 2 + addition, 1, 1, 1)
        layout.addWidget(label_loop_stop_temperature, 3 + addition, 0, 1, 1)
        layout.addWidget(self.input_loop_stop_temperature, 3 + addition, 1, 1, 1)
        layout.addWidget(label_loop_temperature_step, 4 + addition, 0, 1, 1)
        layout.addWidget(self.input_loop_temperature_step, 4 + addition, 1, 1, 1)

        layout.addWidget(label_loop_field, 1 + addition, 2, 1, 2)
        layout.addWidget(label_loop_start_field, 2 + addition, 2, 1, 1)
        layout.addWidget(self.input_loop_start_field, 2 + addition, 3, 1, 1)
        layout.addWidget(label_loop_stop_field, 3 + addition, 2, 1, 1)
        layout.addWidget(self.input_loop_stop_field, 3 + addition, 3, 1, 1)
        layout.addWidget(label_loop_field_step, 4 + addition, 2, 1, 1)
        layout.addWidget(self.input_loop_field_step, 4 + addition, 3, 1, 1)
        layout.addWidget(label_loop_measure_points, 5 + addition, 2, 1, 1)
        layout.addWidget(self.input_loop_measure_points, 5 + addition, 3, 1, 1)

        layout.addWidget(label_s_parameters, 1 + addition, 4, 1, 1)
        layout.addWidget(self.s21_checkbox, 2 + addition, 4, 1, 1)
        layout.addWidget(self.s12_checkbox, 3 + addition, 4, 1, 1)
        layout.addWidget(self.s11_checkbox, 4 + addition, 4, 1, 1)
        layout.addWidget(self.s22_checkbox, 5 + addition, 4, 1, 1)

        layout.addWidget(label_measure, 1 + addition, 5, 1, 3)
        layout.addWidget(label_measure_path, 2 + addition, 5, 1, 1)
        layout.addWidget(self.input_measure_path, 2 + addition, 6, 1, 2)
        layout.addWidget(label_measure_start_field, 3 + addition, 5, 1, 1)
        layout.addWidget(self.input_measure_start_field, 4 + addition, 5, 1, 2)
        layout.addWidget(label_measure_stop_field, 3 + addition, 6, 1, 1)
        layout.addWidget(self.input_measure_stop_field, 4 + addition, 6, 1, 2)
        layout.addWidget(label_measure_field_step, 3 + addition, 7, 1, 1)
        layout.addWidget(self.input_measure_field_step, 4 + addition, 7, 1, 2)

        layout.addWidget(self.label_monitor_temp, 0, 6, 1, 2)
        layout.addWidget(self.label_monitor_field, 1, 6, 1, 2)

        layout.addWidget(self.btn_start_measure, 5 + addition, 5, 1, 2)
        layout.addWidget(self.btn_stop_measure, 5 + addition, 7, 1, 1)

        # 建立方法链接
        self.btn_start_measure.clicked.connect(self.start_measure_reader)
        self.btn_stop_measure.clicked.connect(self.stop_measure)

        # 建立ParameterThread，然后直接打开，自动运行其中的run函数
        self.parameter_thread = ParameterThread()
        # run函数发射数据信号给更新标签的方法
        self.parameter_thread.parameter_updated_signal.connect(self.update_parameter_label)
        self.parameter_thread.start()

        # 更改VNA的s测量参数
        self.s21_checkbox.stateChanged.connect(self.s_21_on)
        self.s12_checkbox.stateChanged.connect(self.s_12_on)
        self.s11_checkbox.stateChanged.connect(self.s_11_on)
        self.s22_checkbox.stateChanged.connect(self.s_22_on)

        # 窗口展示
        self.setGeometry(400, 100, 1440, 1200)
        self.setWindowTitle('VNA Measure')
        self.show()

    # 一系列待更改的S参数
    def s_21_on(self, state):
        if state == 2:
            self.s_21 = 'S21'
        else:
            self.s_21 = 0

    def s_12_on(self, state):
        if state == 2:
            self.s_12 = 'S12'
        else:
            self.s_12 = 0

    def s_11_on(self, state):
        if state == 2:
            self.s_11 = 'S11'
        else:
            self.s_11 = 0

    def s_22_on(self, state):
        if state == 2:
            self.s_22 = 'S22'
        else:
            self.s_22 = 0

    def start_measure_reader(self):
        # 等待ParameterThread进程结束
        self.parameter_thread.stop_thread()
        self.parameter_thread.wait()

        # 需要测量S参数循环的列表
        s_parameter = (self.s_21, self.s_12, self.s_11, self.s_22)

        # 读取必填的参数
        path = self.input_measure_path.text()
        start_field = int(self.input_measure_start_field.text())
        stop_field = int(self.input_measure_stop_field.text())
        field_step = int(self.input_measure_field_step.text())
        start_temp = float(self.input_loop_start_temperature.text())

        # 尝试读取循环场参数，如果有缺写项，默认不进行测量
        try:
            measure_points = list(int(p) for p in self.input_loop_measure_points.text().split(','))
            f_loop = list((int(self.input_loop_start_field.text()), int(self.input_loop_stop_field.text()),
                           int(self.input_loop_field_step.text()))) + measure_points
        except ValueError:
            f_loop = [1, 1, 1, 0]

        # 变温循环可选填，不填则默认不改变温度，起始温度当做最外层文件夹
        stop_temp = self.input_loop_stop_temperature.text()
        if not stop_temp:
            stop_temp = start_temp
        stop_temp = float(stop_temp)
        if stop_temp == start_temp:

            temp_step = 1   # 设为1之后就不会变温
        else:
            temp_step = float(self.input_loop_temperature_step.text())

        # 点击按钮后建立StartMeasureThread，接收参数，开始测试
        self.start_measure_thread = StartMeasureThread(self.ax, self.canvas, path, start_field, stop_field, field_step,
                                                       start_temp, stop_temp, temp_step, f_loop, s_parameter)
        self.start_measure_thread.start()
        # 完成测试后发送结束指令，调用ParameterThread开始
        self.start_measure_thread.finished_signal.connect(self.parameter_thread.start_thread)
        self.start_measure_thread.start()

    def stop_measure(self):
        self.start_measure_thread.stop_measure()
        self.start_measure_thread.wait()

    def update_parameter_label(self, temperature, field):
        # 更新物理场标签
        self.label_monitor_temp.setText(f'Temp: {temperature} K')
        self.label_monitor_field.setText(f'Field: {field} Gs')

    def closeEvent(self, event):
        print("Window is closing")
        # 调用父类的closeEvent，确保窗口正常关闭
        super().closeEvent(event)
        # 关闭所有可能存在的连接
        try:
            VnaController.vna.close()
            print("VNA connection closed")
        except visa.VisaIOError:
            pass
        try:
            self.ppms.close_client()
            print("PPMS connection closed")
        except AttributeError:
            pass


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MyWindow()
    sys.exit(app.exec_())
    