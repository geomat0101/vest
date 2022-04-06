#!/usr/bin/env python

class Bunch:
	"""

	## from http://code.activestate.com/recipes/52308/

	#  Now, you can create a Bunch whenever you want to group a few variables:

	>>> point = Bunch(datum=2, squared=2*2, coord=1)

	# and of course you can read/write the named
	# attributes you just created, add others, del
	# some of them, etc, etc:

	>>> if point.squared > 3:
	...     point.isok = 1
	... 
	>>> point.isok
	1

	>>> b=Bunch()
	>>> b.foo = 'bar'
	>>> b['bar'] = 'baz'
	>>> b.foo
	'bar'
	>>> b['foo']
	'bar'
	>>> b.bar
	'baz'
	>>> b['bar']
	'baz'
	>>> 'foo' in b
	True
	>>> 'baz' in b
	False

	"""

	def __init__(self, **kwds):
		self.__dict__.update(kwds)
	
	def __setitem__ (self, item, value):
		self.__dict__[item] = value
	
	def __getitem__ (self, item):
		return self.__dict__[item]
	
	def __iter__ (self):
		return self.__dict__.__iter__()


if __name__ == "__main__":
	import doctest
	doctest.testmod()
