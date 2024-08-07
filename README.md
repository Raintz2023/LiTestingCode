# LiTestingCode

本项目是来自USTC的Peng Li教授课题组的磁学测试代码，基于Python，主要利用Quantum Design的PPMS和Ceyear的VNA，还有部分电学仪表（详见代码），实现了FMR，stFMR，谐振器表征等测试，项目尚未完善，还请多多担待。

（注意：软件的熟练使用基于硬件的连接，请保证在VNA等电学仪表执行操作时，已经通过GPIB和您的电脑建立了连接；同样PPMS执行操作时，确保PPMS控制端电脑打开服务器，您的电脑网络连接正常。）

主代码目前有四个部分，分别是auto_measure，auto_processing，以及两个基于PyQt5的测试窗口，以下分别介绍各个部分的用途：

1. auto_measure，顾名思义是把一些测试可能用到的操作一股脑放到一个class中，例如改变PPMS的磁场，温度，读取一次VNA数据，读取VNA设置等等操作。同时也有一些整次测量，简单举例来看:
   
  ![auto举例](https://github.com/user-attachments/assets/995108ee-bd21-40c1-9c93-a0a5708d1af5)

  a. 建立一个测量实例，参数是之后数据要保存的地址

  b. 将PPMS的磁场设置成1000 Oe，速率为100 Oe/s

  c. 进行一次FMR测量，扫场从0到1000 Oe，步长为100 Oe/s，数据采集时间为0.5s一次，微波源频率设置成5GHz，微波源功率设置成-5dBm，fmr_init参数返回两个仪器。

  这个类的建立主要是为了方便各位进行DIY测试，比如你在测试之前加入循环场之类的。但是其中方法还是很有限，希望以后有机会再扩展。

2. auto_processing，
