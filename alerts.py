#!/usr/bin/env python

"""
collection of functions which trigger market alerts
"""

import matplotlib.dates as dates
import mdcache
import sto
import ystockquote
import datetime
from decimal import *

D = Decimal


def sto_limits (symbols=None, debug=False):
	"""
	alerts based on a high (80+) or low (20-) stochastic value (10-day period)
	shows if price at last close was either strong or weak relative to all price movement over the period
	"""
	if symbols is None:
		symbols = mdcache.entries()
	
	res = {
			'strong': 	[],
			'weak':		[],
			'neutral':	[]
		}

	todaynum = dates.date2num(datetime.date.today())

	for symbol in symbols:
		data = mdcache.mdcache(symbol).get_data()[-10:]

		if data[-1][0] < todaynum:
			if debug:
				print("%s: adding current spot" % symbol)

			try:
				spot = D(ystockquote.get_price(symbol))
			except (IOError, InvalidOperation):
				print("Error getting %s spot, skipping" % symbol)
				continue

			data += [[todaynum, spot, spot, spot, spot, 0]]

		value = sto.sto(data)[-1][0]

		if value >= 80:
			res['strong'] += [(symbol, value)]
		elif value <= 20:
			res['weak'] += [(symbol, value)]
		else:
			res['neutral'] += [(symbol, value)]
	
	if debug:
		for k in res.keys():
			print("%s:" % k)
			for (s,v) in res[k]:
				print("\t%7s: %0.2f" % (s, v))
			print("\n")
	
	return(res)

