#!/usr/bin/env python

from decimal import *

D = Decimal

"""
	stochastic oscillator

	according to http://stockcharts.com/school/doku.php?id=chart_school:technical_indicators:stochastic_oscillato ...

	%K = (Current Close - Lowest Low)/(Highest High - Lowest Low) * 100
	%D = 3-day SMA of %K
	Lowest Low = lowest low for the look-back period
	Highest High = highest high for the look-back period
	%K is multiplied by 100 to move the decimal point two places
"""


def sto (quotes, period=10):
	"""
	quotes is data as returned from mdcache.get_data()
	i.e. array of (time, open, close, high, low, volume) tuples

	returns list of (%K, %D) tuples
	"""

	if len(quotes) < period:
		period = len(quotes)

	res = []
	lookback = quotes[:period]
	quotes = quotes[period:]

	max_hi  = D(0)
	min_low = None
	sma = []

	# initial values from priming the lookback period
	for (time, open, close, hi, low, volume) in lookback:
		if hi > max_hi:
			max_hi = D(hi)
		if min_low is None:
			min_low = D(low)
		elif low < min_low:
			min_low = D(low)

		if max_hi == min_low:
			# div0
			continue
		val = (close - min_low) / (max_hi - min_low) * 100
		sma += [val]
		if len(sma) > 3:
			sma = sma[-3:]

		res += [ (val, sum(sma)/len(sma)) ]


	def compute (lookback):
		max_hi  = D(0)
		min_low = None
		last_close = D(0)
		for (time, open, close, hi, low, volume) in lookback:
			last_close = close
			if hi > max_hi:
				max_hi = hi
			if min_low is None:
				min_low = D(low)
			elif low < min_low:
				min_low = D(low)

		if max_hi == min_low:
			return D(0)

		val = (last_close - min_low) / (max_hi - min_low) * 100
		return(val)

	
	# lookback primed, let's roll
	for q in quotes:
		lookback = lookback[1:] + [q]

		val = compute(lookback)
		sma += [val]
		if len(sma) > 3:
			sma = sma[-3:]

		res += [ (val, sum(sma)/len(sma)) ]
	
	return res

