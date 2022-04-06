#!/usr/bin/env python

import os
from account import account
import commission
from bunch import Bunch
import numpy as np
import matplotlib.pyplot as plt
import datetime
from decimal import Decimal as D

pennies = D('0.01')

class book (object):
	"""
	A portfolio / collection of accounts
	"""

	def __init__ (self):
		self.alloc_data = None

		# metals
		self.s = account("Silver", units="1 oz.")
		self.s.load_xacts_from_file('data/silver.dat')
		self.g = account("Gold", units="0.10 oz.")
		self.g.load_xacts_from_file('data/gold.dat')

		self.accounts = [self.s, self.g]

		self.eq = Bunch()

		# equities
		for e in [ e for e in os.listdir('data') if e.startswith('eq.') ]:
			sym = e.split('.')[1]	# eq.sym.dat
			a = account(sym.upper(), commission=commission.pershare(D('0.05')))
			a.load_xacts_from_file('data/%s' % e)
			self.accounts += [a]
			self.eq[sym] = a

		# ib
		for e in [ e for e in os.listdir('data') if e.startswith('ib.') ]:
			sym = e.split('.')[1]	# ib.sym.dat
			a = account(sym.upper(), commission=commission.ib())
			a.load_xacts_from_file('data/%s' % e)
			self.accounts += [a]
			self.eq[sym] = a

		# sb
		for e in [ e for e in os.listdir('data') if e.startswith('sb.') ]:
			sym = e.split('.')[1]	# sb.sym.dat
			a = account(sym.upper(), commission=commission.sb())
			a.load_xacts_from_file('data/%s' % e)
			self.accounts += [a]
			self.eq[sym] = a

		self.needs_calc = True
		self.recalc()
	

	def compute_alloc (self, target_factor=75):
		"""
		must be called after check_alerts so we have the spot info available first
		"""
		res = []

		ttl_alloc = ttl_cost = ttl_adjustment = ttl_avail_target = ttl_new_alloc = 0
		for a in self.accounts:
			curr_res = a.compute_alloc(target_factor=target_factor)

			if not curr_res:
				# no allocation configured on account
				continue

			# list is in allocation tab column order
			# [name, alloc, cost, avail, pct_spent, spot, spot_factor, target_factor, avail_target, adjustment, new_alloc]
			ttl_alloc += curr_res[1]
			ttl_cost += curr_res[2]
			ttl_avail_target += curr_res[8]
			ttl_adjustment += curr_res[9]
			ttl_new_alloc += curr_res[10]

			res.append(curr_res)

		res.append(['','','','','','','','','','',''])
		ttl_avail = ttl_alloc - ttl_cost
		ttl_pct_spent = (ttl_cost / ttl_alloc * 100).quantize(pennies)
		res.append(['Total', ttl_alloc, ttl_cost, ttl_avail, ttl_pct_spent, '','','', ttl_avail_target, ttl_adjustment, ttl_new_alloc])
		self.alloc_data = res
	

	def fifo_report(self, year=None):
		"""
		only does eq accounts at the moment
		"""
		if year is None:
			raise ValueError('year required')

		for s in sorted(self.eq):
			print(s.upper())
			self.eq[s].fifo_report(year)

	

	def report(self, year=None, global_only=False):
		if year is None:
			year = datetime.date.today().year

		total_marked_value1 = D(0)
		total_position_cost1 = D(0)

		total_marked_value2 = D(0)
		total_position_cost2 = D(0)

		for a in self.accounts:
			if not global_only:
				print a.name
			(x1, x2) = a.report(year=year, quiet=global_only)
			if x1 is not None:
				total_marked_value1 += x1.marked_value
				total_position_cost1 += x1.position_cost

			if x2 is not None:
				total_marked_value2 += x2.marked_value
				total_position_cost2 += x2.position_cost

		if total_position_cost1 == D(0):
			total_return1 = D(0)
		else:
			total_return1 = (total_marked_value1 - total_position_cost1) * 100 / total_position_cost1

		if total_position_cost2 == D(0):
			total_return2 = D(0)
		else:
			total_return2 = (total_marked_value2 - total_position_cost2) * 100 / total_position_cost2

		total_marked_value_diff = total_marked_value2 - total_marked_value1
		total_position_cost_diff = total_position_cost2 - total_position_cost1
		total_return_diff = total_return2 - total_return1

		print("%20s: %15d %15d %15s" % ("GLOBAL", year-1, year, "Diff"))
		fmt = "%20s: %15.2f %15.2f %15.2f"
		print(fmt % ('total_position_cost', total_position_cost1, total_position_cost2, total_position_cost_diff))
		print(fmt % ('total_marked_value', total_marked_value1, total_marked_value2, total_marked_value_diff))
		print(fmt % ('total_return', total_return1, total_return2, total_return_diff))
		if total_position_cost_diff:
			ytd_return = (total_marked_value_diff-total_position_cost_diff)/total_position_cost_diff*100
		else:
			ytd_return = 0.
		print("%20s: %15s %15s %15.2f %%" % ('YTD return', "", "", ytd_return))


	def recalc (self):
		self.total_cash = D(0)
		self.total_cost = D(0)
		self.total_marked_value = D(0)
		self.total_reserve_req = D(0)

		self.data = {}
		active_accounts = [ a for a in self.accounts if a.xacts and a.xacts[-1].position_qty > 0 ]

		# running totals
		for a in active_accounts:
			x = a.detail(quiet=True)
			self.data[a.name] = Bunch(detail=x)
			self.total_cash += x.cash
			self.total_cost += x.position_cost
			self.total_marked_value += x.marked_value

			self.total_reserve_req += a.reserve_req		# note this comes from the account rather than the last xact
														# honors fixed_value account configurations
		
		self.total_invested = self.total_cash + self.total_cost
		self.total_value = self.total_marked_value + self.total_cash

		# pct allocations
		for a in active_accounts:
			x = self.data[a.name]
			x.pct_alloc = x.detail.total_value / self.total_value * 100

		self.paper_profit = self.total_marked_value - self.total_cost
		self.roi = self.paper_profit / self.total_cost * 100

		self.needs_calc = False
	

	def detail (self):
		active_accounts = [ a for a in self.accounts if a.xacts and a.xacts[-1].position_qty > 0 ]
		buf = "%20s: " % "Account"
		for a in active_accounts:
			buf += "%15s " % a.name
		buf += "%15s\n" % "Totals"

		for k in account.key_order:
			buf += "%20s: " % k
			for a in active_accounts:
				if k == 'reserve_req':
					buf += account.keys[k].fmt % a.reserve_req
				else:
					buf += account.keys[k].fmt % self.data[a.name].detail.__dict__[k]
				buf += " "
			if k == "cash":
				buf += "%15.2f" % (self.total_cash)
			elif k == "position_cost":
				buf += "%15.2f " % self.total_cost
			elif k == "marked_value":
				buf += "%15.2f " % self.total_marked_value
			elif k == "paper_profit":
				buf += "%15.2f " % self.paper_profit
			elif k == "roi":
				buf += "%%%14.2f " % self.roi
			elif k == "total_value":
				buf += "%15.2f " % self.total_value
			elif k == "total_invested":
				buf += "%15.2f " % self.total_invested
			elif k == "reserve_req":
				buf += "%15.2f " % self.total_reserve_req
			buf += "\n"

		buf += "%20s: " % "Pct Allocation"
		for a in active_accounts:
			buf += "%%%14.2f " % self.data[a.name].pct_alloc
		buf += "\n"
		print(buf)
		return(buf)


	def chartbook (self):
		for a in self.accounts:
			a.chartbook()
			a.chart_buysell()
		self.chart_allocation_pie()


	def chart_allocation (self, subplot=None):
		"""
		sample chart that plots all account costs together over
		time as separate lines.  not currently used but you can 
		chart it interactively by doing this from python -i:

		v.canvas_charts = v.plant_chart(b.chart_allcoation(), can=v.canvas_charts)
		"""
		if subplot is None:
			fig = plt.figure()
			ax = fig.add_subplot(111)
		else:
			ax = subplot

		names = []
		dates = []
		cash  = []
		cost  = []

		for a in self.accounts:
			names += [a.name]
			dates += [[x.date for x in a.xacts]]
			cost  += [[x.position_cost for x in a.xacts]]

		# use a colormap
		colors = [plt.cm.spectral(i) for i in np.linspace(0, 1, len(names))]

		for i in range(len(names)):
			ax.plot_date(dates[i], cost[i], fmt='-', label=names[i], color=colors[i])

		ax.legend()
		return fig


	def chart_allocation_pie (self, subplot=None):
		if subplot is None:
			fig = plt.figure()
			ax = fig.add_subplot(111)
		else:
			ax = subplot

		values = []
		labels = []

		for a in self.accounts:

			try:
				d = self.data[a.name].detail
			except KeyError:
				continue

			labels += ["%s" % a.name]
			values += [d.position_cost]
		
		ax.pie(values, labels=labels)
		return fig
	
