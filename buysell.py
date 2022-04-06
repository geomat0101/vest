#!/usr/bin/env python

from decimal import *

D = Decimal
pennies = D('0.01')

def next_sell_at (last_price, position_qty, factor=1):
	""" 
	Theory of Sell

	Ideally we just sell every 1% up, but while we are holding less than
	100 units, that means that we would be selling greater than 1% of our
	position every 1% up.  This eats into the core and exhausts the position.

	To account for this, we move out the sell intervals to the
	point where they become interesting for a single unit relative to the
	the position size.  Sells become less frequent as the position decreases
	in size, to the point where a position of one unit will require an upward
	price movement of 100% in order to trigger a sell signal.  As additional
	accumulation of the position occurs that ceiling comes down.

	restated:
	the price needs to move up (next_at - last_xact)
	enough to justify selling
	qty ( >= 1 ) units from the total position (qty/posqty)
	at its present value (last * (qty/posqty)), so:

		(next_at - last_xact) = (last_xact * (qty/posqty))

	solving for next_at, posqty:
		next_at = (last_xact * qty / posqty) + last_xact

	"""

	last_price = D(last_price)
	factor = D(factor)

	qty = 1 

	next_sell = (last_price * qty / (factor * position_qty)) + last_price

	# maintain one percent minimum intervals
	while (next_sell - last_price) < (last_price * D('0.01')):
		qty += 1
		next_sell = (last_price * qty / (factor * position_qty)) + last_price

	next_sell = next_sell.quantize(pennies)
	return(qty, next_sell)


def next_buy_at (last_price, position_value, factor=1):
	""" 
	Theory of Buy

	Similar to above, except that instead of applying the movement to the position
	quantity, it is applied to the total value of the position (marked position value
	plus cash).  If the spot value is below the break even point, the buy rate is
	accelerated by some factor.

	restated:

	the ratio of price movement basis the last transaction ((last_xact - next_at) / last_xact)
	is equal to the ratio of the next buy price basis the total position value (next_at / total_value)

	(last_xact - next_at) / last_xact = qty * next_at / total_value

	solving for next_at:
		next_at = (last_xact * total_value) / (qty * last_xact + total_value)

	like above, if buy intervals start to fall under 1% then increase buy sizes
	"""

	last_price = D(last_price)
	position_value = D(position_value)
	factor = D(factor)

	qty = 1 

	next_buy = (last_price * position_value * factor) / (qty * last_price + position_value * factor)

	# maintain one percent minimum intervals
	while (last_price - next_buy) < (last_price * D('0.01')):
		qty += 1
		next_buy = (last_price * position_value * factor) / (qty * last_price + position_value * factor)

	next_buy = next_buy.quantize(pennies)
	return(qty, next_buy)


def buy_factor(price, total_value, dca_min_ask):
	"""
	takes the last transaction price, the total_value of the position, and the break even value
	returns tuple of (qty, next_buy_price, buy_factor)
	"""
	# buy factor
	factor = 3
	(next_qty, next_at) = next_buy_at(price, total_value, factor=factor)
	if next_qty > 1:
		factor = 2
		(next_qty, next_at) = next_buy_at(price, total_value, factor=factor)
		if next_qty > 1:
			factor = D('4.')/3
			(next_qty, next_at) = next_buy_at(price, total_value, factor=factor)
			if next_qty > 1:
				factor = 1
				(next_qty, next_at) = next_buy_at(price, total_value, factor=factor)
	
	if factor > 1 and next_at > dca_min_ask:
		# no leverage above the break-even line
		factor = 1
		(next_qty, next_at) = next_buy_at(price, total_value, factor=factor)

	return(next_qty, next_at, factor)
