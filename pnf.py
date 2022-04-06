#!/usr/bin/env python

import datetime
import mdcache
import matplotlib.dates as dates
from decimal import Decimal as D
import gtk, pango	# for text buffer output mode


class Column (object):
	"""
	represents a column of pnf graph data
	"""
	marker = ''			# X or O
	high = 0			# col high, must be box aligned
	low = 0				# col low, must be box aligned
	uptrend = None		# box position of uptrend line (if any)
	downtrend = None	# box position of downtrend line (if any)
	months = None		# list of month markers and box locations (if any)

	def __init__ (self, marker, high, low, start_date):
		"""
		marker: either 'X' or 'O'
		high: box-fitted high value (from fit_value) for the col
		low: box-fitted low value (from fit_value) for the col
		"""
		assert marker in ['X', 'O']
		self.marker = marker
		self.high = high
		self.low = low
		self.months = []
		self.start_date = start_date


class Graph (object):
	"""
	Top level pnf object
	contains methods to load data, draw graphs
	"""
	month_labels = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'A', 'B', 'C']
	sym = None
	boxes = None
	columns = None
	last_close = None

	def __init__ (self, sym, reversal=2):
		"""
		sym is the name of the security to graph
		reversal is the inital box reversal value passed to parse_data()
		"""
		self.box_reversal = reversal
		self.sym = sym
		self.columns = []	# list of Column instances
		self.boxes   = []	# list of box values corresponding to rows
		self.data = mdcache.mdcache(sym).get_data()
		self.last_close = self.data[-1][2]
		self.parse_data(reversal=reversal)
	

	def status (self, current_spot=None):
		"""
		returns a tuple of strings suitable for stuffing into the ui's pnf summary
		(sym, rising/falling, age(days), trend, countertrend, other)
		'other' may be things like imminent reversals, breakout/breakdown, HSR tests, trendline crosses, etc
		current_spot is needed to test for imminent reversals
		"""
		col = self.columns[-1]
		prior_col = self.columns[-2]
		other = ''
		trend = 'None'
		counter = 'No'

		age = (datetime.datetime.utcnow().replace(tzinfo=dates._UTC()) - col.start_date).days

		if col.uptrend or col.downtrend:
			# trend / countertrend
			rcols = self.columns.__reversed__()
			count_ut = count_dt = 0
			date_ut = date_dt = None	# trend col origin dates
			ut_done = dt_done = False
			for rcol in rcols:
				if not ut_done:
					if rcol.uptrend:
						count_ut += 1
					else:
						ut_done = True
				if not dt_done:
					if rcol.downtrend:
						count_dt += 1
					else:
						dt_done = True
				if ut_done and dt_done:
					break
			if count_ut > count_dt:
				trend = 'Up'
				if count_dt:
					counter = 'Yes'
			else:
				trend = 'Down'
				if count_ut:
					counter = 'Yes'

		if self.reversal_is_imminent(current_spot):
			other += '[imminent reversal] '

		if age <= 3:
			other += '[recent reversal] '

		if (prior_col.uptrend and not col.uptrend) or (prior_col.downtrend and not col.downtrend):
			other += '[trendline break]'

		if col.marker == 'X':
			rf = 'rising'
			try:
				if col.high > self.columns[-3].high:
					other += '[breakout] '
				elif col.high == self.columns[-3].high:
					if len(self.columns) > 5 and col.high == self.columns[-5].high:
						other += '[triple top] '
					else:
						other += '[double top] '
			except IndexError:
				pass
		else:
			rf = 'falling'
			try:
				if col.low < self.columns[-3].low:
					other += '[breakdown] '
				elif col.low == self.columns[-3].low:
					if len(self.columns) > 5 and col.low == self.columns[-5].low:
						other += '[triple bottom] '
					else:
						other += '[double bottom] '
			except IndexError:
				pass

		return (self.sym, rf, '%s' % age, trend, counter, other)
	

	def explain (self, current_spot=None):
		"""
		textual explanation of the status data
		"""
		(sym, rf, age, trend, counter, other) = self.status(current_spot=current_spot)

		output = "\n%s is " % sym
		if trend == 'None':
			output += "not currently trending.\n"
		else:
			output += 'in a primary %strend with ' % trend
			if counter == 'Yes':
				output += 'a '
			else:
				output += 'NO '
			output += "countertrend currently present.\n"
		output += "It has been %s for the past %s days.\n" % (rf, age)
		if other:
			output += "Events: %s\n" % other

		return output
	

	def reversal_is_imminent (self, current_spot):
		"""
		Given supplied spot, see if a reversal could be triggered
		
		Note this isn't guaranteed to produce a reversal, e.g. a continuation may instead occur
		depending on the opposite end of the day's price range
		"""

		if current_spot is None:
			return False

		col = self.columns[-1]
		reversal = self.get_reversal()

		if col.marker == 'O' and current_spot > reversal:
			return True

		if col.marker == 'X' and current_spot < reversal:
			return True

		return False
	

	def get_reversal (self):
		"""
		returns price at which the active column will reverse
		"""
		col = self.columns[-1]
		if col.marker == 'O':
			return self.boxes[self.boxes.index(col.low)+self.box_reversal]
		else:
			return self.boxes[self.boxes.index(col.high)-self.box_reversal]
	

	def get_continuation (self):
		"""
		returns min price at which the active column will continue
		"""
		col = self.columns[-1]
		if col.marker == 'O':
			return self.boxes[self.boxes.index(col.low)-1]
		else:
			return self.boxes[self.boxes.index(col.high)+1]


	def fit_value (self, value, descending=False):
		"""
		takes a Decimal input and returns the appropriate box for it
		based on box sizing.  Creates new boxes as needed
		"""
		pennies = D('0.01')
		# FIXME: assuming 1% box size for now
		if not self.boxes:
			target = value
			self.boxes.append(value)
			# add a header row
			target *= D('1.01')
			target = target.quantize(pennies)
			self.boxes += [target]
			return value

		if value < self.boxes[0]:
			# need more boxes under the low point
			target = self.boxes[0]
			new_boxes = []
			while value < target:
				target *= D('0.99')
				target = target.quantize(pennies)
				new_boxes = [target] + new_boxes
			self.boxes = new_boxes + self.boxes
			return self.boxes[1]
		
		if value >= self.boxes[-1]:
			# need more boxes after the high point
			target = self.boxes[-1]
			while value > target:
				target *= D('1.01')
				target = target.quantize(pennies)
				self.boxes += [target]
			# add a header row
			target *= D('1.01')
			target = target.quantize(pennies)
			self.boxes += [target]
			return self.boxes[-2]

		# somewhere in the existing range already
		last_box = self.boxes[0]
		for box in self.boxes[1:]:
			if box > value:
				if descending:
					return box
				else:
					return last_box
			last_box = box
	

	def parse_data (self, reversal=2):
		"""
		takes data and builds out box / column pnf data based on supplied reversal param
		"""
		# reset graph data
		self.boxes = []
		self.columns = []

		curr_col = last_month = None

		for record in self.data:
			(datenum, x_open, x_close, x_high, x_low, x_vol) = record
			record_date = dates.num2date(datenum)
			curr_month = record_date.month

			if not curr_col:
				# first record, assume it's an up col
				last_month = curr_month
				box_high = self.fit_value(x_high)
				box_low = self.fit_value(x_low, descending=True)		# desc first time just to establish range based on the day
				curr_col = Column('X', box_high, box_low, record_date)
				continue
			
			if curr_col.marker == 'X':
				box_high = self.fit_value(x_high)
				if box_high > curr_col.high:
					# new high, Xs continue
					curr_col.high = box_high
				else:
					# check for a reversal
					box_low = self.fit_value(x_low, descending=True)
					distance = self.boxes.index(curr_col.high) - self.boxes.index(box_low)
					if distance >= reversal:
						# reverse to 'O'
						self.columns.append(curr_col)
						ind_col_high = self.boxes.index(curr_col.high)
						curr_col = Column('O', self.boxes[ind_col_high-1], box_low, record_date)
					else:
						# NOP
						pass
			else:
				# 'O' column
				box_low = self.fit_value(x_low, descending=True)
				if box_low < curr_col.low:
					# new low, Os continue
					curr_col.low = box_low
				else:
					# check for reversal
					box_high = self.fit_value(x_high)
					distance = self.boxes.index(box_high) - self.boxes.index(curr_col.low)
					if distance >= reversal:
						# reverse to 'X'
						self.columns.append(curr_col)
						ind_col_low = self.boxes.index(curr_col.low)
						curr_col = Column('X', box_high, self.boxes[ind_col_low+1], record_date)
					else:
						# NOP
						pass

			# check for month change
			if curr_month != last_month:
				box_month = self.fit_value(x_close, descending=(curr_col.marker == 'O'))
				if box_month > curr_col.high:
					box_month = curr_col.high
				elif box_month < curr_col.low:
					box_month = curr_col.low
				curr_col.months.append((self.month_labels[curr_month], box_month))
				last_month = curr_month
			

		# append final col
		self.columns.append(curr_col)

		# do trendlines
		self.apply_trendlines()
	

	def apply_trendlines (self):
		"""
		add trendline data
		"""
		ncols = len(self.columns)
		i = 2	# start with 3rd col because we need to identify breakouts / breakdowns
		while i < ncols:
			col = self.columns[i]
			prev_col = self.columns[i-2]
			if col.marker == 'X':
				if not col.uptrend and (col.high > prev_col.high):
					# breakout, acquire start of new uptrend line
					low_col = self.columns[i-1]	# default to prior col
					j = i-3	# start scanning 2 back from default
					while j >= 0:
						r_col = self.columns[j]
						if r_col.uptrend:
							# prior trend, stop
							break
						if r_col.low < low_col.low:
							# new low, start here?
							low_col = r_col
						j -= 2	# skip X cols

					# start drawing the uptrend line with low_col
					trendline_idx = self.boxes.index(low_col.low)-1
					j = self.columns.index(low_col)
					if (i-j) > 1:	# don't draw if it started on prior col
						while j < ncols:
							curr_col = self.columns[j]
							if self.boxes.index(curr_col.low) > trendline_idx:
								curr_col.uptrend = self.boxes[trendline_idx]
								trendline_idx += 1
							else:
								# trendline violated, stop
								break
							j += 1
			else:
				# 'O' column
				if not col.downtrend and (col.low < prev_col.low):
					# breakdown, acquire start of new downtrend line
					high_col = self.columns[i-1]	# default to prior col
					j = i-3	# start scanning 2 back from default
					while j >= 0:
						r_col = self.columns[j]
						if r_col.downtrend:
							# prior trend, stop
							break
						if r_col.high > high_col.high:
							# new high, start here?
							high_col = r_col
						j -= 2	# skip O cols

					# start drawing the downtrend line with high_col
					trendline_idx = self.boxes.index(high_col.high)+1
					j = self.columns.index(high_col)
					if (i-j) > 1:	# don't draw if it started on prior col
						while j < ncols:
							curr_col = self.columns[j]
							if self.boxes.index(curr_col.high) < trendline_idx:
								curr_col.downtrend = self.boxes[trendline_idx]
								trendline_idx -= 1
							else:
								# trendline violated, stop
								break
							j += 1
				pass
			i += 1


	def get_output (self, style=''):
		"""
		build ascii representation of the graph data

		style: color support.  supported: 'ansi', 'pango'
		simple ascii with no color used by default

		When using pango, a gtk text buffer is returned instead of a string
		"""
		spot = self.last_close
		last_marker = self.columns[-1].marker
		going_down = (last_marker == 'X' and spot < self.columns[-1].high) or (last_marker == 'O' and spot <= self.columns[-1].low)
		spot_box = self.fit_value(spot, descending=going_down)
		output = self.explain() + "\n\t\t" + ' ' * (len(self.columns)/2 - len(self.sym)/2) + "%s" % self.sym.upper() + "\n"

		if style == 'pango':
			textbuf = gtk.TextBuffer()
			tag_downtrend = textbuf.create_tag("dt", foreground='#FF0000')
			tag_uptrend = textbuf.create_tag("ut", foreground='#0000FF')
			tag_month = textbuf.create_tag("mon", foreground='#FFFFFF', background='#000000', weight=pango.WEIGHT_BOLD)
			tag_spot  = textbuf.create_tag("spot", foreground='#FF0000', weight=pango.WEIGHT_BOLD)
			pos = textbuf.get_end_iter()
			textbuf.insert(pos, output)

		row = ''
		for box in self.boxes.__reversed__():
			row += "%7.2f\t\t" % box
			if style == 'pango':
				pos = textbuf.get_end_iter()
				textbuf.insert(pos, "%7.2f\t\t" % box)
			for col in self.columns:
				if box == col.downtrend:
					if style == 'ansi':
						row += "\033[31m+\033[0m"
					elif style == 'pango':
						pos = textbuf.get_end_iter()
						textbuf.insert_with_tags(pos, "+", tag_downtrend)
					else:
						row += "+"
					continue
				if box == col.uptrend:
					if style == 'ansi':
						row += "\033[34m+\033[0m"
					elif style == 'pango':
						pos = textbuf.get_end_iter()
						textbuf.insert_with_tags(pos, "+", tag_uptrend)
					else:
						row += "+"
					continue
				if col.months:
					mark_month = False
					for mon, mon_box in col.months:
						if mon_box == box:
							mark_month = True
							if style == 'ansi':
								row += "\033[7m\033[1m%s\033[0m" % mon
							elif style == 'pango':
								pos = textbuf.get_end_iter()
								textbuf.insert_with_tags(pos, "%s" % mon, tag_month)
							else:
								row += "%s" % mon
							break
					if mark_month:
						continue

				if col.high >= box and col.low <= box:
					row += col.marker
					if style == 'pango':
						pos = textbuf.get_end_iter()
						textbuf.insert(pos, col.marker)
				else:
					row += ' '
					if style == 'pango':
						pos = textbuf.get_end_iter()
						textbuf.insert(pos, ' ')

			if box == spot_box:
				if style == 'ansi':
					row += "\t\033[31m\033[1m%7.2f\033[0m" % box
				elif style == 'pango':
					pos = textbuf.get_end_iter()
					textbuf.insert_with_tags(pos, "\t%7.2f" % box, tag_spot)
				else:
					row += "\t%7.2f" % box
			else:
				row += "\t%7.2f" % box
				if style == 'pango':
					pos = textbuf.get_end_iter()
					textbuf.insert(pos, "\t%7.2f" % box)
			output += "%s\n" % row
			if style == 'pango':
				pos = textbuf.get_end_iter()
				textbuf.insert(pos, "\n")
			row = ''

		if style == 'pango':
			return textbuf

		return output

		
	def draw (self, style='ansi'):
		""" output ascii graph """
		print self.get_output(style=style)


if __name__ == '__main__':
	import sys

	if len(sys.argv) > 1:
		for sym in sys.argv[1:]:
			Graph(sym, reversal=2).draw()
			print
	else:
		Graph('gdxj', reversal=2).draw()


