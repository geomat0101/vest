#!/usr/bin/env python

from book import book
import pnf
import matplotlib.pyplot as plt
import numpy as np
import sys

def newfig ():
	"""
	create a new figure and subplot, return them as a tuple
	"""
	fig = plt.figure()
	ax = fig.add_subplot(111)
	return (fig, ax)


b = book()


import os
import datetime
import pygtk
pygtk.require("2.0")
import gtk
import gtk.glade
import pango
import matplotlib.dates as dates
from matplotlib.backends.backend_gtkagg import FigureCanvasGTKAgg as FigureCanvas
from matplotlib.backends.backend_gtkagg import NavigationToolbar2GTKAgg as NavigationToolbar
from matplotlib.dates import DateFormatter, WeekdayLocator, HourLocator, DayLocator, MONDAY

# N.B. I use ystockquote for the treeview data but the matplotlib function
# to get the historical quote data because the mpl func returns it in the format that
# the candlestick function likes it to be in
import urllib2	# for HTTPError
from matplotlib.finance import candlestick
import ystockquote

from account import account, next_buy_at, next_sell_at
from mdcache import mdcache, cachedir, DataError
from rsi import rsi
from sto import sto
import commission

from alerts import sto_limits

from decimal import *

D = Decimal
pennies = D('0.01')

class vest (object):

	ui = gtk.glade.XML("ui.glade")
	win = ui.get_widget("window1")

	accounts = b.accounts
	acct = b.s
	cb_acct = ui.get_widget("combobox1")

	box_chart = ui.get_widget("vbox5")
	box_alert = ui.get_widget("vbox7")
	cb_chart = ui.get_widget("combobox2")	# chartname
	spin_timeqty = ui.get_widget("spinbutton1")
	cb_timeunits = ui.get_widget("combobox3")
	ck_legend = ui.get_widget("checkbutton1")
	ck_gridlines = ui.get_widget("checkbutton2")
	chartmodel = None
	canvas_charts = None
	canvas_alerts = None
	nav_chart = None

	tvdata = ui.get_widget("treeview2")
	tvdca = ui.get_widget("treeview4")

	texttab = ui.get_widget("textview1")

	text_pnf = ui.get_widget("textview3")

	quote_detail = {}
	tv_q_detail = ui.get_widget("treeview1")
	text_explain = ui.get_widget("textview2")
	symbol = None
	spin_q_rsi = ui.get_widget("spinbutton3")
	nav_chart = None
	ck_q_volume = ui.get_widget("checkbutton4")
	ck_next_buy = ui.get_widget("checkbutton5")
	ck_next_sell = ui.get_widget("checkbutton6")
	ck_q_dca = ui.get_widget("checkbutton7")

	# alerts tab
	tvalerts = ui.get_widget("treeview3")	# alloc
	tvalerts2 = ui.get_widget("treeview5")	# sto
	tvalerts3 = ui.get_widget("treeview7")	# pnf
	label_alert_update = ui.get_widget("label7")

	# alloc tab
	tvalloc  = ui.get_widget("treeview6")
	spin_targetfactor = ui.get_widget("spinbutton2")
	

	def chart_alerts (self):
		"""
		needs spot info to be applied, so check_alerts() needs to be called first
		"""
		f = plt.figure()
		plt.axhline(1, color='g')
		plt.axhline(0, color='k')
		plt.axhline(-1, color='b')
		syms = sorted([a for a in b.eq if b.eq[a].xacts and b.eq[a].xacts[-1].position_qty > 0])
		N = len(syms)
		xfactors = []
		for sym in syms:
			x = b.eq[sym].xacts[-1]
			if x.spot:
				xfactors.append( ((x.spot - x.next_buy_at) / (x.next_sell_at - x.next_buy_at) - D('0.5')) * 2 )
			else:
				xfactors.append(0)

		ind = np.arange(N)  # the x locations for the groups
		width = 0.35       # the width of the bars

		#plt.subplot(111)
		rects1 = plt.bar(ind, xfactors, width, color='r')

		# add some
		plt.xticks(ind+width, syms )

		def autolabel(rects):
			# attach some text labels
			for rect in rects:
				height = rect.get_y()
				if not height:
					height = rect.get_height()
				if height < 0:
					placement = 0.25
				else:
					placement = -0.5
				plt.text(rect.get_x()+rect.get_width()/2., placement, '%0.2f'% height,
						ha='center', va='bottom')

		autolabel(rects1)
		self.canvas_alerts = self.plant_chart(f, box=self.box_alert, can=self.canvas_alerts)


	def plant_chart (self, figure, box=None, can=None):
		"""
		stick the new chart where it belongs
		removes the previous one if needed
		defaults to chart tab plot if box (vbox/hbox) not supplied
		returns the canvas object, caller needs to supply this for subsequent calls
		e.g.
			c = plant_chart(can=None)
			c = plant_chart(can=c)
		"""
		if box is None:
			box = self.box_chart

		if can is not None:
			can.parent.remove(can)

		figure.subplots_adjust(left=0.05, right=0.95, bottom=0.1, top=0.9)
		can = FigureCanvas(figure)
		box.pack_start(can, True, True)
		can.show()
		return can


	def nav_reset (self, box=None, can=None, nav=None):
		"""
		add navigation bar to currently displayed chart
		"""
		assert(box is not None)
		assert(can is not None)

		if nav is not None:
			nav.parent.remove(nav)

		nav = NavigationToolbar(can, self.win)
		nav.lastDir = '/var/tmp'
		box.pack_end(nav, False, True)
		nav.show()
		return nav
	

	def load_data (self):
		data = gtk.ListStore(str, str, str, str, str, str, str, str, str, str, str,
				str, str, str, str, str, str, str, str, str, str, str, str, str)
		self.tvdata.set_model(data)
		for x in self.acct.xacts.__reversed__():
			row = []
			for k in account.key_order:
				row += [x.__dict__[k]]
			data.append(row)
	

	def load_dca (self):
		data = gtk.ListStore(str, str, str)
		self.tvdca.set_model(data)
		try:
			curr_posqty = self.acct.xacts[-1].position_qty
		except IndexError:
			curr_posqty = 0
		last_good_dca = last_good_date = None
		data.append(["qty=%d" % curr_posqty, "", ""])
		under = last_date = None

		def _get_cross (x, last_date, last_posqty, last_dca):
			days = (x.date - last_date).days
			if not days: days = 1
			qty_diff = x.position_qty - last_posqty
			wanted_diff = curr_posqty - last_posqty
			day_offset = (wanted_diff * days) / qty_diff
			wanted_date = last_date + datetime.timedelta(int(day_offset))
			dca_diff = x.dca_min_ask - last_dca
			wanted_dca_diff = dca_diff * day_offset / days
			wanted_dca = last_dca + wanted_dca_diff
			return(wanted_date, wanted_dca)

		for x in self.acct.xacts:
			if x.position_qty < curr_posqty:
				if under:
					# still under
					pass
				elif under is None:
					# newly under from even
					under = True
				else:
					# over/under cross
					wanted_date, wanted_dca = _get_cross(x, last_date, last_posqty, last_dca)
					if last_good_dca is None:
						change = "N/A"
					else:
						change = "%.2f" % (100 * (wanted_dca - last_good_dca) / last_good_dca)
					data.append([wanted_date, "%.2f" % wanted_dca, change])
					last_good_dca = wanted_dca
					last_good_date = wanted_date
					last_date = wanted_date
					last_posqty = curr_posqty
					last_dca = wanted_dca
					under = None
					continue
			elif x.position_qty > curr_posqty:
				if under is None:
					# new from even
					under = False
				elif not under:
					# still over
					pass
				else:
					# under/over cross
					wanted_date, wanted_dca = _get_cross(x, last_date, last_posqty, last_dca)
					if last_good_dca is None:
						change = "N/A"
					else:
						change = "%.2f" % (100 * (wanted_dca - last_good_dca) / last_good_dca)
					data.append([wanted_date, "%.2f" % wanted_dca, change])
					last_good_dca = wanted_dca
					last_good_date = wanted_date
					last_date = wanted_date
					last_posqty = curr_posqty
					last_dca = wanted_dca
					under = None
					continue
			elif x.position_qty == curr_posqty:
				under = None
				if last_good_dca is None:
					# first record
					change = "N/A"
					date = x.date
				else:
					if last_good_dca:
						change = "%.2f" % (100 * (x.dca_min_ask - last_good_dca) / last_good_dca)
					else:
						change = '0.00'

					date = x.date
				last_good_dca = x.dca_min_ask
				last_good_date = x.date
				data.append([date, x.dca_min_ask, change])
			last_posqty = x.position_qty
			last_date = x.date
			last_dca = x.dca_min_ask
	

	def quote_load_detail (self):
		"""
		load quote detail treeview for given symbol
		"""
		if self.symbol is None:
			return

		try:
			data = ystockquote.get_all(self.symbol)
		except IndexError:
			# something raising this in ystockquote for data from some index symbols, e.g. ^DJI
			# setting to an empty dict makes it blank out the detail pane
			data = {}
		except IOError:
			# network down?
			data = {}

		self.quote_detail = data
		model = gtk.ListStore(str, str)
		self.tv_q_detail.set_model(model)
		for k,v in data.iteritems():
			model.append([k,v])

		self.load_dca()
	

	def quote_load_chart (self, date_from=None, date_to=None, pnf_graph=None):
		"""
		draw the candlestick chart on the quotes tab
		date args are datetime.date
		"""
		if self.symbol in [None, '']:
			print("No symbol requested")
			return

		today = datetime.date.today()

		if date_to is None:
			date_to = today

		if date_from is None:
			# 1 yr ago by default
			date_from = today - datetime.timedelta(days=365)

		try:
			md = mdcache(self.symbol, date_from, date_to)
		except DataError:
			print("DataError: Cannot draw chart")
			return

		quotes = md.get_data()

		datevals = [ q[0] for q in quotes ]
		closes   = [ q[2] for q in quotes ]
		spot = closes[-1]

		todaynum = dates.date2num(today)
		if (todaynum <= datevals[-1] + 5) and ('price' in self.quote_detail):
			# today's data not in yet, use detail price for spot
			spot = D(self.quote_detail['price'])
			datevals += [ todaynum ]
		
		f = plt.figure()
		atop = f.add_axes([0.1, 0.8, 0.8, 0.1])
		a    = f.add_axes([0.1, 0.1, 0.8, 0.7], sharex=atop)

		fillcolor = '#c0c0ff'

		# rsi vs. sto
		if False:
			# rsi
			if (todaynum <= datevals[-1] + 5) and ('price' in self.quote_detail):
				closes   += [ spot ]
				a.plot_date(todaynum, spot)

			rsivals = rsi(closes, n=int(self.spin_q_rsi.get_value()))

			atop.plot(datevals, rsivals, color='black')
			atop.axhline(70, color=fillcolor)
			atop.axhline(30, color=fillcolor)
			atop.fill_between(datevals, rsivals, 70, where=(rsivals>=70), facecolor=fillcolor, edgecolor=fillcolor)
			atop.fill_between(datevals, rsivals, 30, where=(rsivals<=30), facecolor=fillcolor, edgecolor=fillcolor)
			atop.set_ylim(0, 100)
			atop.set_yticks([30,70])
		else:
			# sto
			if (todaynum <= datevals[-1] + 5) and ('price' in self.quote_detail):
				quotes += [(todaynum, spot, spot, spot, spot, 0)]
				a.plot_date(todaynum, spot)
			stovals = sto(quotes, period=int(self.spin_q_rsi.get_value()))
			k_vals = np.zeros_like(datevals)
			d_vals = np.zeros_like(datevals)
			for i in range(len(stovals)):
				k, d = stovals[i]
				k_vals[i] = k
				d_vals[i] = d

			atop.plot(datevals, k_vals, color='black')
			atop.plot(datevals, d_vals, color='red')
			atop.axhline(80, color=fillcolor)
			atop.axhline(50, color=fillcolor, ls='-.')
			atop.axhline(20, color=fillcolor)
			atop.fill_between(datevals, k_vals, 80, where=(k_vals>=80), facecolor=fillcolor, edgecolor=fillcolor)
			atop.fill_between(datevals, k_vals, 20, where=(k_vals<=20), facecolor=fillcolor, edgecolor=fillcolor)
			atop.set_ylim(0, 100)
			atop.set_yticks([20,80])


		candlestick(a, quotes, width=0.6)
		a.xaxis_date()
		a.autoscale_view()
		f.autofmt_xdate(bottom=0.1)
		a.grid(True)
		f.suptitle(self.symbol.upper())

		lowsym = self.symbol.lower()
		if lowsym in b.eq:
			acct = b.eq[lowsym]
			acct.chart_buysell(date_from=date_from, date_to=date_to, subplot=a, volume=self.ck_q_volume.get_active(), title=False, show_dca=self.ck_q_dca.get_active(), adjust_splits=True, pnf_graph=pnf_graph)

			try:
				last_xact = acct.xacts[-1]
			except IndexError:
				last_xact = None

			if last_xact and last_xact.position_qty > 0:
				detail = self.tv_q_detail.get_model()
				detail.append(['last_buy', last_xact.last_buy])
				detail.append(['last_sell', last_xact.last_sell])
				detail.append(['mark', last_xact.mark])
				detail.append(['position_qty', last_xact.position_qty])
				detail.append(['dca', last_xact.dca_min_ask])

				last_xact.apply_spot(spot, acct)

				movement = last_xact.spot_movement
				detail.append(['movement', '%%%s' % ((movement*100).quantize(D('0.0001')))])

				# explain
				buf = gtk.TextBuffer()
				buf.set_text('')
				self.text_explain.set_buffer(buf)

				# if it's a buy and the spot adj buy qty doesn't match the allocation based qty
				if movement <= 0 and last_xact.spot_next_buy_qty and last_xact.spot_next_buy_qty != last_xact.next_buy_qty:
					a.axhline(last_xact.spot_next_buy_at, color='blue', ls='-.')

				a.axhline(last_xact.spot_next_sell_at, color='green', ls='-.')

				buf.set_text("\n".join(last_xact.spot_explain))
				self.text_explain.set_buffer(buf)

				next_at = last_xact.spot_next_at
				if self.ck_next_sell.get_active():
					# next sell line
					a.axhline(next_at, color='green', ls='-.')

					if next_at > last_xact.dca_min_ask:
						if last_xact.sell_factor > 1 and last_xact.next_sell_at > last_xact.dca_min_ask:
							# only losers book losses
							# 1% -> ~1.3% intervals moving from 75 units @ f1.3 to 76 @ f1 (normal sells)
							a.axhline(last_xact.next_sell_at, color='#E36F10', ls='-.')

				if self.ck_next_buy.get_active():
					# next buy at:
					if acct.fixed_value is None:
						# only allow leverage on floating value accounts (not fixed)
						if last_xact.buy_factor > 1 and last_xact.next_buy_at < last_xact.dca_min_ask:
							a.axhline(last_xact.next_buy_at, color='#E36F10', ls='-.')

					a.axhline(last_xact.next_buy_at, color='blue', ls='-.')

		self.canvas_charts = self.plant_chart(f, box=self.box_chart, can=self.canvas_charts)
		self.nav_chart = self.nav_reset(box=self.box_chart, can=self.canvas_charts, nav=self.nav_chart)
	

	def quote_load (self, widget=None, symbol=None, pnf_graph=None):
		"""
		drives the quote tab once someone asks for a symbol
		"""
		if symbol is None:
			symbol = self.cb_acct.get_active_text()
			
		self.symbol = symbol
		self.quote_load_detail()
		timeqty = self.spin_timeqty.get_value()
		timeunits = self.cb_timeunits.get_model()[self.cb_timeunits.get_active()][0]
		date_delta = self._get_period_delta(timeqty, timeunits)
		date_from = datetime.date.today() - date_delta
		self.quote_load_chart(date_from=date_from, pnf_graph=pnf_graph)
	

	def switch_account (self, widget=None):
		self.acct = self.accounts[self.cb_acct.get_active()]
		self.switch_chart()
		self.load_data()
	

	def load_pnf (self):
		"""
		sets the pnf window text (the graph)
		returns the pnf.Graph instance
		"""
		try:
			graph = pnf.Graph(self.acct.name)
			buf = graph.get_output(style='pango')
		except IndexError:
			return
		self.text_pnf.modify_font(pango.FontDescription('Courier 9'))
		self.text_pnf.set_buffer(buf)
		return(graph)
	

	def _get_period_delta (self, timeqty, timeunits):

		date_delta = None

		if timeunits == 'Years':
			date_delta = datetime.timedelta(days=365*timeqty)
		elif timeunits == 'Months':
			date_delta = datetime.timedelta(days=30*timeqty)
		elif timeunits == 'Weeks':
			date_delta = datetime.timedelta(weeks=timeqty)
		elif timeunits == 'Days':
			date_delta = datetime.timedelta(days=timeqty)
		else:
			assert(False)

		return(date_delta)

	
	def switch_chart (self, widget=None):
		"""
		This drives what shows up in the chart tab
		acts as the signal handler for things like the redraw button and combobox selection changes
		"""
		chartname = self.chartmodel[self.cb_chart.get_active()][0]

		# figure out chart period
		timeqty = self.spin_timeqty.get_value()
		timeunits = self.cb_timeunits.get_model()[self.cb_timeunits.get_active()][0]

		date_delta = self._get_period_delta(timeqty, timeunits)

		date_from = datetime.date.today() - date_delta

		legend = self.ck_legend.get_active()
		grid   = self.ck_gridlines.get_active()

		f,a=newfig()

		if chartname == 'chartbook':
			self.acct.chartbook(figure=f, date_from=date_from)
		elif chartname == 'buysell':
			if self.acct.name in ['Silver', 'Gold']:
				self.acct.chart_buysell(subplot=a, date_from=date_from, legend=legend, grid=grid, volume=False)
			else:
				pnf_graph = self.load_pnf()
				self.quote_load(symbol=self.acct.name, pnf_graph=pnf_graph)
				return
		elif chartname == 'allocation':
			self.acct.chart_allocation(subplot=a)
		else:
			# print("chartname: %s" % chartname)
			self.acct.chart(chartname, subplot=a, date_from=date_from, legend=legend, grid=grid)

		self.canvas_charts = self.plant_chart(f, can=self.canvas_charts)
		self.nav_chart = self.nav_reset(box=self.box_chart, can=self.canvas_charts, nav=self.nav_chart)
		self.load_pnf()
	

	def widget_check_alerts (self, widget=None):
		self.check_alerts()


	def check_alerts (self, autoalert=False):
		# alerts
		print("Starting alert analysis")

		def add_alloc_alert (alerts, sym, base, spot, adj_qty, adj_price, buy):
			"""
			buy must be true (buy signal) or false (sell signal)
			base is allocation based model next xact
			adjusted is spot adjusted version of same
			"""
			d_spot = D(spot) # spot is passed in as a string but we need it for pnf reversal comparisons
			adjusted = "%d @ %0.2f" % (adj_qty, adj_price)
			a = b.eq[sym]
			idx = -1
			ax = a.xacts[idx]
			while ax.qty == 0:
				# skip cash xacts / splits
				idx -= 1
				ax = a.xacts[idx]
			p = pnf.Graph(sym)
			alloc_data = a.compute_alloc(as_dict=True)
			message = ''
			if buy:
				buysell = 'buy'
				if p.columns[-1].marker == 'O':
					# O col
					if d_spot > p.get_reversal():
						# imminent reversal?
						message += 'PnF: possible reversal imminent '
						pnftxt = 'OK'
						pnfcolor = 'orange'
					else:
						pnftxt = 'WAIT'
						pnfcolor = 'red'
				else:
					# X col
					if d_spot < p.get_reversal():
						message += 'PnF: possible reversal imminent '
						pnftxt = 'WAIT'
						pnfcolor = 'orange'
					else:
						pnftxt = 'OK'
						pnfcolor = '#00A000'

				if ax.qty > 0 or (datetime.date.today() > (ax.date + datetime.timedelta(days=30))):
					# either the last xact was a buy, or it was more than 30 days ago
					thirtyday = 'OK'
					tdcolor = '#00A000'
				else:
					remaining = ((ax.date + datetime.timedelta(days=30)) - datetime.date.today()).days
					thirtyday = '%sDays' % remaining
					tdcolor = 'red'

				if alloc_data and d_spot < ax.dca_min_ask and alloc_data['adjustment'] < 0:
					# we're under DCA and funding recommendation is to reduce avail cash, so buy more maybe
					alloc_buy = int(alloc_data['adjustment'] * -1 / d_spot) - adj_qty
					if alloc_buy > 0:
						message += '$$$: buy %d extra shares ' % alloc_buy
			else:
				buysell = 'sell'
				if p.columns[-1].marker == 'X':
					# X col
					if d_spot < p.get_reversal():
						message += 'PnF: possible reversal imminent '
						pnftxt = 'OK'
						pnfcolor = 'orange'
					else:
						pnftxt = 'WAIT'
						pnfcolor = 'red'
				else:
					# O col
					if d_spot > p.get_reversal():
						message += 'PnF: possible reversal imminent '
						pnftxt = 'WAIT'
						pnfcolor = 'orange'
					else:
						pnftxt = 'OK'
						pnfcolor = '#00A000'

				if ax.qty < 0 or (datetime.date.today() > (ax.date + datetime.timedelta(days=30))):
					# either the last xact was a sell, or it was more than 30 days ago
					thirtyday = 'OK'
					tdcolor = '#00A000'
				else:
					remaining = ((ax.date + datetime.timedelta(days=30)) - datetime.date.today()).days
					thirtyday = '%sDays' % remaining
					tdcolor = 'red'

				if alloc_data and d_spot > ax.dca_min_ask and alloc_data['adjustment'] > 0:
					# we're over DCA and funding recommendation is to increase avail cash, so sell more maybe
					alloc_sell = int(alloc_data['adjustment'] / d_spot) - adj_qty
					if alloc_sell > 0:
						message += '$$$: sell %d extra shares ' % alloc_sell

			# Percent commission
			adj_xact_cost = (adj_qty * adj_price)
			pctcomm = b.eq[sym].commission(adj_qty, adj_price) / adj_xact_cost * 100
			pctcomm = pctcomm.quantize(pennies)
			if pctcomm >= D('5'):
				commcolor = 'red'
			elif pctcomm >= D('3'):
				commcolor = 'orange'
			else:
				commcolor = '#00A000'

			fgcolor = 'white'
			alerts += [(sym, buysell, thirtyday, base, spot, adjusted, pctcomm, message, fgcolor, tdcolor, commcolor, pnftxt, pnfcolor)]


		active_equities = sorted([a for a in b.eq if b.eq[a].xacts and b.eq[a].xacts[-1].position_qty > 0])

		current_spot = {}
		def get_spot (sym):
			# spot memoizer
			if sym not in current_spot:
				try:
					current_spot[sym] = D(ystockquote.get_price(sym))
				except InvalidOperation:
					# yahoo likes to return an html error when it can't connect
					raise
			return current_spot[sym]

		# foundational pgens
		print("Checking foundational buy and sell points")
		alerts = []
		for sym in active_equities:
			last_xact = b.eq[sym].xacts[-1]

			try:
				spot = get_spot(sym)
				last_xact.apply_spot(spot, b.eq[sym])
			except (IOError, decimal.InvalidOperation):
				print("Error getting %s spot, skipping" % sym)
				continue

			if spot <= last_xact.next_buy_at:
				add_alloc_alert(
						alerts,
						sym,
						"%d @ %0.2f" % (last_xact.next_buy_qty, last_xact.next_buy_at),
						"%0.2f" % spot,
						last_xact.spot_next_buy_qty, last_xact.spot_next_buy_at,
						buy=True
					)

			if spot >= last_xact.next_sell_at:
				add_alloc_alert(
						alerts,
						sym,
						"%d @ %0.2f" % (last_xact.next_sell_qty, last_xact.next_sell_at),
						"%0.2f" % spot,
						last_xact.spot_next_sell_qty, last_xact.spot_next_sell_at,
						buy=False
					)

		if not autoalert:
			# only drive the ui if we're interactive
			data = gtk.ListStore(str, str, str, str, str, str, str, str, str, str, str, str, str)
			self.tvalerts.set_model(data)
			for row in alerts:
				data.append(row)

		# weakness (stochastic)
		print("Checking stochastics")
		alerts = []
		strong_stos = sto_limits(symbols=active_equities)['strong']
		for (sym, sto) in strong_stos:
			alerts += [(sym, 'Strong')]

		alerts += [('', '')]
		weak_stos = sto_limits(symbols=active_equities)['weak']
		for (sym, sto) in weak_stos:
			alerts += [(sym, 'Weak')]

		print

		# check for needed bids
		print("-=SILVER=-")
		print("bid check:\n")
		b.s.next_bids()
		print
		print("ask check:\n")
		b.s.next_asks()
		print
		print
		print("-=GOLD=-")
		print("bid check:\n")
		b.g.next_bids()
		print
		print("ask check:\n")
		b.g.next_asks()
		print

		if not autoalert:
			# only drive the ui if we're interactive
			data = gtk.ListStore(str, str)
			self.tvalerts2.set_model(data)
			for row in alerts:
				data.append(row)

			# PnF table
			data = gtk.ListStore(str, str, str, str, str, str)
			self.tvalerts3.set_model(data)
			for acct in sorted(b.eq):
				try:
					spot = get_spot(acct)
				except InvalidOperation:
					print("Error getting spot for %s, skipping pnf" % acct)

				try:
					data.append(pnf.Graph(acct).status(current_spot=spot))
				except IndexError:
					print("Error getting pnf status, invalid data for %s" % acct)

			# update timestamp
			self.label_alert_update.set_text('Last Update: %s' % datetime.datetime.now())
			self.chart_alerts()
	

	def widget_update_alloc (self, widget=None):
		self.update_alloc(target_factor=int(self.spin_targetfactor.get_value()))


	def update_alloc (self, target_factor=75):
		b.compute_alloc(target_factor=target_factor)
		data = gtk.ListStore(str, str, str, str, str, str, str, str, str, str, str)
		self.tvalloc.set_model(data)
		for d in b.alloc_data:
			data.append(d)


	def __init__ (self, autoalert=False):
		# alerts
		if not autoalert:
			# only drive the ui if we're interactive
			boldcell = gtk.CellRendererText()
			boldcell.set_property('weight', 900)

			column = gtk.TreeViewColumn("30Day", boldcell, text=2, foreground=8, background=9)
			self.tvalerts.append_column(column)
			column = gtk.TreeViewColumn("PnF", boldcell, text=11, foreground=8, background=12)
			self.tvalerts.append_column(column)
			column = gtk.TreeViewColumn("%Comm", boldcell, text=6, foreground=8, background=10)
			self.tvalerts.append_column(column)
			column = gtk.TreeViewColumn("Symbol", gtk.CellRendererText(), text=0)
			self.tvalerts.append_column(column)
			column = gtk.TreeViewColumn("Trade", gtk.CellRendererText(), text=1)
			self.tvalerts.append_column(column)
			column = gtk.TreeViewColumn("Base", gtk.CellRendererText(), text=3)
			self.tvalerts.append_column(column)
			column = gtk.TreeViewColumn("Spot", gtk.CellRendererText(), text=4)
			self.tvalerts.append_column(column)
			column = gtk.TreeViewColumn("Adjusted", gtk.CellRendererText(), text=5)
			self.tvalerts.append_column(column)
			column = gtk.TreeViewColumn("", gtk.CellRendererText(), text=7)
			self.tvalerts.append_column(column)
			self.tvalerts.set_grid_lines(gtk.TREE_VIEW_GRID_LINES_BOTH)

			column = gtk.TreeViewColumn("Symbol", gtk.CellRendererText(), text=0)
			self.tvalerts2.append_column(column)
			column = gtk.TreeViewColumn("Alert Type", gtk.CellRendererText(), text=1)
			self.tvalerts2.append_column(column)
			self.tvalerts2.set_grid_lines(gtk.TREE_VIEW_GRID_LINES_BOTH)

			column = gtk.TreeViewColumn("Symbol", gtk.CellRendererText(), text=0)
			self.tvalerts3.append_column(column)
			column = gtk.TreeViewColumn("Trend", gtk.CellRendererText(), text=3)
			self.tvalerts3.append_column(column)
			column = gtk.TreeViewColumn("Counter", gtk.CellRendererText(), text=4)
			self.tvalerts3.append_column(column)
			column = gtk.TreeViewColumn("Direction", gtk.CellRendererText(), text=1)
			self.tvalerts3.append_column(column)
			column = gtk.TreeViewColumn("Days", gtk.CellRendererText(), text=2)
			self.tvalerts3.append_column(column)
			column = gtk.TreeViewColumn("Other", gtk.CellRendererText(), text=5)
			self.tvalerts3.append_column(column)
			self.tvalerts3.set_grid_lines(gtk.TREE_VIEW_GRID_LINES_BOTH)

		self.check_alerts(autoalert)

		if autoalert:
			sys.exit()

		for tva in [self.tvalloc]:
			column = gtk.TreeViewColumn("Name", gtk.CellRendererText(), text=0)
			tva.append_column(column)
			column = gtk.TreeViewColumn("Alloc", gtk.CellRendererText(), text=1)
			tva.append_column(column)
			column = gtk.TreeViewColumn("Cost", gtk.CellRendererText(), text=2)
			tva.append_column(column)
			column = gtk.TreeViewColumn("Avail", gtk.CellRendererText(), text=3)
			tva.append_column(column)
			column = gtk.TreeViewColumn("PctSpent", gtk.CellRendererText(), text=4)
			tva.append_column(column)
			column = gtk.TreeViewColumn("Spot", gtk.CellRendererText(), text=5)
			tva.append_column(column)
			column = gtk.TreeViewColumn("SpotFactor", gtk.CellRendererText(), text=6)
			tva.append_column(column)
			column = gtk.TreeViewColumn("TargetFactor", gtk.CellRendererText(), text=7)
			tva.append_column(column)
			column = gtk.TreeViewColumn("TargetAvail", gtk.CellRendererText(), text=8)
			tva.append_column(column)
			column = gtk.TreeViewColumn("Adjustment", gtk.CellRendererText(), text=9)
			tva.append_column(column)
			column = gtk.TreeViewColumn("NewAlloc", gtk.CellRendererText(), text=10)
			tva.append_column(column)
			tva.set_grid_lines(gtk.TREE_VIEW_GRID_LINES_BOTH)

		self.update_alloc()

		# accounts
		acctlist = gtk.ListStore(str)
		for a in self.accounts:
			name = a.name
			if a.units:
				name = '%s (%s)' % (a.name, a.units)
			acctlist.append([name])
		self.cb_acct.set_model(acctlist)
		self.cb_acct.set_active(0)
		self.cb_acct.connect("changed", self.switch_account)

		# chart tab
		# list of chart types
		self.chartmodel = gtk.ListStore(str)
		for k in ['chartbook', 'buysell', 'allocation'] + [k for k in account.key_order if account.keys[k].chartbook]:
			self.chartmodel.append([k])
		self.cb_chart.set_model(self.chartmodel)
		cell = gtk.CellRendererText()
		self.cb_chart.pack_start(cell, False)
		self.cb_chart.add_attribute(cell, 'text', 0)
		self.cb_chart.set_active(1) # buysell
		self.cb_chart.connect("changed", self.switch_chart)

		# account chart period
		adj = gtk.Adjustment(value=1, lower=1, upper=99, step_incr=1)
		self.spin_timeqty.configure(adjustment=adj, climb_rate=1, digits=0)
		self.cb_timeunits.set_active(0) # year
		self.ui.get_widget("button1").connect("clicked", self.switch_chart)	# redraw button

		self.ui.get_widget("button2").connect("clicked", self.widget_check_alerts) # alert refresh button

		# redraw on legend/grid change
		self.ck_legend.connect("clicked", self.switch_chart)
		self.ck_gridlines.connect("clicked", self.switch_chart)

		# load chart
		self.switch_chart()

		# data tab
		# load xact data into the liststore
		self.load_data()

		# bind xact data to treeview in data tab
		ncol = 0
		for k in account.key_order:
			column = gtk.TreeViewColumn(k, gtk.CellRendererText(), text=ncol)
			self.tvdata.append_column(column)
			ncol += 1
		self.tvdata.set_grid_lines(gtk.TREE_VIEW_GRID_LINES_BOTH)

		ncol = 0
		for k in ["Date", "DCA", "%Chg"]:
			column = gtk.TreeViewColumn(k, gtk.CellRendererText(), text=ncol)
			self.tvdca.append_column(column)
			ncol += 1
		self.tvdca.set_grid_lines(gtk.TREE_VIEW_GRID_LINES_BOTH)

		# allocation tab
		self.ui.get_widget("button3").connect("clicked", self.widget_update_alloc) # alloc execute button

		# summary tab
		detailtxt = b.detail()
		buf = gtk.TextBuffer()
		buf.set_text(detailtxt)
		self.texttab.modify_font(pango.FontDescription('Courier 9'))
		self.texttab.set_buffer(buf)

		self.text_explain.modify_font(pango.FontDescription('Courier 9'))

		b.report(global_only=True)

		# add columns for quote detail treeview
		self.tv_q_detail.append_column(gtk.TreeViewColumn('Property', gtk.CellRendererText(), text=0))
		self.tv_q_detail.append_column(gtk.TreeViewColumn('Value', gtk.CellRendererText(), text=1))

		cell = gtk.CellRendererText()
		self.cb_acct.pack_start(cell, False)
		self.cb_acct.add_attribute(cell, 'text', 0)
# for comboboxentry
#		self.cb_acct.set_text_column(0)

		# quote chart period
		adj = gtk.Adjustment(value=1, lower=1, upper=99, step_incr=1)
		self.spin_timeqty.configure(adjustment=adj, climb_rate=1, digits=0)
		self.cb_timeunits.set_active(0) # years


def run_backtest ():
	"""
	helper func which generates new backtest transaction data files
	"""
	from backtest import backtest

	default_fixed_value = 5000.

	fixed_value_map = {}
#	fixed_value_map['ca'] = 0.0
#	fixed_value_map['tap'] = 0.0
	fixed_value_map['sh'] = 4*default_fixed_value

	for sym in sorted(b.eq):
		fixed_value = default_fixed_value
		if sym in fixed_value_map:
			if fixed_value_map[sym] == 0.0:
				print("skipping %s" % sym)
				continue
			fixed_value = fixed_value_map[sym]

		print("running %s with value = %0.2f" % (sym, fixed_value))
		backtest(symbol=sym, start=None, write_to_disk=True, fixed_value=fixed_value)


if __name__ == "__main__":
	args = sys.argv[1:]
	autoalert=False
	if args:
		if args[0] == "-a":
			print("auto-alert mode")
			autoalert=True
	v = vest(autoalert=autoalert)
	if autoalert:
		quit()
	gtk.main()
	# if you buy every % down on everything you're in all the way to zero you need about this much cash
	# i think of this as my worst case scenario exposure number
	# update: meh.  also interesting is (value * 1.01^100), 100 buys at 1% incremental reinvestment
	armageddon = sum([a.xacts[-1].mark for a in b.accounts if a.xacts[-1].position_qty]) * 50
