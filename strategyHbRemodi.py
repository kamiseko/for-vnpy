# encoding: UTF-8

"""
tick合成bar可用BarManager来做，因为不涉及到持仓量序列的记录，但是如果要记录新K线（比如5minK线）每一分钟的持仓量的话
，还是需要自己来写bar线的合成。

BarManager的好处：
1） 记录了前一个tick的数据，因此可计算出每个tick的成交量
2） 可用一分钟合成任意周期的K线新数据而不单单是合成短周期倍数的K线数据

问题是如果盘中才启动的话那么第一个bar线的成交量的计算会出问题。
"""

from __future__ import division

import talib
import numpy as np

from vnpy.trader.vtObject import VtBarData
from vnpy.trader.vtConstant import EMPTY_STRING,STATUS_NOTTRADED,STATUS_PARTTRADED,\
    STATUS_ALLTRADED,STATUS_CANCELLED,STATUS_REJECTED

from vnpy.trader.app.ctaStrategy.ctaTemplate import (CtaTemplate,
                                                     BarManager,
                                                     ArrayManager)



########################################################################
class BarMStrategy(CtaTemplate):
    """多周期策略"""
    className = 'BarMStrategy'
    author = u'toriphy'




    # 策略参数
    kkLength = 15  # 计算通道中值的窗口数
    kkDevUp = 2.2  # 计算通道宽度的偏差 取2.1或者2.2比较好
    kkDevDown = 1.9  # 初始值1.9
    trailingPrcnt = 1.1  # 移动止损, 初始值1.2
    thresholdRatio = 0.15   # 持仓量指标阈值
    initDays = 10  # 初始化数据所用的天数,注意这个值是天数而不是bar的个数
    fixedSize = 1  # 每次交易的数量
    barBin = 5  # 五分钟线 短周期
    barLongBin = 15  # 十五分钟线，长周期



    shortMAperiod  = 6
    longMAperiod = 12



    bufferSize = 100  # 需要缓存的数据的大小 65
    longCycleBufferSize = 30 # 长周期需要缓存的数据大小 20
    bufferCount = 0  # 目前已经缓存了的数据的计数
    longCycleBufferCount = 0  # 长周期目前已经缓存了的数据的计数

    longCycleTradingFlag = 0  # 长周期交易信号



    atrValue = 0  # 最新的ATR指标数值
    kkMid = 0  # KK通道中轨
    kkUp = 0  # KK通道上轨
    kkDown = 0  # KK通道下轨
    openRatioModi = 0 # 开仓指标调整
    intraTradeHigh = 0  # 持仓期内的最高点
    intraTradeLow = 0  # 持仓期内的最低点
    longStop = 0  # 多头的移动止损点位
    shortStop = 0  # 空头的移动止损点位


    openRatioModiArray = np.zeros(bufferSize)
    longCycleLLTArrayShort = np.zeros(longCycleBufferSize)  # 短周期部分 ，alpha

    # 其他不相关的
    buyOrderID = None  # OCO委托买入开仓的委托号
    shortOrderID = None  # OCO委托卖出开仓的委托号
    orderList = []  # 保存委托代码的列表



    # 参数列表，保存了参数的名称
    paramList = ['name',
                 'className',
                 'author',
                 'vtSymbol',
                 'kkLength',
                 'kkDevUp',
                 'kkDevDown',
                 'thresholdRatio',
                 'trailingPrcnt']

    # 变量列表，保存了变量的名称
    varList = ['inited',
               'trading',
               'pos',
               'kkMid',
               'kkUp',
               'kkDown',
               'barOpenRatioModi',
               'longStop',
               'shortStop',
               'longCycleTradingFlag']

    # 同步列表，保存了需要保存到数据库的变量名称
    syncList = ['pos', 'longStop', 'shortStop']  # 持仓数据和trailing stop 是一定要保存的

    # ----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        """Constructor"""
        super(BarMStrategy, self).__init__(ctaEngine, setting)

        # 创建K线合成器对象
        self.bm = BarManager(self.onBar)  # 1分钟线（因为要调取1分钟线的持仓量和成交量信息）
        self.am = ArrayManager()

        self.bm5 = BarManager(self.onBar, self.barBin, self.on5MinBar)
        self.am5 = ArrayManager()

        self.bm15 = BarManager(self.onBar, self.barLongBin, self.on15MinBar)
        self.am15 = ArrayManager(size=self.longCycleBufferSize)

    # ----------------------------------------------------------------------
    def onInit(self):
        """初始化策略（必须由用户继承实现）"""
        self.writeCtaLog(u'%s策略初始化' % self.name)

        # 载入历史数据，并采用回放计算的方式初始化策略数值
        initData = self.loadBar(self.initDays)
        for bar in initData:
            self.onBar(bar)

        self.putEvent()

    # ----------------------------------------------------------------------
    def onStart(self):
        """启动策略（必须由用户继承实现）"""
        self.writeCtaLog(u'%s策略启动' % self.name)
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStop(self):
        """停止策略（必须由用户继承实现）"""
        self.writeCtaLog(u'%s策略停止' % self.name)
        self.putEvent()

    # ----------------------------------------------------------------------
    def onTick(self, tick):
        """收到行情TICK推送（必须由用户继承实现）"""
        self.bm.updateTick(tick)

    # ----------------------------------------------------------------------
    def onBar(self, bar):
        """收到Bar推送（必须由用户继承实现）"""
        # 基于15分钟判断趋势过滤，因此先更新
        self.am.updateBar(bar)
        self.vArray1min = self.am.volume[-5:]
        self.oArray1min = self.am.openInterest[-6:]

        self.bm15.updateBar(bar)


        # 基于5分钟判断
        self.bm5.updateBar(bar)


    # ----------------------------------------------------------------------
    def on5MinBar(self, bar):
        """收到5分钟K线"""
        self.cancelAll()

        # 保存K线数据

        self.am5.updateBar(bar)

        barOpenRatioModi = ((np.sqrt(self.vArray1min) / np.sqrt(self.vArray1min).sum()) * ((self.oArray1min[1:] - \
                            self.oArray1min[:-1]) / self.vArray1min)).mean()

        self.openRatioModiArray[0:self.bufferSize - 1] = self.openRatioModiArray[1:self.bufferSize]
        self.openRatioModiArray[-1] = barOpenRatioModi  # 开仓比例

        self.bufferCount += 1

        if self.bufferCount < self.bufferSize:
            return



        # 计算指标数值
        self.atrValue = talib.ATR(self.am5.high,
                                  self.am5.low,
                                  self.am5.close,
                                  self.kkLength)[-1]
        self.kkMid = talib.MA(self.am5.close, self.kkLength)[-1]
        self.kkUp = self.kkMid + self.atrValue * self.kkDevUp
        self.kkDown = self.kkMid - self.atrValue * self.kkDevDown



        self.openRatioModi = self.openRatioModiArray[-1]    # 开仓量指标


        conditionKKBuy = self.am5.close[-1] > self.kkUp
        conditionKKSell = self.am5.close[-1] < self.kkDown

        conditionOpenRatioModiBuy = self.openRatioModi > 0.022
        conditionOpenRatioModiSell = self.openRatioModi > 0.026  # 最好0.026


        # 当前无仓位，
        if self.pos == 0:
            self.intraTradeHigh = bar.high
            self.intraTradeLow = bar.low
            if conditionKKBuy and conditionOpenRatioModiBuy and self.longCycleTradingFlag == 1:
                self.buy(bar.close + 5, self.fixedSize)
            elif conditionKKSell and conditionOpenRatioModiSell and self.longCycleTradingFlag == -1:
                self.short(bar.close - 5, self.fixedSize)

        # 持有多头仓位
        elif self.pos > 0:
            self.intraTradeHigh = max(self.intraTradeHigh, bar.high)
            self.intraTradeLow = bar.low

            self.longStop = self.intraTradeHigh * (1 - self.trailingPrcnt / 100)
            orderID = self.sell(self.longStop,
                            abs(self.pos), stop=True)
            self.writeCtaLog(u'多头止损价格：' + str(self.longStop))
            self.orderList.append(orderID)

        # 持有空头仓位
        elif self.pos < 0:
            self.intraTradeHigh = bar.high
            self.intraTradeLow = min(self.intraTradeLow, bar.low)

            self.shortStop = self.intraTradeLow * (1 + self.trailingPrcnt / 100)
            orderID = self.cover(self.shortStop,
                                 abs(self.pos), stop=True)

            self.writeCtaLog(u'空头头止损价格：' + str(self.shortStop))
            self.orderList.append(orderID)

        # 发出状态更新事件
        self.putEvent()

    # ----------------------------------------------------------------------
    def on15MinBar(self, bar):
        """15分钟K线推送"""
        #print 'cycletime:', bar.datetime, self.longCycleTradingFlag
        self.am15.updateBar(bar)

        alpha = 0.3  # 5分钟线取0.3最佳
        alphatilde = 2 / (12 + 1)

        LLTShort = (alpha - (alpha ** 2) / 4) * self.am15.close[-1] + (alpha ** 2) / 2 * \
                   self.am15.close[-2] - \
                   (alpha - 3 * alpha ** 2 / 4) * self.am15.close[-3] + 2 * (1 - alpha) * \
                   self.longCycleLLTArrayShort[-1] - (1 - alpha ** 2) * self.longCycleLLTArrayShort[-2]

        self.longCycleLLTArrayShort[0:self.longCycleBufferSize - 1] = self.longCycleLLTArrayShort[
                                                                      1:self.longCycleBufferSize]
        self.longCycleLLTArrayShort[-1] = LLTShort

        #print self.am15.close[-10:],"\n","LLT:", LLTShort

        self.longCycleBufferCount += 1
        if self.longCycleBufferCount < self.longCycleBufferSize:
            return


        longCycleMAlong = talib.MA(self.am15.close, self.longMAperiod)
        longCycleMAshort = talib.MA(self.am15.close, self.shortMAperiod)

        maLongCondition = longCycleMAshort[-1] > longCycleMAlong[-1]
        lltLongCondition = self.longCycleLLTArrayShort[-1] > self.longCycleLLTArrayShort[-2]
        lltShortCondition = self.longCycleLLTArrayShort[-1] < self.longCycleLLTArrayShort[-2]
        if maLongCondition:
            self.longCycleTradingFlag = 1
        elif lltShortCondition:
            self.longCycleTradingFlag = -1
        else:
            self.longCycleTradingFlag = 0

    # ----------------------------------------------------------------------
    def onOrder(self, order):
        """收到委托变化推送（必须由用户继承实现）"""
        pass

    #----------------------------------------------------------------------
    def onStopOrder(self, so):
        """停止单推送"""
        pass

    # ----------------------------------------------------------------------
    def onTrade(self, trade):
        """发出状态更新事件"""
        self.putEvent()

    # ----------------------------------------------------------------------
    def sendOcoOrder(self, buyPrice, shortPrice, volume):
        """
        发送OCO委托

        OCO(One Cancel Other)委托：
        1. 主要用于实现区间突破入场
        2. 包含两个方向相反的停止单
        3. 一个方向的停止单成交后会立即撤消另一个方向的
        """
        # 发送双边的停止单委托，并记录委托号
        self.buyOrderID = self.buy(buyPrice, volume, True)
        self.shortOrderID = self.short(shortPrice, volume, True)

        # 将委托号记录到列表中
        self.orderList.append(self.buyOrderID)
        self.orderList.append(self.shortOrderID)


if __name__ == '__main__':
    # 提供直接双击回测的功能
    # 导入PyQt4的包是为了保证matplotlib使用PyQt4而不是PySide，防止初始化出错
    from vnpy.trader.app.ctaStrategy.ctaBacktesting import *
    from PyQt5 import QtCore, QtGui

    # 创建回测引擎
    savePath = 'C:/Users/tsan/Desktop/BacktestRA/'
    engine = BacktestingEngine()

    # 设置引擎的回测模式为K线
    engine.setBacktestingMode(engine.BAR_MODE)

    # 设置输出详细回测csv的存储位置
    #engine.setSavePath(savePath)

    # 设置回测用的数据起始日期
    engine.setStartDate('20170101')
    engine.setEndDate('20180101')

    # 设置产品相关参数
    #engine.setInitialCapital(20000)  # 初始资金10w
    engine.setCapital(20000)  # 初始资金10w
    #engine.setLeverage(1)  # 1倍杠杆
    engine.setSlippage(1)  # 股指1跳
    engine.setRate(3 / 10000)  # 万3
    engine.setSize(10)  # 股指合约大小
    engine.setPriceTick(1)  # 股指最小价格变动 0.2
    #engine.setpnlPctToggle(True)  # 百分比显示开关
    #engine.writeTrade = True
    # 设置使用的历史数据库
    #engine.setDatabase('FutureData_Index', 'rb000_1min_modi')
    engine.setDatabase('FutureData_Sequence', 'rb888_1min')


    '''
    # 设置使用的历史数据库 焦煤1分钟
    engine.setInitialCapital(100000)  # 初始资金10w
    engine.setLeverage(1)  # 2倍杠杆
    engine.setSlippage(1)  # 1跳
    engine.setRate(3 / 10000)  # 万0.3
    engine.setSize(100)  # 股指合约大小
    engine.setPriceTick(0.5)  # 股指最小价格变动 0.2
    engine.setpnlPctToggle(True)  # 百分比显示开关
    engine.setDatabase('FutureData_Sequence', 'i9888_1min_modi')
    '''


    # 在引擎中创建策略对象
    d = {}
    engine.initStrategy(BarMStrategy, d)

    # 开始跑回测
    engine.runBacktesting()

    # 显示回测结果
    #print u'多仓信号数量为：%d' % len(BarMStrategy.signalBuy)
    #print u'空仓信号数量为：%d' % len(BarMStrategy.signalSell)


    engine.showBacktestingResult()
    engine.showDailyResult()
    #print KkRatioStrategy.signalBuy

    ## 跑优化
    ''''''
    #setting = OptimizationSetting()                 # 新建一个优化任务设置对象
    #setting.setOptimizeTarget('capital')            # 设置优化排序的目标是策略净盈利
    #setting.addParameter('kkLength', 10.0, 16.0, 1.0)    # 增加第一个优化参数kkLength，起始10，结束16，步进1
    #setting.addParameter('kkDevUp', 1.5, 2.5, 0.2)        # 增加第二个优化参数kkDevUp，起始1.5，结束2.5，步进0.1
    #setting.addParameter('kkDevDown', 1.5, 2.5, 0.2)   # 增加第三个优化参数kkDevDown，起始1.5，结束2.5，步进0.1
    #setting.addParameter('thresholdRatio',0.12,0.20,0.01)            # 增加第四个参数thresholdRatio, 起始0.12，结束0.20,步长0.01

    #setting.addParameter('trailingPrcnt',0.8,2.0,0.2)            # 增加第五个参数thresholdRatio, 起始0.12，结束0.20,步长0.01
    #setting.addParameter('fixedCutLoss', 1, 4, 0.5)  # 增加第五个参数thresholdRatio, 起始0.12，结束0.20,步长0.01


    import time
    start = time.time()

    ## 运行单进程优化函数，自动输出结果，耗时：359秒
    #engine.runOptimization(AtrRsiStrategy, setting)

    ## 多进程优化
    #engine.runParallelOptimization(KkRatioStrategy, setting)

    print u'耗时：%s' %(time.time()-start)