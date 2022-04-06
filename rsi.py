#!/usr/bin/env python

# from http://matplotlib.sourceforge.net/examples/pylab_examples/finance_work2.html


import numpy as np

def rsi (closes, n=20):
	"""
	compute the n period relative strength indicator
	http://stockcharts.com/school/doku.php?id=chart_school:glossary_r#relativestrengthindex
	http://www.investopedia.com/terms/r/rsi.asp
	"""

	deltas = np.diff(closes)
	seed = deltas[:n+1]
	up = seed[seed>=0].sum()/n
	down = -seed[seed<0].sum()/n
	rs = up/down
	rsi = np.zeros_like(closes)
	rsi[:n] = 100. - 100./(1.+rs)

	for i in range(n, len(closes)):
		delta = deltas[i-1] # cause the diff is 1 shorter

		if delta>0:
			upval = delta
			downval = 0.
		else:
			upval = 0.
			downval = -delta

		up = (up*(n-1) + upval)/n
		down = (down*(n-1) + downval)/n

		rs = up/down
		rsi[i] = 100. - 100./(1.+rs)

	return rsi

