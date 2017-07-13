#!/Tsan/bin/python
# -*- coding: utf-8 -*-

# Libraries To Use
from __future__ import division
from CloudQuant import MiniSimulator
import numpy as np
import pandas as pd
import statsmodels.api as sm
import scipy.stats
import os
from sklearn import linear_model
from datetime import datetime,time,date
import matplotlib.pyplot as plt
import seaborn as sns
import time

# Import My own library for factor testing
from SingleFactorTest import factorFilterFunctions as ff
#from config import *

def tbDataToVnpy(filePath,fileName,savePath,newName):
    '''Adjust format of data downloaded from TradeBlazer to Vnpy data format.
    Input:
    filePath: String.Old path for original csv data.
    fileName: String.Old file name for original csv data.
    savePath: String.new path for adjusted csv data.
    newName: String.new Name for adjusted csv data.'''
    data = pd.read_csv(filePath+fileName,infer_datetime_format=True,header=None,names = ['Open', 'High', 'Low', 'Close','TotalVolume','Position'])
    data.index = data.index.map(lambda x : pd.to_datetime(x))
    data['Time'] = data.index.map(lambda x : x.time)
    data.index = data.index.map(lambda x : x.date)
    data.index.name = 'Date'
    data.drop('Position',axis=1,inplace = True)
    data.to_csv(savePath+newName,na_rep='NaN',date_format='%Y%m%d')
    return data

if __name__ =='__main__':
    old_path = 'C:/Users/LZJF_02/Desktop/original_data/'
    new_path = 'C:/Users/LZJF_02/Desktop/modified_data/'
    filename = 'rb000_1min.csv'
    newname = 'rb000_1min_modi.csv'
    #c = tbDataToVnpy(old_path, filename, new_path, newname)