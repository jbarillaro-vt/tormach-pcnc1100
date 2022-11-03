# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: See eula.txt file in same directory for license terms.
#-----------------------------------------------------------------------



def parse_output_line(line):
    tokenlist = []
    starttokenix = 0
    scanix = 0
    endix = 0
    while len(line) > 0 and endix != -1:
        endix = line.find(":", scanix)
        if endix == -1:
            # this is the final token - take the rest of the remaining line
            tokenlist.append(line[starttokenix:])

        else:
            # either we have a valid empty token or we have a normal token with a colon delimiter that is not escaped
            if endix == scanix or line[endix-1] != '\\':
                tokenlist.append(line[starttokenix:endix])
                starttokenix = endix + 1

            scanix = endix + 1

    # now that we have discrete tokens, pass through each token and replace any \: match with just a :
    for (ix, token) in enumerate(tokenlist):
        tokenlist[ix] = token.replace("\:", ":")

    return tokenlist

