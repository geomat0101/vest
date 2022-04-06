#!/usr/bin/env python

import pprint
pp = pprint.PrettyPrinter(indent=4).pprint

import datetime
import commission
from buysell import *
from decimal import *

D = Decimal
pennies = D('0.01')


def default_liquidate(cost, qty):
	return(cost/qty)


class xact (object):
	"""
	this is a market order

	>>> x = xact(qty=2, price=D('50.00'), commission=commission.percent(1))
	>>> x.date == datetime.date.today()
	True
	>>> x.qty
	Decimal('2')
	>>> x.price
	Decimal('50.00')
	>>> x.subtotal
	Decimal('100.00')
	>>> x.commission
	Decimal('1.00')
	>>> x.net_xact_cost
	Decimal('101.00')

	>>> xact()
	Traceback (most recent call last):
	ValueError: price must be non-zero

	>>> x = xact(qty=1, price=D('2.00'), date="some_date_string")
	Traceback (most recent call last):
	ValueError: date must be an instance of datetime.date (<type 'str'>)

	"""

	def __init__ (self, date=None, qty=0, price=0, commission=None, liquidate=default_liquidate, split=None):
		"""
		create a new transaction

		date is a datetime.date
		commission is a fn pointer from one of the commission implementations

		if qty is 0, the price is an adjustment to the cash portion of an account
		"""

		qty = D(qty)
		price = D(price).quantize(pennies)

		if date is None:
			self.date = datetime.date.today()
		elif isinstance(date, datetime.date):
			self.date = date
		else:
			raise ValueError("date must be an instance of datetime.date (%s)" % type(date))

		self.qty = qty
		self.price = price
		self.subtotal = self.qty * self.price
		self.commission = D('0.0')
		self.split = split
		
		if commission is not None and self.subtotal != 0:
			self.commission = commission(self.qty, self.price)

		self.liquidate = liquidate		# liquidation function
		
		self.net_xact_cost = self.subtotal + self.commission
		self.spot = None

	
	def calc (self, position_cost=None, position_qty=None, cash=None, total_invested=None, share_price=None,
				total_shares=None, last_buy=None, last_sell=None, buy_counter=None, sell_counter=None, fixed_value=None, last_price=None):
		"""
		this is called from the account scope to update aggregate account info as a result of this transaction
		"""

		if None in [ position_cost, position_qty, cash, total_invested, share_price, total_shares, buy_counter, sell_counter ]:
			# last_buy, last_sell, and fixed_value might actually be none
			raise ValueError("Missing required calc argument")

		# running totals first
		position_cost = D(position_cost)
		position_cost	+= self.net_xact_cost	# the actual money in
		self.position_cost	= position_cost

		position_qty	+= self.qty			# the number of asset units held
		if self.split:
			if self.split < 0:
				# reverse split
				position_qty = int(-(position_qty/self.split))
			else:
				position_qty = int(position_qty * self.split)
		self.position_qty	= position_qty

		cash = D(cash)
		cash -= self.net_xact_cost				# the cash portion of the account

		if self.qty > 0:
			# it's a buy
			self.fifo_start = buy_counter + 1	# serial number start
			buy_counter += self.qty
			self.fifo_end = buy_counter		# serial number end
			last_buy = self.price
			if cash < 0:
				# can't go negative, check is in the mail
				cash = D('0.0')
		elif self.qty < 0:
			self.fifo_start = sell_counter + 1	# serial number start
			sell_counter -= self.qty
			self.fifo_end = sell_counter		# serial number end
			last_sell = self.price
		else:
			# qty is zero: cash adjustment or split
			if self.price:
				# cash adjustment (e.g. option premiums)
				cash += self.price
				self.position_cost -= self.price
			else:
				# split, base new price on the last one
				if self.split < 0:
					# reverse split
					self.price = D(-(last_price * self.split)).quantize(pennies)
				else:
					self.price = D(last_price / self.split).quantize(pennies)

		if last_sell is None:
			# no sells in the account yet, buy is the mark
			last_sell = last_buy

		last_buy  = D(last_buy)
		if self.split:
			if self.split < 0:
				# reverse split
				last_buy = D(-(last_buy * self.split)).quantize(pennies)
			else:
				last_buy = D(last_buy / self.split).quantize(pennies)

		last_sell = D(last_sell)
		if self.split:
			if self.split < 0:
				# reverse split
				last_sell = D(-(last_sell * self.split)).quantize(pennies)
			else:
				last_sell = D(last_sell / self.split).quantize(pennies)

		self.cash = cash
		self.last_buy = last_buy		# price of last buy
		self.last_sell = last_sell		# price of last sell
		self.buy_counter = buy_counter
		self.sell_counter = sell_counter

		self.mark_spread	= self.last_sell - self.last_buy			# bid/ask spread

		self.mark			= ((self.mark_spread / 2) + self.last_buy).quantize(pennies)	# the mark: used for establishing the position's value
																							# halfway in between the last buy and the last sell

		self.marked_value	= (self.mark * self.position_qty * D('0.99')).quantize(pennies)	# total position value without the cash portion
																							# FIXME: ASSUMES 1% COMMISSION MODEL!!!
		self.total_value	= self.marked_value + self.cash				# total value with the cash side of the account included

		if self.position_qty != 0:
			self.dca_min_ask	= self.liquidate(self.position_cost, self.position_qty)	# break-even value with commission incl.
		else:
			self.dca_min_ask	= D('0.0')

		# these 2 not particularly useful
		self.dca_max_bid	= (self.dca_min_ask * D('0.98')).quantize(pennies)	# assumes 1% commission on buy and sell side
		self.dca_spread		= self.dca_min_ask - self.dca_max_bid

		self.paper_profit	= self.marked_value - self.position_cost		# unrealized gains
		self.total_invested	= self.position_cost + self.cash				# total capital already committed to the account

		# fund based pricing model
		# normalizes cash flows to specifically track the asset's performance
		total_invested = D(total_invested)
		self.investment_diff	= self.total_invested - total_invested
		total_invested = self.total_invested

		share_price = D(share_price)
		self.shares = self.investment_diff / share_price
		total_shares = D(total_shares)
		total_shares += self.shares
		self.total_shares = total_shares.quantize(D('0.0001'))

		self.share_price = (self.total_value / self.total_shares).quantize(pennies)
		share_price = self.share_price

		# roi
		if self.position_cost != 0:
			self.roi = (self.paper_profit / self.position_cost * 100).quantize(D('0.0001'))
		else:
			self.roi = D(0)

		# honor fixed value
		if fixed_value is not None:
#			total_value = fixed_value
			fixed_value = D(fixed_value)
			total_value = fixed_value - self.position_cost
#			assert (total_value > 0.), "BUSTED: %s" % self
			# no leverage for fixed accounts
			factor = 1
			args = [ self.price, total_value ]
			if not self.qty:
				args[0] = last_price
			(next_qty, next_at) = next_buy_at(*args)
		else:
			total_value = self.total_value
			(next_qty, next_at, factor) = buy_factor(self.price, total_value, self.dca_min_ask)


		self.buy_factor = factor
		self.next_buy_qty = next_qty
		self.next_buy_at = next_at

		if self.position_qty > 0:
			# sell factor
			factor = 3
			args = [ self.price, self.position_qty ]
			if not self.qty:
				args[0] = last_price
#			pp(args)
			(next_qty, next_at) = next_sell_at(*args, factor=factor)
			if next_qty > 1:
				factor = 2		  # 1% -> ~1.5% intervals moving from 33 units @ f3 to 34 @ f2
				(next_qty, next_at) = next_sell_at(*args, factor=factor)
				if next_qty > 1:
					factor = D('4.')/3   # 1% -> ~1.5% intervals moving from 50 units @ f2 to 51 @ f1.3
					(next_qty, next_at) = next_sell_at(*args, factor=factor)
					if next_qty > 1:
						factor = 1

			if factor == 1 or next_at < self.dca_min_ask:
				# only allow leverage when we're trying to push down our position cost
				factor = 1
				(next_qty, next_at) = next_sell_at(*args, factor=factor)
		else:
			# fake values for dead positions
			factor = 1
			next_qty = 1
			next_at = self.last_sell

		self.sell_factor = factor
		self.next_sell_qty = next_qty
		self.next_sell_at = next_at

		# capital reserve commitment
		# if you keep buying at the current qty and interval all the way to zero this is what you're in for
		try:
			self.reserve_req = (sum( range( 1, int( self.price / ( self.price - self.next_buy_at ) + 1 ) ) ) * ( self.price - self.next_buy_at ) * self.next_buy_qty).quantize(pennies)
		except InvalidOperation, err:
			# div by zero
			self.reserve_req = D(0)


	def apply_spot (self, spot, acct):
		"""
		applies spot information to current transaction
		figures out market movement, adjusts allocation based next buy/sell qtys/prices
		does short term dca evaluation if needed, sets explain text
		"""
		if self.spot == spot:
			# done already
			return

		self.spot = spot

		movement = D(0)

		idx = -1
		while not acct.xacts[idx].qty:
			idx -= 1
		last_price = acct.xacts[idx].price

		if last_price:
			movement = (spot - last_price) / last_price

		self.spot_movement = movement

		if movement > 0:
			size = (self.position_qty * movement).quantize(D('0.0001'))
			# round to a multiple of the current sell qty
			if size > self.next_sell_qty:
				size = int(size / self.next_sell_qty) * self.next_sell_qty
			if self.sell_factor:
				size = size * self.sell_factor
			if size < self.next_sell_qty:
				size = 0
			# from buysell.next_sell_at
			# next_at = (last_xact * qty / posqty) + last_xact
			size = int(size)
			if size:
				next_at = ((last_price * size / (self.sell_factor * self.position_qty)) + last_price).quantize(pennies)
		else:
			if acct.fixed_value is not None:
				# honor fixed_value if set
				total_value = acct.fixed_value - self.position_cost
			else:
				total_value = self.total_value

			# standard buy sizing
			size = abs(total_value * movement / spot).quantize(D('0.0001'))
			# round to a multiple of the current buy qty
			if size > self.next_buy_qty:
				size = int(size / self.next_buy_qty) * self.next_buy_qty
			else:
				size = 0
			# from buysell.next_buy_at
			# next_at = (last_xact * total_value) / (qty * last_xact + total_value)
			size = int(size)
			if size:
				next_at = ((last_price * total_value) / (size * last_price + total_value)).quantize(pennies)

		# explain
		exp = []
		exp.append(acct.name.upper())
		exp.append('\nNext Buy:')
		exp.append("\nAllocation model next buy: %d @ %.2f" % (self.next_buy_qty, self.next_buy_at))
		exp.append("spot is %.2f" % spot)
		next_buy_at = self.next_buy_at
		next_buy_qty = self.next_buy_qty
		if movement <= 0 and size and size != self.next_buy_qty:
			exp.append("Spot adjusted next buy: %d @ %.2f" % (size, next_at))
			next_buy_at = next_at
			next_buy_qty = size
		self.spot_next_buy_at = next_buy_at
		self.spot_next_buy_qty = next_buy_qty
		exp.append("dca is %.2f: " % (self.dca_min_ask))
		if next_buy_at < self.dca_min_ask:
			exp[-1] += "no qty limits"
		else:
			exp[-1] += "qty may be limited"
			# find the most recent sale for less than the next buy price
			# as determined by the allocation based model.  We're over dca, so
			# we want to make sure we're only buying back units sold at higher levels
			target = None
			for xact in acct.xacts.__reversed__():
				if xact.qty >= 0:
					# FIXME: splits
					continue
				if xact.price < next_buy_at:
					target = xact
					break
			if not target:
				exp.append("no prior sales < next buy price")
				exp.append("no qty limits")
			else:
				exp.append("last sale < next buy price was:")
				exp.append("  %s: %s" % (target.date, target.price))
				exp.append("position qty was %d" % target.position_qty)
				if target.position_qty == 0:
					exp.append("no qty limits")
				else:
					exp.append("position qty now is %d" % self.position_qty)
					posqty_diff = target.position_qty - self.position_qty
					if posqty_diff > 0:
						exp.append("buys ok for up to %d units" % posqty_diff)
						if next_buy_qty <= posqty_diff:
							exp.append("no qty limits")
						else:
							next_buy_qty = posqty_diff
							exp.append("Adjusted next buy: %d @ %.2f" % (next_buy_qty, next_buy_at))
					else:
						next_buy_qty = 0
						exp.append("cannot buy any more right now")
						exp.append("sell more above the next buy point")
						exp.append("or wait until the price falls further")

		exp.append("\n\n")
		exp.append("Next Sell:")
		exp.append("\nAllocation model next sell: %d @ %.2f" % (self.next_sell_qty, self.next_sell_at))
		exp.append("spot is %.2f" % spot)
		curr_next_sell_at = self.next_sell_at
		next_sell_qty = self.next_sell_qty
		if movement > 0 and size and size != self.next_sell_qty:
			exp.append("Spot adjusted next sell: %d @ %.2f" % (size, next_at))
			curr_next_sell_at = next_at
			next_sell_qty = size
		exp.append("dca is %.2f: " % (self.dca_min_ask))
		if curr_next_sell_at > self.dca_min_ask:
			exp[-1] += "no qty limits"
		else:
			exp[-1] += "qty may be limited"

			def _acquire_next_buy_xact(acct, start=None):
				"""
				find the most recent buy for more than the next sell price
				as determined by the allocation based model.  We're under dca, so
				we want to make sure we're only selling back units bought at lower levels
				"""
				target = None
				split_factor = 0

				start_ok = False
				if start is None:
					start_ok = True

				for xact in acct.xacts.__reversed__():
					# no sales
					if xact.qty < 0:
						continue

					# split accounting
					if xact.qty == 0:
						if not xact.split:
							continue
						if xact.split < 0:
							split_factor = abs(xact.split)
						else:
							split_factor = 1/xact.split
						continue

					# skip to the starting point if one was given
					if not start_ok:
						if start == xact:
							start_ok = True
						continue
							
					curr_price = xact.price
					if split_factor:
						curr_price *= split_factor

					if curr_price > curr_next_sell_at:
						target = xact
						break
				if target is None:
					return None, None, None

				curr_target_price = target.price
				curr_target_posqty = target.position_qty
				if split_factor:
					curr_target_price *= split_factor
					curr_target_posqty /= split_factor
				curr_target_posqty = int(curr_target_posqty)

				return(curr_target_price, curr_target_posqty, target)

			curr_target_price, curr_target_posqty, target = _acquire_next_buy_xact(acct)

			if not target:
				exp.append("no prior buys > next sell price")
				exp.append("no qty limits")
			else:
				exp.append("position qty now is %d" % self.position_qty)
				exp.append("last buy > next sell price was:")
				exp.append("  %s: %s" % (target.date, curr_target_price))
				exp.append("position qty was %d" % curr_target_posqty)
				if curr_target_posqty == 0:
					exp.append("no qty limits")
				else:
					posqty_diff = curr_target_posqty - self.position_qty

					if posqty_diff >= 0:
						exp.append("cannot sell any more at %.2f" % curr_target_price)
						while posqty_diff >= 0:
							curr_target_price, curr_target_posqty, target = _acquire_next_buy_xact(acct, start=target)
							if not target or curr_target_posqty == 0:
								next_sell_qty = 0
								exp.append("buy more below the next sell point")
								exp.append("or wait until the price rises")
								break
							exp.append("  %s: %s" % (target.date, curr_target_price))
							exp.append("position qty was %d" % curr_target_posqty)
							posqty_diff = curr_target_posqty - self.position_qty
							next_sell_qty = curr_target_posqty
							curr_next_sell_at = curr_target_price

					if posqty_diff < 0:
						exp.append("sells ok for up to %d units" % posqty_diff)
						posqty_diff = abs(posqty_diff)
						if next_sell_qty <= posqty_diff:
							exp.append("no qty limits")
						else:
							next_sell_qty = posqty_diff
							exp.append("Adjusted next sell: %d @ %.2f" % (next_sell_qty, curr_next_sell_at))

		self.spot_next_sell_at = curr_next_sell_at
		self.spot_next_sell_qty = next_sell_qty
		adj_sell_cost =  (next_sell_qty * curr_next_sell_at)
		adj_buy_cost =  (next_buy_qty * next_buy_at)
		exp.append("\n\n")
		exp.append("Action:\n")
		date_limit = self.date + datetime.timedelta(days=30)
		if spot >= curr_next_sell_at and next_sell_qty > 0:
			if self.qty > 0:
				if datetime.date.today() <= date_limit:
					exp.append("HOLD: 30-DAY FAIL (%s)" % date_limit)
				if (adj_sell_cost <= 80):
					exp.append("HOLD: IB 1%% FAIL: %.2f" % (adj_sell_cost))
				elif (adj_sell_cost >= 80 and adj_sell_cost <= 100):
					exp.append("HOLD: IB 1%% - Provisional OK: %.2f" % (adj_sell_cost))
			exp.append("SELL: %d @ %.2f" % (next_sell_qty, curr_next_sell_at))
		elif spot <= next_buy_at and next_buy_at > 0:
			if self.qty < 0:
				if datetime.date.today() <= date_limit:
					exp.append("HOLD: 30-DAY FAIL (%s)" % date_limit)
				if (adj_buy_cost <= 80):
					exp.append("HOLD: IB 1%% FAIL: %.2f" % (adj_buy_cost))
				elif (adj_buy_cost >= 80 and adj_buy_cost <= 100):
					exp.append("HOLD: IB 1%% - Provisional OK: %.2f" % (adj_buy_cost))
			exp.append("BUY: %d @ %.2f" % (next_buy_qty, next_buy_at))
		else:
			exp.append("HOLD")

		self.spot_explain = exp

		(next_qty, next_at) = next_sell_at(last_price, self.position_qty)
		self.spot_next_qty = next_qty
		self.spot_next_at = next_at


	def __str__ (self):
		return("%s : %3d @ $%5.2f + $%4.2f = $%7.2f" %
			(self.date.isoformat(), self.qty, self.price, self.commission, self.net_xact_cost))


	def __repr__ (self):
		return("%s : %3d @ $%5.2f + $%4.2f = $%7.2f" %
			(self.date.isoformat(), self.qty, self.price, self.commission, self.net_xact_cost))


if __name__ == "__main__":
	import doctest
	doctest.testmod()




