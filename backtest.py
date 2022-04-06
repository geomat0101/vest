#!/usr/bin/env python -i

from mdcache import mdcache
import datetime
from sto import sto
from account import account
import matplotlib.dates as dates
import commission
import os

def backtest(symbol=None, start=None, write_to_disk=False, fixed_value=None):

	if symbol is None:
		raise ValueError("symbol is required")
	
	fname = "eq.%s.bt.dat" % symbol
	if os.path.exists(fname):
		print("FILE ALREADY EXISTS: %s" % fname)
		return

	if start is None:
		dt_start = datetime.date(year=2000, month=1, day=1)		# 20000101 by default
	else:
		dt_start = start

	mdata = mdcache(symbol, date_from=dt_start)
	data = mdata.get_data()

	acct = account(name=symbol, commission=commission.pershare(0.05))
	acct.fixed_value = fixed_value
	acct.ignore_fixed_value_assertion = True

	pos_qty = None
	end = 0
	next_buy_at = None
	next_buy_qty = None
	next_sell_at = None
	next_sell_qty = None
	x = None	# last xact

	for (d, o, c, h, l, v) in data:
		if d == 733898.0:
			# flash crash
			continue

		end += 1
		# date, open, close, high, low, volume
		if pos_qty is None:
			# no buys yet, waiting for weakness to enter
			if sto(data[:end])[-1][0] > 20.:
				continue

			# weakness detected -- entry point
			acct.add_xact(date=dates.num2date(d).date(), qty=3, price=c)
			pos_qty = 3

			x = acct.xacts[-1]
			print("%s" % x)
			next_buy_at   = x.next_buy_at
			next_buy_qty  = x.next_buy_qty
			next_sell_at  = x.next_sell_at
			next_sell_qty = x.next_sell_qty

			continue
		

		# we have an initial buy, now start looking for new opportunities


		# foundational trades
		while l <= next_buy_at:
			# buys triggered
			acct.add_xact(date=dates.num2date(d).date(), qty=next_buy_qty, price=next_buy_at)
			x = acct.xacts[-1]
			next_buy_at   = x.next_buy_at
			next_buy_qty  = x.next_buy_qty
		
		while h >= next_sell_at:
			# sells triggered
			acct.add_xact(date=dates.num2date(d).date(), qty=next_sell_qty*-1, price=next_sell_at)
			x = acct.xacts[-1]
			next_sell_at   = x.next_sell_at
			next_sell_qty  = x.next_sell_qty

		x = acct.xacts[-1]
		next_buy_at    = x.next_buy_at
		next_buy_qty   = x.next_buy_qty
		next_sell_at   = x.next_sell_at
		next_sell_qty  = x.next_sell_qty


		# stochastic opportunity trades
		if x.price > x.dca_min_ask:
			# above break-even, look for weakness
			start = 0
			if end > 11:
				start = end - 10
			s = sto(data[start:end])
			if s[-1][0] <= 20.:
				# weakness detected, see if it's ok to trade on
				# FIXME: this doesn't go back far enough
				buy_ok = False
				sto_r = s.__reversed__()
				idx = 0
				for (sr_k, sr_d) in sto_r:
					if sr_d > 80.:
						# 3day avg was over 80, so this is new weakness coming down from strength
						if dates.date2num(x.date) < [z for z in data[start:end].__reversed__()][idx][0]:
							# last xact was before weakness developed
							buy_ok = True
							break
				if buy_ok:
					acct.add_xact(date=dates.num2date(d).date(), qty=next_buy_qty, price=c)
		elif x.price < x.dca_min_ask:
			# below break-even, look for strength
			start = 0
			if end > 11:
				start = end - 10
			s = sto(data[start:end])
			if s[-1][0] >= 80.:
				# strength detected, see if it's ok to trade on
				# FIXME: this doesn't go back far enough
				sell_ok = False
				sto_r = s.__reversed__()
				idx = 0
				for (sr_k, sr_d) in sto_r:
					if sr_d < 20.:
						# 3day avg was under 20, so this is new strength coming up from weakness
						if dates.date2num(x.date) < [z for z in data[start:end].__reversed__()][idx][0]:
							# last xact was before strength developed
							sell_ok = True
							break
				if sell_ok:
					acct.add_xact(date=dates.num2date(d).date(), qty=next_sell_qty, price=c)

		x = acct.xacts[-1]
		print("%s" % x)
		next_buy_at    = x.next_buy_at
		next_buy_qty   = x.next_buy_qty
		next_sell_at   = x.next_sell_at
		next_sell_qty  = x.next_sell_qty
	
	if write_to_disk:
		acct.write_to_disk(fname="eq.%s.bt.dat" % symbol)
	
	return acct

