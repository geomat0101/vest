#!/usr/bin/env python

import os, datetime
from math import sqrt
import numpy as np
import matplotlib.pyplot as plt 
import matplotlib.dates as dates
from xact import xact
from buysell import *
from bunch import Bunch
import commission
from decimal import *
from bd import BDQuote

import pprint
pp = pprint.PrettyPrinter(indent=4).pprint

D = Decimal
pennies = D('0.01')

class account (object):
	"""
	a container for transactions in a given asset

	>>> x = account(name="Silver", commission=commission.percent(1))
	>>> x.name
	'Silver'
	>>> x.commission(10, D('10.'))
	Decimal('1.00')

	>>> account()
	Traceback (most recent call last):
	ValueError: name is required
	"""

	# key is attribute name
	# value is tuple of (fmtstring, chartbook_enabled)
	keys = {
		'date': Bunch(fmt='%15s', chartbook=False),
		'qty': Bunch(fmt='%15d', chartbook=False),
		'price': Bunch(fmt='%15.2f', chartbook=False),
		'subtotal': Bunch(fmt='%15.2f', chartbook=False),
		'commission': Bunch(fmt='%15.2f', chartbook=False),
		'net_xact_cost': Bunch(fmt='%15.2f', chartbook=False),
		'position_cost': Bunch(fmt='%15.2f', chartbook=True),
		'position_qty': Bunch(fmt='%15d', chartbook=True),
		'last_buy': Bunch(fmt='%15.2f', chartbook=False),
		'last_sell': Bunch(fmt='%15.2f', chartbook=False),
		'mark_spread': Bunch(fmt='%15.2f', chartbook=False),
		'mark': Bunch(fmt='%15.2f', chartbook=True),
		'marked_value': Bunch(fmt='%15.2f', chartbook=True),
		'dca_max_bid': Bunch(fmt='%15.2f', chartbook=False),
		'dca_min_ask': Bunch(fmt='%15.2f', chartbook=True),
		'dca_spread': Bunch(fmt='%15.2f', chartbook=False),
		'total_shares': Bunch(fmt='%15.3f', chartbook=False),
		'share_price': Bunch(fmt='%15.2f', chartbook=False),
		'paper_profit': Bunch(fmt='%15.2f', chartbook=True),
		'cash': Bunch(fmt='%15.2f', chartbook=True),
		'total_invested': Bunch(fmt='%15.2f', chartbook=True),
		'total_value': Bunch(fmt='%15.2f', chartbook=True),
		'roi': Bunch(fmt='%%%14.2f', chartbook=True),
		'reserve_req': Bunch(fmt='%15.2f', chartbook=False),
	}

	key_order = [
		'date',
		'qty',
		'price',
		'subtotal',
		'commission',
		'net_xact_cost',
		'position_qty',
		'last_buy',
		'last_sell',
		'mark_spread',
		'mark',
		'dca_max_bid',
		'dca_min_ask',
		'dca_spread',
		'total_shares',
		'share_price',
		'position_cost',
		'marked_value',
		'paper_profit',
		'cash',
		'total_invested',
		'total_value',
		'roi',
		'reserve_req',
	]

	def __init__ (self, name=None, units=None, commission=commission.percent(1), liquidate=commission.percent_liquidate(1)):
		"""
		name is a string
		commission is a fn pointer from one of the commission implementations
		default is 1% commission, because that's the one I happen to care about
		"""

		if name is None:
			raise ValueError("name is required")

		self.name = name
		self.units = units
		if units is not None:
			self.fullname = "%s (%s)" % (name, units)
		else:
			self.fullname = name
		self.commission = commission
		self.liquidate = liquidate
		self.active_trades = []
		self.max_active_bid = None
		self.min_active_bid = None
		self.max_active_ask = None
		self.min_active_ask = None

		self.fixed_value = None		# fixed_value override instead of total_value for buy intervals in next_buy_at()
		self.ignore_fixed_value_assertion = False	# this asserts that fixed_value remains greater than the actual value of the account
		self.reserve_req = None		# will be based on fixed_value calculation when applicable, otherwise defaults to that of last xact
		
		self.xacts = []		# main transaction list for the account
	

	def add_xact(self, date=None, qty=0, price=0, split=None):
		if split:
			qty = price = D(0)
		else:
			qty = D(qty)
			price = D(price)
		self.xacts += [ xact(date=date, qty=qty, price=price, commission=self.commission, liquidate=self.liquidate, split=split) ]
		self.calc()
	

	def load_xacts_from_file (self, filename):
		"""
		loads a transaction set from given file.  expected format is something like:
		
		09/26/2010:2:50.00

		i.e. colon-delimited ISO formatted date, quantity, amount

		special records -- if the date field is:
			'TRADE': then the qty and price are added as an active trade rather than
			an account transaction.  These show up as hlines in the account's buysell
			graph instead of on the buy/sell lines.

			'CONFIG': this sets a property for the account.  The next 2 fields should be
			key:value (e.g. CONFIG:fixed_value:6000.).
			Meaningful CONFIG keys:
				fixed_value:<float>
					This uses a fixed value allocation when determining buy points.
					Normally the total_value of the account is used (marked_value + cash).
					This serves as an override -- particularly useful when increasing the amount
					of capital you want allocated to an account.
		"""

		if not os.path.exists(filename):
			raise ValueError("No such file! (%s)" % filename)

#		print "loading %s" % filename
		file = open(filename)
		for line in file.readlines():
			if line.startswith('#'):
				continue
			try:
				(date, qty, price) = line.split(':')
			except ValueError:
				print("Warning: invalid line: '%s'" % line)
				continue
			if date == 'TRADE':
				# active trades in the market
				qty = int(qty)
				price = D(price)
				self.active_trades += [(qty, price)]
				# track min/max open trades
				if qty > 0:
					if price > self.max_active_bid:
						self.max_active_bid = price
					if self.min_active_bid is None or price < self.min_active_bid:
						self.min_active_bid = price
				else:
					if price > self.max_active_ask:
						self.max_active_ask = price
					if self.min_active_ask is None or price < self.min_active_ask:
						self.min_active_ask = price
			elif date == 'CONFIG':
				# account options
				(key, value) = (qty, price)
				if key == 'fixed_value':
					value = D(value)
					self.fixed_value = value
				elif key == 'COMM':
					value = value.rstrip()
					if value == 'ZERO':
						self.commission = commission.pershare(0)
						self.liquidate  = commission.pershare_liquidate(0)
					elif value == 'FID':
						self.commission = commission.fidelity()
						self.liquidate  = commission.fidelity_liquidate()
					else:
						print("%s commission switch to unknown value %s" % (self.name, value))
						
					if self.xacts:
						last_xact = self.xacts[-1]
						last_xact.liquidate = self.liquidate
						last_xact.dca_min_ask = self.liquidate(last_xact.position_cost, last_xact.position_qty)
				else:
					raise ValueError('unknown config key: %s' % key)
			else:
				(month, day, year) = date.split('/')
				split_factor = None
				if qty == "SPLIT":
					split_factor = int(price)
					qty = 0
					price = 0

				args = {
						'date':		datetime.date(int(year), int(month), int(day)),
						'qty':		int(qty),
						'price':	D(price),
						'split':	split_factor
					}
#				pp(args)
				self.add_xact(**args)

		if not self.xacts:
			return
		x = self.xacts[-1]
		if self.fixed_value is not None:
			print("%6s: value: %8.2f cost: %8.2f -- %8.2f of %8.2f available for buys: %0.2f%% invested" %
					(self.name, x.total_value, x.position_cost, self.fixed_value-x.position_cost, self.fixed_value, (100 * x.position_cost / self.fixed_value).quantize(pennies)))
		else:
			print("%6s: value: %8.2f cost: %8.2f" % (self.name, x.total_value, x.position_cost))
		self.reserve_req = x.reserve_req


	def show (self):
		"""
		display transactions
		"""
		for x in self.xacts:
			print("%s" % x)

	
	def chart (self, data="roi", fmt1="b-", fmt2="r*", legend=True, date_from=None, subplot=None, grid=True, extend2today=True, adjust_splits=False):
		"""
		charts data over time using matplotlib
		default is ROI
		"""
		if date_from is not None:
			xacts = [x for x in self.xacts if x.date >= date_from]
		else:
			xacts = self.xacts

		fig = None

		if subplot is None:
			fig = plt.figure()
			ax = fig.add_subplot(111)
		else:
			ax = subplot

		x = []
		y = []
		for a in xacts:
			if adjust_splits and a.split:
				if a.split < 0:
					# reverse split
					y = [ D(z * (-a.split)) for z in y ]
				else:
					y = [ D(z / a.split).quantize(pennies) for z in y ]

				continue

			x += [ dates.date2num(a.date) ]
			y += [ a.__dict__[data] ]

		if len(x) == 0:
			print("Nothing to chart")
			return
		
		num_today = dates.date2num(datetime.date.today())
		if (x[-1] != num_today) and extend2today:
			x += [num_today]
			y += [y[-1]]

		ax.plot_date(x, y, fmt=fmt1, label=data.upper())
		ax.plot_date(x, y, fmt=fmt2)
		ax.grid(grid)
		if legend:
			ax.legend()

		if fig is not None:
			fig.autofmt_xdate()
	

	def chartbook (self, date_from=None, figure=None):
		"""
		charts everything
		"""
		if date_from is None:
			# default to 6 months
			date_from = datetime.date.today() - datetime.timedelta(weeks=24)

		ncharts = len([x for x in self.keys if self.keys[x].chartbook])
		ncharts += 2	# for the buy/sell chart

		# size the grid
		nrows = int(sqrt(ncharts))
		ncols = nrows
		if nrows * ncols < ncharts:
			ncols += 1
			if nrows * ncols < ncharts:
				nrows += 1

#		print("%d charts, %d rows x %d cols" % (ncharts, nrows, ncols))
		if figure is None:
			fig = plt.figure()
		else:
			fig = figure
		chartnum = 0
		for k in self.key_order:
			if not self.keys[k].chartbook:
				continue
			chartnum += 1
			ax = fig.add_subplot(nrows, ncols, chartnum)
			self.chart(k, legend=False, date_from=date_from, subplot=ax)
			plt.title(k.upper())

		chartnum += 1
		ax = fig.add_subplot(nrows, ncols, chartnum)
		self.chart_buysell(date_from=date_from, subplot=ax, volume=False, trades=False)

		chartnum += 1
		ax = fig.add_subplot(nrows, ncols, chartnum)
		self.chart_allocation(subplot=ax)

		fig.suptitle(self.fullname)
		fig.autofmt_xdate()
	

	def chart_allocation (self, subplot=None):
		x = self.xacts[-1]
		subplot.pie([x.paper_profit, x.cash, x.position_cost], labels=["profit", "cash", "cost"])


	def chart_buysell (self, legend=False, date_from=None, date_to=None, subplot=None, volume=True, trades=True, show_dca=True, grid=True, title=True, adjust_splits=False, pnf_graph=None):
		"""
		special chart for buys and sells
		uses last_buy and last_sell for the lines,
		but the points are when the buy/sell occurred
		"""

		def _adjust (xlist, split_factor):
			newlist = []
			for (date, price) in xlist:
				if split_factor < 0:
					# reverse split
					price *= (-split_factor)
				else:
					price /= split_factor

				newlist += [ (date, D(price).quantize(pennies)) ]

			return newlist


		# separate out the buys and sells
		if date_from is None:
			buys  = []
			sells = []
			for a in self.xacts:
				if a.qty > 0:
					buys += [ (a.date, a.price) ]
				elif a.qty < 0:
					sells += [ (a.date, a.price) ]
				elif adjust_splits and a.split:
					# split
					buys  = _adjust(buys, a.split)
					sells = _adjust(sells, a.split)

		else:
			buys  = []
			sells = []
			for a in self.xacts:
				if a.date < date_from:
					continue

				if a.qty > 0:
					buys += [ (a.date, a.price) ]
				elif a.qty < 0:
					sells += [ (a.date, a.price) ]
				elif adjust_splits and a.split:
					# split
					buys  = _adjust(buys, a.split)
					sells = _adjust(sells, a.split)

		xbuy  = []
		ybuy  = []
		for (date, price) in buys:
			# pull the data out of tuples and make lists
			xbuy += [dates.date2num(date)]
			ybuy += [price]

		xsell = []
		ysell = []
		for (date, price) in sells:
			# pull the data out of tuples and make lists
			xsell += [dates.date2num(date)]
			ysell += [price]

		fig = None

		if subplot is None:
			fig = plt.figure()
			ax = fig.add_subplot(111)
		else:
			ax = subplot

		ax.plot_date(xbuy,  ybuy,  fmt="r*")
		ax.plot_date(xsell, ysell, fmt="r*")

		# filter main line
		qtydict  = {}
		if date_from is None:
			datelist = []
			for a in self.xacts:
				dateval = dates.date2num(a.date)
				datelist += [dateval]
				try:
					qtydict[dateval] += a.qty
				except KeyError:
					qtydict[dateval] = a.qty
			lastbuyvals  = []
			lastsellvals = []
			for a in self.xacts:
				if adjust_splits and a.split:
					if a.split < 0:
						# reverse split
						lastbuyvals  = [ D(x * (-a.split)) for x in lastbuyvals ]
						lastsellvals = [ D(x * (-a.split)) for x in lastsellvals ]
					else:
						lastbuyvals  = [ D(x / a.split).quantize(pennies) for x in lastbuyvals ]
						lastsellvals = [ D(x / a.split).quantize(pennies) for x in lastsellvals ]
				else:
					lastbuyvals  += [ a.last_buy ]
					lastsellvals += [ a.last_sell ]
		else:
			datelist = []
			for a in self.xacts:
				if a.date < date_from or (adjust_splits and a.split):
					continue
				dateval = dates.date2num(a.date)
				datelist += [dateval]
				try:
					qtydict[dateval] += a.qty
				except KeyError:
					qtydict[dateval] = a.qty
			lastbuyvals  = []
			lastsellvals = []
			for a in self.xacts:
				if a.date < date_from:
					continue
				if adjust_splits and a.split:
					if a.split < 0:
						# reverse split
						lastbuyvals  = [ D(x * (-a.split)) for x in lastbuyvals ]
						lastsellvals = [ D(x * (-a.split)) for x in lastsellvals ]
					else:
						lastbuyvals  = [ D(x / a.split).quantize(pennies) for x in lastbuyvals ]
						lastsellvals = [ D(x / a.split).quantize(pennies) for x in lastsellvals ]
				else:
					lastbuyvals  += [ a.last_buy ]
					lastsellvals += [ a.last_sell ]


		if self.name in ['Silver', 'Gold']:
#			bd = BDQuote(self.name)
#			bid_price = bd.getBid()
#			ask_price = bd.getAsk()
#			ax.fill_between([earliest, latest], bid_price, ask_price, facecolor='0.9', edgecolor='0.9')
                    pass
		elif pnf_graph:
			# fill in continuation-to-reversal spread
			fillcolor = '#c0ffc0'
			if pnf_graph.columns[-1].marker == 'O':
				fillcolor = '#ffc0c0'
			ax.fill_between([date_from, date_to], float(pnf_graph.get_continuation()), float(pnf_graph.get_reversal()), facecolor=fillcolor, edgecolor='0.9')


		if len(datelist) == 0:
			return

		# only extend the buy/sell last value lines out to today
		# if the position qty is > 0 (i.e. hasn't totally sold out)
		extend2today = False
		if self.xacts[-1].position_qty > 0:
			extend2today = True

		num_today = dates.date2num(datetime.date.today())
		if (datelist[-1] != num_today) and extend2today:
			datelist += [num_today]
			lastbuyvals += [lastbuyvals[-1]]
			lastsellvals += [lastsellvals[-1]]

		earliest = datelist[0]
		latest = datelist[-1]

		ax.plot_date(datelist, lastbuyvals,  fmt="b-", label="Buys")
		ax.plot_date(datelist, lastsellvals, fmt="g-", label="Sells")

		if trades:
			first_bid = first_ask = True
			for (qty, price) in self.active_trades:
				label = None
				if int(qty) < 0:
					curr_fmt = 'g-.'
					if first_ask:
						first_ask = False
						label = 'Asks'
				else:
					curr_fmt = 'c-.'
					if first_bid:
						first_bid = False
						label = 'Bids'
				ax.plot_date([earliest, latest], [price, price], fmt=curr_fmt, label=label)

		if show_dca:
			dca = self.xacts[-1].dca_min_ask
			if dca > 0:
				ax.plot_date([earliest, latest], [dca, dca], fmt='m-.', label="DCA")

		if volume:
			ax2 = ax.twinx()
			ax2.plot_date([earliest, latest], [0,0], fmt="k:")
			for x in qtydict:
				ax2.vlines(x, 0, qtydict[x], linestyle="dashed")

		self.chart("mark", subplot=ax, legend=False, fmt1="r--", fmt2="r+", date_from=date_from, extend2today=extend2today, adjust_splits=adjust_splits)

		if fig is not None:
			fig.autofmt_xdate()
	
		if title:
			plt.title("Transaction History: %s" % self.fullname)
		ax.grid(grid)
		if legend:
			ax.legend()

		# 30 day rule vlines
		idx = -1
		last_xact = self.xacts[idx]
		while last_xact.qty == 0:
			# skip cash only xacts, splits
			idx -= 1
			last_xact = self.xacts[idx]

		if last_xact.date >= date_from:
			if last_xact.qty < 0:
				color = 'green'
			else:
				color = 'blue'
			ax.axvline(x=dates.date2num(last_xact.date), color=color)

			if last_xact.qty < 0:
				color = 'blue'
			else:
				color = 'green'
			ax.axvline(x=dates.date2num(last_xact.date + datetime.timedelta(days=30)), color=color)


	def table (self):
		"""
		table dump of xact data
		"""
		header = "%10s %5s %10s %10s %10s %10s %5s %10s %10s %10s %10s %10s %10s %7s" % (
			"Date", "Qty", "Price", "Comm.", "Net Cost", "Pos. Cost", "P.Qty", "Mark", "DCA", "Value", "Cash", "TtlValue", "Invested", "ROI")

		counter = 0
		for x in self.xacts:
			if counter % 25 == 0:
				print("\n%s\n" % header)
			counter += 1
			print("%10s %5d %10.2f %10.2f %10.2f %10.2f %5d %10.2f %10.2f %10.2f %10.2f %10.2f %10.2f %%%6.2f" %
				(x.date, x.qty, x.price, x.commission, x.net_xact_cost,
				x.position_cost, x.position_qty, x.mark, x.dca_min_ask, x.marked_value, x.cash, x.total_value, x.total_invested, x.roi))
	

	def print_detail (self, target_xact):
		for k in self.key_order:
			fmt = "%20s: " + self.keys[k].fmt
			if k == 'reserve_req':
				v = self.reserve_req
			else:
				v = target_xact.__dict__[k]
			print(fmt % (k, v))
			

	def detail (self, date=None, quiet=False):
		"""
		show xact detail with computed info
		returns xact
		suppress output w/ quiet=True
		"""

		if not self.xacts:
			return
		idx = -1
		target_xact = self.xacts[idx]
		while target_xact.qty == 0:
			# skip cash only xacts
			idx -= 1
			target_xact = self.xacts[idx]

		if date is not None:
			for x in self.xacts:
				if x.date <= date:
					target_xact = x
					continue
				break

		if not quiet:
			self.print_detail(target_xact)

		return(target_xact)
	

	def diff (self, date=None, date2=None, quiet=False):
		"""
		meant for things like quarterly / annual reporting (and *TD)
		"""
		if not self.xacts:
			return(None, None)

		xact1 = self.detail(date=date, quiet=True)
		xact2 = self.detail(date=date2, quiet=True)

		if xact2.date < date and xact2.position_qty == 0:
			return(None, None)

		if xact2.date > date2:
			xact2 = None

		if xact1.date > date:
			xact1 = None

		if xact1 is None and xact2 is None:
			return(None, None)

		# diffable fields
		fields = ['date', 'position_qty', 'dca_min_ask', 'share_price',
					'position_cost', 'marked_value', 'paper_profit', 'cash',
					'total_invested', 'total_value']

		for x in fields:
			subfmt = self.keys[x].fmt
			fmt = "%%20s: %s %s %s" % (subfmt, subfmt, subfmt)
			if xact2 is not None:
				val2 = xact2.__dict__[x]
				if xact1 is None:
					if type(val2) == datetime.date:
						val1 = date
					else:
						val1 = 0
				else:
					val1 = xact1.__dict__[x]
			else:
				val1 = xact1.__dict__[x]
				if type(val1) == datetime.date:
					val2 = date
				else:
					val2 = 0
			diff = val2 - val1
			if not quiet:
				print(fmt % (x, val1, val2, diff))


		if xact1 is None:
			return1 = D(1)
		else:
			return1 = xact1.total_value / xact1.total_invested

		return2 = xact2.total_value / xact2.total_invested
		returndiff = return2 - return1
		if not quiet:
			print("%20s: %15.2f %15.2f %15.2f" % ('return', return1, return2, returndiff))

		return(xact1, xact2)
	

	def report(self, year=None, quiet=False):
		"""
		yearly report
		"""

		return(self.diff(date=datetime.date(year-1,12,31), date2=datetime.date(year,12,31), quiet=quiet))


	def calc (self):
		"""
		this causes the aggregate data for the most recent transaction to be calculated

		needs to be called each time a new transaction is added

		the results are stored on each transaction so that the transaction list may be used
		as a point in time index of the aggregate account subtotals
		"""

		assert (len(self.xacts) >= 1), "Need at least one xact to calc"
		x = self.xacts[-1]
		if (len(self.xacts) == 1):
			# first xact
			position_cost	= D('0.0')
			position_qty	= 0
			cash			= D('0.0')
			total_invested	= D('0.0')
			share_price		= D('100.')
			total_shares	= D('0.0')
			last_buy		= None
			last_sell		= None
			buy_counter		= 0
			sell_counter	= 0
			last_price		= 0
		else:
			idx = -2
			pre_x = self.xacts[idx]

			position_cost	= pre_x.position_cost
			position_qty	= pre_x.position_qty
			cash			= pre_x.cash
			total_invested	= pre_x.total_invested
			share_price		= pre_x.share_price
			total_shares	= pre_x.total_shares
			last_buy		= pre_x.last_buy
			last_sell		= pre_x.last_sell
			buy_counter		= pre_x.buy_counter
			sell_counter	= pre_x.sell_counter
			# last_price with non-zero qty
			while not pre_x.qty:
				idx -= 1
				pre_x = self.xacts[idx]
			last_price		= pre_x.price

		x.calc(position_cost, position_qty, cash, total_invested, share_price, total_shares, last_buy, last_sell, buy_counter, sell_counter, self.fixed_value, last_price)


	def next_bids (self, quiet=False):
		"""
		figure out what bids need to be placed based on available info

		if no active trades are on record, it will just be the standard algo

		if there are, it will use the standard as a guideline for the interval,
		but new buy points will be offered relative to existing active trades

		one trade is skipped when reversing direction (i.e. when last xact was a sell)
		in order to help maintain a healthy spread

		returns the bid array if called with quiet=True
		"""
		idx = -1
		x = self.xacts[idx]
		while x.qty == 0:
			# skip cash only xacts
			idx -= 1
			x = self.xacts[idx]
		interval = (x.price - x.next_buy_at).quantize(pennies)
		if interval == 0:
			print("0.00 interval, skipping...")
			return
		if not quiet:
			print("\tinterval is %s" % interval)
			if x.buy_factor > 1:
				print("\tleverage factor is %0.2f" % x.buy_factor)
			else:
				print("\tno leverage")

		bids = []
		if self.max_active_bid is not None:
			# active bids already exist in the market
			limit = x.next_buy_at
			if not quiet:
				print("\tactive bids found, bid upper bound set to %s" % limit)
			if x.qty < 0:
				# skip one, reversing trade
				limit = x.next_buy_at - interval
				if not quiet:
					print("\tlast trade was a sell, skipping one: new bid upper bound is %s" % limit)
			last_bid = self.max_active_bid
			while True:
				last_bid += interval
				if last_bid <= limit and last_bid > 0:
					bids.append(last_bid)
				else:
					break
		else:
			next_buy = x.next_buy_at
			if not quiet:
				if next_buy < 0:
					print("\tno active bids found, and we are LIQUIDATION ONLY")
				else:
					print("\tno active bids found, bid upper bound set to %s" % next_buy)
			if x.qty < 0:
				# skip one, reversing trade
				next_buy = x.next_buy_at - interval
				if not quiet:
					print("\tlast trade was a sell, skipping one: new starting bid is %s" % next_buy)
			if next_buy > 0:
				bids.append(next_buy)
				for i in range(3):
					next_buy -= interval
					if next_buy > 0:
						bids.append(next_buy)

		if not quiet:
			print
			if len(bids) == 0:
				# bids are already in market and good
				print("\tNo additional bids need to be placed at this time")
			else:
				print("\tThe following bid orders need to be placed:")
				for b in bids:
					print("\t\t%s bid %d @ %s" % (self.name, x.next_buy_qty, b))
			if self.max_active_bid is not None:
				print("\tCurrent max bid is %s" % self.max_active_bid)
		else:
			return(bids)


	def next_asks (self, quiet=False):
		"""
		figure out what asks need to be placed based on available info

		if no active trades are on record, it will just be the standard algo

		if there are, it will use the standard as a guideline for the interval,
		but new sell points will be offered relative to existing active trades

		one trade is skipped when reversing direction (i.e. when last xact was a sell)
		in order to help maintain a healthy spread

		returns the ask array if called with quiet=True
		"""
		idx = -1
		x = self.xacts[idx]
		while x.qty == 0:
			# skip cash only xacts
			idx -= 1
			x = self.xacts[idx]
		interval = (x.next_sell_at - x.price).quantize(pennies)
		if interval == 0:
			print("0.00 interval, skipping...")
			return
		if not quiet:
			print("\tinterval is %s" % interval)
			if x.sell_factor > 1:
				print("\tleverage factor is %0.2f" % x.sell_factor)
			else:
				print("\tno leverage")

		asks = []
		if self.min_active_ask is not None:
			# active asks already exist in the market
			limit = x.next_sell_at
			if not quiet:
				print("\tactive asks found, ask lower bound set to %s" % limit)
			if x.qty > 0:
				# reversing trade
				if (interval/x.price) >= D('0.02'):
					# interval > 2%, don't need to skip one
					if not quiet:
						print("\tlast trade was a buy, but interval is wide -- not changing lower bound")
				else:
					# skip one
					limit = x.next_sell_at + interval
					if not quiet:
						print("\tlast trade was a buy, skipping one: new ask lower bound is %s" % limit)
			last_ask = self.min_active_ask
			while True:
				last_ask -= interval
				if last_ask >= limit:
					asks.append(last_ask)
				else:
					break
		else:
			next_sell = x.next_sell_at
			if not quiet:
				print("\tno active asks found, ask lower bound set to %s" % next_sell)
			if x.qty > 0:
				# reversing trade
				if (interval/x.price) >= D('0.02'):
					# interval > 2%, don't need to skip one
					if not quiet:
						print("\tlast trade was a buy, but interval is wide -- not changing starting ask")
				else:
					# skip one
					next_sell = x.next_sell_at + interval
					if not quiet:
						print("\tlast trade was a buy, skipping one: new starting ask is %s" % next_sell)
			asks.append(next_sell)
			for i in range(3):
				next_sell += interval
				asks.append(next_sell)

		if not quiet:
			print
			if len(asks) == 0:
				# asks are already in market and good
				print("\tNo additional asks need to be placed at this time")
			else:
				print("\tThe following ask orders need to be placed:")
				for a in asks:
					print("\t\t%s ask %d @ %s" % (self.name, x.next_sell_qty, a))
			if self.min_active_ask is not None:
				print("\tCurrent min ask is %s" % self.min_active_ask)
		else:
			return(asks)


	def fifo_lookup (self, fifo_start, fifo_end):
		"""
		pass in the start and end points for a sale and it returns the fifo cost basis
		start and end points are inclusive (like serial numbers), so (1,3) means units 1, 2, and 3
		returns list of (date, qty, price, total) tuples
		"""
		buys = [x for x in self.xacts if x.qty > 0 and x.fifo_end >= fifo_start and x.fifo_start <= fifo_end]
		res = []
		for x in buys:
			if x.fifo_start == fifo_start:
				slice_qty = x.qty
			elif x.fifo_start < fifo_start:
				slice_qty = x.qty - (fifo_start - x.fifo_start)

			if x.fifo_end > fifo_end:
				slice_qty -= (x.fifo_end - fifo_end)

			res += [(x.date, slice_qty, x.price, x.price * slice_qty)]

			fifo_start = x.fifo_end + 1

		return(res)


	def fifo_report (self, year):
		"""
		sell date, sell qty, unit price, subtotal, commission
			buy date, buy qty, unit price, commission, net cost
			...
		cost basis = sum(buy net cost) + sell commission

		if min(buy date) < sell date - 1 yr and max(buy date) > sell date - 1 yr , need to split it up into two cost basis records
		cost basis date = max(buy date)
		"""
		print("%10s %5s %10s %10s %10s %10s %5s %10s" % ("sell date", "qty", "total", "basis", "cb date", "pnl", "term", "multibuys"))

		# grand totals
		total_qty   = 0
		total_sell  = D(0)
		total_basis = D(0)

		res = {}

		sells = [x for x in self.xacts if x.qty < 0 and x.date > datetime.date(year-1,12,31) and x.date <= datetime.date(year,12,31)]
		for x in sells:
			sell_date	   = x.date
			sell_qty		= abs(x.qty)
			sell_price	  = abs(x.price)
			sell_subtotal   = abs(x.subtotal)
			sell_commission = abs(x.commission)

			year_prior = x.date - datetime.timedelta(days=365)

			# cost basis aggregates
			cb_date	= None
			cb_qty	 = 0
			cost_basis = sell_commission

			cost_basis_buys = self.fifo_lookup(x.fifo_start, x.fifo_end)
			for (date, qty, price, total) in cost_basis_buys:
				if cb_date is not None and cb_date < year_prior and date > year_prior:
					print("WARNING: COMBINED LONG/SHORT TERM BUYS")
				cb_date = date
				cb_qty += qty
				cost_basis += total + self.commission(qty, price)

			assert (sell_qty == cb_qty), "ERROR: COST BASIS / SELL QTY MISMATCH (%d / %d)" % (sell_qty, cb_qty)

			# reduce the cost basis records to one per day (i.e. for multiple sales on a day)
			# this aggregates the sell records, so the individual prices won't survive this reduction
			if sell_date not in res:
				res[sell_date] = Bunch()
				cb = res[sell_date]
				cb.sell_qty = 0
				cb.sell_subtotal = D(0)
				cb.cost_basis	= D(0)
				cb.cb_date	   = None
				cb.buy_nums		 = 0

			cb = res[sell_date]

			if cb.cb_date is not None and cb.cb_date < year_prior and cb_date > year_prior:
				print("WARNING: COMBINED LONG/SHORT TERM BUYS WHEN REDUCING FOR %s" % sell_date)

			cb.sell_qty	  += sell_qty
			cb.sell_subtotal += sell_subtotal
			cb.cost_basis	+= cost_basis
			cb.cb_date	   = cb_date
			cb.buy_nums	  += 1


		for sell_date in sorted(res):
			cb = res[sell_date]

			pnl = cb.sell_subtotal - cb.cost_basis

			year_prior = sell_date - datetime.timedelta(days=365)
			term = "short"
			if cb.cb_date < year_prior:
				term = "long"

			multibuys = ""
			if cb.buy_nums > 1:
				multibuys = "*"

			print("%10s %5d %10.2f %10.2f %10s %10.2f %5s %10s" % (sell_date, cb.sell_qty, cb.sell_subtotal, cb.cost_basis, cb.cb_date, pnl, term, multibuys))

			total_qty   += cb.sell_qty
			total_sell  += cb.sell_subtotal
			total_basis += cb.cost_basis

		print("%10s %5d %10.2f %10.2f %10s %10.2f %5s" % ("totals", total_qty, total_sell, total_basis, "", total_sell - total_basis, ""))
	

	def write_to_disk (self, fname=None):
		if fname is None:
			fname = self.name

		if os.path.exists(fname):
			raise ValueError("file already exists: %s" % fname)

		f = open(fname, 'w')
		for x in self.xacts:
			d = x.date
			date = '/'.join([str(d.month), str(d.day), str(d.year)])
			qty = x.qty
			price = x.price
			f.write("%s:%d:%0.2f\n" % (date, qty, price))
		f.close()


	def compute_alloc (self, target_factor=75, as_dict=False):
		""" 
		this code was pushed down from book.py
		"""
		if not self.fixed_value:
			# no allocation configured on account
			return

		lx = self.xacts[-1]
		if not lx.position_qty:
			# dead position
			return

		name = self.name
		alloc = self.fixed_value
		cost = lx.position_cost
		avail = alloc - cost
		pct_spent = (cost / alloc * 100).quantize(pennies)

		if not lx.spot:
			# no spot, e.g. metals
			spot = spot_factor = ''
			avail_target = avail
		else:
			spot = lx.spot
			spot_factor = (avail / spot).quantize(pennies)
			avail_target = (spot * target_factor).quantize(pennies)

		adjustment = avail_target - avail
		new_alloc = alloc + adjustment
		if as_dict:
			res = {}
			res['name'] = name
			res['alloc'] = alloc
			res['cost'] = cost
			res['avail'] = avail
			res['pct_spent'] = pct_spent
			res['spot'] = spot
			res['spot_factor'] = spot_factor
			res['target_factor'] = target_factor
			res['avail_target'] = avail_target
			res['adjustment'] = adjustment
			res['new_alloc'] = new_alloc
			return(res)
		else:
			return([name, alloc, cost, avail, pct_spent, spot, spot_factor, target_factor, avail_target, adjustment, new_alloc])


	def __str__(self):
		return(self.name)


if __name__ == "__main__":
	import doctest
	doctest.testmod()
