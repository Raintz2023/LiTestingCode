# Li-sTestingCode

本项目是来自USTC的Peng Li教授课题组的磁学测试代码，基于Python，主要利用Quantum Design的PPMS和Ceyear的VNA，还有部分电学仪表（详见代码），实现了FMR，stFMR，谐振器表征等测试，项目尚未完善，还请多多担待。

目前有四个部分，分别是auto_measure，auto_processing，以及两个基于PyQt5的测试窗口，以下分别介绍各个部分的用途：

1.auto_measure，顾名思义是把一些测试可能用到的操作一股脑放到一个class中，例如改变PPMS的磁场，温度，读取一次VNA数据，读取VNA设置等等操作。同时也将一整次测试写入进去
