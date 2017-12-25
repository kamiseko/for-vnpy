# encoding: UTF-8

"""
基于King Keltner通道的交易策略，适合用在股指上，
展示了OCO委托和5分钟K线聚合的方法。

注意事项：
1. 作者不对交易盈利做任何保证，策略代码仅供参考
2. 本策略需要用到talib，没有安装的用户请先参考www.vnpy.org上的教程安装
3. 将IF0000_1min.csv用ctaHistoryData.py导入MongoDB后，直接运行本文件即可回测策略
"""

from __future__ import division

import talib
import numpy as np

from vnpy.trader.vtObject import VtBarData
from vnpy.trader.vtConstant import EMPTY_STRING,STATUS_NOTTRADED,STATUS_PARTTRADED,\
    STATUS_ALLTRADED,STATUS_CANCELLED,STATUS_REJECTED

from vnpy.trader.app.ctaStrategy.ctaTemplate import CtaTemplate



########################################################################
class MultiCycleStrategy(CtaTemplate):
    """多周期策略"""
    className = 'MultiCycleStrategy'
    author = u'toriphy'

    # global preBarOpenInterest
    preBarOpenInterest = 0

    # 记录初始成交量
    #preTickVolume = -100
    preBarVolume = 0
    trueCalVolFlag = False

    # 策略参数
    openRatioMaLength = 4  # 计算openRatioMA的窗口数
    #atrLength = 22  # 计算ATR指标的窗口数
    atrMaLength = 10  # 计算ATR均线的窗口数
    kkLength = 15  # 计算通道中值的窗口数
    kkDevUp = 2.2 # 计算通道宽度的偏差 取2.1或者2.2比较好
    kkDevDown = 1.9  # 初始值1.9
    trailingPrcnt = 1 # 移动止损, 初始值1.2 之前已经有一轮大趋势，目前算比较震荡的行情的情况下可以设置小一点，但也要>0.8
    thresholdRatio = 0.15   # 持仓量指标阈值
    fixedCutLoss = 2   # 成本固定止损, 初始值3
    initDays = 10  # 初始化数据所用的天数,注意这个值是天数而不是bar的个数
    fixedSize = 1  # 每次交易的数量
    barBin = 5  # 五分钟线 短周期
    barLongBin = 15  # 十五分钟线，长周期


    SVDShort = 5  # 计算SVD指标的短窗口数  # 8,15,20 是一组很好的参数
    SVDLong = 10  # 计算SVD指标的长窗口数
    ShapeNum = 15  # SVD矩阵的形状
    shortMAperiod  = 6
    longMAperiod = 12


    # 策略变量
    bar = None  # 1分钟K线对象
    barMinute = EMPTY_STRING  # K线当前的分钟
    fiveBar = None  # 5分钟K线对象
    longCycleBar = None # 长周期bar

    bufferSize = 100  # 需要缓存的数据的大小 65
    longCycleBufferSize = 30 # 长周期需要缓存的数据大小 20
    bufferCount = 0  # 目前已经缓存了的数据的计数
    longCycleBufferCount = 0  # 长周期目前已经缓存了的数据的计数

    longCycleTradingFlag = 0  # 长周期判断趋势,初始为0

    # 短周期K线组
    highArray = np.zeros(bufferSize)  # K线最高价的数组
    lowArray = np.zeros(bufferSize)  # K线最低价的数组
    closeArray = np.zeros(bufferSize)  # K线收盘价的数组
    volumeArray = np.zeros(bufferSize)  # K线交易量
    obvArray = np.zeros(bufferSize)  # 能量潮指标
    volumeMaArray = np.zeros(bufferSize)

    # 长周期K线组
    longCycleHighArray = np.zeros(longCycleBufferSize)  # 长周期K线组最高价
    longCycleLowArray = np.zeros(longCycleBufferSize)  # 长周期K线组最低价
    longCycleCloseArray = np.zeros(longCycleBufferSize)  # 长周期K线组收盘价
    longCycleVolumeArray = np.zeros(longCycleBufferSize)  # 长周期K线组成交量
    longCycleLLTArray = np.zeros(longCycleBufferSize)  # 长周期LLT
    longCycleLLTArrayShort = np.zeros(longCycleBufferSize)  # 短周期部分 ，alpha

    MACD = np.zeros(longCycleBufferSize)  # MACD数组

    #shortMA = np.zeros(bufferSize)
    #longMA = np.zeros(bufferSize)
    atrArray = np.zeros(bufferSize)
    openInterestArray = np.zeros(bufferSize)
    openRatioModiArray = np.zeros(bufferSize)
    kamaArray = np.zeros(bufferSize)
    changePerVolumeArray = np.zeros(bufferSize)

    svdArrayShort = np.zeros(ShapeNum)
    svdArrayLong = np.zeros(ShapeNum)

    atrValue = 0  # 最新的ATR指标数值
    kkMid = 0  # KK通道中轨
    kkUp = 0  # KK通道上轨
    kkDown = 0  # KK通道下轨
    openRatioModi = 0 # 开仓指标调整
    openRatio = 0    # 开仓指标
    monitoringVolume = 0  # 监控计算的分钟线成交量
    intraTradeHigh = 0  # 持仓期内的最高点
    intraTradeLow = 0  # 持仓期内的最低点
    longStop = 0  # 多头的移动止损点位
    shortStop = 0  # 空头的移动止损点位



    buyOrderID = None  # OCO委托买入开仓的委托号
    shortOrderID = None  # OCO委托卖出开仓的委托号
    orderList = []  # 保存委托代码的列表
    buyCost = []    # 买入成本
    shortCost = []  # 卖出成本
    signalBuy = []   # 统计买入信号
    signalSell = []   # 统计卖出信号

    buycutProfitList = []
    sellcutProfitList= []

    # 参数列表，保存了参数的名称
    paramList = ['name',
                 'className',
                 'author',
                 'vtSymbol',
                 'kkLength',
                 'kkDevUp',
                 'kkDevDown',
                 'thresholdRatio',
                 'trailingPrcnt',
                 'fixedCutLoss']

    # 变量列表，保存了变量的名称
    varList = ['inited',
               'trading',
               'pos',
               'kkMid',
               'kkUp',
               'kkDown',
               'openRatioModi',
               'monitoringVolume',
               'longStop',
               'shortStop',
               'longCycleTradingFlag']

    # ----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        """Constructor"""
        super(MultiCycleStrategy, self).__init__(ctaEngine, setting)

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
        # 聚合为1分钟K线
        tickMinute = tick.datetime.minute

        if tickMinute != self.barMinute:
            if self.bar and self.trueCalVolFlag:  # bar线计算正确才运行(bar线必须要运行一次else)
                self.onBar(self.bar)

            bar = VtBarData()
            bar.vtSymbol = tick.vtSymbol
            bar.symbol = tick.symbol
            bar.exchange = tick.exchange

            bar.open = tick.lastPrice
            bar.high = tick.lastPrice
            bar.low = tick.lastPrice
            bar.close = tick.lastPrice
            #trueVolume = tick.volume - self.preTickVolume  # 真实成交量,CTP推送的成交量是累计成交量
            #self.preTickVolume = tick.volume  # 更新数据
            #bar.volume = trueVolume
            bar.volume = tick.volume
            self.preBarVolume = tick.volume
            bar.openInterest = tick.openInterest

            bar.date = tick.date
            bar.time = tick.time
            bar.datetime = tick.datetime  # K线的时间设为第一个Tick的时间

            self.bar = bar  # 这种写法为了减少一层访问，加快速度
            self.barMinute = tickMinute  # 更新当前的分钟
        else:  # 否则继续累加新的K线
            bar = self.bar  # 写法同样为了加快速度

            bar.high = max(bar.high, tick.lastPrice)
            bar.low = min(bar.low, tick.lastPrice)
            bar.close = tick.lastPrice
            #trueVolume = tick.volume - self.preTickVolume  # 真实成交量
            #self.preTickVolume = tick.volume  # 更新数据
            bar.volume = tick.volume - self.preBarVolume  # 每个新到tick的成交量减去此bar线成交量的初始值
            bar.openInterest = tick.openInterest
            self.monitoringVolume = bar.volume
            self.trueCalVolFlag = True

    # ----------------------------------------------------------------------
    def onBar(self, bar):
        """收到Bar推送（必须由用户继承实现）"""
        # 如果当前是一个5分钟走完
        if (bar.datetime.minute+1) % self.barBin == 0:

            # 如果已经有聚合5分钟K线
            if self.fiveBar:
                # 将最新分钟的数据更新到目前5分钟线中
                fiveBar = self.fiveBar
                fiveBar.high = max(fiveBar.high, bar.high)
                fiveBar.low = min(fiveBar.low, bar.low)
                fiveBar.close = bar.close
                fiveBar.volume += bar.volume
                fiveBar.openInterest = bar.openInterest

                fiveBar.volumeList.append(bar.volume)  # 记录每个bar的成交量（此处为1分钟）
                fiveBar.openInterestList.append(bar.openInterest)  # 记录每个bar的持仓数据

                # print fiveBar.volume

                self.preBarOpenInterest = bar.openInterest  # 记录前一个Bar线的持仓数据

                #  推送5分钟线数据
                self.onFiveBar(fiveBar)

                # 清空5分钟线数据缓存
                #print preBarOpenInterest
                self.fiveBar = None
        else:
            # 如果没有缓存则新建
            if not self.fiveBar:
                fiveBar = VtBarData()
                fiveBar.volumeList = []   # 创建成交量List
                try:
                    #print 'read last openInterest data'
                    fiveBar.openInterestList = [self.preBarOpenInterest]    # 创建持仓量List
                except:
                    fiveBar.openInterestList = []  # 创建持仓量List

                fiveBar.vtSymbol = bar.vtSymbol
                fiveBar.symbol = bar.symbol
                fiveBar.exchange = bar.exchange

                fiveBar.open = bar.open
                fiveBar.high = bar.high
                fiveBar.low = bar.low
                fiveBar.close = bar.close
                fiveBar.volume = bar.volume
                fiveBar.openInterest = bar.openInterest

                fiveBar.volumeList.append(bar.volume)   # 记录每个bar的成交量（此处为1分钟）
                fiveBar.openInterestList.append(bar.openInterest)  # 记录每个bar的持仓数据



                fiveBar.date = bar.date
                fiveBar.time = bar.time
                fiveBar.datetime = bar.datetime



                self.fiveBar = fiveBar
            else:
                fiveBar = self.fiveBar
                fiveBar.high = max(fiveBar.high, bar.high)
                fiveBar.low = min(fiveBar.low, bar.low)
                fiveBar.close = bar.close
                fiveBar.volume += bar.volume
                fiveBar.openInterest = bar.openInterest

                fiveBar.volumeList.append(bar.volume)  # 记录每个bar的成交量（此处为1分钟）
                fiveBar.openInterestList.append(bar.openInterest)  # 记录每个bar的持仓数据


    # ----------------------------------------------------------------------
    def onFiveBar(self, bar):
        """收到5分钟K线"""
        # 撤销之前发出的尚未成交的委托（包括限价单和停止单）
        for orderID in self.orderList:
            self.cancelOrder(orderID)
        #print bar.openInterestList
        #print bar.datetime.minute
        # 如果当前是一个15分钟走完
        if (bar.datetime.minute + 1 * self.barBin) % self.barLongBin == 0:
            # 如果已经有聚合5分钟K线
            if self.longCycleBar:
                # 将最新分钟的数据更新到目前5分钟线中
                longCycleBar = self.longCycleBar
                longCycleBar.high = max(longCycleBar.high, bar.high)
                longCycleBar.low = min(longCycleBar.low, bar.low)
                longCycleBar.close = bar.close
                longCycleBar.volume += bar.volume
                longCycleBar.openInterest = bar.openInterest

                #  推送5分钟线数据
                self.onLongCycle(longCycleBar)

                # 清空5分钟线数据缓存
                # print preBarOpenInterest
                self.longCycleBar = None
        else:
            # 如果没有缓存则新建
            if not self.longCycleBar:
                longCycleBar = VtBarData()
                longCycleBar.vtSymbol = bar.vtSymbol
                longCycleBar.symbol = bar.symbol
                longCycleBar.exchange = bar.exchange

                longCycleBar.open = bar.open
                longCycleBar.high = bar.high
                longCycleBar.low = bar.low
                longCycleBar.close = bar.close
                longCycleBar.volume = bar.volume
                longCycleBar.openInterest = bar.openInterest

                longCycleBar.date = bar.date
                longCycleBar.time = bar.time
                longCycleBar.datetime = bar.datetime

                self.longCycleBar = longCycleBar
            else:
                longCycleBar = self.longCycleBar
                longCycleBar.high = max(longCycleBar.high, bar.high)
                longCycleBar.low = min(longCycleBar.low, bar.low)
                longCycleBar.close = bar.close
                longCycleBar.volume += bar.volume
                longCycleBar.openInterest = bar.openInterest

        vArray1min = np.array(bar.volumeList)

        oArray1min = np.array(bar.openInterestList)

        barOpenRatioModi = ((np.sqrt(vArray1min) / np.sqrt(vArray1min).sum()) * ((oArray1min[1:] - \
                                                                                oArray1min[:-1]) / vArray1min)).mean()
        #print barOpenRatioModi
        #print 'Volume Array:', vArray1min, '\n', 'OpenInterestArray:', oArray1min,'\n','OpenRatioMOdi:',barOpenRatioModi


        print 'Long cycle:',self.longCycleTradingFlag
        self.orderList = []

        # 保存K线数据
        self.closeArray[0:self.bufferSize - 1] = self.closeArray[1:self.bufferSize]
        self.highArray[0:self.bufferSize - 1] = self.highArray[1:self.bufferSize]
        self.lowArray[0:self.bufferSize - 1] = self.lowArray[1:self.bufferSize]
        self.volumeArray[0:self.bufferSize - 1] = self.volumeArray[1:self.bufferSize]
        self.openInterestArray[0:self.bufferSize - 1] = self.openInterestArray[1:self.bufferSize]
        self.openRatioModiArray[0:self.bufferSize - 1] = self.openRatioModiArray[1:self.bufferSize]

        self.closeArray[-1] = bar.close
        self.highArray[-1] = bar.high
        self.lowArray[-1] = bar.low
        self.volumeArray[-1] = bar.volume
        self.openInterestArray[-1] = bar.openInterest  # 持仓量

        self.openRatioModiArray[-1] = barOpenRatioModi  # 开仓比例
        #print self.volumeArray
        #print self.openInterestArray

        self.bufferCount += 1
        if self.bufferCount < self.bufferSize:
            return

        # 计算指标数值
        self.atrValue = talib.ATR(self.highArray,
                                  self.lowArray,
                                  self.closeArray,
                                  self.kkLength)[-1]
        self.kkMid = talib.MA(self.closeArray, self.kkLength)[-1]
        self.kkUp = self.kkMid + self.atrValue * self.kkDevUp
        self.kkDown = self.kkMid - self.atrValue * self.kkDevDown

        #self.obvArray = talib.OBV(self.closeArray, self.volumeArray)

        #self.shortMA = talib.MA(self.closeArray, self.shortMAperiod)
        #self.longMA = talib.MA(self.closeArray, self.longMAperiod)

        self.atrMa = talib.MA(self.atrArray,
                              self.atrMaLength)[-1]


        #print self.vol
        # 量价指标
        #self.changePerVolumeArray = np.abs(self.closeArray[1:] - self.closeArray[:-1]) / self.volumeArray[1:]
        #self.changePerVolumeArray = np.abs(self.highArray - self.lowArray) / self.volumeArray   # 最高价最低价

        # 成交量均值指标
        #self.volumeMa = talib.MA(self.volumeArray, 6)[-1]





        self.openRatio = (self.openInterestArray[-1] - self.openInterestArray[-2]) / self.volumeArray[-1] #

        self.openRatioModi = self.openRatioModiArray[-1]    # 开仓量指标


        self.openRatioArray = (self.openInterestArray[1:] - self.openInterestArray[:-1]) / self.volumeArray[1:]

        #self.openRatioMaArray = talib.EMA(self.openRatioArray, timeperiod=self.openRatioMaLength)
        self.hb = talib.HT_TRENDLINE(self.closeArray)
        #print self.closeArray
        #self.kamaArray = talib.KAMA(self.closeArray, timeperiod=30)
        #print self.openRatio
        #print self.kamaArray [-1],self.kamaArray [-2]



        #kdjLongCondition = slowk[-1] > slowd[-1] and slowk[-2] < slowd[-2]
        #kdjShortCondition = slowk[-1] < slowd[-1] and  slowk[-2] > slowd[-2]

        conditionKKBuy = self.closeArray[-1] > self.kkUp
        conditionKKSell = self.closeArray[-1] < self.kkDown

        #conditionImpulseBuy = self.changePerVolumeArray[-1] > talib.MA(self.changePerVolumeArray, 6)[-1]
        #conditionVolume = self.volumeArray[-1] > self.volumeMa   # 成交量指标
        conditionHBBuy = self.closeArray[-1] > self.hb[-1] and self.closeArray[-2] < self.hb[-2]

        conditionHBSell = self.closeArray[-1] < self.hb[-1] and self.closeArray[-2] > self.hb[-2]
        #conditionOpenRatioBuy = self.openRatio > self.thresholdRatio
        #conditionOpenRatioSell = self.openRatio > self.thresholdRatio + 0.015
        #conditionkamabuy = (self.kamaArray[-1] >= self.kamaArray[-2] >= self.kamaArray[-3])
        #conditionkamasell = (self.kamaArray[-1] <= self.kamaArray[-2] <= self.kamaArray[-3])

        conditionOpenRatioModiBuy = self.openRatioModi > 0.022
        conditionOpenRatioModiSell = self.openRatioModi > 0.026  # 最好0.026


        #conditionOpenRatio = self.openRatioMaArray[-1] > self.openRatioMaArray[-2] and \
         #                  self.openRatioMaArray[-1] > 0.095

        # 保存信号
        if conditionHBBuy and conditionOpenRatioModiBuy:
            self.signalBuy.append(bar.datetime)
        elif conditionHBSell and conditionOpenRatioModiSell:
            self.signalSell.append(bar.datetime)


        # 判断是否要进行交易

        # 当前无仓位，
        if self.pos == 0:
            #print len(self.buyCost)
            #self.svdArrayShort = getSVD(self.closeArray, self.ShapeNum, self.SVDShort)
            #self.svdArrayLong = getSVD(self.closeArray, self.ShapeNum, self.SVDLong)


            self.intraTradeHigh = bar.high
            self.intraTradeLow = bar.low
            if conditionKKBuy and conditionOpenRatioModiBuy and self.longCycleTradingFlag == 1:
                self.buy(bar.close + 5, self.fixedSize)
                self.buyCost.append(bar.close + 5)

            elif conditionKKSell and conditionOpenRatioModiSell and self.longCycleTradingFlag == -1:
                self.short(bar.close - 5, self.fixedSize)
                self.shortCost.append(bar.close - 5)

        # 持有多头仓位
        elif self.pos > 0:
            self.intraTradeHigh = max(self.intraTradeHigh, bar.high)
            self.intraTradeLow = bar.low

            self.longStop = self.intraTradeHigh * (1 - self.trailingPrcnt / 100)
            orderID = self.sell(self.longStop,
                            abs(self.pos), stop=True)
            self.buycutProfitList.append(orderID)
            self.writeCtaLog(u'多头止损价格：' + str(self.longStop))
            self.orderList.append(orderID)

        # 持有空头仓位
        elif self.pos < 0:
            self.intraTradeHigh = bar.high
            self.intraTradeLow = min(self.intraTradeLow, bar.low)

            self.shortStop = self.intraTradeLow * (1 + self.trailingPrcnt / 100)
            orderID = self.cover(self.shortStop,
                                 abs(self.pos), stop=True)
            self.sellcutProfitList.append(orderID)
            self.writeCtaLog(u'空头头止损价格：' + str(self.shortStop))
            self.orderList.append(orderID)

        # 发出状态更新事件
        self.putEvent()

    # ----------------------------------------------------------------------
    def onLongCycle(self,bar):

        #print 'cycletime:', bar.datetime
        #print bar.datetime
        self.longCycleCloseArray[0:self.longCycleBufferSize - 1] = self.longCycleCloseArray[1:self.longCycleBufferSize]
        self.longCycleHighArray[0:self.longCycleBufferSize - 1] = self.longCycleHighArray[1:self.longCycleBufferSize]
        self.longCycleLowArray[0:self.longCycleBufferSize - 1] = self.longCycleLowArray[1:self.longCycleBufferSize]
        self.longCycleVolumeArray[0:self.longCycleBufferSize - 1] = self.longCycleVolumeArray[1:self.longCycleBufferSize]

        self.longCycleCloseArray[-1] = bar.close
        self.longCycleHighArray[-1] = bar.high
        self.longCycleLowArray[-1] = bar.low
        self.longCycleVolumeArray[-1] = bar.volume

        alpha = 0.3  # 5分钟线取0.3最佳
        alphatilde = 2 / (12+1)

        LLTShort = (alpha - (alpha**2)/4) * self.longCycleCloseArray[-1] + (alpha**2) / 2 * self.longCycleCloseArray[-2] -\
              (alpha - 3 * alpha ** 2 / 4) * self.longCycleCloseArray[-3] + 2 * (1 - alpha) * self.longCycleLLTArrayShort[-1] -\
              (1 - alpha ** 2) * self.longCycleLLTArrayShort[-2]
        self.longCycleLLTArrayShort[0:self.longCycleBufferSize - 1] = self.longCycleLLTArrayShort[1:self.longCycleBufferSize]
        self.longCycleLLTArrayShort[-1] = LLTShort

        #LLTLong = (alphatilde - (alphatilde ** 2) / 4) * self.longCycleCloseArray[-1] + alphatilde ** 2 / 2 * \
         #                                                                      self.longCycleCloseArray[-2] - \
          #         (alphatilde - 3 * alphatilde ** 2 / 4) * self.longCycleCloseArray[-3] + 2 * (1 - alphatilde) * \
           #                                                                      self.longCycleLLTArray[-1] - \
            #       (1 - alphatilde ** 2) * self.longCycleLLTArray[-2]
        #self.longCycleLLTArray[0:self.longCycleBufferSize - 1] = self.longCycleLLTArray[1:self.longCycleBufferSize]
        #self.longCycleLLTArray[-1] = LLTLong

        #print 'LLTShort:', self.longCycleLLTArrayShort
        #print 'LLTLong:', self.longCycleLLTArray

        self.longCycleBufferCount += 1
        if self.longCycleBufferCount < self.longCycleBufferSize:
            return

        self.longCycleMAlong = talib.MA(self.longCycleCloseArray, self.longMAperiod)
        self.longCycleMAshort = talib.MA(self.longCycleCloseArray, self.shortMAperiod)

        maLongCondition = self.longCycleMAshort[-1] > self.longCycleMAlong[-1]
        slowk, slowd = talib.STOCH(self.longCycleHighArray, self.longCycleLowArray,
                                  self.longCycleCloseArray, fastk_period=5, slowk_period=3, slowk_matype=0, slowd_period=3, slowd_matype=0)
        fastk, fastd = talib.STOCHF(self.longCycleHighArray, self.longCycleLowArray,
                                    self.longCycleCloseArray, fastk_period=5, fastd_period=3, fastd_matype=0)
        kdjLongCondition = slowk[-1] > slowd[-1]
        kdjShortCondition = slowk[-1] < slowd[-1]

        lltLongCondition = self.longCycleLLTArrayShort[-1] > self.longCycleLLTArrayShort[-2]
        lltShortCondition = self.longCycleLLTArrayShort[-1] < self.longCycleLLTArrayShort[-2]
        #lltLongCondition = self.longCycleLLTArrayShort[-1] > self.longCycleLLTArray[-1]
        #lltShortCondition = self.longCycleLLTArrayShort[-1] < self.longCycleLLTArray[-1]


        ta_adx = talib.ADX(self.longCycleHighArray, self.longCycleLowArray, self.longCycleCloseArray, 14)
        ta_ndi = talib.MINUS_DI(self.longCycleHighArray, self.longCycleLowArray, self.longCycleCloseArray, 14)
        ta_pdi = talib.PLUS_DI(self.longCycleHighArray, self.longCycleLowArray, self.longCycleCloseArray, 14)
        taLongCondition = ta_adx[-1] > 25
        diLongCondition = ta_pdi[-1] > ta_ndi[-1]
        diShortCondition = ta_pdi[-1] < ta_ndi[-1]
        #maLongCondition = (self.longCycleMAshort[-2:] > self.longCycleMAlong[-2:]).all()
        #maShortCondition = (self.longCycleMAshort[-2:] < self.longCycleMAlong[-2:]).all()
        #self.MACD = talib.MACD(self.longCycleCloseArray,fastperiod=self.shortMAperiod,slowperiod=self.longMAperiod,signalperiod=9)
        #print self.MACD[-1]
        #MACDLongCondition = self.MACD[0][-1] > self.MACD[-1][-1]
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

    # ----------------------------------------------------------------------
    def onTrade(self, trade):
        """
        # 多头开仓成交后，撤消空头委托
        if self.pos > 0:
            self.cancelOrder(self.shortOrderID)
            if self.buyOrderID in self.orderList:
                self.orderList.remove(self.buyOrderID)
            if self.shortOrderID in self.orderList:
                self.orderList.remove(self.shortOrderID)
        # 反之同样
        elif self.pos < 0:
            self.cancelOrder(self.buyOrderID)
            if self.buyOrderID in self.orderList:
                self.orderList.remove(self.buyOrderID)
            if self.shortOrderID in self.orderList:
                self.orderList.remove(self.shortOrderID)

        # 发出状态更新事件"""
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
    engine = BacktestingEngine()

    # 设置引擎的回测模式为K线
    engine.setBacktestingMode(engine.BAR_MODE)

    # 设置回测用的数据起始日期
    engine.setStartDate('20170601')
    engine.setEndDate('20171201')

    # 设置产品相关参数
    engine.setInitialCapital(20000)  # 初始资金10w
    engine.setLeverage(1)  # 1倍杠杆
    engine.setSlippage(1)  # 股指1跳
    engine.setRate(3 / 10000)  # 万3
    engine.setSize(10)  # 股指合约大小
    engine.setPriceTick(1)  # 股指最小价格变动 0.2
    engine.setpnlPctToggle(True)  # 百分比显示开关
    #engine.writeTrade = True
    # 设置使用的历史数据库
    #engine.setDatabase('FutureData_Index', 'rb000_1min_modi')
    engine.setDatabase('FutureData_Sequence', 'rb888_1min_modi')


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
    engine.initStrategy(MultiCycleStrategy, d)

    # 开始跑回测
    engine.runBacktesting()

    # 显示回测结果
    print u'多仓信号数量为：%d' % len(MultiCycleStrategy.signalBuy)
    print u'空仓信号数量为：%d' % len(MultiCycleStrategy.signalSell)
    print u'多仓止盈止损信号数量为：%d' % len(MultiCycleStrategy.buycutProfitList)
    print u'空仓止盈止损信号数量为：%d' % len(MultiCycleStrategy.sellcutProfitList)


    engine.showBacktestingResult()

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