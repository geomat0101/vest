#!/usr/bin/env python

import urllib
from BeautifulSoup import *

class BDQuote (object):
	urlmap = {
			'Silver':	'http://www.bulliondirect.com/nucleo/lp/US_Mint_American_Eagle_Silver_Coin_%281.00_oz%29.html',
			'Gold':		'http://www.bulliondirect.com/nucleo/lp/American_Eagle_Gold_Coin_%280.10_oz%29.html'
		}
	
	def __init__(self, acct):
		html = urllib.urlopen(self.urlmap[acct]).read()
		self.bs = BeautifulSoup(html)
		t = self.bs.find(name='table', attrs={'class': 'tableRightSideFieldContainer'})
		(self.bid, self.ask) = t.findAll('table')
	
	def getQuote(self, table):
		return float(table.tr.contents[3].prettify().split()[-2][1:])

	def getBid(self):
		return self.getQuote(self.bid)

	def getAsk(self):
		return self.getQuote(self.ask)

