#!/usr/bin/env python

import os, datetime, json, time, traceback
import urllib2	# for exceptions
from matplotlib.finance import quotes_historical_yahoo
import matplotlib.dates as dates

from decimal import *

D = Decimal


cachedir = '/var/tmp/mdcache'


class DataError (Exception):
	pass


def entries ():
	"""
	returns a list of cached symbols
	"""
	return(os.listdir(cachedir))


class mdcache (object):
	"""
	Data abstraction layer for historical HLOC data
	maintains a cache of symbol data retrieved from yahoo
	subsequent calls fill in any gaps from the cache if needed and return that
	"""

	if not os.path.exists(cachedir):
		os.system("mkdir -p %s" % cachedir)
	
	assert(os.path.exists(cachedir))

	symbol = None


	def __init__ (self, symbol, date_from=None, date_to=None):
		assert(symbol is not None)

		self.symbol = symbol

		today = datetime.date.today()

		if date_to is None:
			date_to = today

		self.date_to = dates.date2num(date_to)

		if date_from is None:
			# 1 yr ago by default
			date_from = today - datetime.timedelta(days=365)
		self.date_from = dates.date2num(date_from)

		symfname = os.path.join(cachedir, symbol.upper())

		if os.path.exists(symfname):
			f = open(symfname)

			try:
				data = json.loads(f.read())
			except ValueError, e:
				# No JSON object could be decoded
				print("MDERROR -- Recovering by Invalidating %s: %s" % (symbol, e))
				f.close()
				os.unlink(symfname)
				# return a reinstantiated object that takes the new-symbol code path in the ctor
				return(mdcache.__init__(self, symbol, date_from=date_from, date_to=date_to))

			f.close()

			extend_early = False
			extend_late  = False
			refresh_from = data['hloc'][0][0]
			refresh_to   = data['hloc'][-1][0]
			if self.date_from < refresh_from:
				extend_early = True
				refresh_from = self.date_from
				#print("1refresh_from: %s" % refresh_from)
			else:
				# don't need earlier data.  If we need any data it will be after the high date
				refresh_from = data['hloc'][-1][0]
				#print("2refresh_from: %s" % refresh_from)

			if self.date_to > refresh_to:
				extend_late = True
				refresh_to = self.date_to
				#print("1refresh_to: %s" % refresh_to)
			else:
				# don't need later data.  If we need any data it will be from before the low date
				refresh_to = data['hloc'][0][0]
				#print("2refresh_to: %s" % refresh_to)

			if not(extend_early or extend_late):
				# it's all in the cache
				self.data = data
				#print("it's all in the cache")
				return

			#print("fetching from %s to %s" % (refresh_from, refresh_to))

			try:
				quotes = self.get_data_from_yahoo(date_from=refresh_from, date_to=refresh_to)
			except urllib2.URLError:
				# network down?
				print("WARNING: cannot retrieve quotes.  Cached data still available")
				quotes = None

			#print("quotes: %s" % quotes)

			if quotes:
				if extend_early and extend_late:
					# total rewrite
					data['hloc'] = quotes
					data['date_low'] = refresh_from
					data['date_high'] = refresh_to
				elif extend_early:
					# prepend but do not duplicate
					if quotes[-1][0] == data['hloc'][0][0]:
						quotes = quotes[:-1]
					data['hloc'] = quotes + data['hloc']
					data['date_low'] = refresh_from
				elif extend_late:
					# append but do not duplicate
					if quotes is not None:	# this is often None during early am for current day
						if quotes[0][0] == data['hloc'][-1][0]:
							quotes = quotes[1:]
						data['hloc'] += quotes
						data['date_high'] = refresh_to

		else:
			# new symbol in cache
			try:
				quotes = self.get_data_from_yahoo(self.date_from, self.date_to)
			except urllib2.URLError:
				# network down?
				print("ERROR: cannot retrieve quotes, and no relevant data in cache")
				raise DataError("Network down?")

			data = {}
			data['date_low']  = self.date_from
			data['date_high'] = self.date_to
			data['hloc']      = quotes

		# stash the cache
		self.data = data

		# write new cache file
		if data['hloc']:
			f = open(symfname, 'w')
			f.write(json.dumps(data))
			f.close()


	def get_data_from_yahoo (self, date_from, date_to):
		"""
		date args are already nums from dates.date2num by the time we get here
		"""

		date_from = dates.num2date(date_from)
		date_to = dates.num2date(date_to)
		quotes = []

		strikes = 0

		while strikes < 10:
			try:
				quotes = quotes_historical_yahoo(self.symbol, date_from, date_to)
				break
			except (urllib2.HTTPError, urllib2.URLError), err:
				# friendly way of saying input does not compute
				# seen intermittent 404s from yahoo before so this is all in a retry loop now
				strikes += 1

		if strikes:
			print("History data retrieval failed %d times for %s" % (strikes, self.symbol))
			traceback.print_exc(err)

		return quotes
	

	def get_data (self):
		"""
		returns array of (time, open, close, high, low, ...) tuples
		"""

		res = []

		for d in self.data['hloc']:
			# time, open, close, high, low, volume
			try:
				(t, o, c, h, l, v) = d
			except Exception, e:
				print("%s: %s" % (e, d))
				raise
			if t >= self.date_from and t <= self.date_to:
				o = D("%.2f" % o)
				c = D("%.2f" % c)
				h = D("%.2f" % h)
				l = D("%.2f" % l)

				res += [(t, o, c, h, l, v)]

		return res

