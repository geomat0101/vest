#!/usr/bin/env python

from decimal import *

D = Decimal
pennies = D('0.01')


def percent (pct_value):
	"""
	returns a function which will apply a percent value commission to an input transaction value.

	>>> x = percent(10)
	>>> x(10, D('10.0'))
	Decimal('10.00')
	>>> x(-10, D('10.0'))
	Decimal('10.00')
	"""

	pct_value = D(pct_value)

	def commission (xact_qty, xact_price):
		return (abs((pct_value / D('100.')) * xact_qty * xact_price)).quantize(pennies)
	
	return commission


def percent_liquidate (pct_value):

	pct_value = D(pct_value)

	def liquidate (position_cost, position_qty):
		return (position_cost / ((100 - pct_value) / D('100.') * position_qty)).quantize(pennies)
	
	return liquidate


def ib ():
	"""
	returns a function which applies a fixed cost per share

	>>> x = ib()
	>>> x(1, 100)
	Decimal('1')
	>>> x(200, 100)
	Decimal('1.00')
	>>> x(199, 100)
	Decimal('1')
	>>> x(202, 100)
	Decimal('1.01')
	"""

	def commission (xact_qty, xact_price):
		""" 
		0.005 per share, one dollar min
		"""
		comm = xact_qty * D('0.005')
		if comm < D(1):
			return(D(1))
		return comm.quantize(pennies)
	
	return commission

def sb ():
	"""
	returns a function which applies a fixed cost per share
	(JSCOTT SHAREBUILDER)

	>>> x = ib()
	>>> x(1, 100)
	Decimal('1')
	>>> x(200, 100)
	Decimal('1.00')
	>>> x(199, 100)
	Decimal('1')
	>>> x(202, 100)
	Decimal('1.01')
	"""

	def commission (xact_qty, xact_price):
		""" 
		0.005 per share, one dollar min
		"""
		comm = D('9.95')
		return comm
	
	return commission


def pershare (per_value):
	"""
	returns a function which applies a fixed cost per share

	>>> x = pershare(D('0.05'))
	>>> x(10, D('10.0'))
	Decimal('0.50')
	>>> x(-10, D('100.0'))
	Decimal('0.50')
	"""

	per_value = D(per_value)

	def commission (xact_qty, xact_price):
		""" price not used """
		return (abs(per_value * xact_qty)).quantize(pennies)
	
	return commission


def pershare_liquidate (per_value):

	per_value = D(per_value)

	def liquidate (position_cost, position_qty):
		return ((position_cost + (per_value * position_qty)) / position_qty).quantize(pennies)
	
	return liquidate


def fidelity ():
	def commission (xact_qty, xact_price):
		return(D('7.95'))
	
	return commission


def fidelity_liquidate ():
	def liquidate (position_cost, position_qty):
		return(((position_cost + D('7.95'))/position_qty).quantize(pennies))
	
	return liquidate


if __name__ == "__main__":
	import doctest
	doctest.testmod()
