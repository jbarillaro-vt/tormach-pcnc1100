# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------


twilio_installed = True
try:
    from twilio.rest import Client
except:
    twilio_installed = False

account_sid = "AC06e02dd8bc4f4e178058ac6cd59eb792"
auth_token = "5b22f820837bdd2a8efa151105ca84da"

from_number="+16089608693"

def send_sms_alert(alert, to, msg):
    if twilio_installed:
        try:
            client = Client(account_sid, auth_token)

            # prepend a + on the number if needed as twilio requires it
            if len(to) > 0 and to[0] != '+':
                to = '+' + to

            message = client.messages.create(to=to, from_=from_number, body=msg)
        except:
            print "Ignoring exception trying to send SMS."
    else:
        print "SMS library not installed, skipping alert %s %s" % (to, msg)
