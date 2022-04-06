				movement = D(0)
				if last_xact.price:
					movement = (spot - last_xact.price) / last_xact.price
				detail.append(['movement', '%%%s' % ((movement*100).quantize(D('0.0001')))])

				if movement > 0:
					size = (last_xact.position_qty * movement).quantize(D('0.0001'))
					# round to a multiple of the current sell qty
					if size > last_xact.next_sell_qty:
						size = int(size / last_xact.next_sell_qty) * last_xact.next_sell_qty
					if last_xact.sell_factor:
						size = size * last_xact.sell_factor
					if size < last_xact.next_sell_qty:
						size = 0
					# from buysell.next_sell_at
					# next_at = (last_xact * qty / posqty) + last_xact
					size = int(size)
					if size:
						next_at = ((last_xact.price * size / (last_xact.sell_factor * last_xact.position_qty)) + last_xact.price).quantize(pennies)
#						detail.append(['SELL(%s)' % last_xact.sell_factor, '%d @ %s' % (size, next_at)])
					else:
#						detail.append(['HOLD', 'HOLD'])
						pass
				else:
					if acct.fixed_value is not None:
						# honor fixed_value if set
						total_value = acct.fixed_value - last_xact.position_cost
					else:
						total_value = last_xact.total_value

					# standard buy sizing
					size = abs(total_value * movement / spot).quantize(D('0.0001'))
					# round to a multiple of the current buy qty
					if size > last_xact.next_buy_qty:
						size = int(size / last_xact.next_buy_qty) * last_xact.next_buy_qty
					else:
						size = 0
					# from buysell.next_buy_at
					# next_at = (last_xact * total_value) / (qty * last_xact + total_value)
					size = int(size)
					if size:
						next_at = ((last_xact.price * total_value) / (size * last_xact.price + total_value)).quantize(pennies)
#						detail.append(['BUY', '%d @ %s' % (size, next_at)])
#						detail.append(['TOTAL', '%s' % (size * next_at)])
					else:
#						detail.append(['HOLD', 'HOLD'])
						pass

				# explain
				buf = gtk.TextBuffer()
				buf.set_text('')
				self.text_explain.set_buffer(buf)

				exp = []
				exp.append(self.symbol.upper())
				exp.append('\nNext Buy:')
				exp.append("\nAllocation model next buy: %d @ %.2f" % (last_xact.next_buy_qty, last_xact.next_buy_at))
				exp.append("spot is %.2f" % spot)
				next_buy_at = last_xact.next_buy_at
				next_buy_qty = last_xact.next_buy_qty
				if movement <= 0 and size and size != last_xact.next_buy_qty:
					exp.append("Spot adjusted next buy: %d @ %.2f" % (size, next_at))
					next_buy_at = next_at
					next_buy_qty = size
					a.axhline(next_buy_at, color='blue', ls='-.')
				exp.append("dca is %.2f: " % (last_xact.dca_min_ask))
				if next_buy_at < last_xact.dca_min_ask:
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
							exp.append("position qty now is %d" % last_xact.position_qty)
							posqty_diff = target.position_qty - last_xact.position_qty
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
				exp.append("\nAllocation model next sell: %d @ %.2f" % (last_xact.next_sell_qty, last_xact.next_sell_at))
				exp.append("spot is %.2f" % spot)
				curr_next_sell_at = last_xact.next_sell_at
				next_sell_qty = last_xact.next_sell_qty
				if movement > 0 and size and size != last_xact.next_sell_qty:
					exp.append("Spot adjusted next sell: %d @ %.2f" % (size, next_at))
					curr_next_sell_at = next_at
					next_sell_qty = size
				exp.append("dca is %.2f: " % (last_xact.dca_min_ask))
				if curr_next_sell_at > last_xact.dca_min_ask:
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
						exp.append("position qty now is %d" % last_xact.position_qty)
						exp.append("last buy > next sell price was:")
						exp.append("  %s: %s" % (target.date, curr_target_price))
						exp.append("position qty was %d" % curr_target_posqty)
						if curr_target_posqty == 0:
							exp.append("no qty limits")
						else:
							posqty_diff = curr_target_posqty - last_xact.position_qty

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
									posqty_diff = curr_target_posqty - last_xact.position_qty
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

				a.axhline(curr_next_sell_at, color='green', ls='-.')
				exp.append("\n\n")
				exp.append("Action:\n")
				date_limit = last_xact.date + datetime.timedelta(days=30)
				if spot >= curr_next_sell_at and next_sell_qty > 0:
					if last_xact.qty > 0:
						if datetime.date.today() <= date_limit:
							exp.append("HOLD: 30-DAY FAIL (%s)" % date_limit)
					exp.append("SELL: %d @ %.2f" % (next_sell_qty, curr_next_sell_at))
				elif spot <= next_buy_at and next_buy_at > 0:
					if last_xact.qty < 0:
						if datetime.date.today() <= date_limit:
							exp.append("HOLD: 30-DAY FAIL (%s)" % date_limit)
					exp.append("BUY: %d @ %.2f" % (next_buy_qty, next_buy_at))
				else:
					exp.append("HOLD")

				buf.set_text("\n".join(exp))
				self.text_explain.set_buffer(buf)

				if self.ck_next_sell.get_active():
					# next sell line
					(next_qty, next_at) = next_sell_at(last_xact.price, last_xact.position_qty)
					a.axhline(next_at, color='green', ls='-.')
#					detail.append(['Next Sell', '%d @ %.2f' % (next_qty, next_at)])

					if next_at > last_xact.dca_min_ask:
						if last_xact.sell_factor > 1 and last_xact.next_sell_at > last_xact.dca_min_ask:
							# only losers book losses
							# 1% -> ~1.3% intervals moving from 75 units @ f1.3 to 76 @ f1 (normal sells)
							a.axhline(last_xact.next_sell_at, color='#E36F10', ls='-.')
#							detail.append(['Next Sell%0.1f' % last_xact.sell_factor, '%d @ %.2f' % (last_xact.next_sell_qty, last_xact.next_sell_at)])

				if self.ck_next_buy.get_active():
					# next buy at:
					if acct.fixed_value is None:
						# only allow leverage on floating value accounts (not fixed)
						if last_xact.buy_factor > 1 and last_xact.next_buy_at < last_xact.dca_min_ask:
#							detail.append(['Next Buy%0.1f' % last_xact.buy_factor, '%d @ %.2f' % (last_xact.next_buy_qty, last_xact.next_buy_at)])
							a.axhline(last_xact.next_buy_at, color='#E36F10', ls='-.')

					a.axhline(last_xact.next_buy_at, color='blue', ls='-.')
#					detail.append(['Next Buy', '%d @ %.2f' % (last_xact.next_buy_qty, last_xact.next_buy_at)])

