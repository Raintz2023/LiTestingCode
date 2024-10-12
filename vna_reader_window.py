import os.path
import time
import datetime
import sys
import pyvisa as visa
import numpy as np
import MultiPyVu as mpv
import skrf as rf
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from PyQt5.QtGui import QFont
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import (QApplication, QWidget, QGridLayout, QLabel, QLineEdit,
                             QPushButton, QCheckBox, QDesktopWidget)


class VnaController:
    """
    This class is used to establish a connection with the VNA,
    and clear previous measurements before creating a new measurement.
    Please note that VNA should be connected to this computer using GPIB.
    """

    rm = visa.ResourceManager()
    vna = rm.open_resource("GPIB0::16::INSTR")
    vna.write("*CLS")
    vna.write(":CALC:PAR:DEL:ALL")
    vna.write(":CALC:PAR:DEF:EXT 'My_measure', 'S2_1'")
    vna.write(":DISP:WIND1:TRAC1:FEED 'My_measure' ")
    time.sleep(3)


class VnaSetupThread(QThread):
    """
    This class performs operations to modify the state of the VNA.
    """
    finished_signal = pyqtSignal(int, str)

    # 接受多个数据信号，而只调用内建方法，传递出结束信号数字0和绘图格式的Thread定义
    def __init__(self, s_parameter, start_frequency, stop_frequency, power, bandwidth,
                 points, average_counts, vna_format):
        super().__init__()
        self.s_parameter = s_parameter
        self.start_frequency = start_frequency
        self.stop_frequency = stop_frequency
        self.power = power
        self.bandwidth = bandwidth
        self.points = points
        self.average_counts = average_counts
        self.vna_format = vna_format

    def run(self):
        # run函数会在__init__之后自动运行一次
        self.vna_setup()

    def vna_setup(self):
        """
        This method sets up the VNA, where the required inputs include the start frequency and stop frequency. ***
        The remaining parameters have default values: power is set to -5, bandwidth is set to 500,
        measurement points is set to 1001, averaging is turned on by default with 3 counts.
        Before starting the experiment, please ensure that the VNA is configured properly.

        """
        # 选中测量
        VnaController.vna.write(":CALC:PAR:SEL 'My_measure' ")

        # 连续扫，若要关闭在后面加OFF
        VnaController.vna.write("INITiate:CONTinuous")

        # 设置S参数
        if self.s_parameter:
            VnaController.vna.write(f":CALC:PAR:MOD:EXT {self.s_parameter} ")

        # 功率
        if self.power:
            VnaController.vna.write(f":SOUR:POW {int(self.power)}")

        # 中频带宽
        if self.bandwidth:
            VnaController.vna.write(f":SENSe1:BANDwidth {int(self.bandwidth)}")

        # 起始频率
        if self.start_frequency:
            VnaController.vna.write(f":SENSe1:FREQ:STAR {float(self.start_frequency)}e9")

        # 终止频率
        if self.stop_frequency:
            VnaController.vna.write(f":SENSe1:FREQ:STOP {float(self.stop_frequency)}e9")

        # 测量点数
        if self.points:
            VnaController.vna.write(f":SENSe1:SWEep:POIN {int(self.points)}")

        # 设置数据平均次数，等待3s，这样防止自动比例出错
        if self.average_counts:
            # 设置数据平均打开
            VnaController.vna.write(":SENSe1:AVERage:STATe ON")
            VnaController.vna.write(f":SENSe1:AVERage:COUNt {int(self.average_counts)}")

        time.sleep(4)
        # 发送设置结束信号数字0结束归一化操作，同时激活（重置）实时绘图函数
        self.finished_signal.emit(0, self.vna_format)


class VnaReadDrawThread(QThread):
    """
    This class is used to read VNA data in real time and display it on the canvas.
    """
    data_ready_signal = pyqtSignal(np.ndarray, np.ndarray)

    # 接受多个数据信号（画布和坐标轴），而只调用内建方法更新画布，传递出实时数据信号的Thread定义
    def __init__(self, ax, canvas, normalize, vna_format, q_fitting_signal, w_res):
        super().__init__()
        self.ax = ax
        self.canvas = canvas
        self.normalize = np.array(normalize)
        self.vna_format = vna_format
        self.q_fitting_signal = q_fitting_signal
        self.w_res = w_res
        self._is_running = True

        # 创建一个标记，先不显示，当点击后显示，用来标记数据
        self.connection_id = None
    
    def onclick(self, event):
        x_click = event.xdata
        y_click = event.ydata
        self.annot.xy = (x_click, y_click)
        text = f"({(x_click/1e9):.4g}, {y_click:.4g})"
        self.annot.set_text(text)
        self.annot.set_visible(True)
        try:
            self.canvas.draw()
        except AttributeError:
            pass

    def run(self):
        # 持续读取数据并且绘图
        while self._is_running:
            time.sleep(0.2)
            self.vna_read_draw()

    def vna_read_draw(self):
        """
        This method is to read the data of vna and draw it on the canvas.
        """
        # 选中'My_measure'测量
        VnaController.vna.write(":CALC:PAR:SEL 'My_measure'")

        # 查询起始频率
        start_freq = VnaController.vna.query_ascii_values(":SENSe1:FREQ:STAR?")

        # 查询终止频率
        stop_freq = VnaController.vna.query_ascii_values(":SENSe1:FREQ:STOP?")

        # 查询测量点数
        points = VnaController.vna.query_ascii_values(":SENSe1:SWEep:POIN?")

        # 查询S参数
        s_parameter = VnaController.vna.query(":CALC:PAR:CAT?").strip().split(',')[1][0:3]

        # 获取曲线的测量原始数据
        try:
            raw_data = np.array(VnaController.vna.query_ascii_values(":CALC:DATA? SDATA"))
        except visa.errors.VisaIOError:
            self.stop_reading()  # 捕获错误，终止进程
            return
        
        time.sleep((points[0]/2001) * 1.2)

        freq = np.linspace(start_freq[0], stop_freq[0], int(points[0]))

        if self.vna_format == "log":    # 对数幅值
            # 创建一个空向量用来存储x+yi数据
            x_re = np.array([], dtype=np.complex128)
            y_im = np.array([], dtype=np.complex128)
            for i in range(0, len(raw_data), 2):
                x_re = np.append(x_re, raw_data[i])
                y_im = np.append(y_im, raw_data[i + 1])

            x_yi = x_re + 1j * y_im
            freq_rf = rf.Frequency(float(freq[0]), float(freq[-1]), len(freq), 'hz')
            network = rf.Network(frequency=freq_rf, s=x_yi)
            s21 = network.s_db[:, 0, 0] # 获取S21的幅值，传递出去保存

            self.ax.clear()
            # 根据normalize的值来决定是否归一化
            if self.normalize.any():
                s21 = s21 - self.normalize
            
            if self.q_fitting_signal == 1 and self.w_res != 0:  # Q值拟合信号和谐振器频率同时给出才进入拟合模式

                if (self.w_res.split(',')[0]) == 't':
                    q = rf.Qfactor(network[f"{self.w_res.split(',')[1]}GHz"], res_type='transmission')
                else:
                    q = rf.Qfactor(network[f"{self.w_res.split(',')[1]}GHz"], res_type='reflection')
                try:       # ***使用else优化try
                    res = q.fit()
                    q0 = q.Q_unloaded(A=1.0)    
                    fitted_network = q.fitted_network(frequency=freq_rf)
                    fitted_network.plot_s_db(ax=self.ax, label='Fitted Model', lw=2, color='C0', ls='--')
                    print(f'Fitted Resonant Frequency: f_L = {q.f_L / 1e9} GHz')
                    print(f'Fitted Loaded Q-factor: Q_L = {q.Q_L}')
                    print(f'Fitted Unloaded Q-factor: Q_0 = {q0}')
                except np.linalg.LinAlgError:
                    print("Change the frequency of the resonator!")

            self.annot = self.ax.annotate("", xy=(0, 0), xytext=(-40, 40), textcoords="offset points",
                                          bbox=dict(boxstyle='round4, pad=0.3', fc='linen', ec='k', lw=1),
                                          arrowprops=dict(arrowstyle='-|>'), fontsize=20, va='center', ha='center')
            self.annot.set_visible(False)

            self.ax.plot(freq, s21, color='red')    # 绘出S21幅值图

            if self.connection_id is None:
                self.connection_id = self.canvas.mpl_connect('button_press_event', self.onclick) 

            self.ax.set_title(f'{s_parameter}', fontsize='40')
            self.ax.set_xlabel('Frequency (GHz)', fontsize='30')
            self.ax.set_ylabel(f'{s_parameter} (dBm)', fontsize='30')   # 设置X,Y的label
            self.ax.xaxis.set_tick_params(labelsize=20)  
            self.ax.yaxis.set_tick_params(labelsize=20)   # 设置X,Y的tick
            self.ax.set_aspect('auto')
            for spine in self.ax.spines.values():
                spine.set_edgecolor('black')  # 设置边框颜色
                spine.set_linewidth(2)
            self.ax.grid(True)

            self.canvas.draw()
            self.canvas.updateGeometry()
            
            self.data_ready_signal.emit(freq, s21)  # 传出实时频率范围和测试数据

        elif self.vna_format == "smith":    # smith圆图

            x_re = np.array([], dtype=np.complex128)
            y_im = np.array([], dtype=np.complex128)
            for i in range(0, len(raw_data), 2):
                x_re = np.append(x_re, raw_data[i])
                y_im = np.append(y_im, raw_data[i + 1])
            x_yi = x_re + 1j * y_im

            # 使用rf，根据vna设置来建立一个网络
            network = rf.Network(frequency=freq, s=x_yi)
            # 展示vna测量的史密斯原图
            self.ax.clear()
            self.annot = self.ax.annotate("", xy=(0, 0), xytext=(-40, 40), textcoords="offset points",
                                          bbox=dict(boxstyle='round4, pad=0.3', fc='linen', ec='k', lw=1),
                                          arrowprops=dict(arrowstyle='-|>'), fontsize=20, va='center', ha='center')
            self.annot.set_visible(False)

            
            network.plot_s_smith(ax=self.ax, show_legend=False)

            if self.connection_id is None:
                self.connection_id = self.canvas.mpl_connect('button_press_event', self.onclick) 

            self.ax.set_title(f'{s_parameter} Smith Plot', fontsize='40')

            self.canvas.draw()
            self.canvas.updateGeometry()

            self.data_ready_signal.emit(freq, x_yi)

    def stop_reading(self):
        self._is_running = False
        # 点击动作显示标签的连接，在Thread结束的时候解除，放置再次进入建立多次连接 ***
        if self.connection_id is not None:
            self.canvas.mpl_disconnect(self.connection_id)
            self.connection_id = None

class VnaDataNormalizeThread(QThread):
    """
    This class is used to obtain the current data, which is used to normalize the measured data.
    """
    # 接受开始信号，传输出np.ndarray类型数据的Thread定义
    data_normalize_signal = pyqtSignal(np.ndarray)

    def __init__(self):
        super().__init__()
        self.data = np.array([])

    def run(self):
        self.vna_normalize()

    def vna_normalize(self):

        VnaController.vna.write(":CALC:PAR:SEL 'My_measure'")
        raw_data = np.array(VnaController.vna.query_ascii_values(":CALC:DATA? SDATA"))
        # 获取当前数据，保存用来归一化(省去建立网络需要的频率范围)
        for i in range(0, len(raw_data), 2):
            log_magnitude = 20 * np.log10(np.sqrt(raw_data[i] ** 2 + raw_data[i + 1] ** 2))
            self.data = np.append(self.data, log_magnitude)

        self.data_normalize_signal.emit(self.data)


class MyWindow(QWidget):
    """
    在窗口里面切记只放一些控件，按钮，Thread，以及不费时函数，什么是不费时函数？
    就是函数里面只有简单的读取操作，而不进行数据处理和实时绘图等等耗时操作。
    费时操作要写进Thread中，交给多线程处理，
    否则如果在主线程里运行耗时操作，窗口可能会卡死！！！
    """
    def __init__(self):
        super().__init__()
        self.current_freq = np.array([])
        self.current_data = np.array([])    # 主线程实时保存数据
        self.init_ui()

    def init_ui(self):
        desktop = QDesktopWidget()
        # 获取屏幕分辨率
        screen_rect = desktop.screenGeometry()
        screen_width = screen_rect.width()
        screen_height = screen_rect.height()

        def width_trans(w):
            return int((w/2560.0) * screen_width)

        def height_trans(w):
            return int((w/1600.0) * screen_height)

        width = 180
        height = 45

        # VNA输入控件
        self.input_vna_s_parameter = QLineEdit()
        self.input_vna_s_parameter.setFixedSize(width_trans(width), height_trans(height))
        self.input_vna_startFreq = QLineEdit()
        self.input_vna_startFreq.setFixedSize(width_trans(width), height_trans(height))
        self.input_vna_stopFreq = QLineEdit()
        self.input_vna_stopFreq.setFixedSize(width_trans(width), height_trans(height))
        self.input_vna_power = QLineEdit()
        self.input_vna_power.setFixedSize(width_trans(width), height_trans(height))
        self.input_vna_bandwidth = QLineEdit()
        self.input_vna_bandwidth.setFixedSize(width_trans(width), height_trans(height))
        self.input_vna_points = QLineEdit()
        self.input_vna_points.setFixedSize(width_trans(width), height_trans(height))
        self.input_vna_averageCounts = QLineEdit()
        self.input_vna_averageCounts.setFixedSize(width_trans(width), height_trans(height))
        self.input_ppms_set_field = QLineEdit()
        self.input_ppms_set_field.setFixedSize(width_trans(width), height_trans(height))
        self.input_vna_format = QLineEdit()
        self.input_vna_format.setFixedSize(width_trans(width), height_trans(height))
        self.input_vna_format.setPlaceholderText('log')
        self.input_path_read = QLineEdit()
        self.input_path_read.setFixedSize(width_trans(width*2.2), height_trans(height))
        self.input_fitting_q = QLineEdit()
        self.input_fitting_q.setFixedSize(width_trans(width), height_trans(height))

        # VNA标志控件
        label_vna = QLabel('VNA')
        label_vna.setFixedSize(width_trans(2 * width), height_trans(height))
        label_vna_s = QLabel('S-Parameter:')
        label_vna_s.setFixedSize(width_trans(width), height_trans(height))
        label_vna_start_freq = QLabel('Start Freq:')
        label_vna_start_freq.setFixedSize(width_trans(width), height_trans(height))
        label_vna_stop_freq = QLabel('Stop Freq:')
        label_vna_stop_freq.setFixedSize(width_trans(width), height_trans(height))
        label_vna_power = QLabel('Power:')
        label_vna_power.setFixedSize(width_trans(width), height_trans(height))
        label_vna_bandwidth = QLabel('Bandwidth:')
        label_vna_bandwidth.setFixedSize(width_trans(width), height_trans(height))
        label_vna_points = QLabel('Points:')
        label_vna_points.setFixedSize(width_trans(width), height_trans(height))
        label_vna_average_counts = QLabel('Average:')
        label_vna_average_counts.setFixedSize(width_trans(width), height_trans(height))

        # 分割线控件
        label_split_1 = QLabel('               |')
        label_split_2 = QLabel('               |')
        label_split_3 = QLabel('               |')
        label_split_4 = QLabel('               |')
        label_split_5 = QLabel('               |')
        label_split_1.setFixedSize(width_trans(width), height_trans(height))
        label_split_2.setFixedSize(width_trans(width), height_trans(height))
        label_split_3.setFixedSize(width_trans(width), height_trans(height))
        label_split_4.setFixedSize(width_trans(width), height_trans(height))
        label_split_5.setFixedSize(width_trans(width), height_trans(height))

        # 绘图控件
        self.figure = Figure()
        self.ax = self.figure.add_subplot(111)
        self.canvas = FigureCanvas(self.figure)
        # FigureCanvas也是继承QWidget的一个类，因此利用setFixedSize可以设置大小***
        self.canvas.setFixedSize(1200, 1000)

        # 按钮控件
        self.btn_vna_setup = QPushButton('VNA SETUP')
        self.btn_vna_setup.setFixedSize(width_trans(4 * width + 80), height_trans(height))
        self.btn_vna_normalize = QPushButton('Normal')
        self.btn_vna_normalize.setFixedSize(width_trans(width), height_trans(height*1.5))
        self.btn_vna_raw = QPushButton('Raw')
        self.btn_vna_raw.setFixedSize(width_trans(width), height_trans(height*1.5))
        self.btn_ppms_set_field = QPushButton('Set Field')
        self.btn_ppms_set_field .setFixedSize(width_trans(width), height_trans(height))
        self.btn_vna_format = QPushButton('Format')
        self.btn_vna_format.setFixedSize(width_trans(width), height_trans(height))
        self.btn_data_save = QPushButton('Save Data')
        self.btn_data_save.setFixedSize(width_trans(width), height_trans(height))
        self.btn_graph_save = QPushButton('Save Graph')
        self.btn_graph_save.setFixedSize(width_trans(width), height_trans(height))
        self.btn_fitting_q = QPushButton('Fit')
        self.btn_fitting_q.setFixedSize(width_trans(width), height_trans(height))

        # 检测控件
        self.ppms_connect_checkbox = QCheckBox('Connect PPMS', self)
        self.fitting_q_checkbox = QCheckBox('Fitting Q', self)

        # 设置字体
        font1 = QFont()
        font1.setPointSize(9)
        font1.setBold(True)
        font1.setFamily('Arial')
        font2 = QFont()
        font2.setPointSize(16)
        font2.setBold(True)
        font2.setFamily('Arial')
        label_vna.setFont(font2)
        label_vna_s.setFont(font1)
        label_vna_start_freq.setFont(font1)
        label_vna_stop_freq.setFont(font1)
        label_vna_power.setFont(font1)
        label_vna_points.setFont(font1)
        label_vna_bandwidth.setFont(font1)
        label_vna_average_counts.setFont(font1)
        self.btn_vna_setup.setFont(font2)
        self.btn_vna_normalize.setFont(font2)
        self.btn_vna_raw.setFont(font2)
        self.btn_ppms_set_field.setFont(font1)
        self.btn_fitting_q.setFont(font1)
        self.btn_vna_format.setFont(font1)
        self.input_vna_format.setFont(font1)
        label_split_1.setFont(font1)
        label_split_2.setFont(font1)
        label_split_3.setFont(font1)
        label_split_4.setFont(font1)
        label_split_5.setFont(font1)
        self.ppms_connect_checkbox.setFont(font1)
        self.fitting_q_checkbox.setFont(font1)
        self.btn_data_save.setFont(font1)
        self.btn_graph_save.setFont(font1)

        # 设置窗口布局
        layout = QGridLayout(self)
        layout.setRowStretch(8, 1)
        layout.setColumnStretch(13, 1)
        addition = 7

        layout.addWidget(self.canvas, 0, 0, 7, 6)
        layout.addWidget(self.ppms_connect_checkbox, 0, 6, 1, 1)
        layout.addWidget(self.input_ppms_set_field, 1, 6, 1, 1)
        layout.addWidget(self.btn_ppms_set_field, 2, 6, 1, 1)
        layout.addWidget(self.fitting_q_checkbox, 4, 6, 1, 1)
        layout.addWidget(self.input_fitting_q, 5, 6, 1, 1)
        layout.addWidget(self.btn_fitting_q, 6, 6, 1, 1)
        layout.addWidget(label_vna, 1 + addition, 0, 1, 2)
        layout.addWidget(label_vna_s, 1 + addition, 2, 1, 1)
        layout.addWidget(self.input_vna_s_parameter, 1 + addition, 3, 1, 1)
        layout.addWidget(label_vna_start_freq, 2 + addition, 0, 1, 1)
        layout.addWidget(self.input_vna_startFreq, 2 + addition, 1, 1, 1)
        layout.addWidget(label_vna_stop_freq, 2 + addition, 2, 1, 1)
        layout.addWidget(self.input_vna_stopFreq, 2 + addition, 3, 1, 1)
        layout.addWidget(label_vna_power, 3 + addition, 0, 1, 1)
        layout.addWidget(self.input_vna_power, 3 + addition, 1, 1, 1)
        layout.addWidget(label_vna_bandwidth, 3 + addition, 2, 1, 1)
        layout.addWidget(self.input_vna_bandwidth, 3 + addition, 3, 1, 1)
        layout.addWidget(label_vna_points, 4 + addition, 0, 1, 1)
        layout.addWidget(self.input_vna_points, 4 + addition, 1, 1, 1)
        layout.addWidget(label_vna_average_counts, 4 + addition, 2, 1, 1)
        layout.addWidget(self.input_vna_averageCounts, 4 + addition, 3, 1, 1)

        layout.addWidget(label_split_1, 1 + addition, 4, 1, 1)
        layout.addWidget(label_split_2, 2 + addition, 4, 1, 1)
        layout.addWidget(label_split_3, 3 + addition, 4, 1, 1)
        layout.addWidget(label_split_4, 4 + addition, 4, 1, 1)
        layout.addWidget(label_split_5, 5 + addition, 4, 1, 1)

        layout.addWidget(self.btn_vna_setup, 5+  addition, 0, 1, 4)
        layout.addWidget(self.btn_vna_normalize, 1 + addition, 5, 2, 1)
        layout.addWidget(self.btn_vna_raw, 1 + addition, 6, 2, 1)
        layout.addWidget(self.input_vna_format, 3 + addition, 5, 1, 1)
        layout.addWidget(self.btn_vna_format, 3 + addition, 6, 1, 1)
        layout.addWidget(self.input_path_read, 4 + addition, 5, 1, 2)
        layout.addWidget(self.btn_data_save, 5 + addition, 5, 1, 1)
        layout.addWidget(self.btn_graph_save, 5 + addition, 6, 1, 1)

        # 建立Thread，然后直接打开，自动运行其中的run函数以实现实时绘图
        self.vna_draw()

        # 和读取用户VNA设置的函数建立连接
        self.btn_vna_setup.clicked.connect(self.vna_setup_read)

        # 和开始vna归一化的函数建立连接，暂时中断实时绘图
        self.btn_vna_normalize.clicked.connect(self.vna_data_normalize)

        # 和取消vna归一化的函数建立连接
        self.btn_vna_raw.clicked.connect(self.vna_data_raw)

        # 和更改vna绘图格式函数建立连接
        self.btn_vna_format.clicked.connect(self.vna_format)

        # 和保存数据和绘图函数建立连接
        self.btn_data_save.clicked.connect(self.save_data)
        self.btn_graph_save.clicked.connect(self.save_graph)

        # 检测控件被勾选时输出2，部分勾选输出1，不勾选输出0
        self.ppms_connect_checkbox.stateChanged.connect(self.ppms_connect)

        # 和设置ppms磁场的函数建立连接
        self.btn_ppms_set_field.clicked.connect(self.ppms_set_field)

        # 和开启fitting函数建立连接
        self.fitting_q_checkbox.stateChanged.connect(self.q_fitting_on)
        self.btn_fitting_q.clicked.connect(self.q_fitting_parameter)

        # 窗口展示
        self.setGeometry(800, 100, 1200, 1200)
        self.setWindowTitle('VNA Reader')
        self.show()

    def vna_draw(self, normalize=0, vna_format="log", q_fitting_signal=0, w_res=0):
        # 最开始自动绘出实时数据,之后调用相当于重启
        # normalize默认为零，即不进行归一化操作，当接收到归一化数据信号后，进行相减操作归一化
        self.vna_read_draw_thread = VnaReadDrawThread(self.ax, self.canvas, normalize, vna_format,
                                                      q_fitting_signal, w_res)
        # 先建立信号和槽函数的connect再start()！
        self.vna_read_draw_thread.data_ready_signal.connect(self.change_current_data)
        self.vna_read_draw_thread.start()

    def change_current_data(self, current_freq, current_data):
        # 实时更改当前测试数据，可以用来保存
        self.current_freq = current_freq
        self.current_data = current_data

    def save_data(self):
        # 点击保存当前测试数据
        path = self.input_path_read.text()
        current_time = datetime.datetime.now()
        # 如果不给保存路径，默认保存到桌面
        if not path:
            path = os.path.join(os.path.expanduser("~"), "Desktop")
        # 根据目前时间进行命名
        name = os.path.join(path, current_time.strftime("%Y_%m_%d_%H_%M_%S") + ".csv")
        if not os.path.exists(path):
            os.makedirs(path)
        # 都以字符串格式保存
        print(name)
        np.savetxt(name, np.vstack((self.current_freq, self.current_data)), delimiter=',', fmt="%s")

    def save_graph(self):
        # 点击保存当前测试图
        path = self.input_path_read.text()
        current_time = datetime.datetime.now()
        if not path:
            path = os.path.join(os.path.expanduser("~"), "Desktop")
        name = os.path.join(path, current_time.strftime("%Y_%m_%d_%H_%M_%S") + ".png")
        if not os.path.exists(path):
            os.makedirs(path)
        print(name)
        self.figure.savefig(name)

    def vna_setup_read(self):
        # 先关闭读取vna的实时数据，防止冲突
        self.vna_read_draw_thread.stop_reading()
        self.vna_read_draw_thread.wait()

        # 读取要传递的字符串参数
        s_parameter = self.input_vna_s_parameter.text()
        start_frequency = self.input_vna_startFreq.text()
        stop_frequency = self.input_vna_stopFreq.text()
        power = self.input_vna_power.text()
        bandwidth = self.input_vna_bandwidth.text()
        points = self.input_vna_points.text()
        average_counts = self.input_vna_averageCounts.text()
        # 设置也要读取vna的绘图格式
        vna_format = self.input_vna_format.text()
        if not vna_format:
            vna_format = "log"

        # 点击按钮之后创建VnaSetupThread，接受参数，运行run函数
        self.vna_setup_thread = VnaSetupThread(s_parameter, start_frequency, stop_frequency,
                                               power, bandwidth, points, average_counts, vna_format)
        # 设置结束信号,启动vna实时绘图
        self.vna_setup_thread.finished_signal.connect(self.vna_draw)
        self.vna_setup_thread.start()

    def vna_data_normalize(self):
        # 中断实时绘图
        self.vna_read_draw_thread.stop_reading()
        self.vna_read_draw_thread.wait()

        # 获取当前数据
        self.vna_normalize_thread = VnaDataNormalizeThread()
        # 再次激活实时绘图，此时normalize不再是0
        self.vna_normalize_thread.data_normalize_signal.connect(self.vna_draw)
        self.vna_normalize_thread.start()

    def vna_data_raw(self):
        # 中断实时绘图
        self.vna_read_draw_thread.stop_reading()
        self.vna_read_draw_thread.wait()

        # 重置实时绘图，normalize再次是0，取消归一化
        self.vna_draw(normalize=0)

    def vna_format(self):
        vna_format = self.input_vna_format.text()
        # 默认绘图格式是对数幅值
        if not vna_format:
            vna_format = "log"
        # 暂停实时绘图
        self.vna_read_draw_thread.stop_reading()
        self.vna_read_draw_thread.wait()
        # 重启，更换绘图格式
        self.vna_draw(vna_format=vna_format)

    def ppms_connect(self, state):
        # checkbox激活PPMS连接
        if state == 2:
            print("Connect to PPMS")
            self.ppms = mpv.Client("222.195.78.246", 5000)
            self.ppms.open()
        else:
            print('Close PPMS connection')
            self.ppms.close_client()

    def ppms_set_field(self):
        # 读取输入磁场，改变ppms磁场
        field = self.input_ppms_set_field.text()
        try:
            self.ppms.set_field(field, 200, approach_mode=self.ppms.field.approach_mode.linear)
        except AttributeError:
            print("Please check PPMS connection!")

    def q_fitting_on(self, state):
        # checkbox激活fitting模式
        if state == 2:
            self.q_fitting_signal = 1
        else:
            self.q_fitting_signal = 0
            # 退激活fitting模式
            self.vna_read_draw_thread.stop_reading()
            self.vna_read_draw_thread.wait()

            self.vna_draw()

    def q_fitting_parameter(self):
        # 点击开始拟合，人为给出谐振器的谐振频率大致点
        self.w_res = self.input_fitting_q.text()
        if not self.w_res:
            self.w_res = 0
            print("Please check your input parameter!")
        # 中断实时绘图
        self.vna_read_draw_thread.stop_reading()
        self.vna_read_draw_thread.wait()

        self.vna_draw(q_fitting_signal=self.q_fitting_signal, w_res=self.w_res)

    def closeEvent(self, event):
        print("Window is closing.")
        # 关闭窗口时记得中断VNA读取数据，否者可能会和关闭VNA冲突
        self.vna_read_draw_thread.stop_reading()
        super().closeEvent(event)

        # 关闭所有可能存在的连接
        try:
            VnaController.vna.close()
        except visa.VisaIOError:
            pass
        else:   # try没有错误执行打印       
            print("VNA connection closed.")

        try:
            self.ppms.close_client()
        except AttributeError:
            pass
        else:
            print("PPMS connection closed.")


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MyWindow()
    sys.exit(app.exec_())
