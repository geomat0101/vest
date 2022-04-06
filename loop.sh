#!/bin/bash

cd /Users/mdg/src/vest

while :
do

	./vest.py -a 2>&1 > /var/tmp/alerts.tmp

	if [ `diff -u /var/tmp/alerts /var/tmp/alerts.tmp | wc -c` != 0 ]
	then
		diff -u /var/tmp/alerts /var/tmp/alerts.tmp | mail -s "Market Alert" mdg.home@gmail.com
		cp /var/tmp/alerts.tmp /var/tmp/alerts
	fi

	SLEEPMINS=$((${RANDOM}%30+45))
	sleep $((60*${SLEEPMINS}))

done
